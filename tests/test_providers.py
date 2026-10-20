import unittest
from snapshot_laya.providers import playtech_catalog_state,PLAYTECH_CATALOG,playtech_demo_url,playtech_catalog


class ProviderTests(unittest.TestCase):
    def test_cookies_offer_only_fresh_visible_enabled_reject(self):
        e={'name':'REJECT ALL','ref':'cookie-current','visible':True,'enabled':True}
        self.assertEqual(playtech_catalog_state(PLAYTECH_CATALOG,[e])['cookie_action']['ref'],'cookie-current')
        self.assertIsNone(playtech_catalog_state(PLAYTECH_CATALOG,[dict(e,visible=False)])['cookie_action'])
    def test_login_is_blocker_not_no_purchases(self):
        state=playtech_catalog_state(PLAYTECH_CATALOG,[{'name':n,'visible':True} for n in ('Username','Password','Log in')])
        self.assertEqual(state['status'],'login_required')
        self.assertFalse(state['purchase_search_ready'])
    def test_unrelated_site_cannot_use_provider_profile(self):
        with self.assertRaises(ValueError):playtech_catalog_state('https://example.com/',[])
    def test_direct_demo_uses_offline_and_fake_money_without_catalog_login(self):
        self.assertEqual(playtech_demo_url('gpas_olwilds_pop'),'https://cachedownload.playtechone.com/ngmdesktop/casinoclient.html?game=gpas_olwilds_pop&preferedmode=offline&real=0')
        with self.assertRaises(ValueError):playtech_demo_url('game&real=1')
    def test_bundled_catalog_is_slots_only_and_does_not_claim_runtime_support(self):
        catalog=playtech_catalog()
        self.assertGreater(len(catalog['games']),500)
        self.assertTrue(all(g['game_kind']=='slot' and g['demo_url'].endswith('real=0') for g in catalog['games']))
        self.assertFalse(catalog['runtime_adapter_ready'])
