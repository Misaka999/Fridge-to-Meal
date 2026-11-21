"""Independent declared references for Yangyang's 100-case partition."""
import json
from pathlib import Path
import unittest
from agent.tools.recipe_search import validate_request,search_recipes
from eval.project_contexts import contexts_for

ROOT=Path(__file__).resolve().parents[1]


class ProjectTaskTests(unittest.TestCase):
    def test_reference_cases_use_correct_shared_catalogues(self):
        tasks=[json.loads(s) for s in (ROOT/'eval/project/tasks_yangyang_100.jsonl').read_text().splitlines()]
        self.assertEqual(len(tasks),100);self.assertEqual(len({t['id'] for t in tasks}),100)
        fingerprints=[(json.dumps(t['request'],sort_keys=True),t['catalogue_scope']) for t in tasks]
        self.assertEqual(len(set(fingerprints)),100)
        contexts,_=contexts_for(tasks)
        self.assertEqual(len(contexts['RN01']['recipes']),3)
        self.assertEqual(len(contexts['YN001']['recipes']),20)
        for task in tasks:
            with self.subTest(id=task['id']):
                request=task['request'];expected=task['expected'];issue=validate_request(request)
                if issue:self.assertEqual(expected['status'],'needs_clarification');continue
                result=search_recipes(**request,recipes=contexts[task['id']]['recipes'])
                if expected['status']=='needs_clarification':
                    self.assertEqual(result.get('error_code'),'INPUT_INCOMPLETE')
                else:
                    actual={r['recipe_id'] for r in result['candidates']}
                    self.assertEqual(actual,set(expected['allowed_recipe_ids']))
                    self.assertEqual(result['status'],'found' if actual else 'no_match')

if __name__=='__main__':unittest.main()
