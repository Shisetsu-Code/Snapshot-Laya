"""Conservative common-UI filtering for Playtech OCR, not a runtime hit adapter."""
import math
import re
import unicodedata


COMMON=re.compile(r'^(TOTAL BET|COIN VALUE|BET|BET OPTIONS|BALANCE|CREDITS?|WIN|TOTAL WIN|LINES|WAYS|AUTO|AUTO PLAY|AUTOPLAY|HOLD FOR AUTOPLAY|TURBO|TURBO MODE|MODE|INFO|INF|INFORMATION|HELP|PAYTABLE|RULES|GAME RULES|SOUND|MUSIC|VOLUME|SETTINGS|LOBBY|BLITZ LOBBY|PLAYTECH|PLAYING FOR FUN|APUESTA TOTAL|SALDO|GANANCIA|SONIDO|AYUDA)$')
SPIN=re.compile(r'^(SPIN|START SPIN|GIRAR)$')
DIRECT=re.compile(r'\b(BUY|PURCHASE|FEATURE|EXTRA BET|ANTE(?: BET)?|DOUBLE CHANCE|BONUS BOOST|CONFIRM|CANCEL|CONTINUE|COLLECT|CHOOSE)\b')
CAPTION=re.compile(r'^(HIGHER CHANCE|TO TRIGGER BONUS|MORE CATS?)$')


def normalized(text):
    return ' '.join(re.sub(r'[^A-Z0-9 ]',' ',unicodedata.normalize('NFKD',text).upper()).split())


def nearby(a,b,distance=140):
    return abs(a['rect']['x']-b['rect']['x'])<250 and abs(a['rect']['y']-b['rect']['y'])<distance


def filter_playtech_ocr(snapshot,stage='base',game_name=''):
    width,height=snapshot.get('width'),snapshot.get('height')
    if not all(isinstance(n,(float,int)) and math.isfinite(n) and n>0 for n in (width,height)):
        raise ValueError('Falta el tamaño válido de la captura OCR.')
    raw=snapshot.get('lines',[])
    if not isinstance(raw,list) or len(raw)>500:raise ValueError('El OCR admite hasta 500 líneas.')
    lines=[]
    for i,item in enumerate(raw):
        text=item.get('text');rect=item.get('rect') or {}
        if not isinstance(text,str) or len(text)>500:raise ValueError('Texto OCR inválido o demasiado largo.')
        values=[rect.get(k) for k in ('x','y','width','height')]
        if not all(isinstance(n,(float,int)) and math.isfinite(n) for n in values) or min(values[2:])<=0:
            raise ValueError('Geometría OCR inválida.')
        if not (0<=rect['x']+rect['width']/2<width and 0<=rect['y']+rect['height']/2<height):
            raise ValueError('Texto OCR fuera de la captura.')
        lines.append({'index':i,'text':text.strip(),'normalized':normalized(text),'rect':dict(rect)})
    ignored=[];support=[];unclassified=[];anchors=[]
    for item in lines:
        n=item['normalized']
        # Targets win over common words: EXTRA BET is never discarded as BET.
        direct=bool(DIRECT.search(n))
        toggle=bool((CAPTION.fullmatch(n) and any(x['normalized'] in ('ON','OFF') and nearby(item,x) for x in lines))
                    or n in ('ON','OFF') and any((CAPTION.fullmatch(x['normalized']) or re.search(r'\b(EXTRA BET|ANTE|DOUBLE CHANCE)\b',x['normalized'])) and nearby(item,x) for x in lines))
        if direct or toggle:
            anchors.append(dict(item,kind='toggle' if toggle or re.search(r'\b(EXTRA BET|ANTE|DOUBLE CHANCE|BONUS BOOST)\b',n) else 'action'))
        elif SPIN.fullmatch(n):
            support.append({**item,'role':'spin','reason':'normal_spin_support','click_target_verified':False})
        elif COMMON.fullmatch(n) or game_name and n==normalized(game_name):
            ignored.append({**item,'reason':'known_common_interface'})
        else:
            unclassified.append({**item,'reason':'not_identified_as_common_interface'})
    ignored_ids={x['index'] for x in ignored+support}
    groups=[]
    for item in sorted(anchors,key=lambda x:(x['rect']['y'],x['rect']['x'])):
        group=next((g for g in groups if any(
            nearby(item,x,80) and {item['normalized'],x['normalized']}=={'BUY','FEATURE'}
            or item['kind']==x['kind']=='toggle' and nearby(item,x)
            for x in g)),None)
        if group is None:groups.append([item])
        else:group.append(item)
    controls=[]
    for group in groups:
        labels=[x['text'] for x in lines if x['index'] not in ignored_ids and any(nearby(x,a) for a in group)][:16]
        name=' '.join(x['text'] for x in group)
        x=min(a['rect']['x'] for a in group);y=min(a['rect']['y'] for a in group)
        right=max(a['rect']['x']+a['rect']['width'] for a in group)
        bottom=max(a['rect']['y']+a['rect']['height'] for a in group)
        controls.append({'text':name,'ocr_rect':{'x':x,'y':y,'width':right-x,'height':bottom-y},
            'source':'ocr_text_candidate','click_target_verified':False,
            'model_input':{'name':name,'labels':labels,'sprites':[],'events':[],
                'path':'Playtech/OCR/'+re.sub(r'[^a-zA-Z0-9_-]','_',stage[:80])+'/text-'+str(group[0]['index'])}})
    return {'provider':'playtech','profile':'common_ui_v1','controls':controls,'support_controls':support,
            'ignored_common':ignored,'unclassified':unclassified,'runtime_hit_targets_verified':False,
            'stats':{'ocr_lines':len(lines),'model_candidates':len(controls),'ignored_common':len(ignored),'support_controls':len(support)}}


def analyze_playtech_ocr(snapshot,classifier,stage='base',game_name=''):
    result=filter_playtech_ocr(snapshot,stage,game_name)
    if len(result['controls'])>32:raise ValueError('Hay más de 32 candidatos; dividí la captura en paneles.')
    for control in result['controls']:
        control['classification']={**classifier.classify(control),'source':'laya_ocr'}
    result['validated']=False
    result['scope']='filtered_ocr_classification_only'
    return result
