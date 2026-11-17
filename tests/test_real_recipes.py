"""Held-out expectations against real-source reviewed recipes, not model benchmarks."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from agent.tools.dietary import detected_conflicts
from agent.tools.ingredient_names import normalize_name, retrieval_name
from agent.tools.recipe_search import load_recipes, search_recipes, validate_request

ROOT=Path(__file__).resolve().parents[1]
CATALOGUE=ROOT/'data/recipes_recipenlg.json'


class RealRecipeTests(unittest.TestCase):
    def test_explicit_gold_cases_keep_quantity_serving_and_diet_checks(self):
        recipes=load_recipes(recipe_file=CATALOGUE)
        tasks=[json.loads(s) for s in (ROOT/'eval/week6/tasks_recipenlg_yangyang.jsonl').read_text().splitlines()]
        for task in tasks:
            with self.subTest(task=task['id']):
                request=task['request'];expected=task['expected'];before=deepcopy(request)
                issue=validate_request(request)
                if issue:
                    self.assertEqual(expected['status'],'needs_clarification')
                    continue
                result=search_recipes(**request,recipes=recipes)
                if expected['status']=='needs_clarification':
                    self.assertEqual(result['error_code'],'INPUT_INCOMPLETE')
                else:
                    self.assertEqual(result['status'],'found' if expected['allowed_recipe_ids'] else 'no_match')
                    self.assertEqual({r['recipe_id'] for r in result['candidates']},set(expected['allowed_recipe_ids']))
                    if expected.get('top_recipe_ids'):
                        self.assertIn(result['candidates'][0]['recipe_id'],expected['top_recipe_ids'])
                self.assertEqual(request,before)

    def test_name_normalization_does_not_turn_retrieval_variants_into_strict_substitutes(self):
        self.assertEqual(normalize_name('  CARROTS '),'carrot')
        self.assertEqual(normalize_name('vegetable_oil'),'oil')
        self.assertEqual(retrieval_name('extra-firm tofu'),'tofu')
        self.assertNotEqual(normalize_name('firm tofu'),normalize_name('silken tofu'))
        self.assertNotEqual(normalize_name('coconut milk'),normalize_name('milk'))

    def test_raw_diet_conflict_checks_use_all_ingredients_and_word_boundaries(self):
        result=detected_conflicts(['1 cup chicken broth','1 egg','soy sauce'],['vegetarian','egg-free','soy-free'])
        self.assertEqual({r['restriction'] for r in result},{'vegetarian','egg-free','soy-free'})
        self.assertEqual(detected_conflicts(['eggplant','peanut butter'],['egg-free']),[])

    def test_real_records_retain_explicit_yields_and_exact_original_steps(self):
        records=load_recipes(recipe_file=CATALOGUE)
        index=ROOT/'data/recipenlg.sqlite3'
        if not index.exists():self.skipTest('Downloaded index not available.')
        conn=sqlite3.connect(index)
        try:
            for r in records:
                raw=conn.execute('SELECT payload FROM recipes WHERE json_extract(payload,\'$.id\')=? LIMIT 1',(r['id'],)).fetchone()[0]
                original=json.loads(raw)
                self.assertEqual(r['raw_record_sha256'],hashlib.sha256(raw.encode()).hexdigest())
                self.assertEqual(r['steps'],original['steps'])
                self.assertEqual(r['raw_ingredients'],original['raw_ingredients'])
                self.assertIn(str(r['servings']),r['servings_source'])
                self.assertEqual({i for x in r['ingredients'] for i in x['raw_indices']},set(range(len(r['raw_ingredients']))))
        finally:conn.close()

    def test_agent_adapter_clarifies_missing_servings_without_calling_model(self):
        from eval.agent_adapter import run
        result = run({'servings': None}, {'recipes': []})
        self.assertEqual(result['answer']['status'], 'needs_clarification')
        self.assertEqual(result['metrics']['model_calls'], 0)
        self.assertEqual(result['trace'], [])

if __name__=='__main__':unittest.main()
