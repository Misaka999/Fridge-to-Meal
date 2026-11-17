"""Exercise the search hook documented by the root README without an Agent."""
from functools import partial
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import load_recipes, search_recipes, validate_request

ROOT=Path(__file__).resolve().parents[1]


class ReadmeContractTests(unittest.TestCase):
    def test_documented_keyword_hook_returns_scaled_candidates(self):
        request=json.loads((ROOT/'data/example_request_real.json').read_text())
        search=partial(search_recipes,recipes=load_recipes(recipe_file=ROOT/'data/recipes_recipenlg.json'))
        result=search(**request)
        self.assertEqual(result['status'],'found')
        self.assertEqual(result['candidates'][0]['recipe_id'],'recipenlg_68810')
        self.assertEqual(result['candidates'][0]['servings'],request['servings'])
        request['pantry']=[]
        self.assertEqual(search(**request)['status'],'no_match')
        request['servings']=None
        self.assertEqual(validate_request(request)['status'],'needs_clarification')
        self.assertEqual(search(**request)['error_code'],'INPUT_INCOMPLETE')


if __name__=='__main__':unittest.main()
