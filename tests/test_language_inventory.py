"""Natural pantry additions ask normal questions and commit only valid amounts."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import Mock,patch
from langchain_core.messages import AIMessage
from agent.session import MealSessions
from agent.tools.language_inventory import apply_language_edits


def request():
    return {'pantry':[{'name':'egg','quantity':4,'unit':'count','expires_on':None}],
            'servings':1,'preferences':{'dietary_restrictions':['vegetarian'],'likes':[]},'as_of_date':'2026-11-23'}


def result():
    return {'result':{'status':'no_feasible_recipe','recipe_ids':[],'message':'Checked pantry.'},
            'metrics':{'model_calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0,'tool_calls':0},'tool_trace':[]}


class LanguageInventoryTests(TestCase):
    def test_missing_quantities_ask_without_json_and_do_not_write(self):
        old=request()['pantry'];before=deepcopy(old)
        new,pending,q=apply_language_edits(old,[{'op':'add','name':'oil','quantity':None,'unit':None},
                                             {'op':'add','name':'tomatos','quantity':None,'unit':None}])
        self.assertEqual(new,old);self.assertEqual(old,before)
        self.assertEqual(pending[1]['name'],'tomato')
        self.assertIn('How much oil',q);self.assertIn('How many tomatoes',q)
        self.assertNotIn('{',q)

    def test_complete_batch_commits_atomically_and_invalid_batch_does_not(self):
        old=request()['pantry']
        edits=[{'op':'add','name':'oil','quantity':2,'unit':'tbsp'},
               {'op':'add','name':'tomatos','quantity':3,'unit':'count'}]
        new,pending,q=apply_language_edits(old,edits)
        self.assertIsNone(q);self.assertEqual(pending,[])
        self.assertEqual(new[-1]['name'],'tomato');self.assertEqual(len(old),1)
        edits[-1]['quantity']=-1
        new,pending,q=apply_language_edits(old,edits)
        self.assertEqual(new,old);self.assertTrue(q)

    def test_pending_edits_survive_until_next_natural_reply(self):
        model=Mock();sessions=MealSessions(model=model)
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        model.invoke.return_value=AIMessage(content=json.dumps({'inventory_updates':[
            {'op':'add','name':'oil','quantity':None,'unit':None},
            {'op':'add','name':'tomato','quantity':None,'unit':None}]}))
        first=sessions.run_turn('a',message='and i have oil and tomatos')
        self.assertEqual(first['request'],request())
        model.invoke.return_value=AIMessage(content=json.dumps({'inventory_updates':[
            {'op':'add','name':'oil','quantity':2,'unit':'tbsp'},
            {'op':'add','name':'tomato','quantity':3,'unit':'count'}]}))
        with patch('react_agent.run_agent',return_value=result()) as recommend:
            second=sessions.run_turn('a',message='2 tablespoons of oil and 3 tomatoes')
        payload=json.loads(model.invoke.call_args.args[0][-1].content)
        self.assertEqual(len(payload['pending_inventory']),2)
        self.assertEqual(second['request']['pantry'][-1]['quantity'],3)
        self.assertEqual(second['request']['preferences'],request()['preferences'])
        self.assertEqual(recommend.call_args.args[0],second['request'])
        self.assertEqual(sessions._pending_inventory.get('a',[]),[])
        self.assertEqual(sessions.get_state('b')['pantry'],None)

    def test_pending_edits_can_be_cancelled_without_writes(self):
        model=Mock();sessions=MealSessions(model=model)
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        model.invoke.side_effect=[AIMessage(content='{"inventory_updates":[{"op":"add","name":"oil","quantity":null,"unit":null}]}'),
                                  AIMessage(content='{"cancel_inventory":true}')]
        sessions.run_turn('a',message='I also have oil')
        sessions.run_turn('a',message='Forget adding oil')
        self.assertEqual(sessions.get_state('a'),request())
        self.assertEqual(sessions._pending_inventory.get('a',[]),[])

class MealFlagShapeTests(TestCase):
    def test_consistent_per_edit_flags_are_lifted_without_changing_amounts(self):
        from agent.tools.language_inventory import normalize_meal_flag
        value={'inventory_updates':[{'op':'add','name':'tomato','quantity':3,'unit':'count','use_in_meal':True},
                                    {'op':'add','name':'oil','quantity':2,'unit':'tbsp','use_in_meal':True}]}
        result=normalize_meal_flag(value)
        self.assertIs(result['use_in_meal'],True)
        self.assertEqual(result['inventory_updates'][0]['quantity'],3)
        self.assertNotIn('use_in_meal',result['inventory_updates'][0])
        self.assertIn('use_in_meal',value['inventory_updates'][0])

    def test_conflicting_or_partial_flags_are_not_guessed(self):
        from agent.tools.language_inventory import normalize_meal_flag
        for flags in [(True,False),(True,None),('yes',True)]:
            edits=[{'op':'add','name':name,**({'use_in_meal':flag} if flag is not None else {})}
                   for name,flag in zip(['tomato','oil'],flags)]
            with self.assertRaises(ValueError):normalize_meal_flag({'inventory_updates':edits})
