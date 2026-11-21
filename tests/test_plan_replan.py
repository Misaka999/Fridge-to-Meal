"""Offline protocol/state tests; fake completions are not model-evaluation results."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from agent.model_client import ModelCallError
from agent.plan_replan import run_agent,PlanRunError
from agent.tools.recipe_search import load_recipes

ROOT=Path(__file__).resolve().parents[1]


class ScriptedCompletion:
    def __init__(self,*answers):self.answers=list(answers);self.inputs=[]
    def __call__(self,messages):
        self.inputs.append(deepcopy(messages));answer=self.answers.pop(0)
        if isinstance(answer,Exception):raise answer
        metrics={'model_calls':1,'input_tokens':10,'output_tokens':5,'total_tokens':15,'model':'offline-only'}
        return deepcopy(answer),metrics,[{'kind':'offline_test_only'}]


def plan(*steps):return {'steps':list(steps)}
def answer(status='recommended',ids=None):
    return {'status':status,'recipe_ids':ids if ids is not None else ['recipenlg_7524'],'message':'Offline test answer.'}


class PlanReplanTests(unittest.TestCase):
    def setUp(self):
        self.request=json.loads((ROOT/'examples/example_request_expanded_pasta.json').read_text())
        self.context={'recipes':load_recipes(recipe_file=ROOT/'data/recipes_expanded.json')}
        self.good={'status':'found','error_code':None,'candidates':[{'recipe_id':'recipenlg_7524','title':'Pasta','ingredients':[],'steps':[]}]}

    def test_explicit_plan_executes_shared_tools_without_inventory_writes(self):
        before=deepcopy(self.request)
        model=ScriptedCompletion(plan('search_recipes','rank_candidates','respond'),answer())
        result=run_agent(self.request,context=self.context,complete=model)
        self.assertEqual(result['result']['recipe_ids'],['recipenlg_7524'])
        self.assertEqual(result['metrics']['model_calls'],2)
        self.assertEqual(result['metrics']['total_tokens'],30)
        self.assertEqual([x['name'] for x in result['tool_trace'] if x['kind']=='tool'],['search_recipes','rank_candidates'])
        self.assertEqual(self.request,before)

    def test_operational_failure_gets_observation_based_replan_and_one_retry(self):
        calls=[]
        def flaky(**request):
            calls.append(request)
            if len(calls)==1:raise TimeoutError('synthetic only')
            return self.good
        model=ScriptedCompletion(plan('search_recipes','respond'),plan('search_recipes','respond'),answer())
        result=run_agent(self.request,search=flaky,complete=model)
        self.assertEqual(len(calls),2);self.assertEqual(result['metrics']['replans'],1)
        observed=json.loads(model.inputs[1][1]['content'])['observation']
        self.assertEqual(observed['error_code'],'RECIPE_SEARCH_FAILED')

    def test_no_match_replans_to_respond_without_unnecessary_retry(self):
        model=ScriptedCompletion(plan('search_recipes','respond'),plan('respond'),answer('no_feasible_recipe',[]))
        result=run_agent(self.request,search=lambda **r:{'status':'no_match','candidates':[],'error_code':None},complete=model)
        self.assertEqual(result['result']['status'],'no_feasible_recipe')
        self.assertEqual(sum(x.get('name')=='search_recipes' for x in result['tool_trace']),1)

    def test_authoritative_request_update_invalidates_old_candidates(self):
        updated=deepcopy(self.request);updated['preferences']['dietary_restrictions']=['egg-free']
        model=ScriptedCompletion(plan('search_recipes','respond'),plan('search_recipes','respond'),plan('respond'),answer('no_feasible_recipe',[]))
        result=run_agent(self.request,context=self.context,request_updates=[updated],complete=model)
        self.assertEqual(result['result']['recipe_ids'],[])
        calls=[x for x in result['tool_trace'] if x.get('name')=='search_recipes']
        self.assertEqual(calls[-1]['arguments']['preferences']['dietary_restrictions'],['egg-free'])
        self.assertEqual(result['metrics']['replans'],2)

    def test_model_selection_is_kept_but_display_priority_is_canonical(self):
        candidates=[{'recipe_id':rid,'title':rid,'ingredients':[],'steps':['Mix.']} for rid in ['recipenlg_7524','B','C']]
        model=ScriptedCompletion(plan('search_recipes','respond'),answer(ids=['recipenlg_7524','C','B']))
        result=run_agent(self.request,search=lambda **r:{'status':'found','error_code':None,'candidates':candidates},complete=model)
        self.assertEqual(result['result']['recipe_ids'],['recipenlg_7524','B','C'])
        self.assertEqual(result['metrics']['model_calls'],2)
        self.assertTrue(any(r['kind']=='priority_normalization' for r in result['tool_trace']))

    def test_missing_information_returns_before_model_use(self):
        self.request['servings']=None
        result=run_agent(self.request,complete=lambda x:self.fail('Must not call a model'))
        self.assertEqual(result['result']['status'],'needs_clarification')
        self.assertEqual(result['metrics']['model_calls'],0)

    def test_unknown_source_details_are_clarification_not_tool_failure(self):
        model=ScriptedCompletion(plan('search_recipes','respond'),plan('respond'),answer('needs_clarification',[]))
        observation={'status':'error','candidates':[],'error_code':'RECIPE_DETAILS_UNVERIFIED','message':'No explicit yield.'}
        result=run_agent(self.request,search=lambda **r:observation,complete=model)
        self.assertEqual(result['result']['status'],'needs_clarification')

    def test_invalid_or_injected_action_is_rejected(self):
        for payload in [plan('delete_inventory','respond'), {'steps':[{'action':'search_recipes'},'respond']}]:
            with self.subTest(payload=payload):
                model=ScriptedCompletion(payload)
                with self.assertRaises(PlanRunError) as error:run_agent(self.request,search=lambda **r:self.fail('Must not run'),complete=model)
                self.assertEqual(error.exception.metrics['model_calls'],1)

    def test_output_contract_failure_has_one_evidence_bounded_repair(self):
        model=ScriptedCompletion(plan('search_recipes','respond'),answer(ids=['invented']),answer())
        result=run_agent(self.request,context=self.context,complete=model)
        self.assertEqual(result['result']['recipe_ids'],['recipenlg_7524'])
        self.assertEqual(result['metrics']['model_calls'],3)
        self.assertTrue(any(x['kind']=='output_validation' for x in result['tool_trace']))

    def test_failure_keeps_prior_successful_usage_and_tool_trace(self):
        error=ModelCallError('Synthetic provider error',{'model_calls':1})
        model=ScriptedCompletion(plan('search_recipes','respond'),error)
        with self.assertRaises(PlanRunError) as caught:run_agent(self.request,context=self.context,complete=model)
        self.assertEqual(caught.exception.metrics['model_calls'],2)
        self.assertIsNone(caught.exception.metrics['total_tokens'])
        self.assertTrue(any(x['kind']=='tool' for x in caught.exception.trace))

    def test_replanning_cap_does_not_fake_completion(self):
        model=ScriptedCompletion(plan('search_recipes','respond'))
        with self.assertRaises(PlanRunError):
            run_agent(self.request,search=lambda **r:{'status':'no_match','candidates':[],'error_code':None},complete=model,max_replans=0)

if __name__=='__main__':unittest.main()
