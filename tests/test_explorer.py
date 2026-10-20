import copy
from pathlib import Path
import tempfile
import unittest
from snapshot_laya.explorer import Explorer, optional_zeus_selection


def button(path, role, rule=None):
    return {'path':path, 'name':path, 'id':path,'action_id':'fresh',
            'classification':{'role':role,'source':'catalog','needs_review':False,'rule':rule}}


class Demo:
    def __init__(self, root):
        self.data_dir=Path(root); self.session=None; self.queue=[]; self.starts=0; self.closes=0; self.clicks=[]
    def enqueue(self, urls, auto):
        assert self.session is None
        self.starts+=1; self._state('base')
    def _state(self, state):
        controls={'base':[button('BuyA','buy_bonus'),button('BuyB','buy_bonus')],
                  'menu':[button('Yes','confirm'),button('No','cancel')],
                  'bonus':[button('Continue','continue')],
                  'antebase':[button('Ante','ante_bet'),button('Spin','spin','normal-spin-support')],
                  'anteon':[button('Ante','ante_bet'),button('Spin','spin','normal-spin-support')]}[state]
        self.session={'snapshot':{'id':state,'controls':controls,'blockers':[],'unresolved':[]},
                      'view':{'flags':{},'operation':{},'wager':{'betLevelIndex':1 if state=='anteon' else 0}},
                      'purchase_complete':False,'ledger':{}}
    def act(self, snap, cid, automatic):
        assert automatic; assert snap==self.session['snapshot']['id']
        self.clicks.append((self.starts,cid)); started=False
        if cid.startswith('Buy'): self._state('menu')
        elif cid=='No': self._state('base')
        elif cid=='Yes': self._state('bonus'); started=True
        elif cid=='Continue': self._state('base'); self.session['purchase_complete']=True
        elif cid=='Ante': self._state('anteon')
        elif cid=='Spin':
            started=True; self.session['view']['operation']={'submitted':True,'protocolComplete':True}
        return {'effect_verified':True,'outcome':{'operationStarted':started,'reason':'STATE_CHANGED'}}
    def finish(self, incomplete, advance):
        assert not advance
        self.closes+=1; self.session=None
        return {'id':str(self.closes),'har':{'har_path':'raw.har'}}


class ExplorerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.live=Demo(self.tmp.name); self.exp=Explorer(self.live)
    def tearDown(self): self.tmp.cleanup()
    def test_color_exception_is_limited_to_zeus_mode_and_quiet_timeout(self):
        c={'name':'Zeus','path':'GameRoot/Game/SelectionScreen/Content/Chars/ZeusLeft/Btn/Zeus'}
        url='https://www.pragmaticplay.com/en/games/zeus-vs-hades-gods-of-war/'
        result={'outcome':{'reason':'QUIET_TIMEOUT','operationStarted':False}}
        self.assertTrue(optional_zeus_selection(url,c,result))
        self.assertFalse(optional_zeus_selection(url.replace('zeus-vs-hades-gods-of-war','another'),c,result))
        self.assertFalse(optional_zeus_selection(url,dict(c,path='GameRoot/Game/Purchase/Zeus'),result))
        self.assertFalse(optional_zeus_selection(url,c,{'outcome':{'reason':'TOKEN_EXPIRED','operationStarted':False}}))
    def test_ready_game_without_targets_saves_capture_and_closes(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        self.live.session['snapshot'].update(controls=[],support_controls=[button('Spin','spin','normal-spin-support')])
        self.live.session['view']['flags']={'canSpin':True}
        captures=[]
        self.live.capture_evidence=lambda reason: captures.append(reason) or {'path':'evidence.jpg'}
        for _ in range(8):self.exp.tick()
        self.assertEqual(captures,['no_target_controls_detected'])
        self.assertEqual(self.exp.tree.data['outcome'],'no_target_controls_detected')
        self.assertFalse(self.exp.running)
        self.assertFalse(self.exp.tree.complete())
        self.assertEqual(self.live.closes,1)
    def test_empty_loading_game_is_not_reported_as_no_purchases(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        self.live.session['snapshot']['controls']=[]
        for _ in range(8):self.exp.tick()
        self.assertTrue(self.exp.running)
        self.assertEqual(self.live.closes,0)
    def test_zeus_color_exception_is_not_retried_or_counted_as_verified(self):
        original=self.live._state
        path='GameRoot/Game/SelectionScreen/Content/Chars/ZeusLeft/Btn/Zeus'
        def state(name):
            original(name)
            self.live.session['snapshot']['controls']=[dict(button(path,'choice'),name='Zeus')]
        def act(*args,**kwargs):
            self.live.clicks.append('Zeus')
            return {'effect_verified':False,'outcome':{'operationStarted':False,'reason':'QUIET_TIMEOUT'}}
        self.live._state=state;self.live.act=act
        self.exp.start('https://www.pragmaticplay.com/en/games/zeus-vs-hades-gods-of-war/')
        for _ in range(15):self.exp.tick()
        self.assertEqual(self.live.clicks,['Zeus'])
        self.assertFalse(self.exp.running)
        self.assertFalse(self.exp.tree.data['unresolved'])
        self.assertEqual(self.exp.tree.data['branches'][0]['status'],'selection_exception')
        self.assertFalse(self.exp.tree.complete())
    def test_two_purchases_cancel_confirm_use_independent_sessions(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(60):
            self.exp.tick()
            if not self.exp.running: break
        self.assertTrue(self.exp.tree.complete(),self.exp.state())
        self.assertEqual(len(self.exp.tree.data['branches']),6)
        self.assertEqual(self.live.starts,4) # only the four terminal paths need sessions
        self.assertEqual(self.live.closes,4)
        self.assertEqual(self.live.clicks[:2],[(1,'BuyA'),(1,'Yes')])
        self.assertTrue(all(b.get('session_report') for b in self.exp.tree.data['branches']))
        confirms=[session for session,name in self.live.clicks if name=='Yes']
        self.assertEqual(len(set(confirms)),2)
    def test_unknown_semantics_are_still_traversed_as_drawn_branches(self):
        original=self.live._state
        def state(name):
            original(name)
            for c in self.live.session['snapshot']['controls']:
                if c['classification']['role']=='continue':continue
                c['classification'].update(source='laya',role='unknown',needs_review=True)
                c['decision']={'role':'probe','source':'rendered_probe','eligible':True}
        self.live._state=state
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(90):
            self.exp.tick()
            if not self.exp.running:break
        self.assertTrue(self.exp.tree.complete(),self.exp.state())
        self.assertEqual(sum(name=='Yes' for _,name in self.live.clicks),2)
        self.assertEqual(sum(name=='No' for _,name in self.live.clicks),2)
    def test_every_bonus_pick_gets_a_new_session_and_replayed_prefix(self):
        original_state=self.live._state;original_act=self.live.act
        def state(name):
            original_state(name)
            if name=='bonus':
                picks=[button('Pick1','unknown'),button('Pick2','unknown')]
                for c in picks:
                    c['classification'].update(source='laya',needs_review=True)
                    c['decision']={'role':'probe','source':'rendered_probe','eligible':True}
                self.live.session['snapshot']['controls']=picks
        def act(snap,cid,automatic):
            if cid in ('Pick1','Pick2'):
                self.live.clicks.append((self.live.starts,cid))
                original_state('bonus')
                return {'effect_verified':True,'outcome':{'operationStarted':True,'reason':'OPERATION_STARTED'}}
            return original_act(snap,cid,automatic)
        self.live._state=state;self.live.act=act
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(160):
            self.exp.tick()
            if not self.exp.running:break
        self.assertTrue(self.exp.tree.complete(),self.exp.state())
        picks=[(session,cid) for session,cid in self.live.clicks if cid.startswith('Pick')]
        self.assertEqual(len(picks),4)
        self.assertEqual(len({session for session,cid in picks}),4)
        self.assertEqual(sum(b['status']=='expanded' for b in self.exp.tree.data['branches']),4)
        self.assertEqual(self.live.starts,6) # four bonus picks plus two cancellations
    def test_new_siblings_remain_pending_while_first_child_uses_live_session(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(10):
            self.exp.tick()
            if self.exp.current and len(self.exp.current['steps'])==2:break
        self.assertEqual(self.live.starts,1)
        self.assertEqual(self.live.closes,0)
        self.assertEqual(self.live.clicks,[(1,'BuyA')])
        self.assertEqual(self.exp.position,1)
        self.assertEqual(len(self.exp.evidence['actions']),1)
        pending=[b['steps'][-1]['path'] for b in self.exp.tree.data['branches'] if b['status']=='pending']
        self.assertCountEqual(pending,['BuyB','No'])
        self.assertFalse(self.exp.tree.complete())
    def test_ante_runs_two_new_normal_operations(self):
        original=self.live.enqueue
        def enqueue(urls, auto): original(urls,auto); self.live._state('antebase')
        self.live.enqueue=enqueue
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(30):
            self.exp.tick()
            if not self.exp.running: break
        self.assertTrue(self.exp.tree.complete(),self.exp.state())
        self.assertEqual([name for _,name in self.live.clicks],['Ante','Spin','Spin'])
        self.assertEqual(len(self.exp.tree.data['branches'][0]['evidence']['rounds']),2)
    def test_unknown_during_bonus_stops_without_retry(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(30):
            self.exp.tick()
            if self.exp.phase=='purchase': break
        c=button('mystery','unknown');c['classification']['source']='laya'
        self.live.session['snapshot']['controls']=[c]
        before=len(self.live.clicks); self.exp.tick(); self.exp.tick()
        self.assertFalse(self.exp.running)
        self.assertFalse(self.exp.tree.complete())
        self.assertEqual(len(self.live.clicks),before)
    def test_stability_wait_does_not_click_first_observation(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        self.exp.tick(); self.exp.tick()
        self.assertEqual(self.live.starts,1)
        self.exp.tick()
        self.assertFalse(self.live.clicks)
        self.exp.tick()
        self.assertEqual(self.live.clicks,[(1,'BuyA')])
    def test_failed_effect_is_not_retried(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        original=self.live.act
        def act(*args,**kwargs):
            result=original(*args,**kwargs); result['effect_verified']=False;return result
        self.live.act=act
        for _ in range(12):self.exp.tick()
        self.assertFalse(self.exp.running)
        self.assertEqual(len(self.live.clicks),1)
        self.assertFalse(self.exp.tree.complete())
    def test_pulsing_continue_is_not_clicked_twice(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(30):
            self.exp.tick()
            if self.exp.phase=='purchase':break
        original=self.live.act
        def act(snap,cid,automatic):
            if cid=='Continue':
                self.live.clicks.append((self.live.starts,cid))
                self.live.session['snapshot']['id']='pulse-2'
                return {'effect_verified':True,'outcome':{'operationStarted':False,'reason':'STATE_CHANGED'}}
            return original(snap,cid,automatic)
        self.live.act=act
        for i in range(8):
            self.live.session['snapshot']['id']='pulse-'+str(i)
            self.exp.tick()
        self.assertEqual(sum(name=='Continue' for _,name in self.live.clicks),1)
    def test_known_invisible_background_does_not_block_bonus_continue(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(30):
            self.exp.tick()
            if self.exp.phase=='purchase':break
        self.live.session['view']['flags']={'logicIsFreeSpin':True}
        self.live.session['snapshot']['unresolved']=[{'path':'BuyA','reason':'NO_VERIFIED_VISIBLE_DRAWING'}]
        for _ in range(3):self.exp.tick()
        self.assertTrue(any(name=='Continue' for _,name in self.live.clicks))
        self.assertFalse(self.exp.tree.data['unresolved'])
    def test_unrecognized_invisible_control_still_blocks_bonus(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(30):
            self.exp.tick()
            if self.exp.phase=='purchase':break
        self.live.session['view']['flags']={'logicIsFreeSpin':True}
        self.live.session['snapshot']['unresolved']=[{'path':'UnknownChoice','reason':'NO_VERIFIED_VISIBLE_DRAWING'}]
        self.exp.tick()
        self.assertFalse(self.exp.running)
        self.assertFalse(self.exp.tree.complete())
    def test_protocol_pending_never_validates_ante(self):
        original=self.live.enqueue
        def enqueue(urls,auto): original(urls,auto);self.live._state('antebase')
        self.live.enqueue=enqueue
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(15):
            self.exp.tick()
            if self.exp.round_pending: break
        self.live.session['view']['operation']={'submitted':True,'protocolComplete':False}
        before=len(self.live.clicks)
        for _ in range(5):self.exp.tick()
        self.assertFalse(self.exp.tree.complete())
        self.assertEqual(len(self.live.clicks),before)
    def test_close_failure_does_not_validate_a_branch(self):
        self.exp.start('https://www.pragmaticplay.com/en/games/demo/')
        for _ in range(5):self.exp.tick()
        def finish(*args,**kwargs):raise RuntimeError('cierre no confirmado')
        self.live.finish=finish
        for _ in range(10):self.exp.tick()
        self.assertFalse(self.exp.running)
        self.assertFalse(self.exp.tree.complete())
        self.assertIsNotNone(self.live.session)

if __name__=='__main__':unittest.main()
