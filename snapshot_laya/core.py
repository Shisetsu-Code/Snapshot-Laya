import hashlib
import json
import math
import re

ROLES = {'buy_bonus','ante_bet','bet_up','bet_down','bet_menu','confirm','cancel','choice','continue','spin','other','unknown'}
TARGETS = {'buy_bonus','ante_bet','bet_up','bet_down','bet_menu','confirm','choice','unknown'}
NOISE = re.compile(r'(SoundButtons|Autoplay|HyperPlay|HiperPlay|GameSpeed|/Paytable/|/Settings/|MoneyAndCoinsSwitcher)',re.I)


def clean_snapshot(raw, blockers=None):
    blockers = blockers or []
    width=raw.get('image_size',{}).get('width',0)
    height=raw.get('image_size',{}).get('height',0)
    kept, discarded, seen = [], [], set()
    for item in raw.get('controls',[]):
        rect=item.get('hit_rect') or {}
        numbers=[rect.get(k) for k in ('x','y','width','height')]
        reason=None
        if blockers: reason='page_overlay'
        elif raw.get('modal_roots') and not any(item.get('path','').startswith(root) for root in raw['modal_roots']): reason='behind_runtime_modal'
        elif item.get('enabled') is not True or item.get('visible') is False or item.get('alpha')==0: reason='hidden_or_disabled'
        elif item.get('clickable')!='RUNTIME_COLLIDER': reason='no_verified_hit_target'
        elif any(not isinstance(n,(float,int)) or not math.isfinite(n) for n in numbers): reason='missing_hit_rect'
        elif rect['width']<=0 or rect['height']<=0: reason='empty_hit_rect'
        elif not (0<=rect['x']+rect['width']/2<width and 0<=rect['y']+rect['height']/2<height): reason='outside_viewport'
        elif NOISE.search(item.get('path','')): reason='unrelated_universal_ui'
        key=(item.get('path'),tuple(numbers))
        if not reason and key in seen: reason='duplicate'
        if reason:
            discarded.append({'id':item.get('id'),'name':item.get('name'),'reason':reason})
            continue
        seen.add(key)
        events=[h.get('event') for h in item.get('handlers',[]) if h.get('event')]
        semantic={'name':item.get('name',''),'path':item.get('path',''),
            'labels':item.get('labels',[]),'sprites':item.get('sprite_names',[]),'events':events}
        kept.append({**item,'model_input':semantic,'occlusion':item.get('occlusion','NOT_VERIFIED')})
    visual_identity={'controls':[(c['model_input'],c['hit_rect'],c.get('drawn_rect'),c.get('occlusion')) for c in kept],
        'image_size':raw.get('image_size'),'state_key':raw.get('state_key'),'blockers':blockers,'modal_roots':raw.get('modal_roots',[])}
    digest=hashlib.sha256(json.dumps(visual_identity,sort_keys=True).encode()).hexdigest()[:20]
    return {'id':digest,'capture_id':raw.get('capture_id'),'controls':kept,'discarded':discarded,
        'blockers':blockers,'unresolved':raw.get('unresolved',[]),'occlusion_verified':raw.get('occlusion_verified',False),
        'image_size':raw.get('image_size',{}),'screenshot':raw.get('full_path'),
        'visibility_scope':'rendered_runtime_controls; occlusion requires visual review'}


def completion(ledger, flags, unresolved, observations, purchase_complete=False):
    reasons=[]
    if not observations or not ledger: reasons.append('No hay controles comprobados.')
    if any(c.get('status')!='verified' for c in ledger): reasons.append('Hay controles observados pendientes o no verificados.')
    if unresolved: reasons.append('El extractor informa controles o bloqueos sin resolver.')
    if any(flags.get(k) for k in ('logicIsFreeSpin','respinInProgress','spinBlockingFeatureIsRunning','stopActive','lastWinIsCounting','waitInResultForBigWin')):
        reasons.append('La ronda o el bonus sigue activo.')
    if any(c.get('role') in ('buy_bonus','confirm') for c in ledger) and not purchase_complete:
        reasons.append('Falta comprobar la finalización del protocolo de compra.')
    return {'validated':not reasons,'scope':'observed_controls_and_visited_states','reasons':reasons,
        'exhaustive_game_coverage':False}


def evidence_effect(role,before,after,outcome):
    if role=='ante_bet':
        a,b=before.get('wager',{}).get('betLevelIndex'),after.get('wager',{}).get('betLevelIndex')
        return a is not None and b is not None and a!=b
    if role in ('bet_up','bet_down'):
        return bool(before.get('bet_signature') and after.get('bet_signature') and before['bet_signature']!=after['bet_signature'])
    if role=='confirm': return outcome.get('operationStarted') is True
    if role in ('buy_bonus','continue','choice') and outcome.get('operationStarted') is True: return True
    return outcome.get('reason')=='STATE_CHANGED' and before.get('state_key')!=after.get('state_key')


def valid_demo_url(url):
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('www.pragmaticplay.com','pragmaticplay.com') or not parsed.path.startswith('/en/games/') or parsed.query or parsed.fragment:
        raise ValueError('Usá una URL oficial https://www.pragmaticplay.com/en/games/.../ sin parámetros ni sesión.')
    return url
