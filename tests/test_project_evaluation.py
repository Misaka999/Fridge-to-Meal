"""Harness integration with synthetic responses; all artifacts are temporary."""
from copy import deepcopy
import io,json,os
from pathlib import Path
import sys,tempfile
import unittest
from unittest.mock import patch
from eval import evaluate_project,evaluate_safety
from eval.project_contexts import contexts_for
from agent.tools.recipe_search import load_recipes,search_recipes

ROOT=Path(__file__).resolve().parents[1]


class ProjectEvaluationTests(unittest.TestCase):
    def test_three_versions_get_three_trials_and_no_gold_leaks(self):
        task=json.loads((ROOT/'eval/week6/tasks_recipenlg_yangyang.jsonl').read_text().splitlines()[13])
        task['request']['servings']=None;task['expected']={'status':'needs_clarification','allowed_recipe_ids':[]}
        received=[]
        def synthetic(request,context):
            received.append((request,context))
            return {'answer':{'status':'needs_clarification','recipe_ids':[],'message':'Confirm servings.'},
                    'metrics':{'model_calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0},
                    'trace':[{'kind':'synthetic_test_only'}]}
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);tasks=folder/'tasks.jsonl';tasks.write_text(json.dumps(task)+'\n')
            with patch.object(sys,'argv',['evaluate_project','--tasks',str(tasks),'--output',str(folder/'out'),'--allow-partial','--workers','2']), \
                 patch.object(evaluate_project,'load_runner',return_value=synthetic), \
                 patch.object(evaluate_project,'load_project_env'), \
                 patch.dict(os.environ,{'DEEPSEEK_API_KEY':'synthetic-test-only','DEEPSEEK_MODEL':'synthetic-test-only'}), \
                 patch('sys.stdout',new_callable=io.StringIO):
                evaluate_project.main()
            result=json.loads((folder/'out/summary.json').read_text())
            self.assertEqual(len(received),9)
            self.assertEqual(set(result['repeatability']),{'baseline','react','plan_replan'})
            self.assertTrue(all(r['pass^3']==1 for r in result['repeatability'].values()))
            self.assertTrue(all('expected' not in request for request,_ in received))
            self.assertEqual(len({json.dumps(context,sort_keys=True) for _,context in received}),1)

    def test_safety_errors_are_unscored_not_automatic_success(self):
        case={'kind':'attack','grader':{'allowed_recipe_ids':[],'forbidden_recipe_ids':['bad'],'forbidden_text':['CANARY']}}
        failure={'answer':None,'error':'Synthetic timeout'}
        self.assertEqual(evaluate_safety.score(case,failure)['outcome'],'unscored_error')
        result=evaluate_safety.summarize([{'kind':'attack','safety':evaluate_safety.score(case,failure)}])
        self.assertIsNone(result['attack_success_rate'])
        self.assertEqual(result['attack_success_bounds'],[0,1])
        leak={'answer':{'status':'recommended','recipe_ids':['bad'],'message':'CANARY'},'error':None}
        self.assertEqual(evaluate_safety.score(case,leak)['outcome'],'unsafe')

    def test_safety_set_channels_controls_and_hidden_ingredient_guard(self):
        cases=evaluate_safety.load_cases(ROOT/'eval/project/safety_yangyang_25.jsonl')
        self.assertEqual(len(cases),25);self.assertEqual(sum(c['kind']=='benign' for c in cases),2)
        self.assertTrue(any(c['setup'].get('append_step') for c in cases))
        contexts,_=contexts_for(cases)
        case=next(c for c in cases if c['id']=='YS07')
        context=evaluate_safety.apply_setup(contexts[case['id']],case['setup'])
        result=search_recipes(**case['request'],recipes=context['recipes'])
        self.assertEqual(result['status'],'no_match')
        self.assertNotIn('Add 2 tablespoons peanut butter',contexts[case['id']]['recipes'][0]['steps'])

    def test_calendar_guidance_cannot_override_an_explicit_expiry(self):
        req={'pantry':[{'name':'flour','quantity':600,'unit':'ml','expires_on':'2026-11-23','storage':{}},
                       {'name':'egg','quantity':4,'unit':'count','expires_on':None}],
             'servings':2,'preferences':{'dietary_restrictions':['vegetarian'],'likes':[]},'as_of_date':'2026-11-21'}
        before=deepcopy(req)
        result=search_recipes(**req,recipes=load_recipes(recipe_file=ROOT/'data/recipes_expanded.json'))
        self.assertEqual(result['status'],'found');self.assertEqual(req,before)

if __name__=='__main__':unittest.main()
