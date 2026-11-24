"""Inventory additions and the user's current meal choice are separate state."""
from unittest import TestCase
from unittest.mock import Mock,patch
import json
from langchain_core.messages import AIMessage
from agent.session import MealSessions
from agent.recipe_adaptation import validate_proposal
from test_recipe_adaptation import payload,request as adaptation_request,observed


def request():
    return {'pantry':[{'name':'egg','quantity':4,'unit':'count','expires_on':None}],
            'servings':2,'preferences':{'dietary_restrictions':[],'likes':[]},'as_of_date':'2026-11-23'}


def result():
    return {'result':{'status':'recommended','recipe_ids':['original'],'message':'Current egg dish.'},
            'metrics':{'model_calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0,'tool_calls':0},'tool_trace':[]}


class MealIntentTests(TestCase):
    def create(self):
        model=Mock();sessions=MealSessions(model=model,adapt_recipes=True,search=Mock())
        with patch('react_agent.run_agent',return_value=result()):sessions.run_turn('a',request())
        return model,sessions

    def add_chicken(self,model,sessions):
        model.invoke.return_value=AIMessage(content='{"inventory_updates":[{"op":"add","name":"chicken","quantity":200,"unit":"g"}]}')
        return sessions.run_turn('a',message='just 200g')

    def test_added_chicken_is_recorded_but_user_is_asked_before_replanning(self):
        model,sessions=self.create()
        with patch('react_agent.run_agent') as agent:out=self.add_chicken(model,sessions)
        agent.assert_not_called()
        self.assertIn('use chicken in this meal',out['result']['message'])
        self.assertEqual(sessions.get_state('a')['pantry'][-1]['quantity'],200)
        self.assertEqual(sessions._pending_meal_choice['a'],['chicken'])

    def test_keep_choice_keeps_new_stock_without_another_recommendation(self):
        model,sessions=self.create();self.add_chicken(model,sessions)
        model.invoke.return_value=AIMessage(content='{"meal_choice":{"keep":true}}')
        with patch('react_agent.run_agent') as agent:out=sessions.run_turn('a',message='keep the current meal')
        agent.assert_not_called();self.assertIn('meal kept',out['display_title'])
        self.assertEqual(sessions.get_state('a')['pantry'][-1]['quantity'],200)
        self.assertEqual(sessions._meal_focus.get('a'),[])

    def test_use_choice_carries_chicken_to_search_and_adaptation_without_duplicate_stock(self):
        model,sessions=self.create();self.add_chicken(model,sessions)
        model.invoke.return_value=AIMessage(content='{"meal_choice":{"use":["chicken"]}}')
        with patch('react_agent.run_agent',return_value=result()) as agent:
            out=sessions.run_turn('a',message='yes use chicken')
        self.assertEqual(agent.call_args.kwargs['meal_ingredients'],['chicken'])
        self.assertEqual(agent.call_args.kwargs['search'].keywords['meal_ingredients'],['chicken'])
        self.assertEqual(out['meal_ingredients'],['chicken'])
        self.assertEqual(len([i for i in out['request']['pantry'] if i['name']=='chicken']),1)

    def test_chicken_choice_cannot_silently_override_vegetarian(self):
        model,sessions=self.create();self.add_chicken(model,sessions)
        model.invoke.return_value=AIMessage(content='{"preferences":{"dietary_restrictions":["vegetarian"]},"meal_choice":{"use":["chicken"]}}')
        with patch('react_agent.run_agent') as agent:out=sessions.run_turn('a',message='make it vegetarian with chicken')
        agent.assert_not_called();self.assertIn('conflict',out['result']['message'])
        self.assertEqual(out['request']['preferences']['dietary_restrictions'],['vegetarian'])

    def test_adaptation_cannot_ignore_an_explicit_chicken_focus(self):
        r=adaptation_request();r['meal_ingredients']=['chicken'];r['pantry'].append({'name':'chicken','quantity':200,'unit':'g'})
        with self.assertRaisesRegex(ValueError,'user-selected'):validate_proposal(payload(),r,observed())

    def test_nested_meal_use_flags_work_in_the_session(self):
        model,sessions=self.create()
        model.invoke.return_value=AIMessage(content='{"inventory_updates":[{"op":"add","name":"tomato","quantity":3,"unit":"count","use_in_meal":true},{"op":"add","name":"oil","quantity":2,"unit":"tbsp","use_in_meal":true}]}')
        with patch('react_agent.run_agent',return_value=result()) as agent:
            out=sessions.run_turn('a',message='I also have 3 tomatoes and 2 tbsp oil. Use them now.')
        self.assertEqual(set(agent.call_args.kwargs['meal_ingredients']),{'tomato','oil'})
        self.assertEqual(out['request']['pantry'][-1]['quantity'],2)

    def test_conflicting_meal_flags_return_a_question_without_changing_pantry(self):
        model,sessions=self.create();before=sessions.get_state('a')
        model.invoke.return_value=AIMessage(content='{"inventory_updates":[{"op":"add","name":"tomato","quantity":3,"unit":"count","use_in_meal":true},{"op":"add","name":"oil","quantity":2,"unit":"tbsp","use_in_meal":false}]}')
        out=sessions.run_turn('a',message='Add ingredients')
        self.assertEqual(out['result']['status'],'needs_clarification')
        self.assertEqual(sessions.get_state('a'),before)
