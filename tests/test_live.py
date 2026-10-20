import copy
import json
from pathlib import Path
import tempfile
import unittest
from snapshot_laya.live import Live
from snapshot_laya.mcp import decode_rpc
from snapshot_laya.core import valid_demo_url

RAW=json.loads((Path(__file__).parent/'fixtures/sweet-bonanza.json').read_text())

class FakeSource:
    def __init__(self): self.calls=[];self.close_fail=False
    def call(self,name,args):
        self.calls.append(name)
        if name=='pragmatic_guided_start': return {'job_id':'owned','tab_id':12,'actions':[],'flags':{},'state_key':'one'}
        if name=='pragmatic_guided_observe': return {'job_id':'owned','tab_id':12,'actions':[],'flags':{},'state_key':'one','token':'fresh'}
        if name=='hardfire_find': return {'elements':[]}
        if name=='pragmatic_drawn_buttons': return copy.deepcopy(RAW)
        if name=='pragmatic_guided_close':
            if self.close_fail: raise RuntimeError('close failed')
            return {'status':getattr(self,'close_status','CLOSED')}
        raise AssertionError('unexpected side effect: '+name)

class FakeModel:
    def classify(self,c): return {'role':'unknown','confidence':.2,'needs_review':True,'milliseconds':0}

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.source=FakeSource()
        self.live=Live(self.source,FakeModel(),self.tmp.name)
        self.live.enqueue(['https://www.pragmaticplay.com/en/games/sweet-bonanza-slot/'])
    def tearDown(self): self.tmp.cleanup()
    def test_classification_does_not_validate(self): self.assertFalse(self.live.validation()['validated'])
    def test_no_target_capture_is_copied_and_included_in_report(self):
        image=Path(self.tmp.name)/'original.jpg';image.write_bytes(b'saved screenshot')
        self.live.images['testimage']=image
        self.live.session['snapshot']['image_url']='/api/images/testimage'
        capture=self.live.capture_evidence('no_target_controls_detected')
        image.unlink()
        self.assertEqual(Path(capture['path']).read_bytes(),b'saved screenshot')
        report=self.live.finish(True,advance=False)
        self.assertEqual(report['captures'],[capture])
    def test_common_interface_is_not_model_input_or_branch(self):
        class RejectModel:
            def classify(self,c):raise AssertionError('Known common interface reached model: '+c['path'])
        live=Live(self.source,RejectModel(),self.tmp.name)
        live.enqueue(['https://www.pragmaticplay.com/en/games/demo/'])
        self.assertEqual({c['name'] for c in live.session['snapshot']['controls']},{'OptionButton','Level0Button'})
        self.assertEqual([c['name'] for c in live.session['snapshot']['support_controls']],['StartSpin_Button'])
        self.assertEqual(len(live.session['snapshot']['ignored_controls']),2)
    def test_novel_drawn_button_executes_without_catalog_or_model_certainty(self):
        c=copy.deepcopy(RAW['controls'][4]);c.update(name='ButtonOpt0',path='GameRoot/Game/FeaturePurchase/FSPurchaseWindow/Buttons/ButtonOpt0',labels=[],fingerprint='novel')
        original=self.source.call; clicks=[]
        def call(name,args):
            if name=='pragmatic_drawn_buttons':return dict(copy.deepcopy(RAW),controls=[copy.deepcopy(c)])
            if name=='pragmatic_guided_observe':return {'token':'fresh-novel','state_key':'one','flags':{},'actions':[{'fingerprint':'novel','action_id':'b0'}],'wager':{'betLevelIndex':0}}
            if name=='pragmatic_guided_act':
                clicks.append(args)
                self.assertEqual(args['token'],'fresh-novel')
                return {'outcome':{'reason':'OPERATION_STARTED','operationStarted':True},'view':{'state_key':'two','flags':{},'wager':{'betLevelIndex':0},'operation':{'submitted':True,'protocolComplete':False}}}
            return original(name,args)
        self.source.call=call
        self.live.observe()
        target=self.live.session['snapshot']['controls'][0]
        self.assertTrue(target['classification']['needs_review'])
        self.assertEqual(target['decision']['role'],'probe')
        result=self.live.act(self.live.session['snapshot']['id'],target['id'],automatic=True)
        self.assertTrue(result['effect_verified'])
        self.assertEqual(len(clicks),1)
        self.assertTrue(self.live.session['purchase_started'])
        self.assertFalse(self.live.validation()['validated'])
    def test_age_notice_behind_fullscreen_is_isolated_but_inside_notice_blocks(self):
        original=self.source.call
        age={'visible':True,'name':'Yes, I am 18 years or older','ref':'age','frame_id':'top','role':'link'}
        inside=[False]
        def call(name,args):
            if name=='hardfire_find':
                css=args['css']
                if css=='.game-fullscreen.fullscreen[data-fullscreen]':
                    return {'elements':[{'frame_id':'top','rect':{'x':0,'y':0,**RAW['image_size']}}]}
                if css=='.game-fullscreen.fullscreen [data-age-check-confirm]':return {'elements':[age] if inside[0] else []}
                return {'elements':[age]}
            return original(name,args)
        self.source.call=call
        self.live._scan({'flags':{'canSpin':True},'state_key':'fullscreen','actions':[]})
        self.assertFalse(self.live.session['snapshot']['blockers'])
        self.assertTrue(self.live.session['snapshot']['controls'])
        self.assertTrue(self.live.session['snapshot']['ignored_page_controls'])
        inside[0]=True
        self.live._scan({'flags':{'canSpin':True},'state_key':'fullscreen','actions':[]})
        self.assertTrue(self.live.session['snapshot']['blockers'])
        self.assertFalse(self.live.session['snapshot']['controls'])
    def test_hidden_popup_does_not_replace_visible_modal(self):
        original=self.source.call
        def call(name,args):
            result=original(name,args)
            if name=='pragmatic_drawn_buttons':
                visible=copy.deepcopy(RAW['controls'][4])
                visible.update(name='ButtonYes',path='GameRoot/ActiveWindow/ButtonYes')
                hidden=copy.deepcopy(visible)
                hidden.update(enabled=False,path='GameRoot/VeryLongHiddenWindow/AnotherHiddenWindow/ButtonYes')
                result['controls'] += [visible,hidden]
            return result
        self.source.call=call
        self.live._scan({'flags':{'spinBlockingFeatureIsRunning':True},'actions':[],'state_key':'modal'})
        self.assertEqual([c['path'] for c in self.live.session['snapshot']['controls']],['GameRoot/ActiveWindow/ButtonYes'])
    def test_stale_action_does_not_click(self):
        before=len(self.source.calls)
        with self.assertRaisesRegex(ValueError,'vencido'): self.live.act('stale','id',True)
        self.assertEqual(len(self.source.calls),before)
    def test_normal_spin_maps_explicit_guided_action_without_fingerprint(self):
        self.live._scan({'actions':[{'kind':'spin','action_id':'spin_normal'}],'flags':{},'state_key':'one'})
        spin=next(c for c in self.live.session['snapshot']['support_controls'] if c['name']=='StartSpin_Button')
        self.assertEqual(spin['action_id'],'spin_normal')
    def test_auto_spin_is_blocked_when_ante_is_off(self):
        view={'actions':[{'kind':'spin','action_id':'spin_normal'}],'flags':{'canSpin':True},'wager':{'betLevelIndex':0},'state_key':'one','token':'fresh'}
        original=self.source.call
        self.source.call=lambda name,args: copy.deepcopy(view) if name=='pragmatic_guided_observe' else original(name,args)
        self.live._scan(copy.deepcopy(view))
        spin=next(c for c in self.live.session['snapshot']['support_controls'] if c['name']=='StartSpin_Button')
        with self.assertRaisesRegex(ValueError,'ante bet activo'):
            self.live.act(self.live.session['snapshot']['id'],spin['id'],automatic=True)
        self.assertNotIn('pragmatic_guided_act',self.source.calls)
    def test_auto_unknown_is_blocked(self):
        c=self.live.session['snapshot']['controls'][0]
        c['classification']['source']='laya'
        with self.assertRaisesRegex(ValueError,'acción guiada'):
            self.live.act(self.live.session['snapshot']['id'],c['id'],automatic=True)
    def test_auto_resolves_pulsing_geometry_with_fresh_guided_token(self):
        c=next(c for c in self.live.session['snapshot']['controls'] if c['name']=='Level0Button')
        old_rect=copy.deepcopy(c['hit_rect'])
        original=self.source.call
        def call(name,args):
            if name=='pragmatic_guided_observe':
                return {'token':'fresh-animation','state_key':'one','flags':{},'wager':{'betLevelIndex':0},
                        'actions':[{'fingerprint':c['fingerprint'],'action_id':'ante'}]}
            if name=='pragmatic_drawn_buttons':
                result=original(name,args)
                target=next(x for x in result['controls'] if x['name']=='Level0Button')
                target['hit_rect']['x']+=9
                return result
            if name=='pragmatic_guided_act':
                self.assertEqual(args['token'],'fresh-animation')
                after=call('pragmatic_guided_observe',{});after['wager']['betLevelIndex']=1
                return {'outcome':{'operationStarted':False,'reason':'STATE_CHANGED'},'view':after}
            return original(name,args)
        self.source.call=call
        self.live.session['snapshot']['controls'][self.live.session['snapshot']['controls'].index(c)]['action_id']='ante'
        result=self.live.act(self.live.session['snapshot']['id'],c['id'],automatic=True)
        self.assertTrue(result['effect_verified'])
        self.assertEqual(self.live.session['events'][-1]['executed_hit_rect']['x'],old_rect['x']+9)
    def test_action_requires_visual_review(self):
        with self.assertRaisesRegex(ValueError,'captura'): self.live.act(self.live.session['snapshot']['id'],'id')
        self.assertNotIn('pragmatic_guided_act',self.source.calls)
    def test_validated_finish_rejects_pending(self):
        with self.assertRaisesRegex(ValueError,'No validado'): self.live.finish()
        self.assertNotIn('pragmatic_guided_close',self.source.calls)
    def test_close_failure_keeps_ownership(self):
        self.source.close_fail=True
        with self.assertRaisesRegex(RuntimeError,'close failed'): self.live.finish(True)
        self.assertEqual(self.live.session['job_id'],'owned')
    def test_unconfirmed_close_keeps_ownership(self):
        self.source.close_status='BLOCKED'
        with self.assertRaisesRegex(RuntimeError,'cierre'): self.live.finish(True)
        self.assertEqual(self.live.session['job_id'],'owned')
    def test_incomplete_close_is_not_validation(self):
        report=self.live.finish(True)
        self.assertEqual(report['status'],'incomplete')
        self.assertFalse(report['validation']['validated'])
        self.assertIsNone(self.live.session)
    def test_saved_reports_survive_restart_without_reopening_session(self):
        report=self.live.finish(True)
        restored=Live(self.source,FakeModel(),self.tmp.name)
        self.assertIsNone(restored.session)
        self.assertEqual(restored.reports[0]['id'],report['id'])
    def test_no_public_observation_token(self):
        self.assertNotIn('token',json.dumps(self.live.state()))
    def test_shutdown_does_not_open_next_game(self):
        self.live.queue=[{'url':'https://www.pragmaticplay.com/en/games/gates-of-olympus-1000/','auto_close':False}]
        starts=self.source.calls.count('pragmatic_guided_start')
        self.live.finish(True,advance=False)
        self.assertEqual(self.source.calls.count('pragmatic_guided_start'),starts)
        self.assertIsNone(self.live.session)
    def test_change_before_click_is_not_attributed_to_click(self):
        original=self.source.call
        fingerprint=next(c['fingerprint'] for c in RAW['controls'] if c['name']=='Level0Button')
        def call(name,args):
            if name=='pragmatic_guided_observe':
                return {'token':'fresh','state_key':'one','flags':{},'wager':{'betLevelIndex':1},
                    'actions':[{'fingerprint':fingerprint,'action_id':'ante'}]}
            if name=='pragmatic_guided_act':
                return {'outcome':{'reason':'STATE_CHANGED','operationStarted':False},'view':call('pragmatic_guided_observe',{})}
            return original(name,args)
        self.source.call=call
        self.live.session['view']['wager']={'betLevelIndex':0}
        control=next(c for c in self.live.session['snapshot']['controls'] if c['name']=='Level0Button')
        result=self.live.act(self.live.session['snapshot']['id'],control['id'],True,'ante_bet')
        self.assertFalse(result['effect_verified'])
    def test_validated_finish_refreshes_active_bonus(self):
        for row in self.live.session['ledger'].values():
            row.update(status='verified',ante_rounds_complete=[{'protocol_complete':True}])
        self.live.session['purchase_complete']=True
        original=self.source.call
        def call(name,args):
            result=original(name,args)
            if name=='pragmatic_guided_observe': result['flags']={'logicIsFreeSpin':True}
            return result
        self.source.call=call
        self.assertTrue(self.live.validation()['validated'])
        with self.assertRaisesRegex(ValueError,'bonus'): self.live.finish()
        self.assertNotIn('pragmatic_guided_close',self.source.calls)

class TransportTests(unittest.TestCase):
    def test_sse_rpc_response(self): self.assertEqual(decode_rpc('event: message\ndata: {"id":1,"result":{"x":2}}\n\n')['result'],{'x':2})
    def test_disallows_non_demo_and_session_urls(self):
        for url in ['https://casino.example/play','http://www.pragmaticplay.com/en/games/a/','https://www.pragmaticplay.com/en/games/a/?token=secret']:
            with self.assertRaises(ValueError): valid_demo_url(url)

if __name__=='__main__': unittest.main()
