import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid
from .core import TARGETS, ROLES, clean_snapshot, completion, evidence_effect, valid_demo_url
from .mcp import MCP
from .laya import Laya
from .catalog import known, modal_roots, decision, common_interface


class Live:
    def __init__(self,source=None,classifier=None,data_dir=None):
        self.source=source or MCP(os.environ.get('HARDFIRE_MCP_URL','http://127.0.0.1:8765/mcp'))
        self.model=classifier or Laya()
        self.data_dir=Path(data_dir or os.environ.get('SNAPSHOT_LAYA_DATA','runs')).resolve()
        self.lock=threading.RLock()
        self.session=None
        self.queue=[]
        self.reports=[]
        for path in sorted(self.data_dir.glob('*.json')):
            if not re.fullmatch(r'[0-9a-f]{32}',path.stem): continue
            try:
                report=json.loads(path.read_text(encoding='utf-8'))
                if report.get('id')==path.stem and report.get('status') and report.get('game_url'):
                    self.reports.append(report)
            except (OSError,ValueError):
                continue
        self.images={}
        self.message='Listo para abrir una demo.'
        self.error=None

    def image_key(self,path):
        if not path: return None
        p=Path(path).resolve()
        allowed=(Path.home()/'.hardfire'/'fuzzer').resolve()
        if not p.is_relative_to(allowed) or not p.is_file(): return None
        key=hashlib.sha256(str(p).encode()).hexdigest()
        self.images[key]=p
        return '/api/images/'+key

    def capture_evidence(self,reason):
        s=self.session
        key=(s['snapshot'].get('image_url') or '').rsplit('/',1)[-1]
        source=self.images.get(key)
        if not source or not source.is_file():
            raise ValueError('Falta una captura verificable para cerrar la búsqueda sin controles.')
        folder=self.data_dir/'evidence';folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(s['id']+'-'+re.sub(r'[^a-z0-9_-]','_',reason.lower())+'.jpg')
        shutil.copyfile(source,dest)
        image_key=hashlib.sha256(str(dest).encode()).hexdigest()
        self.images[image_key]=dest
        evidence={'path':str(dest),'image_url':'/api/images/'+image_key,'reason':reason}
        s.setdefault('captures',[]).append(evidence)
        return evidence

    def enqueue(self,urls,auto_close=False):
        validated=[valid_demo_url(url.strip()) for url in urls if url.strip()]
        if not validated or len(validated)>20: raise ValueError('Elegí entre 1 y 20 demos oficiales.')
        with self.lock:
            if self.session is not None: raise ValueError('Cerrá la sesión actual antes de cambiar la cola.')
            self.queue=[{'url':url,'auto_close':auto_close} for url in validated]
            self.error=None
            self._next()

    def _next(self):
        if not self.queue: return
        item=self.queue.pop(0)
        self.message='Abriendo demo aislada y cargando Laya…'
        opened=self.source.call('pragmatic_guided_start',{'game_url':item['url'],'max_sessions':3})
        if not opened.get('job_id') or not opened.get('tab_id'): raise RuntimeError('HardFire no abrió una sesión demo válida.')
        self.session={'id':uuid.uuid4().hex,'game_url':item['url'],'job_id':opened['job_id'],'tab_id':opened['tab_id'],
            'auto_close':item['auto_close'],'observations':0,'snapshot':None,'view':opened,'ledger':{},'events':[],
            'purchase_started':False,'purchase_complete':False,'started':time.time(),'state':'active'}
        # Ownership is registered before inference: a model failure must not orphan the game.
        self._scan(opened)

    def observe(self):
        with self.lock:
            if not self.session or self.session['state']!='active': return
            view=self.source.call('pragmatic_guided_observe',{'job_id':self.session['job_id']})
            self._scan(view)
            if self.session['auto_close'] and self.validation()['validated']:
                self._finish(False)

    def _scan(self,view):
        s=self.session
        dom=self.source.call('hardfire_find',{'tab_id':s['tab_id'],'css':'[data-age-check-confirm], [role="dialog"]','visible':True,'limit':10,'max_bytes':8000})
        blockers=[{'ref':e['ref'],'name':(e.get('name') or e.get('text') or 'Aviso de la página').strip()[:160]} for e in dom.get('elements',[]) if e.get('visible') and e.get('ref')]
        raw=self.source.call('pragmatic_drawn_buttons',{'tab_id':s['tab_id'],'include_universal':True})
        ignored_page=[]
        age_name='Yes, I am 18 years or older'
        if any(b['name']==age_name for b in blockers) and view.get('flags',{}).get('canSpin') is True:
            full=self.source.call('hardfire_find',{'tab_id':s['tab_id'],'css':'.game-fullscreen.fullscreen[data-fullscreen]','visible':True,'limit':3,'max_bytes':5000})
            active=full.get('elements',[])
            if len(active)==1:
                rect=active[0].get('rect',{});size=raw.get('image_size',{})
                age_frames={e.get('frame_id') for e in dom.get('elements',[]) if (e.get('name') or '').strip()==age_name}
                covering=(bool(active[0].get('frame_id')) and active[0].get('frame_id') in age_frames and -1<=rect.get('x',99)<=1 and -1<=rect.get('y',99)<=1 and rect.get('width',0)>=size.get('width',99999)-1 and rect.get('height',0)>=size.get('height',99999)-1)
                if covering:
                    inside=self.source.call('hardfire_find',{'tab_id':s['tab_id'],'css':'.game-fullscreen.fullscreen [data-age-check-confirm]','visible':True,'limit':3,'max_bytes':5000})
                    if not inside.get('elements'):
                        blockers=[b for b in blockers if b['name']!=age_name]
                        ignored_page=[{'name':age_name,'reason':'outside_active_fullscreen_game'}]
        raw['state_key']=view.get('state_key')
        # Enabled confirmation controls establish a modal ancestor; base buttons behind it are excluded.
        modal=modal_roots(raw.get('controls',[]))
        if view.get('flags',{}).get('spinBlockingFeatureIsRunning'):
            for control in raw.get('controls',[]):
                if control.get('enabled') is not True or control.get('visible') is False or control.get('alpha')==0 or control.get('clickable')!='RUNTIME_COLLIDER': continue
                if re.search(r'(ButtonYes|ButtonNo|Confirm|Cancel|CloseButton)',control.get('name',''),re.I):
                    parts=control.get('path','').split('/')
                    for i,part in enumerate(parts):
                        if re.search(r'(Window|Dialog|Popup)',part,re.I): modal.append('/'.join(parts[:i+1])+'/')
        if modal: raw['modal_roots']=sorted(set(modal),key=len,reverse=True)[:1]
        snapshot=clean_snapshot(raw,blockers)
        snapshot['ignored_page_controls']=ignored_page
        guided={a.get('fingerprint'):a for a in view.get('actions',[]) if a.get('fingerprint')}
        normal_spins=[a for a in view.get('actions',[]) if a.get('kind')=='spin' and a.get('action_id')=='spin_normal']
        targets=[];support=[];ignored=[]
        for control in snapshot['controls']:
            signature=known(control)
            if common_interface(control) and not (signature and signature.get('rule')=='normal-spin-support'):
                ignored.append({'name':control.get('name'),'path':control.get('path'),'reason':'known_common_interface'})
                continue
            control['classification']=signature or dict(self.model.classify(control),source='laya')
            control['image_url']=self.image_key(control.get('crop_path'))
            control['action_id']=guided.get(control.get('fingerprint'),{}).get('action_id')
            if control['classification'].get('rule')=='normal-spin-support' and len(normal_spins)==1:
                control['action_id']=normal_spins[0]['action_id']
            control['id']=control.get('fingerprint') or control['id']
            control['decision']=decision(control)
            if control['classification'].get('rule')=='normal-spin-support':
                support.append(control)
                continue
            targets.append(control)
            role=control['decision']['role']
            if role in TARGETS:
                key=self.control_key(control,role)
                s['ledger'].setdefault(key,{'key':key,'name':control.get('name'),'labels':control.get('labels',[]),
                    'role':role,'status':'pending','evidence':None})
        snapshot.update(controls=targets,support_controls=support,ignored_controls=ignored)
        snapshot['image_url']=self.image_key(raw.get('full_path'))
        # GUI bet label is stronger evidence for bet +/- than a generic state hash.
        bet=[c.get('labels',[]) for c in raw.get('controls',[]) if 'MoneyAndCoinsSwitcher' in c.get('path','')]
        view['bet_signature']=json.dumps(bet,sort_keys=True) if bet else None
        s['view']=view
        s['snapshot']=snapshot
        s['observations']+=1
        operation=view.get('operation',{})
        busy=any(view.get('flags',{}).get(k) for k in ('logicIsFreeSpin','respinInProgress','spinBlockingFeatureIsRunning','stopActive','lastWinIsCounting'))
        if s['purchase_started'] and operation.get('submitted') and operation.get('protocolComplete') and not busy:
            s['purchase_complete']=True
        self.message=f"{len(snapshot['controls'])} controles filtrados · {s['observations']} observaciones"
        if blockers: self.message='Un aviso de la página tapa el juego. Resolvelo antes de analizar los controles.'

    @staticmethod
    def control_key(control,role):
        path=control.get('path') or control['id']
        if role=='ante_bet': path=re.sub(r'Level\d+Button','AnteBetToggle',path)
        return path

    def act(self,snapshot_id,control_id,visual_reviewed=False,role=None,automatic=False):
        with self.lock:
            s=self.session
            if not s or not s.get('snapshot'): raise ValueError('No hay snapshot activo.')
            if s['snapshot']['id']!=snapshot_id: raise ValueError('Snapshot vencido. Revisá los controles actuales.')
            if not visual_reviewed and not automatic: raise ValueError('Verificá primero el control en la captura actual.')
            selected=next((c for c in s['snapshot']['controls']+s['snapshot'].get('support_controls',[]) if c['id']==control_id),None)
            if not selected: raise ValueError('El control ya no está presente.')
            selected=copy.deepcopy(selected)
            selected_decision=decision(selected)
            if automatic and not selected_decision['eligible']:
                raise ValueError('La exploración exige un control de juego dibujado y una acción guiada vigente.')
            selected_role=role or (selected_decision['role'] if automatic else selected['classification']['role'])
            if automatic and selected_role!=selected_decision['role']:
                raise ValueError('La función automática debe coincidir con la decisión del snapshot.')
            if selected_role not in ROLES or selected_role=='unknown': raise ValueError('Elegí una función concreta antes de ejecutar un control ambiguo.')
            fresh=self.source.call('pragmatic_guided_observe',{'job_id':s['job_id']})
            self._scan(fresh)
            if s['snapshot']['id']!=snapshot_id and not automatic:
                raise ValueError('La geometría o el estado visual cambió; revisá la captura nueva.')
            before=copy.deepcopy(s['view'])
            if automatic and selected_role=='spin':
                from .explorer import ante_active, idle
                if not ante_active(before) or not idle(before) or before.get('flags',{}).get('canSpin') is not True:
                    raise ValueError('La tirada automática exige ante bet activo y juego listo.')
            current=next((c for c in s['snapshot']['controls']+s['snapshot'].get('support_controls',[]) if c['id']==control_id and c['model_input']==selected['model_input']),None)
            if not current or s['snapshot']['blockers']: raise ValueError('El control cambió o está bloqueado; no se hizo clic.')
            if automatic and (not decision(current)['eligible'] or decision(current)['role']!=selected_decision['role'] or known(current)!=known(selected)):
                raise ValueError('Cambió la identidad de la decisión o la acción guiada.')
            execution_snapshot_id=s['snapshot']['id']
            # Automatic decisions use the freshly scanned collider, not the old
            # geometry. Semantic identity and the catalog rule must agree; the
            # guided adapter independently validates its fresh token at execution.
            if current.get('action_id'):
                result=self.source.call('pragmatic_guided_act',{'job_id':s['job_id'],'token':fresh['token'],
                    'action_id':current['action_id'],'reason':('Snapshot-Laya: '+('authorized snapshot branch ' if automatic else 'visually reviewed ')+selected_role)[:256]})
                outcome=result.get('outcome',{})
                after=result.get('view') or self.source.call('pragmatic_guided_observe',{'job_id':s['job_id']})
            elif selected_role in ('bet_up','bet_down','bet_menu','cancel'):
                center=current.get('center')
                if not center: raise ValueError('No hay coordenadas actuales verificables.')
                self.source.call('hardfire_click_relative',{'tab_id':s['tab_id'],'rx':center['x'],'ry':center['y']})
                after=self.source.call('pragmatic_guided_observe',{'job_id':s['job_id']})
                outcome={'reason':'STATE_CHANGED' if after.get('state_key')!=before.get('state_key') else 'NO_CHANGE_OBSERVED','operationStarted':False}
            else: raise ValueError('El adaptador no ofrece una acción segura para este control; queda pendiente.')
            if outcome.get('operationStarted') and selected_role in ('buy_bonus','confirm','probe'): s['purchase_started']=True
            self._scan(after)
            verified=evidence_effect(selected_role,before,s['view'],outcome)
            observed_role='ante_bet' if selected_role=='probe' and before.get('wager',{}).get('betLevelIndex')==0 and isinstance(s['view'].get('wager',{}).get('betLevelIndex'),(int,float)) and s['view']['wager']['betLevelIndex']>0 else selected_role
            key=self.control_key(selected,selected_decision['role'])
            decision_source=selected_decision['source'] if automatic else 'operator'
            if key in s['ledger']:
                s['ledger'][key].update(role=observed_role,status='verified' if verified else 'unverified',
                    evidence={'outcome':outcome,'before_state':before.get('state_key'),'after_state':s['view'].get('state_key'),
                        'before_wager':before.get('wager'),'after_wager':s['view'].get('wager'),'visual_reviewed':visual_reviewed,
                        'decision_source':decision_source})
            s['events'].append({'control':selected['model_input'],'model':selected['classification'],'selected_role':selected_role,
                'observed_role':observed_role,
                'outcome':outcome,'effect_verified':verified,'time':time.time(),
                'decision_source':decision_source,
                'executed_hit_rect':copy.deepcopy(current.get('hit_rect')),
                'fresh_snapshot_id':execution_snapshot_id})
            self.error=None
            return {'effect_verified':verified,'outcome':outcome,'before_wager':before.get('wager',{}),
                    'after_wager':s['view'].get('wager',{}),'before_operation':before.get('operation',{}),
                    'after_operation':s['view'].get('operation',{})}

    def dismiss(self,ref):
        with self.lock:
            if not self.session: raise ValueError('No hay sesión activa.')
            blocker=next((b for b in self.session['snapshot']['blockers'] if b['ref']==ref),None)
            if not blocker: raise ValueError('El aviso ya no es actual.')
            fresh=self.source.call('hardfire_find',{'tab_id':self.session['tab_id'],'css':'[data-age-check-confirm], [role="dialog"]','visible':True,'limit':10,'max_bytes':8000})
            element=next((e for e in fresh.get('elements',[]) if (e.get('name') or e.get('text') or '').strip()==blocker['name']),None)
            if not element: raise ValueError('El aviso cambió.')
            if element.get('role') not in ('link','button'): raise ValueError('Resolvé este diálogo directamente en la ventana del juego.')
            self.source.call('hardfire_click_ref',{'tab_id':self.session['tab_id'],'ref':element['ref']})
            self.observe()

    def validation(self):
        s=self.session
        if not s: return {'validated':False,'reasons':['No hay sesión.']}
        snapshot=s.get('snapshot') or {}
        view=s.get('view') or {}
        unresolved=list(snapshot.get('unresolved',[]))+list(view.get('unresolved',[]))+list(snapshot.get('blockers',[]))
        operation=view.get('operation',{})
        if operation.get('submitted') and not operation.get('protocolComplete'): unresolved.append('protocol_pending')
        if s['purchase_started'] and not s['purchase_complete']:unresolved.append('started_operation_not_finished')
        return completion(list(s['ledger'].values()),view.get('flags',{}),unresolved,s['observations'],s['purchase_complete'])

    def finish(self,incomplete=False,advance=True):
        with self.lock: return self._finish(incomplete,advance)

    def _finish(self,incomplete,advance=True):
        if not self.session: raise ValueError('No hay sesión que cerrar.')
        if not incomplete:
            fresh=self.source.call('pragmatic_guided_observe',{'job_id':self.session['job_id']})
            self._scan(fresh)
        check=self.validation()
        if not incomplete and not check['validated']: raise ValueError('No validado: '+' '.join(check['reasons']))
        s=self.session
        report={'id':s['id'],'game_url':s['game_url'],'validation':check,
            'status':'validated_observed_scope' if check['validated'] and not incomplete else 'incomplete',
            'observations':s['observations'],'controls':list(s['ledger'].values()),'events':s['events'],
            'purchase_started':s['purchase_started'],'purchase_complete':s['purchase_complete'],
            'captures':s.get('captures',[]),
            'final_flags':s['view'].get('flags',{}),'final_operation':s['view'].get('operation',{}),
            'seconds':round(time.time()-s['started'],1)}
        self.data_dir.mkdir(parents=True,exist_ok=True)
        path=self.data_dir/(s['id']+'.json')
        # Save before closing; an evidence-write or upstream close failure retains ownership.
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        closed=self.source.call('pragmatic_guided_close',{'job_id':s['job_id']})
        if closed.get('status')!='CLOSED': raise RuntimeError('HardFire no confirmó el cierre; se conserva la sesión para revisión.')
        report['upstream_close_status']=closed.get('status','closed')
        report['har']=closed
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        self.reports.append(report)
        self.session=None
        self.message='Juego cerrado; informe guardado.'
        self.error=None
        if advance: self._next()
        return report

    def state(self):
        s=self.session
        snapshot=copy.deepcopy(s.get('snapshot')) if s and s.get('snapshot') else None
        if snapshot:
            snapshot.pop('screenshot',None)
            for c in snapshot['controls']+snapshot.get('support_controls',[]): c.pop('crop_path',None)
        return {'message':self.message,'error':self.error,'snapshot':snapshot,
            'session':{'id':s['id'],'game_url':s['game_url'],'observations':s['observations'],'auto_close':s['auto_close'],
                'ledger':list(s['ledger'].values()),'purchase_started':s['purchase_started'],'purchase_complete':s['purchase_complete']} if s else None,
            'validation':self.validation(),'queue':[i['url'] for i in self.queue],
            'reports':[{'id':r['id'],'game_url':r['game_url'],'status':r['status'],'validation':r['validation']} for r in self.reports]}
