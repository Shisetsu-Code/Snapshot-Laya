"""Persistent semantic paths; every branch gets a newly owned demo session."""
import copy
import hashlib
import json
import re
from pathlib import Path
import time
from .catalog import TARGET_ROLES, identity, match
from .core import valid_demo_url

BUSY = ('logicIsFreeSpin', 'respinInProgress', 'spinBlockingFeatureIsRunning', 'stopActive', 'lastWinIsCounting', 'waitInResultForBigWin')


def ante_active(view):
    value = view.get('wager', {}).get('betLevelIndex')
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def idle(view):
    return not any(view.get('flags', {}).get(k) for k in BUSY)


class Branches:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
        if self.data:
            self.data['running'] = False
            for b in self.data['branches']:
                if b['status'] == 'running':
                    b.update(status='interrupted', reason='Interrumpido; revisar antes de repetir.')
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def start(self, url, rounds=2, max_branches=60):
        valid_demo_url(url)
        if self.data and self.data.get('running'): raise ValueError('Ya hay un recorrido activo.')
        if not 1 <= rounds <= 5: raise ValueError('Elegí entre 1 y 5 tiradas de ante bet.')
        self.data = {'game_url': url, 'running': True, 'rounds_required': rounds,
                     'max_branches': max_branches, 'branches': [], 'unresolved': [],
                     'scope': 'discovered_purchase_and_ante_paths', 'exhaustive_game_coverage': False,
                     'message': 'Descubriendo controles iniciales.', 'created': time.time()}
        self.save()

    def unresolved(self, message):
        if message not in self.data['unresolved']: self.data['unresolved'].append(message)
        self.save()

    def discover(self, prefix, controls):
        known_paths = {b['id'] for b in self.data['branches']}
        added = 0
        for c in controls:
            m = c['classification']
            role = m['role']
            d=c.get('decision')
            role=(d or {}).get('role',role)
            if m.get('source')=='catalog' and role in ('spin', 'other', 'bet_up', 'bet_down', 'bet_menu'): continue
            if not ((d or {}).get('eligible') or d is None and m.get('source')=='catalog' and not m.get('needs_review') and c.get('action_id')) or role not in TARGET_ROLES:
                self.unresolved('Control requiere revisión: ' + c.get('path', c.get('name', '?')))
                continue
            step = identity(c)
            # Returning to a previously traversed semantic control does not create an infinite loop.
            if step in prefix: continue
            steps = prefix + [step]
            key = hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()[:20]
            if key in known_paths: continue
            if len(steps) > 10 or len(self.data['branches']) >= self.data['max_branches']:
                self.unresolved('Límite de recorrido alcanzado; quedan ramas pendientes.')
                continue
            self.data['branches'].append({'id': key, 'steps': steps, 'status': 'pending', 'evidence': None})
            known_paths.add(key); added += 1
        self.save()
        return added

    def next(self):
        branch = next((b for b in self.data['branches'] if b['status'] == 'pending'), None)
        if branch: branch['status'] = 'running'; self.save()
        return branch

    def done(self, branch, evidence):
        if branch['steps'][-1]['role'] == 'ante_bet' or evidence.get('observed_function')=='ante_bet':
            rounds = evidence.get('rounds', [])
            if not evidence.get('activated') or len(rounds) < self.data['rounds_required']:
                raise ValueError('Ante bet necesita activación y tiradas completas.')
            if not all(r.get('started') and r.get('protocol_complete') and r.get('normal') and
                       r.get('ante_before', 0) > 0 and r.get('ante_before') == r.get('ante_after') for r in rounds):
                raise ValueError('No se comprobó ante bet activo durante todas las tiradas.')
        branch.update(status='verified', evidence=evidence)
        self.save()

    def complete(self):
        if not self.data or not self.data['branches'] or self.data['unresolved']:return False
        for b in self.data['branches']:
            if b['status']=='verified':continue
            if b['status']!='expanded' or not any(len(child['steps'])>len(b['steps']) and child['steps'][:len(b['steps'])]==b['steps'] for child in self.data['branches']):return False
        return True


class Explorer:
    def __init__(self, live):
        self.live = live
        self.tree = Branches(live.data_dir/'branches.json')
        self.current = None
        self.position = 0
        self.phase = None
        self.deadline = 0
        self.evidence = {}
        self.round_pending = None
        self.wait_count = 0
        self.age_dismissed = False
        self.stable_snapshot = None

    @property
    def running(self): return bool(self.tree.data and self.tree.data['running'])

    def start(self, url, rounds=2):
        if self.live.session: raise ValueError('Cerrá la sesión actual antes del recorrido.')
        if self.live.queue: raise ValueError('Terminá la cola manual antes del recorrido.')
        if self.tree.data:
            archive = self.live.data_dir / ('branches-' + str(time.time_ns()) + '.json')
            archive.write_text(json.dumps(self.tree.data, ensure_ascii=False, indent=2), encoding='utf-8')
        self.tree.start(url, rounds)
        self.phase = 'discover'
        self.deadline = time.monotonic()+300
        self._open()

    def _open(self):
        self.live.enqueue([self.tree.data['game_url']], False)
        self.wait_count = 0
        self.age_dismissed = False
        self.stable_snapshot = None

    def pause(self):
        if not self.running: return
        self.tree.data['running'] = False
        self.tree.data['message'] = 'Pausado; sesión conservada para revisión.'
        self.tree.save()

    def fail(self, message):
        if self.current: self.current.update(status='unresolved', reason=message, evidence=self.evidence)
        self.tree.unresolved(message)
        self.pause()
        self.tree.data['message'] = message
        self.tree.save()

    def resume(self):
        if not self.tree.data: raise ValueError('No hay recorrido guardado.')
        # Resume never silently retries an uncertain action or an interrupted purchase.
        if self.tree.data['unresolved'] or any(b['status'] in ('interrupted','unresolved') for b in self.tree.data['branches']):
            raise ValueError('Hay decisiones sin resolver. Revisá el informe antes de iniciar otro recorrido.')
        self.tree.data['running'] = True
        if not self.live.session:
            self.phase = 'next'
        self.deadline = time.monotonic()+300
        self.tree.save()

    def _close(self):
        report = self.live.finish(True, advance=False)
        if self.current:
            self.current['session_report'] = report['id']
            self.current['har'] = (report.get('har') or {}).get('cleanup', {})
        self.tree.save()

    def _execute(self, control):
        before = [identity(c) for c in self.live.session['snapshot']['controls']]
        result = self.live.act(self.live.session['snapshot']['id'], control['id'], automatic=True)
        self.evidence.setdefault('actions', []).append({'control': identity(control), 'before_controls': before, **result})
        if self.current: self.current['evidence']=copy.deepcopy(self.evidence)
        self.tree.save()
        return result

    def tick(self):
        if not self.running: return
        try:
            self._tick()
        except Exception as exc:
            self.fail(str(exc))

    def _tick(self):
        if time.monotonic() > self.deadline:
            raise ValueError('Tiempo de espera agotado; rama pendiente, sin repetir acciones.')
        s = self.live.session
        if self.phase == 'next':
            self.current = self.tree.next()
            if not self.current:
                self.tree.data.update(running=False, message='Recorrido comprobado.' if self.tree.complete() else 'Recorrido incompleto; revisar pendientes.')
                self.tree.save(); return
            self.position = 0; self.evidence = {}; self.round_pending = None
            self.phase = 'replay'; self.deadline = time.monotonic()+300
            self._open(); return
        if not s: raise ValueError('Se perdió la sesión de la rama.')
        snap = s['snapshot']; view = s['view']
        if snap['blockers']:
            age = [b for b in snap['blockers'] if b['name'] == 'Yes, I am 18 years or older']
            if len(age) == 1 and len(snap['blockers']) == 1 and not self.age_dismissed:
                # The operator has explicitly confirmed adulthood for these demo tests.
                self.age_dismissed = True
                self.live.dismiss(age[0]['ref'])
                return
            self.tree.data['message'] = 'Resolvé el aviso de la página para continuar.'
            self.tree.save(); return
        unresolved=list(snap.get('unresolved',[]))+list(view.get('unresolved',[]))
        if unresolved:
            baseline_paths={step['path'] for branch in self.tree.data['branches'] for step in branch['steps'] if step['role']=='buy_bonus' or step['role']=='probe' and re.search(r'(Purchase|BuyFeature)',step['path'],re.I)}
            deferred=[]; blocking=[]
            for item in unresolved:
                if self.phase in ('purchase','ante') and not idle(view) and isinstance(item,dict) and item.get('reason')=='NO_VERIFIED_VISIBLE_DRAWING' and item.get('path') in baseline_paths:
                    deferred.append({'path':item['path'],'reason':item['reason']})
                else: blocking.append(item)
            if deferred:
                self.evidence['deferred_background']=deferred
            if blocking: raise ValueError('El extractor informa controles sin resolver.')
        controls = snap['controls']
        # Require the same semantic controls in two observations. Geometry may
        # pulse continuously; Live resolves the current collider and guided token
        # again, and rejects changes in semantic identity or catalog rule.
        signature = json.dumps(sorted([identity(c) for c in controls],key=lambda x:(x['path'],x['role'])),sort_keys=True)
        if self.stable_snapshot != signature:
            self.stable_snapshot = signature
            return
        if self.phase == 'discover':
            if not controls: return
            self.tree.discover([], controls)
            self._close(); self.phase = 'next'; return
        if self.phase == 'replay':
            step = self.current['steps'][self.position]
            choices = [c for c in controls if match(c, step)]
            if len(choices) != 1:
                self.wait_count += 1
                if self.wait_count < 5 or not idle(view): return
                raise ValueError('No se pudo localizar una única acción del camino: '+step['path'])
            self.wait_count = 0
            c = choices[0]
            before = copy.deepcopy(view)
            if step['role'] == 'ante_bet' and ante_active(before):
                raise ValueError('La sesión comenzó con ante bet activo; falta comprobar OFF → ON.')
            result = self._execute(c)
            after = self.live.session['view']
            if not result['effect_verified']:
                raise ValueError('La acción no tuvo un efecto comprobado; no se reintenta.')
            self.position += 1
            self.tree.data['message'] = 'Recorriendo: ' + ' → '.join(x['role'] for x in self.current['steps'])
            self.tree.save()
            if self.position < len(self.current['steps']): return
            role = step['role']
            activated=(result.get('before_wager',{}).get('betLevelIndex')==0 and ante_active(after))
            if role == 'ante_bet' or role=='probe' and activated:
                if not ante_active(after): raise ValueError('No se comprobó ante bet activado.')
                self.evidence.update(activated=True, rounds=[], ante_level=after['wager']['betLevelIndex'],observed_function='ante_bet')
                self.phase = 'ante'
            elif result['outcome'].get('operationStarted'):
                self.phase = 'purchase'
            elif role == 'cancel':
                parent=self.evidence['actions'][-2]['control'] if len(self.evidence['actions'])>1 else None
                returned=self.live.session['snapshot']['controls']
                if parent and not any(match(c,parent) for c in returned):
                    raise ValueError('Cancelar no devolvió al control de compra anterior.')
                self.evidence['returned'] = True
                self._done()
            else:
                earlier=[a['control'] for a in self.evidence.get('actions',[])[:-1]]
                returned=self.live.session['snapshot']['controls']
                if role=='probe' and any(any(match(c,ancestor) for c in returned) for ancestor in earlier):
                    self.evidence.update(returned=True,observed_function='return_to_ancestor')
                    if self.live.session.get('purchase_started') and not self.live.session['purchase_complete']:
                        self.phase='purchase'
                    else:
                        if self.live.session['purchase_complete']:self.evidence['purchase_complete']=True
                        self._done()
                    return
                previous_controls=self.evidence['actions'][-1]['before_controls']
                newly_shown=[c for c in self.live.session['snapshot']['controls'] if identity(c) not in previous_controls]
                discovered = self.tree.discover(self.current['steps'], newly_shown)
                if not discovered:
                    raise ValueError('La rama no mostró nuevos controles verificables.')
                self.evidence['children_discovered'] = discovered
                self._done()
            return
        if self.phase in ('ante', 'purchase'):
            # Continue areas may be full-screen colliders, but must have explicit catalog semantics.
            continuations = [c for c in controls if c['classification'].get('source') == 'catalog' and c['classification']['role'] == 'continue']
            if continuations:
                if len(continuations) != 1: raise ValueError('Más de una continuación; requiere revisión.')
                path=identity(continuations[0])
                if path in self.evidence.get('continued_paths',[]): return
                self.evidence.setdefault('continued_paths',[]).append(path)
                self._execute(continuations[0]); return
            if self.phase=='purchase' and idle(view) and s['purchase_complete']:
                self.evidence['purchase_complete']=True
                self._done();return
            unknown = [c for c in controls if c['classification'].get('source') != 'catalog' and not c.get('decision',{}).get('eligible')]
            if unknown: raise ValueError('Hay un control sin acción guiada durante la ronda; revisar su función.')
            choices=[c for c in controls if c.get('decision',{}).get('eligible') and c['decision']['role'] in ('probe','choice','confirm','cancel')]
            if choices:
                if self.phase=='ante':raise ValueError('La tirada de ante bet abrió opciones; falta completar sus dos rondas.')
                prefix=[a['control'] for a in self.evidence.get('actions',[])]
                count=self.tree.discover(prefix,choices)
                if not count:raise ValueError('Se repitió una decisión sin una transición comprobada.')
                self.evidence['children_discovered']=count
                self._close()
                self.current.update(status='expanded',evidence=copy.deepcopy(self.evidence))
                self.tree.save();self.phase='next';self.deadline=time.monotonic()+300;return
            if not idle(view): return
            operation = view.get('operation', {})
            if self.phase == 'purchase':
                if not s['purchase_complete']: return
                self.evidence['purchase_complete'] = True
                self._done(); return
            if self.round_pending:
                if not operation.get('submitted') or not operation.get('protocolComplete'): return
                self.round_pending.update(protocol_complete=True, ante_after=view.get('wager', {}).get('betLevelIndex'))
                if not ante_active(view) or self.round_pending['ante_after'] != self.evidence['ante_level']:
                    raise ValueError('Ante bet dejó de estar activo durante la tirada.')
                self.evidence['rounds'].append(self.round_pending)
                self.round_pending = None
                if len(self.evidence['rounds']) >= self.tree.data['rounds_required']:
                    for row in s['ledger'].values():
                        if row['role'] == 'ante_bet':
                            row['ante_rounds_complete'] = copy.deepcopy(self.evidence['rounds'])
                    self._done(); return
            if not ante_active(view): raise ValueError('Ante bet no está activo antes de girar.')
            spin = [c for c in snap.get('support_controls',[])+controls if c['classification'].get('rule') == 'normal-spin-support']
            if len(spin) != 1: raise ValueError('No hay una única tirada normal disponible.')
            # Record active ante BEFORE clicking and require a new operation-start acknowledgement.
            level = view['wager']['betLevelIndex']
            result = self._execute(spin[0])
            if result['outcome'].get('operationStarted') is not True:
                raise ValueError('No se comprobó el inicio de una nueva tirada normal.')
            self.round_pending = {'started': True, 'normal': True, 'ante_before': level,
                                  'protocol_complete': False, 'ante_after': None}

    def _done(self):
        self._close()
        self.tree.done(self.current, self.evidence)
        self.phase = 'next'
        self.deadline = time.monotonic()+300

    def state(self):
        if not self.tree.data: return None
        return {**copy.deepcopy(self.tree.data), 'validated': self.tree.complete(),
                'phase': self.phase, 'active_branch': self.current['id'] if self.current else None}
