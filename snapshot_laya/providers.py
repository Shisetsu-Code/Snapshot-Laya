"""Catalog preparation; runtime support must be verified per provider."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit,urlencode

PLAYTECH_CATALOG='https://www.playtechone.com/es/view-more/casino-2026/slots/'


def playtech_catalog_state(url,elements):
    """Classify observed page controls, never treat login as an empty game."""
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in ('www.playtechone.com','playtechone.com'):
        raise ValueError('El catálogo de Playtech debe estar en playtechone.com.')
    visible=[e for e in elements if e.get('visible') is True]
    names={' '.join((e.get('name') or e.get('text') or '').upper().split()) for e in visible}
    cookies=next((e for e in visible if ' '.join((e.get('name') or e.get('text') or '').upper().split())=='REJECT ALL'
                  and e.get('enabled') is True and e.get('ref')),None)
    login=bool({'USERNAME','PASSWORD','LOG IN'} <= names)
    age=bool({'DAY','MONTH','YEAR','ENTER'} <= names)
    return {'provider':'playtech','catalog_url':PLAYTECH_CATALOG,
            'status':'login_required' if login else 'age_verification_required' if age else 'cookie_notice' if cookies else 'catalog_inspection',
            'cookie_action':{'ref':cookies['ref'],'name':'REJECT ALL'} if cookies else None,
            'runtime_adapter_ready':False,'purchase_search_ready':False,
            'note':'El extractor actual es de Pragmatic; no aplicar sus rutas o validación de protocolo a Playtech.'}


def provider_status():
    return [{'provider':'pragmatic','runtime_adapter_ready':True},
            {'provider':'playtech','catalog_url':PLAYTECH_CATALOG,'runtime_adapter_ready':False,
             'stage':'catalog_and_direct_demo_preparation','launch_mode':'direct_offline_real_0',
             'common_ui_profile':'common_ui_v1','ocr_analysis':'/api/providers/playtech/analyze',
             'cookies':'REJECT ALL','age':'operator_supplied_only'}]


def playtech_demo_url(code):
    if not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,100}',code):
        raise ValueError('Código de juego de Playtech inválido.')
    return 'https://cachedownload.playtechone.com/ngmdesktop/casinoclient.html?'+urlencode({'game':code,'preferedmode':'offline','real':'0'})


def playtech_catalog():
    doc=json.loads(Path(__file__).with_name('playtech-catalog.json').read_text(encoding='utf-8'))
    games=[{**g,'demo_url':playtech_demo_url(g['symbol'])} for g in doc['games']]
    return {**doc,'games':games,'runtime_adapter_ready':False,'launch_mode':'direct_offline_real_0'}
