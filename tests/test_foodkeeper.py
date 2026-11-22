"""Pinned-source tests; never substitute freezer guidance for refrigerated food."""
from copy import deepcopy
import unittest
from agent.tools.foodkeeper import load_products,lookup_storage,inspect_pantry_storage,_add
from datetime import date


class FoodKeeperTests(unittest.TestCase):
    def test_snapshot_has_provenance_and_complete_product_list(self):
        products,source=load_products();self.assertEqual(len(products),661)
        self.assertIn('403',source['official_fetch_status']);self.assertEqual(len(source['sha256']),64)
    def test_ambiguous_eggs_do_not_select_eggplant_or_a_preparation(self):
        result=lookup_storage('egg');self.assertEqual(result['status'],'needs_clarification')
        self.assertGreater(len(result['candidates']),1)
        self.assertTrue(all(x['name']=='Eggs' for x in result['candidates']))
    def test_exact_product_dates_preserve_condition_and_source(self):
        r=lookup_storage('eggs',product_id='21',condition='refrigerator',stage='purchase',reference_date='2026-11-01',as_of_date='2026-11-21',stored_as_directed=True)
        self.assertEqual(r['guidance_text'],'3 - 5 Weeks')
        self.assertEqual(r['guidance_window']['start'],'2026-11-22')
        self.assertEqual(r['guidance_window']['end'],'2026-12-06')
        self.assertNotIn('expires_on',r)
    def test_no_reference_date_or_condition_means_no_computed_date(self):
        for r in [lookup_storage('tofu'),lookup_storage('eggs',product_id='21',condition='refrigerator',stage='purchase')]:
            self.assertEqual(r['status'],'needs_clarification');self.assertNotIn('guidance_window',r)
    def test_other_storage_guidance_is_never_used_as_fallback(self):
        r=lookup_storage('eggs',product_id='21',condition='refrigerator',stage='opened',reference_date='2026-11-01',as_of_date='2026-11-21',stored_as_directed=True)
        self.assertEqual(r['status'],'not_available');self.assertNotIn('guidance_window',r)
    def test_unconfirmed_conditions_and_invalid_dates_ask(self):
        for kwargs in [{'stored_as_directed':False},{'reference_date':'2026-12-01'},{'reference_date':'wrong'}]:
            fields=dict(product_id='21',condition='refrigerator',stage='purchase',reference_date='2026-11-01',as_of_date='2026-11-21',stored_as_directed=True);fields.update(kwargs)
            self.assertEqual(lookup_storage('eggs',**fields)['status'],'needs_clarification')
    def test_product_id_cannot_apply_egg_guidance_to_carrots(self):
        r=lookup_storage('carrots',product_id='21',condition='refrigerator',stage='purchase')
        self.assertEqual(r['status'],'needs_clarification')
    def test_calendar_months_are_not_assumed_to_be_thirty_days(self):
        self.assertEqual(_add(date(2026,1,31),1,'months'),date(2026,2,28))
    def test_pantry_inspection_never_writes_an_expiration(self):
        request={'pantry':[{'name':'eggs','expires_on':None,'storage':{'product_id':'21','condition':'refrigerator','stage':'purchase','reference_date':'2026-11-01','stored_as_directed':True}}],'as_of_date':'2026-11-21'}
        before=deepcopy(request);result=inspect_pantry_storage(request)
        self.assertFalse(result['inventory_changed']);self.assertEqual(request,before)

if __name__=='__main__':unittest.main()
