"""Pantry budgets are enforced on model-adapted portions before presentation."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch
from langchain_core.messages import AIMessage
from agent.recipe_adaptation import validate_proposal,render_adaptations
from react_agent import run_agent


def request():
    return {'pantry':[{'name':'egg','quantity':4,'unit':'count'},
                      {'name':'tomato','quantity':3,'unit':'count'},
                      {'name':'oil','quantity':2,'unit':'tbsp'}],
            'servings':1,'preferences':{'dietary_restrictions':['vegetarian'],'likes':[]},'as_of_date':'2026-11-23'}


def observed():
    return {'status':'error','candidates':[],'error_code':'RECIPE_DETAILS_UNVERIFIED',
            'alternatives':[{'recipe_id':'source_egg','title':'Source tomato eggs',
                             'raw_ingredients':['6 eggs','4 tomatoes','4 tbsp oil']}]}


def payload():
    return {'adapted_recipes':[{'source_recipe_id':'source_egg','title':'Tomato and Egg Scramble','servings':1,
             'ingredients':[{'name':'egg','quantity':2,'unit':'count'},
                            {'name':'tomato','quantity':1,'unit':'count'},
                            {'name':'oil','quantity':5,'unit':'ml'}],
             'steps':['Heat the oil, add the tomato, then add the egg and stir until set.'],
             'changes':['Suggested portions for one person; original yield was not stated.']}]}


class AdaptationTests(TestCase):
    def test_adapted_portions_fit_pantry_without_using_all_stock(self):
        r=request();before=deepcopy(r)
        drafts=validate_proposal(payload(),r,observed())
        self.assertEqual(drafts[0]['ingredients'][0]['quantity'],2)
        self.assertEqual(r,before)
        self.assertIn('not verified original recipe yields',render_adaptations(r,drafts))
        self.assertIn('egg: 2 count',render_adaptations(r,drafts))

    def test_stock_overrun_incompatible_units_duplicates_and_expired_stock_are_rejected(self):
        for kind in ['overrun','units','duplicates','expired']:
            with self.subTest(kind=kind):
                p=payload();r=request()
                if kind=='overrun':p['adapted_recipes'][0]['ingredients'][2]['quantity']=50
                if kind=='units':p['adapted_recipes'][0]['ingredients'][2]['unit']='g'
                if kind=='duplicates':p['adapted_recipes'][0]['ingredients'].append({'name':'eggs','quantity':3,'unit':'count'})
                if kind=='expired':r['pantry'][1]['expires_on']='2026-11-22'
                with self.assertRaises(ValueError):validate_proposal(p,r,observed())

    def test_dietary_restriction_unknown_source_and_servings_are_enforced(self):
        for kind in ['diet','source','servings']:
            with self.subTest(kind=kind):
                p=payload();r=request()
                if kind=='diet':r['preferences']['dietary_restrictions']=['egg-free']
                if kind=='source':p['adapted_recipes'][0]['source_recipe_id']='invented'
                if kind=='servings':p['adapted_recipes'][0]['servings']=2
                with self.assertRaises(ValueError):validate_proposal(p,r,observed())

    def test_step_cannot_silently_add_unlisted_salt(self):
        p=payload();p['adapted_recipes'][0]['steps']=['Heat oil and add salt, tomato and egg.']
        with self.assertRaisesRegex(ValueError,'unlisted ingredient'):validate_proposal(p,request(),observed())

    def test_dicing_existing_tomatoes_does_not_require_new_inventory(self):
        p=payload();p['adapted_recipes'][0]['steps']=['Dice the tomato. Mix the diced tomatoes with the egg and oil.']
        self.assertTrue(validate_proposal(p,request(),observed()))
        p['adapted_recipes'][0]['steps']=['Mix the diced onion with the egg.']
        with self.assertRaisesRegex(ValueError,'unlisted ingredient'):validate_proposal(p,request(),observed())

    def test_display_tablespoons_are_checked_in_canonical_volume_units(self):
        p=payload();p['adapted_recipes'][0]['ingredients'][2].update(quantity=1,unit='tbsp')
        adapted=validate_proposal(p,request(),observed())
        self.assertEqual(adapted[0]['ingredients'][2]['unit'],'tbsp')
        p['adapted_recipes'][0]['ingredients'][2]['quantity']=3
        with self.assertRaisesRegex(ValueError,'exceed'):validate_proposal(p,request(),observed())

    def test_full_agent_repairs_over_budget_adaptation_once_and_keeps_metrics(self):
        bad=payload();bad['adapted_recipes'][0]['ingredients'][0]['quantity']=5
        model=AdaptiveModel([bad,payload()])
        out=run_agent(request(),model=model,search=lambda **kw:observed(),adapt_recipes=True)
        self.assertEqual(out['result']['status'],'recommended')
        self.assertEqual(out['metrics']['model_calls'],3)
        self.assertEqual(out['adapted_recipes'][0]['ingredients'][0]['quantity'],2)
        self.assertEqual(out['display_title'],'Adjusted recipe suggestions')
        checks=[t['result']['valid'] for t in out['tool_trace'] if t['tool']=='validate_adaptation']
        self.assertEqual(checks,[False,True])

    def test_failed_repair_never_displays_unchecked_recipe(self):
        bad=payload();bad['adapted_recipes'][0]['ingredients'][0]['quantity']=5
        out=run_agent(request(),model=AdaptiveModel([bad,bad]),search=lambda **kw:observed(),adapt_recipes=True)
        self.assertEqual(out['result']['status'],'needs_clarification')
        self.assertEqual(out['result']['recipe_ids'],[])
        self.assertNotIn('adapted_recipes',out)
        self.assertEqual(out['metrics']['model_calls'],3)

    def test_session_details_show_adapted_amounts_and_reject_stale_stock(self):
        from agent.session import MealSessions
        out=run_agent(request(),model=AdaptiveModel([payload()]),search=lambda **kw:observed(),adapt_recipes=True)
        sessions=MealSessions(adapt_recipes=True)
        with patch('react_agent.run_agent',return_value=out):sessions.run_turn('a',request())
        details=sessions.run_turn('a',recipe_id='source_egg')
        self.assertEqual(details['display_title'],'Your adjusted recipe')
        self.assertIn('egg: 2 count',details['result']['message'])
        reduced=deepcopy(request()['pantry']);reduced[0]['quantity']=1
        with patch('react_agent.run_agent',side_effect=RuntimeError),self.assertRaises(RuntimeError):
            sessions.run_turn('a',{'pantry':reduced})
        self.assertEqual(sessions.run_turn('a',recipe_id='source_egg')['result']['status'],'needs_clarification')


class AdaptiveModel:
    model_name='offline-adaptation-test'
    def __init__(self,answers):self.answers=iter(answers)
    def bind_tools(self,*args,**kwargs):return self
    def invoke(self,messages):
        usage={'input_tokens':10,'output_tokens':5,'total_tokens':15}
        if messages[0].content.startswith('Propose practical meal adaptations'):
            return AIMessage(content=json.dumps(next(self.answers)),usage_metadata=usage)
        return AIMessage(content='',tool_calls=[{'id':'search','name':'search_recipes','args':{}}],usage_metadata=usage)
