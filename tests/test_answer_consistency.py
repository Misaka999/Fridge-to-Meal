"""Reply correctness boundaries use synthetic model responses, never live calls."""
import json
from unittest import TestCase
from langchain_core.messages import AIMessage, ToolMessage
from test_recipe_adaptation import request, payload, observed, AdaptiveModel
from agent.recipe_adaptation import validate_proposal
from agent.adaptation_checks import validate_step_amounts
from react_agent import run_agent


class AnswerConsistencyTests(TestCase):
    def test_steps_cannot_exceed_declared_egg_count(self):
        for text in ['Beat 100 eggs.', 'Beat four eggs.', 'Beat 3-4 eggs.']:
            with self.subTest(text=text):
                p=payload();p['adapted_recipes'][0]['steps']=[text]
                with self.assertRaisesRegex(ValueError,'exceeds the listed amount'):
                    validate_proposal(p,request(),observed())

    def test_step_units_are_compared_in_the_same_dimension(self):
        items=[{'name':'oil','quantity':1,'unit':'tbsp'}]
        validate_step_amounts(['Heat 3 teaspoons of oil.'],items)
        with self.assertRaisesRegex(ValueError,'exceeds'):
            validate_step_amounts(['Heat 4 teaspoons of oil.'],items)
        with self.assertRaisesRegex(ValueError,'unverified unit conversion'):
            validate_step_amounts(['Heat 4 g oil.'],items)

    def test_partial_portions_and_references_do_not_double_count(self):
        items=[{'name':'egg','quantity':2,'unit':'count'}, {'name':'oil','quantity':1,'unit':'tbsp'}]
        validate_step_amounts(['Beat 2 eggs.','Cook the 2 beaten eggs in 1/2 tbsp oil.',
                              'Add half a tomato if available.'],items)
        validate_step_amounts(['Heat 1/2 tablespoon of oil.','Add 1/2 tablespoon of oil.'],items)

    def test_invalid_amount_is_repaired_before_any_text_is_exposed(self):
        bad=payload();bad['adapted_recipes'][0]['steps']=['Beat 100 eggs.']
        events=[]
        out=run_agent(request(),model=AdaptiveModel([bad,payload()]),search=lambda **kw:observed(),
                      adapt_recipes=True,on_event=lambda k,v:events.append((k,v)))
        self.assertEqual(out['result']['status'],'recommended')
        self.assertEqual(out['metrics']['model_calls'],3)
        self.assertNotIn('100 eggs',json.dumps([v for k,v in events if k=='text']))
        self.assertEqual([v for k,v in events if k=='text'],[out['result']['message']])

    def test_checked_ordinary_reply_ignores_invented_model_narrative(self):
        class Model:
            def bind_tools(self,*args,**kwargs):return self
            def invoke(self,messages):
                if isinstance(messages[-1],ToolMessage):
                    return AIMessage(content=json.dumps({'status':'recommended','recipe_ids':['r1'],
                        'message':'Use 100 eggs and butter. Your pantry has enough.'}))
                return AIMessage(content='',tool_calls=[{'id':'t','name':'search_recipes','args':{}}])
        search=lambda **kw:{'status':'found','error_code':None,'candidates':[
            {'recipe_id':'r1','title':'Egg dish','ingredients':[{'name':'egg','quantity':2,'unit':'count'}],
             'steps':['Cook the eggs until set.']}]}
        events=[]
        out=run_agent(request(),model=Model(),search=search,on_event=lambda k,v:events.append((k,v)))
        self.assertIn('egg: 2 count',out['result']['message'])
        self.assertNotIn('100 eggs',out['result']['message'])
        self.assertNotIn('butter',out['result']['message'])
        self.assertEqual([v for k,v in events if k=='text'],[out['result']['message']])

    def test_search_failure_does_not_claim_no_recipe_exists(self):
        from agent.grounded_messages import render_react_answer
        out=render_react_answer(request(),{'status':'error'},
            {'status':'tool_error','recipe_ids':[],'message':'No feasible recipe exists.'})
        self.assertIn('feasibility is unknown',out['message'])
        self.assertNotIn('No feasible recipe exists',out['message'])
