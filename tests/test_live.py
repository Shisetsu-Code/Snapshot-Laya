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
        for row in self.live.session['ledger'].values(): row['status']='verified'
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
