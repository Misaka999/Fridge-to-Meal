"""Candidate references resolve to real evidence without changing pantry state."""
import json
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch
from langchain_core.messages import AIMessage
from agent.session import MealSessions
from agent.tools.full_catalogue import conditional_options
from agent.recipe_details import format_source_details


def request():
    return {'pantry':[{'name':'egg','quantity':4,'unit':'count','expires_on':None}],
            'servings':1,'preferences':{'dietary_restrictions':[],'likes':[]},'as_of_date':'2026-11-23'}


def source():
    return {'id':'recipenlg_42','title':'Freezing Eggs','raw_ingredients':['1 egg'],
            'steps':['Use a freezer container.'],'source_url':'example.org/eggs','quantity_verified':False}


def result():
    return {'result':{'status':'needs_clarification','recipe_ids':[],'message':'Freezing Eggs needs source review.'},
            'metrics':{'model_calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0,'tool_calls':1},
            'tool_trace':[{'tool':'search_recipes','result':{'status':'error','candidates':[],
                          'retrieved_candidates':[{'recipe_id':'recipenlg_42','title':'Freezing Eggs'}]}}]}


class RecipeFollowups(TestCase):
    def test_title_and_typo_followups_use_stored_candidate_ids(self):
        model=Mock();model.invoke.return_value=AIMessage(content='{"recipe_details":"recipenlg_42"}')
        reader=Mock(return_value=source());sessions=MealSessions(model=model,recipe_reader=reader)
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        before=sessions.get_state('a')
        for message in ['freezing eggs','the receipt of freezing eggs']:
            out=sessions.run_turn('a',message=message)
            self.assertEqual(out['display_title'],'Source recipe details')
            self.assertIn('food storage or preservation',out['result']['message'])
            self.assertIn('1 egg',out['result']['message'])
            self.assertEqual(out['metrics']['model_calls'],1)
            payload=json.loads(model.invoke.call_args.args[0][-1].content)
            self.assertEqual(payload['available_recipes'][0]['recipe_id'],'recipenlg_42')
        self.assertEqual(sessions.get_state('a'),before)
        self.assertEqual(reader.call_count,2)

    def test_cross_session_and_invented_ids_are_not_read(self):
        reader=Mock(return_value=source());sessions=MealSessions(recipe_reader=reader)
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        self.assertEqual(sessions.run_turn('b',recipe_id='recipenlg_42')['result']['status'],'needs_clarification')
        sessions.run_turn('a',recipe_id='invented')
        reader.assert_not_called()
        sessions.reset('a');sessions.run_turn('a',recipe_id='recipenlg_42');reader.assert_not_called()

    def test_reader_failure_does_not_claim_no_recipe(self):
        sessions=MealSessions(recipe_reader=Mock(side_effect=OSError))
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        self.assertEqual(sessions.run_turn('a',recipe_id='recipenlg_42')['result']['status'],'tool_error')

    def test_closest_options_exclude_storage_and_banned_ingredients(self):
        eggs={'id':'recipenlg_43','title':'Boiled Eggs','quantity_verified':False,
              'ingredient_names':['eggs'],'raw_ingredients':['2 eggs'],'steps':['Cook eggs.'],
              'parse_issue':'No explicit source yield.'}
        freezing={**eggs,'id':'recipenlg_42','title':'Freezing Eggs'}
        r=request();before=deepcopy(r)
        options=conditional_options(r,[freezing,eggs])
        self.assertEqual([x['recipe_id'] for x in options],['recipenlg_43'])
        self.assertEqual(options[0]['raw_ingredients'],['2 eggs'])
        self.assertIn('not confirmed',options[0]['verification'])
        self.assertEqual(r,before)
        r['preferences']['dietary_restrictions']=['egg-free']
        self.assertEqual(conditional_options(r,[eggs]),[])

    def test_checked_alternative_explicitly_reports_missing_flour(self):
        pasta={'id':'pasta','title':'Pasta','servings':1,'quantity_verified':True,
               'ingredients':[{'name':'egg','quantity':1,'unit':'count'},{'name':'flour','quantity':100,'unit':'ml'}],
               'steps':['Knead flour and egg.']}
        alternative=conditional_options(request(),[pasta])[0]
        self.assertEqual(alternative['missing_ingredients'],['flour'])
        self.assertEqual(alternative['required_ingredients'][1]['quantity'],100)
        self.assertIn('not satisfied',alternative['verification'])

    def test_later_source_accompaniments_are_available_to_the_model(self):
        raw={'id':'recipenlg_44','title':'Poached Eggs','quantity_verified':False,
             'ingredient_names':['eggs'],'raw_ingredients':['2 eggs'],
             'steps':['Step '+str(i) for i in range(6)]+['Serve on toast with avocado.']}
        option=conditional_options(request(),[raw])[0]
        self.assertIn('Serve on toast with avocado.',option['source_direction_excerpts'])

    def test_source_oil_amount_is_not_confused_with_available_amount(self):
        from agent.tools.full_catalogue import source_batch_checks
        r=request();r['pantry'].append({'name':'oil','quantity':2,'unit':'tbsp'})
        check=source_batch_checks(r,['4 tbsp cooking oil'])[0]
        self.assertEqual(check['ingredient'],'oil')
        self.assertGreater(check['shortfall'],0)
        self.assertAlmostEqual(check['required_source_amount'],2*check['available_amount'],places=4)
