"""Evaluation protocol checks use offline responses, never benchmark claims."""
import json
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from eval.conversation.scoring import grade_turn
from eval.conversation.runners import BaselineSession
from eval.conversation.judge import make_payload,validate,review,DIMENSIONS
from eval.conversation.evaluate import summarize

ROOT=Path(__file__).resolve().parents[1]
CASE=json.loads((ROOT/'eval/conversation/cases.jsonl').read_text().splitlines()[0])
RECIPES=json.loads((ROOT/'eval/conversation/catalogue.json').read_text())


def good():
    return {'request':deepcopy(CASE['initial']),'pending_inventory':[],'meal_ingredients':[],
            'result':{'status':'recommended','recipe_ids':['recipenlg_1290537'],'message':'Boiled eggs using two eggs, one per person.'},
            'adapted_recipes':[{'source_recipe_id':'recipenlg_1290537','title':'Boiled eggs','servings':2,
                'ingredients':[{'name':'egg','quantity':2,'unit':'count'}],'steps':['Boil the two eggs.'],'changes':['Proposed portions.']}]}


def judgment(severity='none',evidence=None):
    return {'assessments':{d:{'severity':severity,'evidence_ids':evidence or [],'reason':'Concrete finding.'} for d in DIMENSIONS},'uncertainties':[],'overall_reason':'Saved response checked.'}


class ConversationEvaluationTests(TestCase):
    def test_good_response_and_no_oracle_fields_in_baseline_prompt(self):
        self.assertTrue(grade_turn(good(),CASE['turns'][0]['reference'],RECIPES)['passed'])
        messages=[]
        def call(m):messages.append(deepcopy(m));return good(),{'model_calls':1},[]
        runner=BaselineSession(CASE['initial'],RECIPES,call=call);runner.turn();runner.turn('One person.')
        text=json.dumps(messages)
        self.assertNotIn('reference_facts',text)
        self.assertNotIn('"reference":',''.join(m['content'] for batch in messages for m in batch))
        self.assertIn('One person.',text);self.assertIn('Boiled eggs using two eggs',text)
        self.assertEqual(len(messages),2)

    def test_wrong_state_budget_diet_and_invented_source_are_hard_failures(self):
        for kind in ['state','budget','diet','source','step']:
            out=good();ref=deepcopy(CASE['turns'][0]['reference'])
            if kind=='state':out['request']['servings']=1
            if kind=='budget':out['adapted_recipes'][0]['ingredients'][0]['quantity']=100
            if kind=='diet':ref['state']['preferences']['dietary_restrictions']=['egg-free'];out['request']=deepcopy(ref['state'])
            if kind=='source':out['adapted_recipes'][0]['source_recipe_id']='invented'
            if kind=='step':out['adapted_recipes'][0]['steps']=['Beat 100 eggs.']
            with self.subTest(kind=kind):self.assertFalse(grade_turn(out,ref,RECIPES)['passed'])

    def test_conditional_gap_response_has_its_own_valid_outcome(self):
        ref=deepcopy(CASE['turns'][0]['reference']);ref.update(mode='conditional',acceptable_gaps={'recipenlg_683038':['butter']})
        out=good();out.update(result={'status':'needs_clarification','recipe_ids':[],'message':'Fried Mushrooms: missing butter.'},adapted_recipes=[],
            conditional_options=[{'recipe_id':'recipenlg_683038','missing_ingredients':['butter'],'ready_to_cook':False}])
        self.assertTrue(grade_turn(out,ref,RECIPES)['passed'])
        out['conditional_options'][0]['missing_ingredients']=[]
        self.assertFalse(grade_turn(out,ref,RECIPES)['passed'])

    def test_metadata_cannot_hide_missing_user_facing_explanation(self):
        ref=deepcopy(CASE['turns'][0]['reference']);ref.update(mode='conditional',acceptable_gaps={'recipenlg_683038':['butter']})
        out=good();out.update(result={'status':'needs_clarification','recipe_ids':[],'message':'Try this.'},adapted_recipes=[],conditional_options=[{'recipe_id':'recipenlg_683038','missing_ingredients':['butter'],'ready_to_cook':False}])
        self.assertFalse(grade_turn(out,ref,RECIPES)['passed'])

    def test_malformed_outputs_do_not_crash_scoring(self):
        for value in [[],{},None]:
            out={'result':value,'request':[],'adapted_recipes':['bad']}
            self.assertFalse(grade_turn(out,CASE['turns'][0]['reference'],RECIPES)['passed'])
        for field in ('meal_ingredients','dietary_restrictions','source_recipe_id'):
            out=good()
            if field=='meal_ingredients':out[field]=[{'name':'egg'}]
            elif field=='dietary_restrictions':out['request']['preferences'][field]=[{'name':'vegan'}]
            else:out['adapted_recipes'][0][field]={'id':'bad'}
            self.assertFalse(grade_turn(out,CASE['turns'][0]['reference'],RECIPES)['passed'])

    def test_blinding_excludes_architecture_costs_traces_and_previous_scores(self):
        output={**good(),'version':'react','metrics':{'total_tokens':123},'tool_trace':['private architecture'],'rules':{'passed':False}}
        payload=make_payload('Meal goal',[],output,CASE['turns'][0]['reference'],RECIPES)
        self.assertNotIn('private architecture',json.dumps(payload));self.assertNotIn('total_tokens',json.dumps(payload));self.assertNotIn('"version"',json.dumps(payload))
        payload=make_payload('FUTURE_SCENARIO_GOAL',[],output,CASE['turns'][0]['reference'],RECIPES)
        self.assertNotIn('FUTURE_SCENARIO_GOAL',json.dumps(payload))

    def test_deductions_require_real_evidence_and_scores_are_mechanical(self):
        payload=make_payload('Meal goal',[],good(),CASE['turns'][0]['reference'],RECIPES)
        for evidence in [[],['R999']]:
            with self.assertRaises(ValueError):validate(judgment('major',evidence),payload)
        result=validate(judgment('major',['R001']),payload)
        self.assertEqual(set(result['scores'].values()),{0})
        result=validate(judgment('unassessable'),payload);self.assertTrue(result['needs_human_review'])
        self.assertEqual(set(result['scores'].values()),{None})

    def test_judge_gets_objective_expiry_and_missing_input_facts(self):
        state=deepcopy(CASE['initial']);state['servings']=None
        state['pantry'][0]['expires_on']='2026-11-01'
        payload=make_payload('',[],good(),{'state':state,'mode':'clarify'},RECIPES)
        facts=payload['reference_facts']['objective_input_facts']
        self.assertTrue(facts['missing_or_invalid_servings'])
        self.assertEqual(facts['recorded_nonexpired_positive_lots'],[])
        self.assertEqual(len(facts['recorded_expired_lots']),1)

    def test_full_judge_reference_index_does_not_hide_named_sources(self):
        from eval.compare_review import full_payload
        row={'answer':{'status':'needs_clarification','recipe_ids':[],'message':'Fried Mushrooms is in the supplied pool.'},'adapted_recipes':[]}
        payload=full_payload(row,{'request':CASE['initial'],'expectation':'clarify'},{'recipes':RECIPES})
        self.assertEqual(len(payload['source_index']),len(RECIPES))
        self.assertIn('recipenlg_683038',{r['id'] for r in payload['source_recipes']})

    def test_invalid_judge_is_retried_and_never_counts_as_a_perfect_answer(self):
        payload=make_payload('Meal goal',[],good(),CASE['turns'][0]['reference'],RECIPES)
        result=review(payload,call=lambda m:({}, {'model_calls':1},[]))
        self.assertIsNone(result['judgment']);self.assertEqual(len(result['attempts']),2)

    def test_pass_three_means_all_turns_in_all_three_independent_runs(self):
        rows=[{'version':'react','case_id':'x','trial':t,'turn':i,'reference':{'mode':'recommend'},'output':{},'rules':{'passed':not(t==2 and i==2)}} for t in [1,2,3] for i in [1,2]]
        result=summarize(rows,3)['react']
        self.assertEqual(result['pass^3'],0);self.assertEqual(result['pass@3'],1)
        self.assertAlmostEqual(result['conversation_rule_pass_rate'],2/3)
