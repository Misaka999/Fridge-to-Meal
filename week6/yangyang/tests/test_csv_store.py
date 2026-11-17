"""Synthetic regression tests for the real CSV backend; no paid model calls."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recipenlg_store import build_index, retrieve
from tools import search_recipes, load_recipes


class CsvStoreTests(unittest.TestCase):
    def test_real_backend_keeps_original_data_and_unknown_yield(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            source = folder / 'recipes.csv'
            index = folder / 'recipes.sqlite3'
            with source.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['', 'title', 'ingredients', 'directions', 'source', 'link', 'NER'])
                writer.writeheader()
                for identifier, origin in [('41', 'Gathered'), ('42', 'Recipes1M')]:
                    writer.writerow({'':identifier, 'title':'Synthetic tofu', 'ingredients':'["250 g tofu"]',
                                     'directions':'["Cook tofu."]', 'source':origin,
                                     'link':'example.org/test', 'NER':'["tofu"]'})
            stats = build_index(source, index)
            self.assertEqual(stats['recipes'], 1)
            request = {'pantry':[{'name':'tofu', 'quantity':300, 'unit':'g'}], 'servings':2,
                       'preferences':{'dietary_restrictions':['vegan'], 'likes':[]},
                       'as_of_date':'2026-11-16'}
            with patch.dict(os.environ, {'FRIDGE_RECIPE_CSV':str(source), 'FRIDGE_RECIPE_INDEX':str(index)}):
                with patch.dict(os.environ):
                    os.environ.pop('FRIDGE_RECIPE_FILE', None)
                    rows = load_recipes(request)
                    self.assertEqual(rows[0]['id'], 'recipenlg_41')
                    self.assertEqual(rows[0]['raw_ingredients'], ['250 g tofu'])
                    self.assertIsNone(rows[0]['servings'])
                    result = search_recipes(**request)
                    self.assertEqual(result['error_code'], 'RECIPE_DETAILS_UNVERIFIED')
                    self.assertEqual(result['candidates'], [])
                    self.assertEqual(result['retrieved_candidates'][0]['id'], 'recipenlg_41')
                    source.write_text(source.read_text() + '\n')
                    with self.assertRaises(ValueError):
                        retrieve(request)


if __name__ == '__main__':
    unittest.main()
