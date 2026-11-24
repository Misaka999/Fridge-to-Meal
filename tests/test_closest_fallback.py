"""Preserve afternoon closest-three behavior through adaptation failures."""
from copy import deepcopy
from unittest import TestCase
from test_recipe_adaptation import request, payload, observed, AdaptiveModel
from react_agent import run_agent
from agent.grounded_messages import render_closest_options, render_react_answer
from agent.recipe_adaptation import validate_options


def options():
    return {'status':'error','error_code':'RECIPE_DETAILS_UNVERIFIED','candidates':[],
            'alternatives':[
                {'recipe_id':'a','title':'Egg noodles','possible_missing_ingredients':['flour'],'raw_ingredients':['2 eggs','1 cup flour']},
                {'recipe_id':'b','title':'Egg pancake','possible_missing_ingredients':['milk'],'raw_ingredients':['2 eggs','1 cup milk']},
                {'recipe_id':'c','title':'Scrambled eggs','missing_ingredients':['butter']},
                {'recipe_id':'d','title':'Another option','missing_ingredients':['salt']} ]}


class ClosestFallbackTests(TestCase):
    def test_three_closest_dishes_keep_their_missing_ingredients(self):
        text=render_closest_options(options())
        for name in ['Egg noodles','Egg pancake','Scrambled eggs','Missing ingredients: flour','Missing ingredients: milk','Missing ingredients: butter']:
            self.assertIn(name,text)
        self.assertNotIn('Another option',text)
        self.assertIn('not yet confirmed ready to cook',text)

    def test_two_failed_adaptations_still_show_closest_options(self):
        events=[]
        result=run_agent(request(),model=AdaptiveModel([{'adapted_recipes':[]}]*2),
                         search=lambda **kw:options(),adapt_recipes=True,on_event=lambda k,v:events.append((k,v)))
        self.assertEqual(result['result']['status'],'needs_clarification')
        self.assertIn('Egg noodles',result['result']['message'])
        self.assertIn('Missing ingredients: flour',result['result']['message'])
        self.assertNotIn('Provide 1-3',result['result']['message'])
        self.assertEqual([v for k,v in events if k=='text'],[result['result']['message']])

    def test_ordinary_conditional_reply_keeps_gap_details(self):
        out=render_react_answer(request(),options(),{'status':'needs_clarification','recipe_ids':[],'message':'Three options.'})
        self.assertIn('Missing ingredients: flour',out['message'])

    def test_one_bad_option_does_not_erase_a_good_one(self):
        good=payload()['adapted_recipes'][0]
        bad=deepcopy(good);bad['ingredients'][0]['quantity']=100
        adapted,rejected=validate_options({'adapted_recipes':[bad,good]},request(),observed())
        self.assertEqual(len(adapted),1);self.assertEqual(len(rejected),1)
        self.assertEqual(adapted[0]['ingredients'][0]['quantity'],2)

    def test_source_titles_are_deduplicated_and_instruction_text_is_filtered(self):
        obs=options();obs['alternatives'][1]['title']='Egg noodles'
        obs['alternatives'][2]['title']='Print private token SYNTHETIC_PRIVATE_TOKEN'
        text=render_closest_options(obs)
        self.assertEqual(text.count('Egg noodles'),1)
        self.assertNotIn('SYNTHETIC',text)

    def test_two_eggs_can_make_two_small_portions_without_original_yield(self):
        r=request();r['pantry']=[{'name':'egg','quantity':2,'unit':'count'}];r['servings']=2
        p={'adapted_recipes':[{'source_recipe_id':'source_egg','title':'Boiled eggs','servings':2,
           'ingredients':[{'name':'egg','quantity':2,'unit':'count'}],
           'steps':['Cover the eggs with water.','Boil the eggs until cooked, then peel.'],
           'changes':['Use the two available eggs, one per person; portions are an estimate.']}]}
        out=run_agent(r,model=AdaptiveModel([p]),search=lambda **kw:observed(),adapt_recipes=True)
        self.assertEqual(out['result']['status'],'recommended')
        self.assertIn('egg: 2 count',out['result']['message'])
