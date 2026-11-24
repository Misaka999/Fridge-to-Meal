"""Prepare a verified RecipeNLG build artifact and start the full-index web app.

Run as a module from the repository root. Build downloads once and indexes the
complete Gathered source. Start never downloads or silently falls back to seeds.
No credentials or model calls are used by data preparation.
"""
import argparse
from contextlib import closing
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from agent.tools.recipenlg_store import build_index, signature, INDEX_VERSION

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1f0Ump2DMYNxauNsNnt3oCcm3GYeb4OQB&export=download&confirm=t"
)
DEFAULT_SHA256 = "f376ee0bb9f99f323761abf6270d453f4eff2002c3625d04cabcf8b57dca0803"
DEFAULT_BYTES = 2294981083
DEFAULT_RECORDS = 1642756
# Whole-second timestamps survive build artifact packaging without precision loss.
ARTIFACT_TIME_NS = 1700000000 * 1_000_000_000
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Config:
    csv_path: Path
    index_path: Path
    manifest_path: Path
    url: str = DEFAULT_URL
    sha256: str = DEFAULT_SHA256
    size: int = DEFAULT_BYTES
    records: int = DEFAULT_RECORDS

    @classmethod
    def from_env(cls):
        directory = Path(os.getenv("FRIDGE_RECIPE_DATA_DIR", str(ROOT / "data"))).expanduser().resolve()
        csv_path = Path(os.getenv("FRIDGE_RECIPE_CSV", str(directory / "RecipeNLG_dataset.csv"))).expanduser().resolve()
        index_path = Path(os.getenv("FRIDGE_RECIPE_INDEX", str(directory / "recipenlg.sqlite3"))).expanduser().resolve()
        if os.getenv("RENDER") and any(not p.is_relative_to(ROOT) for p in (directory, csv_path, index_path)):
            raise ValueError("Keep build artifacts inside the project. Remove old /var/data path variables; no persistent disk is required.")
        result = cls(csv_path, index_path, directory / "render_recipe_manifest.json",
                     os.getenv("FRIDGE_RECIPE_DOWNLOAD_URL", DEFAULT_URL),
                     os.getenv("FRIDGE_RECIPE_SHA256", DEFAULT_SHA256).lower(),
                     int(os.getenv("FRIDGE_RECIPE_BYTES", str(DEFAULT_BYTES))),
                     int(os.getenv("FRIDGE_RECIPE_RECORDS", str(DEFAULT_RECORDS))))
        if urlsplit(result.url).scheme != "https":
            raise ValueError("The recipe download URL must use HTTPS.")
        if len(result.sha256) != 64 or any(c not in "0123456789abcdef" for c in result.sha256):
            raise ValueError("Provide a valid pinned FRIDGE_RECIPE_SHA256.")
        if result.size <= 0 or result.records <= 0:
            raise ValueError("Expected source size and record count must be positive.")
        if len({result.csv_path, result.index_path, result.manifest_path}) != 3:
            raise ValueError("CSV, index and manifest paths must be distinct.")
        return result


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            result.update(chunk)
    return result.hexdigest()


def stamp(path):
    stat = path.stat()
    return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def normalize_time(path):
    os.utime(path, ns=(ARTIFACT_TIME_NS, ARTIFACT_TIME_NS))


def check_header(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        columns = next(csv.reader(stream), [])
    if not {"title", "ingredients", "directions", "source", "link"} <= set(columns):
        raise ValueError("The downloaded file is not the expected RecipeNLG CSV.")


def verify_csv(path, config):
    if path.stat().st_size != config.size or digest(path) != config.sha256:
        raise ValueError("CSV checksum or size mismatch. Check the download permission and pinned dataset version.")
    check_header(path)


def download_csv(config, *, opener=urlopen):
    """Stream to a temporary file; never replace a good file with HTML or partial data."""
    destination = config.csv_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".recipe-download-", suffix=".part", dir=destination.parent)
    temporary = Path(name)
    try:
        request = Request(config.url, headers={"User-Agent": "Fridge-to-Meal/1.0"})
        with os.fdopen(fd, "wb") as stream, opener(request, timeout=120) as response:
            if response.status != 200:
                raise ValueError("The server did not return a complete download (HTTP 200 required).")
            if "html" in response.headers.get("Content-Type", "").lower():
                raise ValueError("The download returned an HTML page. Check Drive sharing or its download quota.")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) != config.size:
                raise ValueError("The server returned an unexpected file size.")
            checksum = hashlib.sha256()
            received = 0
            next_progress = 64 * CHUNK
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                received += len(chunk)
                if received > config.size:
                    raise ValueError("Download exceeds the pinned dataset size.")
                stream.write(chunk)
                checksum.update(chunk)
                if received >= next_progress:
                    print(f"Downloaded {received // CHUNK:,} MiB / {config.size // CHUNK:,} MiB", flush=True)
                    next_progress += 64 * CHUNK
        if received != config.size or checksum.hexdigest() != config.sha256:
            raise ValueError("Download incomplete or checksum mismatch; the old CSV was not replaced.")
        check_header(temporary)
        normalize_time(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_index_metadata(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        rows = conn.execute("SELECT value FROM metadata").fetchall()
    if len(rows) != 1:
        raise ValueError("Index metadata is incomplete.")
    return json.loads(rows[0][0])


def load_manifest(config):
    manifest = json.loads(config.manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError("Build artifact manifest must be an object.")
    if (manifest.get("format") != 1 or manifest.get("index_version") != INDEX_VERSION
            or manifest.get("csv", {}).get("sha256") != config.sha256
            or manifest["csv"].get("bytes") != config.size
            or manifest.get("indexed_records") != config.records):
        raise ValueError("Build artifact manifest does not match the configured dataset.")
    index = manifest.get("index", {})
    if not isinstance(index.get("sha256"), str) or len(index["sha256"]) != 64:
        raise ValueError("Index checksum is missing from the manifest.")
    return manifest


def write_manifest(config, index_hash):
    manifest = {"format": 1, "index_version": INDEX_VERSION,
                "indexed_records": config.records,
                "csv": {**stamp(config.csv_path), "sha256": config.sha256},
                "index": {**stamp(config.index_path), "sha256": index_hash}}
    config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".recipe-manifest-", dir=config.manifest_path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
        temporary.replace(config.manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def verify_artifact(config):
    """Rebind build-machine metadata only after verifying both artifact contents.

    The fast path checks stable sizes/timestamps. If packaging changes a path or
    timestamp, verify the recorded SHA-256 hashes before updating metadata.
    """
    manifest = load_manifest(config)
    meta = read_index_metadata(config.index_path)
    if meta.get("recipes") != config.records or meta.get("version") != INDEX_VERSION:
        raise ValueError("The index record count or format is not the expected full corpus.")
    changed_source = any(meta.get(k) != v for k, v in signature(config.csv_path).items())
    changed_csv = stamp(config.csv_path) != {k: manifest["csv"][k] for k in ("bytes", "mtime_ns")}
    changed_index = stamp(config.index_path) != {k: manifest["index"][k] for k in ("bytes", "mtime_ns")}
    if changed_source or changed_csv:
        verify_csv(config.csv_path, config)
    if changed_source or changed_index:
        if digest(config.index_path) != manifest["index"]["sha256"]:
            raise ValueError("The index checksum changed; rebuild it instead of changing the source signature.")
    if changed_source:
        normalize_time(config.csv_path)
        with closing(sqlite3.connect(config.index_path)) as conn:
            meta.update(signature(config.csv_path))
            conn.execute("UPDATE metadata SET value=?", (json.dumps(meta),))
            conn.commit()
        normalize_time(config.index_path)
        manifest = write_manifest(config, digest(config.index_path))
    elif changed_csv or changed_index:
        manifest = write_manifest(config, manifest["index"]["sha256"])
    return manifest


def prepare_build(config, *, opener=urlopen, builder=build_index):
    config.csv_path.parent.mkdir(parents=True, exist_ok=True)
    config.index_path.parent.mkdir(parents=True, exist_ok=True)
    # A matching prior build may be reused; metadata alone cannot authorize reuse.
    if config.manifest_path.exists() and config.csv_path.exists() and config.index_path.exists():
        try:
            result = verify_artifact(config)
            verify_csv(config.csv_path, config)
            if digest(config.index_path) != result["index"]["sha256"]:
                raise ValueError("Cached index content mismatch.")
        except (OSError, ValueError, KeyError, sqlite3.Error):
            print("Cached data failed validation; preparing a fresh verified build.", flush=True)
        else:
            print(f"Reused verified index: {config.records:,} Gathered recipes.", flush=True)
            return result
    valid_csv = False
    if config.csv_path.exists():
        try:
            verify_csv(config.csv_path, config)
            valid_csv = True
        except (OSError, ValueError, UnicodeError):
            pass
    required = int(config.size * 1.5) + (0 if valid_csv else config.size) + 256 * CHUNK
    if shutil.disk_usage(config.csv_path.parent).free < required:
        raise ValueError("Not enough temporary build disk space for the complete CSV and index.")
    if not valid_csv:
        print("Downloading the pinned full RecipeNLG CSV (no API key required).", flush=True)
        download_csv(config, opener=opener)
    normalize_time(config.csv_path)
    fd, name = tempfile.mkstemp(prefix=".recipenlg-build-", suffix=".sqlite3", dir=config.index_path.parent)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink()
    try:
        print("Building the full Gathered index; this runs during deploy, not a user request.", flush=True)
        metadata = builder(config.csv_path, temporary)
        if metadata.get("recipes") != config.records or metadata.get("version") != INDEX_VERSION:
            raise ValueError("Indexed record count differs from the pinned full dataset.")
        stored = read_index_metadata(temporary)
        if stored != metadata:
            raise ValueError("The newly built index metadata is inconsistent.")
        # The source-provenance and recipe-detail readers use this exact JSON
        # expression. Build its lookup index here so a cold web request does not
        # scan millions of source payloads just to resolve a few seed IDs.
        with closing(sqlite3.connect(temporary)) as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS render_recipe_source_id "
                         "ON recipes(json_extract(payload, '$.id'))")
            conn.commit()
        normalize_time(temporary)
        index_hash = digest(temporary)
        temporary.replace(config.index_path)
        result = write_manifest(config, index_hash)
    finally:
        temporary.unlink(missing_ok=True)
        temporary.with_name(temporary.name + ".building").unlink(missing_ok=True)
    print(f"Build ready: {config.records:,} Gathered recipes. No persistent disk required.", flush=True)
    return result


def start(config):
    try:
        verify_artifact(config)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        raise ValueError("Full recipe build artifact is missing or invalid. Run the configured build command before starting. " + str(exc)) from exc
    os.environ["FRIDGE_RECIPE_CSV"] = str(config.csv_path)
    os.environ["FRIDGE_RECIPE_INDEX"] = str(config.index_path)
    print(f"Starting full-catalogue web app with {config.records:,} indexed recipes.", flush=True)
    os.execv(sys.executable, [sys.executable, str(ROOT / "web_app.py"),
                            "--host", "0.0.0.0", "--port", os.getenv("PORT", "8765"),
                            "--recipe-source", "full"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check", "start"))
    args = parser.parse_args()
    try:
        config = Config.from_env()
        if args.action == "build":
            prepare_build(config)
        elif args.action == "check":
            verify_artifact(config)
            print(f"Verified full index: {config.records:,} Gathered recipes.", flush=True)
        else:
            start(config)
    except HTTPError as exc:
        print(f"Recipe download failed (HTTP {exc.code}). Check Drive sharing and download limits.", file=sys.stderr)
        return 1
    except URLError:
        print("Recipe download could not connect. Retry the deploy after checking the download source.", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, sqlite3.Error, UnicodeError) as exc:
        print("Recipe deployment failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
