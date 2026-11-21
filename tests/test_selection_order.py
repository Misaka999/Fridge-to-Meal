"""Fix the observed RN09 order error without changing task answers or ID sets."""
import unittest
from agent.selection_order import normalize_selection_order
from agent.plan_replan import validate_answer


class SelectionOrderTests(unittest.TestCase):
    def test_valid_selection_set_is_sorted_to_shared_priority(self):
        observation={'status':'found','error_code':None,'candidates':[{'recipe_id':x} for x in ['A','B','C']]}
        original={'status':'recommended','recipe_ids':['A','C','B'],'message':'Selection.'}
        fixed,record=normalize_selection_order(original,observation)
        self.assertEqual(fixed['recipe_ids'],['A','B','C'])
        self.assertEqual(set(fixed['recipe_ids']),set(original['recipe_ids']))
        self.assertEqual(original['recipe_ids'],['A','C','B'])
        self.assertEqual(validate_answer(fixed,observation),fixed)
        self.assertEqual(record['kind'],'priority_normalization')
    def test_unknown_duplicate_or_missing_priority_ids_are_not_invented_away(self):
        observation={'status':'found','error_code':None,'candidates':[{'recipe_id':x} for x in ['A','B','C']]}
        for ids in [['A','unknown'],['A','A'],['C','B']]:
            answer={'status':'recommended','recipe_ids':ids,'message':'Selection.'}
            fixed,_=normalize_selection_order(answer,observation)
            self.assertEqual(set(fixed['recipe_ids']),set(ids))
            with self.assertRaises(ValueError):validate_answer(fixed,observation)

if __name__=='__main__':unittest.main()
