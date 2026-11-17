"""Synthetic import fixtures only; these tests are not downloaded RecipeNLG data."""
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.import_recipenlg import import_csv
from scripts.compile_recipenlg import compile_records
from agent.tools.recipe_search import RESTRICTIONS,load_recipes,search_recipes


class TestRecipeNLGIntegration(unittest.TestCase):
    def make_queue(self,folder):
        csvfile=folder/'synthetic.csv'
        with csvfile.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['id','title','ingredients','directions','link','source','NER'])
            writer.writeheader()
            writer.writerow({'id':'1','title':'Synthetic tofu fixture','ingredients':"['250 g tofu']",
                'directions':"['Heat the tofu.']",'link':'https://example.org/synthetic-test-only',
                'source':'Gathered','NER':"['tofu']"})
            writer.writerow({'id':'2','title':'Excluded synthetic fixture','ingredients':"['1 egg']",
                'directions':"['Cook.']",'link':'https://example.org/synthetic-test-only',
                'source':'Recipes1M','NER':"['egg']"})
        queue=folder/'queue.jsonl'
        stats=import_csv(csvfile,queue)
        return queue,stats

    def test_gathered_only_no_invented_servings(self):
        with tempfile.TemporaryDirectory() as d:
            queue,stats=self.make_queue(Path(d))
            self.assertEqual(stats['selected_gathered'],1)
            row=json.loads(queue.read_text())
            self.assertEqual(row['id'],'recipenlg_1')
            self.assertIsNone(row['servings'])
            self.assertEqual(row['review_status'],'pending')

    def test_pending_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);queue,_=self.make_queue(folder)
            with self.assertRaises(ValueError):compile_records(queue,folder/'release.json')
            self.assertFalse((folder/'release.json').exists())

    def test_reviewed_release_uses_existing_search_interface(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);queue,_=self.make_queue(folder)
            row=json.loads(queue.read_text())
            row.update(review_status='approved',servings=1,servings_source='Explicit synthetic test serving.',
                       dietary_compatibility={k:k!='soy-free' for k in RESTRICTIONS})
            row['ingredients']=[{'name':'tofu','quantity':250,'unit':'g','raw_indices':[0],
                                 'quantity_basis':'250 g explicitly in synthetic ingredient text.'}]
            queue.write_text(json.dumps(row)+'\n')
            out=folder/'release.json';compile_records(queue,out)
            with patch.dict(os.environ,{'FRIDGE_RECIPE_FILE':str(out)}):
                self.assertEqual(load_recipes()[0]['id'],'recipenlg_1')
                result=search_recipes([{'name':'tofu','quantity':300,'unit':'g','expires_on':None}],1,
                                      {'dietary_restrictions':['vegan'],'likes':[]},'2026-11-16')
                self.assertEqual(result['status'],'found')
                self.assertEqual(result['candidates'][0]['recipe_id'],'recipenlg_1')
                blocked=search_recipes([{'name':'tofu','quantity':300,'unit':'g'}],1,
                                      {'dietary_restrictions':['soy-free'],'likes':[]},'2026-11-16')
                self.assertEqual(blocked['status'],'no_match')

if __name__=='__main__':unittest.main()
