"""Full-index web routing and evidence preservation; synthetic cases only."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from agent.tools.full_catalogue import full_search_recipes
from agent.tools.recipe_search import load_recipes
from react_agent import SearchResult


def request():
    return {'pantry':[{'name':'egg','quantity':4,'unit':'count','expires_on':None}],
            'servings':2,'preferences':{'dietary_restrictions':[],'likes':[]},
            'as_of_date':'2026-11-23'}


class FullCatalogueTests(unittest.TestCase):
    def test_missing_index_is_failure_not_no_match(self):
        with patch('agent.tools.full_catalogue.catalogue_info',side_effect=FileNotFoundError):
            result=full_search_recipes(**request())
        self.assertEqual(result['error_code'],'RECIPE_SEARCH_FAILED')

    def test_missing_input_does_not_query_index(self):
        r=request();r['servings']=None
        with patch('agent.tools.full_catalogue.catalogue_info') as info:
            result=full_search_recipes(**r)
        info.assert_not_called()
        self.assertEqual(result['error_code'],'INPUT_INCOMPLETE')

    def test_unresolved_source_is_not_recommended_and_survives_react_schema(self):
        r=request();before=deepcopy(r)
        raw={'id':'synthetic_unresolved','title':'Synthetic eggs','quantity_verified':False,
             'parse_issue':'No explicit serving count in original directions.',
             'unmatched_ingredient_names':['salt'],'source_url':'example.org/test'}
        with patch('agent.tools.full_catalogue.catalogue_info',return_value={'mode':'full_index','indexed_records':100}), \
             patch('agent.tools.full_catalogue.load_recipes',return_value=[raw]) as load:
            result=full_search_recipes(**r)
        load.assert_called_once_with(r,full_index=True)
        parsed=SearchResult.model_validate(result)
        self.assertEqual(parsed.error_code,'RECIPE_DETAILS_UNVERIFIED')
        self.assertEqual(parsed.candidates,[])
        self.assertEqual(parsed.retrieved_candidates[0]['missing_ingredient_names'],['salt'])
        self.assertIn('not ready-to-cook',parsed.message)
        self.assertEqual(r,before)

    def test_full_mode_ignores_fixture_override_and_parses_dynamic_hit(self):
        raw={'id':'synthetic_dynamic','title':'Synthetic egg test','source':'RecipeNLG/Gathered',
             'source_url':'example.org/test','raw_ingredients':['2 eggs'],
             'steps':['Cook eggs.','Serves 2.'],'quantity_verified':False,'servings':None}
        with patch.dict(os.environ,{'FRIDGE_RECIPE_FILE':'not-a-real-file.json'}), \
             patch('agent.tools.recipenlg_store.retrieve',return_value=[raw]), \
             patch('agent.tools.recipenlg_store.matching_reviewed_records',return_value=[]):
            recipes=load_recipes(request(),full_index=True)
        self.assertEqual(recipes[0]['id'],'synthetic_dynamic')
        self.assertTrue(recipes[0]['quantity_verified'])

    def test_web_full_mode_injects_request_aware_search(self):
        from web_app import make_server
        with patch('agent.tools.full_catalogue.catalogue_info',return_value={'mode':'full_index'}), \
             patch('web_app.ThreadingHTTPServer') as factory:
            server=make_server(0,recipe_source='full')
        self.assertIs(server.sessions.search,full_search_recipes)
        self.assertEqual(server.catalogue['mode'],'full_index')


if __name__=='__main__':unittest.main()
