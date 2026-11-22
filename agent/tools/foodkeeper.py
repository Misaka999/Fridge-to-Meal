"""Read-only FoodKeeper guidance with explicit storage/date semantics.

Pinned third-party archive attributed to USDA, not authenticated as the current
USDA release. No automatic inventory writes or safety guarantees.
"""
from calendar import monthrange
from copy import deepcopy
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'data/foodkeeper'
CONDITIONS={'pantry':'pantry','refrigerator':'refrigerate','freezer':'freeze'}
STAGES={'purchase','opened','thawed','as_listed'}
NOTICE='General storage guidance, not an expiration date or a food-safety guarantee.'


def norm(value):return re.sub(r'\s+',' ',str(value).strip().casefold())


def load_products(directory=DIRECTORY):
    directory=Path(directory)
    payload=(directory/'foodkeeper_en.json').read_bytes()
    provenance=json.loads((directory/'provenance.json').read_text())
    if hashlib.sha256(payload).hexdigest()!=provenance['sha256']:
        raise ValueError('FoodKeeper snapshot checksum mismatch.')
    data=json.loads(payload)
    products=data.get('product_data')
    if not isinstance(products,list) or any(not isinstance(p,dict) or not p.get('id') or not p.get('name') for p in products):
        raise ValueError('Unsupported FoodKeeper snapshot shape.')
    return products,provenance


def _field(condition,stage):
    prefix=CONDITIONS[condition]
    if stage=='purchase':return f'from_date_of_purchase_{prefix}_output_display_only'
    if stage=='opened':return f'{prefix}_after_opening_output_display_only'
    if stage=='thawed':return f'{prefix}_after_thawing_output_display_only'
    return f'{prefix}_output_display_only'


def _iso(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Use YYYY-MM-DD.')
    return date.fromisoformat(value)


def _add(start,quantity,unit):
    if unit=='days':return start+timedelta(days=quantity)
    if unit=='weeks':return start+timedelta(weeks=quantity)
    months=quantity*(12 if unit=='years' else 1)
    ordinal=start.year*12+start.month-1+months;year,month=divmod(ordinal,12);month+=1
    return date(year,month,min(start.day,monthrange(year,month)[1]))


def lookup_storage(food,condition=None,stage=None,reference_date=None,as_of_date=None,
                   product_id=None,stored_as_directed=False,directory=DIRECTORY):
    """Exact product names first; keywords may suggest candidates, never select one."""
    def reply(status,**fields):return {'status':status,'notice':NOTICE,**fields}
    try:products,provenance=load_products(directory)
    except (OSError,ValueError,KeyError) as exc:
        return reply('error',error_code='FOODKEEPER_UNAVAILABLE',error_type=type(exc).__name__)
    if not isinstance(food,str) or not food.strip():return reply('needs_clarification',message='Provide the food name.')
    query=norm(food)
    if query=='egg':query='eggs'
    if query=='carrot':query='carrots'
    if product_id is not None:
        matches=[p for p in products if p['id']==str(product_id)]
    else:
        query=norm(food)
        if query=='egg':query='eggs'
        if query=='carrot':query='carrots'
        matches=[p for p in products if norm(p['name'])==query]
        if not matches:
            suggestions=[p for p in products if query in {norm(x) for x in (p.get('keywords') or '').split(',')}]
            return reply('needs_clarification' if suggestions else 'not_found',
                         message='Confirm a specific product and variety; keyword matches are not an identity match.',
                         candidates=[{'id':p['id'],'name':p['name'],'subtitle':p.get('name_subtitle')} for p in suggestions[:12]])
    if not matches:return reply('not_found',message='No matching product ID in the pinned snapshot.')
    if len(matches)>1:
        return reply('needs_clarification',message='Which food variety or preparation state?',
                     candidates=[{'id':p['id'],'name':p['name'],'subtitle':p.get('name_subtitle')} for p in matches])
    product=matches[0]
    if product_id is not None and query!=norm(product['name']) and query not in {norm(x) for x in (product.get('keywords') or '').split(',')}:
        return reply('needs_clarification',message='The selected product ID does not match the stated food. Confirm the variety.')
    identity={'id':product['id'],'name':product['name'],'subtitle':product.get('name_subtitle')}
    source={'official_catalogue':provenance['official_catalogue'],'archive':provenance['retrieved_from'],
            'snapshot_sha256':provenance['sha256'],'official_fetch_status':provenance['official_fetch_status']}
    if condition not in CONDITIONS:return reply('needs_clarification',product=identity,message='Specify pantry, refrigerator, or freezer.')
    if stage not in STAGES:return reply('needs_clarification',product=identity,message='Specify purchase, opened, thawed, or as_listed date basis.')
    field=_field(condition,stage);text=product.get(field)
    if not text:
        return reply('not_available',product=identity,condition=condition,stage=stage,source=source,
                     message='No guidance for this exact condition and stage; another condition is not substituted.')
    output={'product':identity,'condition':condition,'stage':stage,'guidance_text':text,
            'source_field':field,'source':source,
            'tips':product.get(field.replace('output_display_only','tips'))}
    if reference_date is None or as_of_date is None:
        return reply('needs_clarification',**output,message='Provide the matching reference date and as_of_date; no date is inferred.')
    try:start=_iso(reference_date);today=_iso(as_of_date)
    except ValueError:return reply('needs_clarification',**output,message='Provide valid YYYY-MM-DD dates.')
    if start>today:return reply('needs_clarification',**output,message='The reference date cannot be after as_of_date.')
    if stored_as_directed is not True:
        return reply('needs_clarification',**output,message='Confirm that the stated storage conditions were maintained; no dated window is inferred.')
    match=re.fullmatch(r'\s*(\d+)(?:\s*[-–]\s*(\d+))?\s+(Days?|Weeks?|Months?|Years?)\s*',text,re.I)
    if not match:return reply('guidance_only',**output,message='Qualitative guidance is retained; no numeric date is invented.')
    lower=int(match[1]);upper=int(match[2] or match[1]);unit=match[3].lower().rstrip('s')+'s'
    if upper<lower:return reply('guidance_only',**output,message='Conflicting source interval; do not compute dates.')
    first=_add(start,lower,unit);last=_add(start,upper,unit)
    return reply('found',**output,reference_date=reference_date,
                 guidance_window={'start':first.isoformat(),'end':last.isoformat(),
                                  'kind':'general storage-quality guidance, not expires_on'},
                 window_ended=today>last,
                 next_action='Ask for updated condition information; do not assert safety.' if today>last else 'May inform priority; date alone does not prove safety.')


def inspect_pantry_storage(request):
    """Inspect supplied metadata; leave missing expiry and authoritative inventory untouched."""
    findings=[]
    for item in request.get('pantry',[]):
        if 'storage' not in item:continue
        meta=item['storage']
        if not isinstance(meta,dict):
            findings.append({'food':item.get('name'),'result':{'status':'needs_clarification','message':'Provide structured storage metadata.'}});continue
        allowed={k:meta.get(k) for k in ['condition','stage','reference_date','product_id','stored_as_directed'] if k in meta}
        findings.append({'food':item['name'],'result':lookup_storage(item['name'],as_of_date=request.get('as_of_date'),**allowed)})
    return {'findings':findings,'notice':NOTICE,'inventory_changed':False}


def assess_unknown_storage(request):
    """Optional source guidance for explicit metadata; never set expires_on."""
    subset={**request,'pantry':[x for x in request.get('pantry',[]) if x.get('expires_on') is None and 'storage' in x]}
    inspection=inspect_pantry_storage(subset)
    priority={};notes=[]
    for item in inspection['findings']:
        result=item['result'];status=result['status']
        if status=='error':
            return {'issue':{'status':'error','candidates':[],'error_code':'FOODKEEPER_UNAVAILABLE'},'priority_dates':{},'notes':notes}
        if status!='found' or result.get('window_ended'):
            return {'issue':{'status':'error','candidates':[],'error_code':'INPUT_INCOMPLETE',
                             'missing_field':'pantry.storage','message':result.get('message') or result.get('next_action') or 'Confirm storage details before using this guidance.'},
                    'priority_dates':{},'notes':notes}
        from .ingredient_names import normalize_name
        name=normalize_name(item['food']);end=result['guidance_window']['end']
        priority[name]=min(priority.get(name,end),end)
        notes.append({'food':item['food'],'guidance_window':result['guidance_window'],
                      'source':result['source'],'notice':NOTICE})
    return {'issue':None,'priority_dates':priority,'notes':notes}
