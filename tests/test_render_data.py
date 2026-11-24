"""Deployment tests use a tiny synthetic CSV, never the paid model or real download."""
from dataclasses import replace
from contextlib import closing
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.render_data import (Config, download_csv, prepare_build, verify_artifact,
                                 read_index_metadata, digest, start, ROOT)
from agent.tools.recipenlg_store import signature


class Response(io.BytesIO):
    def __init__(self, content, *, status=200, content_type="application/octet-stream", declared=None):
        super().__init__(content)
        self.status = status
        self.headers = {"Content-Type": content_type}
        if declared is not None:
            self.headers["Content-Length"] = str(declared)


def sample_csv():
    stream = io.StringIO(newline="")
    rows = csv.writer(stream)
    rows.writerow(["", "title", "ingredients", "directions", "source", "link", "NER"])
    rows.writerow(["11", "Boiled eggs", json.dumps(["2 eggs"]), json.dumps(["Boil the eggs."]), "Gathered", "https://example.test/eggs", json.dumps(["eggs"])])
    rows.writerow(["12", "Tofu", json.dumps(["200 g tofu"]), json.dumps(["Cook the tofu."]), "0", "https://example.test/tofu", json.dumps(["tofu"])])
    rows.writerow(["13", "Other source", json.dumps(["1 carrot"]), json.dumps(["Cook."]), "Recipes1M", "https://example.test/other", json.dumps(["carrot"])])
    return stream.getvalue().encode()


class RenderDataTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.payload = sample_csv()
        self.config = Config(self.root / "RecipeNLG_dataset.csv", self.root / "recipenlg.sqlite3",
                             self.root / "render_recipe_manifest.json", "https://example.test/data.csv",
                             hashlib.sha256(self.payload).hexdigest(), len(self.payload), 2)

    def tearDown(self):
        self.folder.cleanup()

    def opener(self, request, timeout):
        self.assertNotIn("Range", request.headers)
        self.assertNotIn("Authorization", request.headers)
        return Response(self.payload, declared=len(self.payload))

    def build(self):
        with patch("builtins.print"):
            return prepare_build(self.config, opener=self.opener)

    def test_real_builder_indexes_every_matching_source_and_pins_hashes(self):
        manifest = self.build()
        self.assertEqual(manifest["indexed_records"], 2)
        self.assertEqual(manifest["csv"]["sha256"], digest(self.config.csv_path))
        self.assertEqual(manifest["index"]["sha256"], digest(self.config.index_path))
        with closing(sqlite3.connect(self.config.index_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM recipes").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT count(*) FROM terms WHERE terms MATCH 'eggs'").fetchone()[0], 1)
            query_plan = conn.execute("EXPLAIN QUERY PLAN SELECT payload FROM recipes "
                                      "WHERE json_extract(payload, '$.id') IN (?,?)",
                                      ("recipenlg_11", "recipenlg_12")).fetchall()
            self.assertIn("render_recipe_source_id", str(query_plan))
        self.assertEqual(read_index_metadata(self.config.index_path)["source"], str(self.config.csv_path.resolve()))

    def test_second_build_reuses_verified_data_without_network_or_reindex(self):
        first = self.build()
        def forbidden(*args, **kwargs):
            self.fail("A valid artifact must not download or rebuild.")
        with patch("builtins.print"):
            second = prepare_build(self.config, opener=forbidden, builder=forbidden)
        self.assertEqual(first, second)

    def test_partial_download_preserves_existing_file_and_removes_temporary(self):
        self.config.csv_path.write_bytes(b"old data")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            download_csv(self.config, opener=lambda *a, **k: Response(self.payload[:-10]))
        self.assertEqual(self.config.csv_path.read_bytes(), b"old data")
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_http_partial_response_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTP 200"):
            download_csv(self.config, opener=lambda *a, **k: Response(self.payload, status=206))
        self.assertFalse(self.config.csv_path.exists())

    def test_html_permission_page_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTML"):
            download_csv(self.config, opener=lambda *a, **k: Response(b"<html>Sign in</html>", content_type="text/html"))
        self.assertFalse(self.config.csv_path.exists())

    def test_wrong_content_length_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "file size"):
            download_csv(self.config, opener=lambda *a, **k: Response(self.payload, declared=1))

    def test_same_size_wrong_content_is_rejected(self):
        bad = self.payload[:-1] + b"X"
        with self.assertRaisesRegex(ValueError, "checksum"):
            download_csv(self.config, opener=lambda *a, **k: Response(bad))

    def test_even_a_pinned_html_file_is_not_a_csv(self):
        body = b"<html>Permission required</html>"
        cfg = replace(self.config, sha256=hashlib.sha256(body).hexdigest(), size=len(body))
        with self.assertRaisesRegex(ValueError, "expected RecipeNLG"):
            download_csv(cfg, opener=lambda *a, **k: Response(body))

    def test_wrong_record_count_does_not_replace_a_valid_index(self):
        self.build()
        before = self.config.index_path.read_bytes()
        cfg = replace(self.config, records=3)
        with patch("builtins.print"), self.assertRaisesRegex(ValueError, "record count"):
            prepare_build(cfg, opener=self.opener)
        self.assertEqual(self.config.index_path.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.building")))

    def test_runtime_accepts_normal_artifact_without_full_hash_or_download(self):
        manifest = self.build()
        with patch("scripts.render_data.digest", side_effect=AssertionError("No reread on unchanged artifact")):
            self.assertEqual(verify_artifact(self.config), manifest)

    def test_packaged_path_and_timestamps_are_verified_and_rebound(self):
        self.build()
        other = self.root / "runtime"
        other.mkdir()
        cfg = replace(self.config, csv_path=other / self.config.csv_path.name,
                      index_path=other / self.config.index_path.name,
                      manifest_path=other / self.config.manifest_path.name)
        for source, target in [(self.config.csv_path, cfg.csv_path),
                               (self.config.index_path, cfg.index_path),
                               (self.config.manifest_path, cfg.manifest_path)]:
            shutil.copyfile(source, target)
        manifest = verify_artifact(cfg)
        meta = read_index_metadata(cfg.index_path)
        self.assertTrue(all(meta[k] == v for k, v in signature(cfg.csv_path).items()))
        self.assertEqual(manifest["index"]["sha256"], digest(cfg.index_path))
        self.assertEqual(verify_artifact(cfg), manifest)

    def test_modified_csv_fails_instead_of_rebinding_wrong_data(self):
        self.build()
        self.config.csv_path.write_bytes(self.payload[:-1] + b"X")
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify_artifact(self.config)

    def test_changed_index_fails_instead_of_accepting_metadata_alone(self):
        self.build()
        with closing(sqlite3.connect(self.config.index_path)) as conn:
            conn.execute("UPDATE recipes SET payload='{}' WHERE id=1")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "index checksum"):
            verify_artifact(self.config)

    def test_missing_artifact_does_not_download_at_startup(self):
        with patch("scripts.render_data.urlopen", side_effect=AssertionError("No startup download")), self.assertRaisesRegex(ValueError, "build artifact"):
            start(self.config)

    def test_start_preserves_platform_port_and_selects_full_mode(self):
        self.build()
        with patch.dict(os.environ, {"PORT": "10000"}), patch("scripts.render_data.os.execv") as launch, patch("builtins.print"):
            start(self.config)
            args = launch.call_args.args[1]
            self.assertEqual(args[args.index("--port") + 1], "10000")
            self.assertEqual(args[args.index("--recipe-source") + 1], "full")
            self.assertEqual(os.environ["FRIDGE_RECIPE_CSV"], str(self.config.csv_path))

    def test_render_paths_cannot_point_to_unbundled_var_data(self):
        with patch.dict(os.environ, {"RENDER": "true", "FRIDGE_RECIPE_CSV": "/var/data/RecipeNLG_dataset.csv"}, clear=True):
            with self.assertRaisesRegex(ValueError, "Remove old /var/data"):
                Config.from_env()

    def test_defaults_need_no_persistent_disk_or_additional_download_package(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_env()
        self.assertEqual(cfg.csv_path, ROOT / "data/RecipeNLG_dataset.csv")
        self.assertEqual(cfg.index_path, ROOT / "data/recipenlg.sqlite3")
        self.assertEqual(cfg.records, 1642756)

    def test_insecure_download_url_is_rejected(self):
        with patch.dict(os.environ, {"FRIDGE_RECIPE_DOWNLOAD_URL": "http://example.test/data.csv"}, clear=True):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                Config.from_env()


if __name__ == "__main__":
    unittest.main()
