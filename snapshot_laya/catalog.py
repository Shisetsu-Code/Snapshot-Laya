"""Shared Pragmatic interface signatures. These are rules, not trained weights."""
import re

TARGET_ROLES = {'buy_bonus', 'ante_bet', 'confirm', 'cancel', 'choice', 'continue', 'probe'}


def known(control):
    name = control.get('name', '')
    path = control.get('path', '')
    labels = ' '.join(control.get('labels', [])).replace('\n', ' ')
    role = rule = None
    purchase = bool(re.search(r'(Purchase|BuyFeature)', path, re.I))
    if purchase and name == 'CloseCollider' and '/BuyWindow/' in path:
        role, rule = 'other', 'purchase-window-backdrop'
    elif purchase and re.fullmatch(r'(ButtonYes|YesButton|ConfirmButton)', name, re.I):
        role, rule = 'confirm', 'purchase-confirm'
    elif purchase and re.fullmatch(r'(ButtonNo|NoButton|CancelButton|CloseButton)', name, re.I):
        role, rule = 'cancel', 'purchase-cancel'
    elif re.search(r'(BetLevel|AnteBet|DoubleChance)', path, re.I) and re.search(r'(Level\d+Button|Level_\d+|AnteBet|Toggle)', name, re.I) and (re.search(r'(DOUBLE\s+CHANCE|ANTE\s*BET|EXTRA\s*BET|BONUS\s*BOOST)', labels, re.I) or re.search(r'(AnteBet|DoubleChance)', path, re.I)):
        role, rule = 'ante_bet', 'ante-level-toggle'
    elif purchase and re.search(r'(BuyButtons|PurchaseButton|/Options/)', path, re.I) and re.search(r'\b(BUY|PURCHASE)\b', labels, re.I):
        role, rule = 'buy_bonus', 'purchase-option'
    elif name == 'StartSpin_Button' and '/SpinButtons/' in path:
        role, rule = 'spin', 'normal-spin-support'
    elif '/SpinButtons/StopSpin_Button' in path:
        role, rule = 'other', 'spin-stop-out-of-scope'
    elif name in ('BetUp_Button', 'BetDown_Button'):
        role, rule = 'other', 'regular-bet-out-of-scope'
    elif re.fullmatch(r'(ButtonContinue|ContinueButton|CollectButton)', name, re.I) and re.search(r'(FreeSpin|Bonus|Result|Win|Feature|FSWindows)', path, re.I):
        role, rule = 'continue', 'bonus-continue'
    elif re.search(r'(click|tap|touch)\s+(anywhere|to continue)|press anywhere', labels, re.I) and re.search(r'(Continue|Intro|Outro|Result|FreeSpin|Bonus|FSWindows)', path, re.I) and name.lower() != 'blocker':
        role, rule = 'continue', 'explicit-continue-area'
    if role is None:
        return None
    return {'role': role, 'source': 'catalog', 'rule': rule, 'confidence': None,
            'needs_review': False, 'milliseconds': 0, 'cached': False,
            'calibrated_for_game': False}


def identity(control):
    path = control.get('path', '')
    role=control.get('decision',{}).get('role',control['classification']['role'])
    if role == 'ante_bet':
        path = re.sub(r'Level\d+Button|Level_\d+', 'AnteToggle', path)
    return {'path': path, 'role': role}


def decision(control):
    """Branch eligibility is independent of the model's semantic guess."""
    signature=known(control)
    if signature:
        return {'role':signature['role'],'source':'catalog','rule':signature['rule'],
                'eligible':bool(control.get('action_id')) and signature['role']!='other'}
    path=control.get('path','')
    eligible=bool(control.get('action_id') and control.get('clickable')=='RUNTIME_COLLIDER'
                  and control.get('enabled') is True and control.get('visible') is not False
                  and control.get('alpha')!=0 and '/Game/' in path and '/GUI/' not in path)
    return {'role':'probe','source':'rendered_probe','eligible':eligible,
            'reason':'current drawn game control with guided action' if eligible else 'no verified scoped guided action'}


def common_interface(control):
    signature=known(control)
    if signature and signature['role'] in TARGET_ROLES:return False
    return bool('/GUI/' in control.get('path','') or signature and signature['role']=='other')


def match(control, step):
    return identity(control) == step


def modal_roots(controls):
    roots = set()
    for c in controls:
        if c.get('enabled') is not True or c.get('visible') is False or c.get('alpha') == 0 or c.get('clickable') != 'RUNTIME_COLLIDER':
            continue
        if not re.fullmatch(r'(ButtonYes|ButtonNo|ButtonOpt\d+|ConfirmButton|CancelButton)', c.get('name', ''), re.I):
            continue
        parts = c.get('path', '').split('/')
        for i, part in enumerate(parts):
            if re.search(r'(Purchase.*Window|PurchaseWindow|Popup|Dialog)', part, re.I):
                roots.add('/'.join(parts[:i + 1]) + '/')
    return sorted(roots)
