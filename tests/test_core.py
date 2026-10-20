import copy
import json
from pathlib import Path
import unittest
from snapshot_laya.core import clean_snapshot, completion, evidence_effect

FIXTURE=Path(__file__).parent/'fixtures/sweet-bonanza.json'

class SnapshotTests(unittest.TestCase):
    def setUp(self): self.raw=json.loads(FIXTURE.read_text())
    def test_keeps_buy_ante_and_both_bet_buttons(self):
        result=clean_snapshot(self.raw)
        names={c['name'] for c in result['controls']}
        self.assertTrue({'OptionButton','Level0Button','BetUp_Button','BetDown_Button'} <= names)
        self.assertNotIn('SoundOff',names)
        self.assertNotIn('AutoplayOpenButton',names)
    def test_excludes_disabled_offscreen_and_missing_hit(self):
        control=copy.deepcopy(self.raw['controls'][0])
        control['enabled']=False
        other=copy.deepcopy(self.raw['controls'][1])
        other['hit_rect']['x']=99999
        self.raw['controls']=[control,other,{'id':'bad','enabled':True}]
        self.assertFalse(clean_snapshot(self.raw)['controls'])
    def test_deduplicates_same_hit_preserving_identity(self):
        self.raw['controls'].append(copy.deepcopy(self.raw['controls'][4]))
        result=clean_snapshot(self.raw)
        self.assertEqual(sum(c['name']=='OptionButton' for c in result['controls']),1)
    def test_dom_overlay_prevents_actionable_snapshot(self):
        result=clean_snapshot(self.raw,blockers=['age_gate'])
        self.assertFalse(result['controls'])
        self.assertIn('age_gate',result['blockers'])
    def test_metadata_does_not_claim_occlusion(self):
        result=clean_snapshot(self.raw)
        self.assertFalse(result['occlusion_verified'])
        self.assertNotIn('crop_path',result['controls'][0]['model_input'])
    def test_modal_excludes_base_controls_behind_it(self):
        self.raw['modal_roots']=['GameRoot/UI Root/Popup/']
        popup=copy.deepcopy(self.raw['controls'][4])
        popup.update(path='GameRoot/UI Root/Popup/ButtonYes',name='ButtonYes',id='yes')
        self.raw['controls'].append(popup)
        result=clean_snapshot(self.raw)
        self.assertEqual([c['name'] for c in result['controls']],['ButtonYes'])
    def test_geometry_change_invalidates_visual_review(self):
        old=clean_snapshot(self.raw)['id']
        self.raw['controls'][4]['hit_rect']['x']+=20
        self.assertNotEqual(old,clean_snapshot(self.raw)['id'])

class ValidationTests(unittest.TestCase):
    def test_empty_or_classified_is_not_validation(self):
        self.assertFalse(completion([],{},[],0)['validated'])
        self.assertFalse(completion([{'status':'pending'}],{},[],1)['validated'])
    def test_pending_bonus_prevents_validation(self):
        self.assertFalse(completion([{'status':'verified'}],{'logicIsFreeSpin':True},[],1)['validated'])
    def test_unresolved_prevents_validation(self):
        self.assertFalse(completion([{'status':'verified'}],{},['opaque'],1)['validated'])
    def test_purchase_needs_completed_protocol(self):
        controls=[{'status':'verified','role':'buy_bonus'}]
        self.assertFalse(completion(controls,{},[],1,purchase_complete=False)['validated'])
        result=completion(controls,{},[],1,purchase_complete=True)
        self.assertTrue(result['validated'])
        self.assertEqual(result['scope'],'observed_controls_and_visited_states')
    def test_ante_needs_actual_wager_change(self):
        before={'wager':{'betLevelIndex':0}}
        after={'wager':{'betLevelIndex':1}}
        self.assertTrue(evidence_effect('ante_bet',before,after,{}))
        self.assertFalse(evidence_effect('ante_bet',before,before,{'reason':'CLICKED'}))
    def test_operation_start_is_evidence_for_bonus_actions(self):
        for role in ('buy_bonus','confirm','continue','choice'):
            self.assertTrue(evidence_effect(role,{}, {},{'operationStarted':True,'reason':'OPERATION_STARTED'}))
    def test_confirm_is_not_verified_by_navigation_alone(self):
        self.assertFalse(evidence_effect('confirm',{'state_key':'a'},{'state_key':'b'},{'reason':'STATE_CHANGED'}))

if __name__=='__main__': unittest.main()
