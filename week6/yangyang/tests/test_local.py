import json
import os
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools
from tools import check_recipe,load_recipes,prioritize_recipes,search_recipes,validate_request,make_tool_registry
from grading import grade
from evaluate import load_tasks,reliability,run_one
ROOT=Path(__file__).resolve().parents[1]
TASKS=load_tasks(ROOT/'tasks_yangyang.jsonl')


def search(request,recipes=None):
    return search_recipes(**{k:request[k] for k in ('pantry','servings','preferences','as_of_date')},recipes=recipes)


class TestLocal(unittest.TestCase):
    def setUp(self):
        fixture=Path(__file__).resolve().parents[1]/"data/recipes.json"
        patcher=patch.dict(os.environ,{"FRIDGE_RECIPE_FILE":str(fixture)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_manual_references_against_tools(self):
        for task in TASKS:
            with self.subTest(task=task['id']):
                req,expected=task['request'],task['expected']
                issue=validate_request(req)
                if expected['status']=='needs_clarification':
                    if issue:
                        self.assertEqual(issue['status'],'needs_clarification')
                    else:
                        self.assertEqual(search(req)['error_code'],'INPUT_INCOMPLETE')
                    continue
                self.assertIsNone(issue)
                result=search(req)
                actual={r['recipe_id'] for r in result['candidates']}
                self.assertEqual(actual,set(expected['allowed_recipe_ids']))
                self.assertEqual(result['status'],'found' if actual else 'no_match')
                if expected.get('top_recipe_ids'):
                    self.assertIn(prioritize_recipes(req,list(actual))[0],expected['top_recipe_ids'])

    def test_exact_interface_example(self):
        req=json.loads((ROOT/'data/example_request.json').read_text())
        result=search(req)
        self.assertEqual(result['status'],'found')
        self.assertIsNone(result['error_code'])
        r=result['candidates'][0]
        self.assertEqual(r['recipe_id'],'r_spinach_tofu_01')
        self.assertEqual([x['quantity'] for x in r['ingredients']],[150,250,15])
        req['servings']=1
        self.assertEqual([x['quantity'] for x in search(req)['candidates'][0]['ingredients']],[75,125,7.5])

    def test_null_fields_clarify_not_no_match(self):
        req=deepcopy(TASKS[1]['request']);req['servings']=None
        self.assertEqual(validate_request(req)['status'],'needs_clarification')
        result=search(req)
        self.assertEqual(result['error_code'],'INPUT_INCOMPLETE')
        self.assertNotEqual(result['status'],'no_match')

    def test_exception_is_tool_failure_not_no_match(self):
        with patch.object(tools,'load_recipes',side_effect=OSError('fixture read failure')):
            result=search(TASKS[1]['request'])
        self.assertEqual(result,{'status':'error','candidates':[],'error_code':'RECIPE_SEARCH_FAILED'})

    def test_grader_rejects_invalid_ids_duplicates_and_wrong_status(self):
        e=TASKS[0]['expected']
        good={'status':'recommended','recipe_ids':['R01'],'message':'Recipe with amounts and steps.'}
        self.assertTrue(grade(good,e)['passed'])
        for ids in [['R01','R01'],['unknown'],[]]:
            self.assertFalse(grade({**good,'recipe_ids':ids},e)['passed'])
        self.assertFalse(grade({**good,'status':'needs_clarification'},e)['passed'])

    def test_state_isolation_and_inventory_cannot_be_invented(self):
        request=deepcopy(TASKS[1]['request']);before=deepcopy(request)
        funcs,_=make_tool_registry(request,{'recipes':load_recipes()})
        supplied={k:deepcopy(request[k]) for k in ('pantry','servings','preferences','as_of_date')}
        self.assertEqual(funcs['search_recipes'](**supplied)['status'],'found')
        supplied['pantry'][0]['quantity']=9999
        self.assertEqual(funcs['search_recipes'](**supplied)['error_code'],'REQUEST_STATE_MISMATCH')
        self.assertEqual(request,before)

    def test_reliability(self):
        tasks=[{'id':'A'},{'id':'B'},{'id':'C'}]
        rows=[{'task_id':key,'passed':x} for key,vals in
              [('A',[True,False,True]),('B',[True]*3),('C',[False]*3)] for x in vals]
        result=reliability(rows,tasks,3)
        self.assertAlmostEqual(result['pass@3'],2/3)
        self.assertAlmostEqual(result['pass^3'],1/3)
        self.assertEqual(result['flipping_tasks'],['A'])

    def test_runner_inputs_are_copied(self):
        def changes(request,context):
            request['pantry'].clear();context['recipes'].clear()
            return {'answer':{},'metrics':{},'trace':[]}
        request=deepcopy(TASKS[0]['request']);context={'recipes':load_recipes()}
        run_one(changes,request,context)
        self.assertTrue(request['pantry']);self.assertTrue(context['recipes'])

if __name__=='__main__':unittest.main()
