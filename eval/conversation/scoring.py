"""Independent end-state and outcome checks; no production proposal validator."""
from collections import defaultdict
import math
import re
from agent.tools.ingredient_names import normalize_name
from agent.tools.recipe_search import UNITS

BANNED={'vegan':{'egg','milk','butter','cheese','honey','chicken','beef','fish'},
        'vegetarian':{'chicken','beef','fish','pork'},'egg-free':{'egg'},
        'dairy-free':{'milk','butter','cheese','cream'},'soy-free':{'tofu','soy sauce'},
        'peanut-free':{'peanut','peanut butter'}}


def stock(state):
    values=defaultdict(float)
    for item in state.get('pantry') or []:
        if not isinstance(item,dict) or type(item.get('quantity')) not in (int,float):raise ValueError('Invalid pantry quantity.')
        if not math.isfinite(item['quantity']) or item['quantity']<0:raise ValueError('Invalid pantry quantity.')
        unit,factor=UNITS[item['unit']]
        values[(normalize_name(item['name']),unit,item.get('expires_on'))]+=item['quantity']*factor
    return dict(values)


def matching_state(actual, expected):
    errors=[]
    if not isinstance(actual,dict):return ['Missing/invalid request state.']
    for key in ('servings','as_of_date'):
        if type(actual.get(key))!=type(expected.get(key)) or actual.get(key)!=expected.get(key):errors.append('Incorrect '+key)
    for field in ('likes','dietary_restrictions'):
        prefs=actual.get('preferences')
        value=prefs.get(field) if isinstance(prefs,dict) else None
        if not isinstance(value,list) or any(not isinstance(x,str) for x in value) or sorted(value)!=sorted(expected['preferences'][field]):errors.append('Incorrect '+field)
    try:
        a,b=stock(actual),stock(expected)
        if a.keys()!=b.keys() or any(abs(a[k]-b[k])>1e-6 for k in a):errors.append('Pantry differs from the reference state.')
    except (KeyError,TypeError,ValueError):errors.append('Invalid pantry representation.')
    return errors


def grade_turn(output, reference, catalogue):
    """Grade observable state/contract separately from open-ended answer quality."""
    errors=[];checks={};answer=output.get('result') or {}
    if not isinstance(answer,dict):errors.append('Invalid result object.');answer={}
    status=answer.get('status')
    if output.get('error'):errors.append('Runtime/parse failure.')
    errors+=matching_state(output.get('request') or {},reference['state'])
    focus=output.get('meal_ingredients',[])
    if not isinstance(focus,list) or any(not isinstance(x,str) for x in focus) or set(focus)!=set(reference.get('focus',[])):errors.append('Incorrect explicit meal focus.')
    pending=output.get('pending_inventory',[])
    try:
        if {normalize_name(x['name']) for x in pending}!=set(reference.get('pending_foods',[])):errors.append('Incorrect pending ingredient details.')
    except (KeyError,TypeError):errors.append('Invalid pending ingredient details.')
    if not isinstance(answer.get('message'),str) or not answer['message'].strip():errors.append('Missing response text.')
    ids=answer.get('recipe_ids')
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):errors.append('Invalid recipe IDs.');ids=[]
    if len(ids)!=len(set(ids)) or len(ids)>3:errors.append('Duplicate/excess recipe IDs.')
    if status not in {'recommended','needs_clarification','no_feasible_recipe','tool_error'}:errors.append('Invalid answer status.')
    if status!='recommended' and ids:errors.append('Conditional/non-recommendation has selected IDs.')
    mode=reference['mode']
    if mode=='recommend' and status!='recommended':errors.append('A known feasible recommendation was not delivered.')
    if mode=='clarify' and status!='needs_clarification':errors.append('A required clarification was not requested.')
    if mode=='no_usable' and status not in {'needs_clarification','no_feasible_recipe'}:errors.append('Unusable pantry produced a ready recommendation.')
    if mode=='conditional' and status not in {'needs_clarification','no_feasible_recipe'}:errors.append('Conditional idea was mislabeled as ready to cook.')
    by_id={r['id']:r for r in catalogue};state=reference['state'];available=defaultdict(float)
    for (name,unit,expires),q in stock(state).items():
        if not expires or expires>=state['as_of_date']:available[(name,unit)]+=q
    if status=='recommended':
        if not 1<=len(ids)<=3:errors.append('Missing selected recipes.')
        drafts=output.get('adapted_recipes',[])
        if not isinstance(drafts,list) or any(not isinstance(d,dict) for d in drafts):
            errors.append('Malformed adaptations.');drafts=[]
        if drafts and [d.get('source_recipe_id') for d in drafts]!=ids:errors.append('Adaptations and selected IDs disagree.')
        if not drafts:
            drafts=[]
            for rid in ids:
                recipe=by_id.get(rid,{})
                if recipe.get('quantity_verified') is False or not recipe.get('servings'):
                    errors.append('Unverified source selected without explicit adaptation.');continue
                drafts.append({**recipe,'source_recipe_id':rid,'servings':state['servings'],
                    'ingredients':[{**i,'quantity':i['quantity']*state['servings']/recipe['servings']} for i in recipe['ingredients']]})
        for draft in drafts:
            if not isinstance(draft.get('source_recipe_id'),str) or draft['source_recipe_id'] not in by_id:errors.append('Invented source ID.')
            if draft.get('servings')!=state['servings']:errors.append('Recipe servings disagree.')
            used=defaultdict(float);names=set()
            for item in draft.get('ingredients',[]):
                try:
                    name=normalize_name(item['name']);q=item['quantity'];dim,factor=UNITS[item['unit']]
                    if type(q) not in (int,float) or not math.isfinite(q) or q<=0:raise ValueError()
                    used[(name,dim)]+=q*factor;names.add(name)
                except (KeyError,TypeError,ValueError):errors.append('Invalid recipe amount.')
            if not names-{'water'}:errors.append('Missing food ingredients.')
            for key,q in used.items():
                if key[0]!='water' and q>available.get(key,0)+1e-6:errors.append('Pantry budget exceeded: '+key[0])
            for rule in state['preferences']['dietary_restrictions']:
                if names&BANNED.get(rule,set()):errors.append('Dietary conflict: '+rule)
            if not set(reference.get('focus',[]))<=names:errors.append('Chosen meal ingredient omitted.')
            if not draft.get('steps'):errors.append('Missing cooking steps.')
            # Bounded independent checks of literal step quantities and hard-diet
            # terms. Open-ended preparation feasibility remains a judge/audit task.
            for step in draft.get('steps',[]) if isinstance(draft.get('steps'),list) else []:
                if not isinstance(step,str):errors.append('Invalid cooking step.');continue
                for rule in state['preferences']['dietary_restrictions']:
                    for food in BANNED.get(rule,set()):
                        for match in re.finditer(r'\b'+re.escape(food)+r'(?:s|es)?\b',step,re.I):
                            if not re.search(r'\b(?:omit|without|no|do not add)\b[^.;]{0,25}$',step[:match.start()],re.I):errors.append('Step dietary conflict: '+rule)
                for (name,dim),amount in used.items():
                    pattern=r'\b(\d+(?:\.\d+)?)\s*(g|kg|ml|l|count|tbsp|tsp|cup)?\s*(?:of\s+)?(?:the\s+)?'+re.escape(name)+r'(?:s|es)?\b'
                    for match in re.finditer(pattern,step,re.I):
                        unit=match[2].lower() if match[2] else 'count';step_dim,factor=UNITS[unit]
                        if step_dim==dim and float(match[1])*factor>amount+1e-6:errors.append('Step quantity exceeds the declared amount: '+name)
    # Conditional content is checked through a common, evidence-backed contract.
    # Unstructured natural-language matches require judge/human review, never guessed.
    alternatives=output.get('conditional_options',[])
    if mode=='conditional':
        if not isinstance(alternatives,list) or not 1<=len(alternatives)<=3:errors.append('Missing 1-3 structured conditional options.')
        else:
            seen=set();required=reference.get('acceptable_gaps',{})
            for option in alternatives:
                if not isinstance(option,dict):errors.append('Malformed conditional option.');continue
                rid=option.get('recipe_id')
                if not isinstance(rid,str):errors.append('Invalid conditional source ID.');continue
                if rid in seen or rid not in required:errors.append('Unacceptable or duplicate conditional source.')
                seen.add(rid)
                gaps=option.get('missing_ingredients',[])
                if not isinstance(gaps,list) or any(not isinstance(x,str) for x in gaps) or sorted(gaps)!=sorted(required.get(rid,[])):errors.append('Incorrect conditional ingredient gaps.')
                if option.get('ready_to_cook') is not False:errors.append('Conditional option incorrectly declared ready.')
                title=by_id.get(rid,{}).get('title','').strip()
                text=answer.get('message','')
                if title and title.casefold() not in text.casefold():errors.append('Conditional recipe is absent from the user-facing answer.')
                if isinstance(gaps,list) and any(isinstance(g,str) and g.casefold() not in text.casefold() for g in gaps):errors.append('Ingredient gaps are absent from the user-facing answer.')
        checks['conditional_contract_checked']=True
    return {'passed':not errors,'failures':sorted(set(errors)),'checks':checks}
