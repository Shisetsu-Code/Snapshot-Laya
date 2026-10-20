import copy
import json
from pathlib import Path
import tempfile
import unittest
from snapshot_laya.catalog import known, modal_roots
from snapshot_laya.explorer import Branches, ante_active


def control(path, role='buy_bonus'):
    return {'path': path, 'name': path.split('/')[-1], 'id': path,
            'classification': {'role': role, 'source': 'catalog', 'needs_review': False}, 'action_id': 'fresh'}


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Branches(Path(self.tmp.name)/'tree.json')
        self.tree.start('https://www.pragmaticplay.com/en/games/a/')
    def tearDown(self): self.tmp.cleanup()
    def test_four_purchases_are_four_separate_paths(self):
        self.tree.discover([], [control('Purchase/'+str(i)) for i in range(4)])
        self.assertEqual(len(self.tree.data['branches']), 4)
        first = self.tree.next()
        self.tree.discover(first['steps'], [control('Window/Yes', 'confirm'), control('Window/No', 'cancel')])
        self.assertEqual(len(self.tree.data['branches']), 6)
        self.assertEqual(len(self.tree.data['branches'][-1]['steps']), 2)
    def test_duplicate_discovery_does_not_repeat_paths(self):
        for _ in range(3): self.tree.discover([], [control('Purchase/A')])
        self.assertEqual(len(self.tree.data['branches']), 1)
    def test_unknown_never_becomes_auto_action(self):
        c = control('Unknown'); c['classification']['source'] = 'laya'
        self.tree.discover([], [c])
        self.assertFalse(self.tree.data['branches'])
        self.assertTrue(self.tree.data['unresolved'])
        self.assertFalse(self.tree.complete())
    def test_model_other_is_still_unresolved(self):
        c=control('mystery','other');c['classification']['source']='laya'
        self.tree.discover([], [c])
        self.assertTrue(self.tree.data['unresolved'])
    def test_branch_limit_is_not_completion(self):
        self.tree.data['max_branches']=1
        self.tree.discover([], [control('Buy/A'),control('Buy/B')])
        self.tree.done(self.tree.next(),{'children_discovered':2})
        self.assertFalse(self.tree.complete())
    def test_reload_does_not_retry_interrupted_purchase(self):
        self.tree.discover([], [control('Purchase/A')]); self.tree.next()
        loaded = Branches(self.tree.path)
        self.assertEqual(loaded.data['branches'][0]['status'], 'interrupted')
        self.assertFalse(loaded.complete())
    def test_ante_activation_without_rounds_is_incomplete(self):
        self.tree.discover([], [control('Ante', 'ante_bet')]); branch=self.tree.next()
        with self.assertRaisesRegex(ValueError, 'tiradas'):
            self.tree.done(branch, {'activated': True, 'rounds': []})
    def test_ante_requires_active_protocol_complete_for_every_round(self):
        self.tree.discover([], [control('Ante', 'ante_bet')]); branch=self.tree.next()
        good={'started':True,'protocol_complete':True,'ante_before':1,'ante_after':1,'normal':True}
        with self.assertRaises(ValueError): self.tree.done(branch, {'activated':True,'rounds':[good,dict(good, ante_after=0)]})
        self.tree.done(branch, {'activated':True,'rounds':[good,copy.deepcopy(good)]})
        self.assertTrue(self.tree.complete())
    def test_ante_requires_evidence_not_generic_change(self):
        self.assertFalse(ante_active({'wager':{'betLevelIndex':0}}))
        self.assertTrue(ante_active({'wager':{'betLevelIndex':1}}))
        self.assertFalse(ante_active({'wager':{}}))
    def test_catalog_confirmation_overrides_inherited_buy_text(self):
        c={'name':'ButtonNo','path':'Game/FSPurchaseWindow_RS/ButtonNo','labels':['BUY FREE SPINS']}
        self.assertEqual(known(c)['role'],'cancel')
        c['name']='ButtonYes'; self.assertEqual(known(c)['role'],'confirm')
    def test_gates_nested_buy_button(self):
        c={'name':'Button','path':'Game/BuyFeature/PurchaseManager/BuyButtons/AT/Option_0/ButtonT/ButtonC/AT/Button','labels':['BUY FREE SPINS']}
        self.assertEqual(known(c)['role'],'buy_bonus')
    def test_modal_detected_even_without_busy_flag(self):
        c={'name':'ButtonYes','path':'Game/FSPurchaseWindow_RS/Buttons/ButtonYes','enabled':True,'clickable':'RUNTIME_COLLIDER'}
        self.assertEqual(modal_roots([c]),['Game/FSPurchaseWindow_RS/'])
    def test_blocker_is_not_continue(self):
        self.assertIsNone(known({'name':'Blocker','path':'Game/Bonus/Result/Blocker','labels':['Click anywhere to continue']}))
    def test_explicit_anywhere_area_is_continue(self):
        self.assertEqual(known({'name':'ContinueArea','path':'Game/Bonus/Intro/ContinueArea','labels':['Tap anywhere to continue']})['role'],'continue')
    def test_plain_bet_levels_are_not_ante(self):
        self.assertIsNone(known({'name':'Level_0','path':'Game/BetLevel/Level_0','labels':['BET $2']}))
    def test_stop_spin_and_child_collider_are_ignored(self):
        for name,path in [('StopSpin_Button','GUI/SpinButtons/StopSpin_Button'),('Collider','GUI/SpinButtons/StopSpin_Button/Collider')]:
            self.assertEqual(known({'name':name,'path':path,'labels':[]})['role'],'other')

if __name__ == '__main__': unittest.main()
