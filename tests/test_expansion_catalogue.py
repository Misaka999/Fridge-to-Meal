"""Real-source expanded catalogue and documented smoke inputs; no paid API."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from agent.tools.recipe_parser import parse_recipe
from agent.tools.recipe_search import load_recipes,search_recipes,validate_request

ROOT=Path(__file__).resolve().parents[1]


class ExpandedCatalogueTests(unittest.TestCase):
    def test_real_source_smoke_cases(self):
        recipes=load_recipes(recipe_file=ROOT/'data/recipes_expanded.json')
        tasks=[json.loads(s) for s in (ROOT/'eval/expansion/tasks_expansion_smoke.jsonl').read_text().splitlines()]
        for task in tasks:
            with self.subTest(task=task['id']):
                request=task['request'];expected=task['expected'];before=deepcopy(request)
                issue=validate_request(request)
                if issue:
                    self.assertEqual(expected['status'],'needs_clarification');continue
                result=search_recipes(**request,recipes=recipes)
                if expected['status']=='needs_clarification':
                    self.assertEqual(result['error_code'],'INPUT_INCOMPLETE')
                else:
                    self.assertEqual(result['status'],'found' if expected['allowed_recipe_ids'] else 'no_match')
                    self.assertEqual({r['recipe_id'] for r in result['candidates']},set(expected['allowed_recipe_ids']))
                self.assertEqual(request,before)

    def test_expanded_records_match_original_payload_and_raw_ingredients(self):
        index=ROOT/'data/recipenlg.sqlite3'
        if not index.exists():self.skipTest('External index not available.')
        records=load_recipes(recipe_file=ROOT/'data/recipes_expanded.json')
        conn=sqlite3.connect(index)
        try:
            for record in records:
                if not record.get('parser_version'):continue
                payload=conn.execute("SELECT payload FROM recipes WHERE json_extract(payload,'$.id')=? LIMIT 1",(record['id'],)).fetchone()[0]
                source=json.loads(payload)
                self.assertEqual(record['source_record_sha256'],hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest())
                self.assertEqual(record['raw_ingredients'],source['raw_ingredients'])
                self.assertEqual(record['steps'],source['steps'])
                self.assertEqual({i for x in record['ingredients'] for i in x['raw_indices']},set(range(len(source['raw_ingredients']))))
                self.assertEqual(record['review_status'],'automatically_source_parsed')
        finally:conn.close()

    def test_csv_retrieval_parses_supported_records_without_replacing_reviewed_records(self):
        source={'id':'recipenlg_dynamic_test','title':'Synthetic pasta','source':'RecipeNLG/Gathered',
                'source_url':'https://example.org/test-only','raw_ingredients':['2 c. flour','2 eggs'],
                'steps':['Knead flour and eggs.','Serves 2.'],'quantity_verified':False,'servings':None}
        request={'pantry':[{'name':'flour','quantity':500,'unit':'ml'},{'name':'eggs','quantity':3,'unit':'count'}],
                 'servings':2,'preferences':{'dietary_restrictions':['vegetarian'],'likes':[]},'as_of_date':'2026-11-18'}
        with patch('agent.tools.recipenlg_store.retrieve',return_value=[source]), \
             patch('agent.tools.recipenlg_store.matching_reviewed_records',return_value=[]), \
             patch.dict('os.environ',{'FRIDGE_RECIPE_FILE':''}):
            rows=load_recipes(request)
            self.assertTrue(rows[0]['quantity_verified'])
            self.assertEqual(search_recipes(**request,recipes=rows)['status'],'found')

    def test_scaled_output_marks_original_directions(self):
        request=json.loads((ROOT/'examples/example_request_expanded_pasta.json').read_text())
        result=search_recipes(**request,recipes=load_recipes(recipe_file=ROOT/'data/recipes_expanded.json'))
        candidate=result['candidates'][0]
        self.assertEqual(candidate['servings'],2)
        self.assertEqual(candidate['original_servings'],4)
        self.assertIn('Original directions',candidate['steps_note'])


if __name__=='__main__':unittest.main()
