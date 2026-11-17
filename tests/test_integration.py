"""Offline integration tests. Synthetic responses are never benchmark results."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from eval import baseline
from eval import evaluate
from agent import model_client
from agent.tools.recipe_search import load_recipes


class TestIntegration(unittest.TestCase):
    def setUp(self):
        fixture=Path(__file__).resolve().parents[1]/"tests/fixtures/recipes.json"
        patcher=patch.dict(os.environ,{"FRIDGE_RECIPE_FILE":str(fixture)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_baseline_single_call_and_usage_capture(self):
        fake_response={'choices':[{'message':{'content':json.dumps({
            'status':'no_feasible_recipe','recipe_ids':[],'message':'No fixture recipe fits.'})},
            'finish_reason':'stop'}], 'model':'offline-test-model',
            'usage':{'prompt_tokens':123,'completion_tokens':45,'total_tokens':168}}
        captured=[]
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        def fake_open(request,timeout):
            captured.append(json.loads(request.data))
            return Response(json.dumps(fake_response).encode())
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'offline-test-value',
                                    'DEEPSEEK_MODEL':'offline-test-model'}), \
             patch.object(model_client,'urlopen',side_effect=fake_open):
            result=baseline.run({'pantry':[]},{'recipes':load_recipes()})
        self.assertEqual(len(captured),1)
        self.assertNotIn('tools',captured[0])
        self.assertEqual(result['metrics']['total_tokens'],168)
        self.assertEqual(result['metrics']['model_calls'],1)
        self.assertNotIn('allowed_recipe_ids',captured[0]['messages'][1]['content'])

    def test_complete_report_generation_with_synthetic_runners(self):
        root=Path(__file__).resolve().parents[1]
        # Explicit clarification case; no real LLM, no live measurements.
        task=json.loads((root/'tests/fixtures/tasks_yangyang.jsonl').read_text().splitlines()[17])
        received=[]
        def synthetic_runner(request,context):
            received.append(deepcopy(request))
            return {'answer':{'status':'needs_clarification',
                              'recipe_ids':[],'message':'Provide spinach quantity.'},
                    'metrics':{'model_calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0},
                    'trace':[{'kind':'test_only','note':'Synthetic response, not a benchmark.'}]}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);taskfile=folder/'tasks.jsonl'
            taskfile.write_text(json.dumps(task)+'\n')
            with patch.object(sys,'argv',['evaluate.py','--tasks',str(taskfile),
                 '--agent','synthetic_agent:run','--baseline','synthetic_baseline:run',
                 '--output',str(folder/'run')]), \
                 patch.dict(os.environ,{'DEEPSEEK_API_KEY':'offline-test-value','DEEPSEEK_MODEL':'test-only'}), \
                 patch.object(evaluate,'load_runner',return_value=synthetic_runner), \
                 patch('sys.stdout',new_callable=io.StringIO):
                evaluate.main()
            result=json.loads((folder/'run/summary.json').read_text())
            self.assertEqual(len(received),4)
            self.assertTrue(all('expected' not in r for r in received))
            self.assertEqual(result['agent_repeatability']['pass@3'],1)
            self.assertEqual(result['agent_repeatability']['pass^3'],1)
            self.assertTrue((folder/'run/results.md').exists())
            self.assertEqual(len((folder/'run/runs.jsonl').read_text().splitlines()),4)
            # Temporary synthetic results are deleted with TemporaryDirectory.

if __name__=='__main__':unittest.main()
