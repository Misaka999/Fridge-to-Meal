"""Week 6 tools aligned with interface_alignment.md. No inventory writes."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import math
import os

ROOT = Path(__file__).resolve().parent
try:
    from .ingredient_names import normalize_name
except ImportError:
    from ingredient_names import normalize_name
UNITS = {'g':('g',1), 'gram':('g',1), 'grams':('g',1), 'kg':('g',1000),
         'ml':('ml',1), 'l':('ml',1000), 'count':('count',1),
         'piece':('count',1), 'pieces':('count',1),
         'lb':('g',453.59237), 'oz':('g',28.349523125),
         'cup':('ml',236.5882365), 'cups':('ml',236.5882365),
         'tbsp':('ml',14.78676478125), 'tsp':('ml',4.92892159375)}
RESTRICTIONS = {
    'vegetarian': {'chicken','beef','pork','fish'},
    'vegan': {'egg','chicken','beef','pork','fish','milk','cheese','butter'},
    'egg-free': {'egg'}, 'peanut-free': {'peanut'},
    'dairy-free': {'milk','cheese','butter'}, 'soy-free': {'tofu','soy sauce'},
}


def load_recipes(request=None, recipe_file=None):
    configured=recipe_file or os.environ.get('FRIDGE_RECIPE_FILE')
    if not configured:
        try:
            from .recipenlg_store import retrieve
        except ImportError:
            from recipenlg_store import retrieve
        if request is None:
            raise ValueError('CSV retrieval requires a request. Old fixture evaluations require an explicit FRIDGE_RECIPE_FILE.')
        raw = [] if validate_request(request) else retrieve(request)
        reviewed_path = ROOT/'data/recipes_recipenlg.json'
        reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.exists() else []
        try:
            from .recipenlg_store import matching_reviewed_records
        except ImportError:
            from recipenlg_store import matching_reviewed_records
        reviewed = matching_reviewed_records(reviewed)
        # Keep all reviewed records for strict matching; do not pre-filter the baseline.
        ids = {r['id'] for r in reviewed}
        return reviewed + [r for r in raw if r['id'] not in ids]
    path=Path(configured).expanduser()
    recipes=json.loads(path.read_text())
    if not isinstance(recipes,list) or not recipes:
        raise ValueError('Recipe collection must be a nonempty list.')
    return recipes


def clarification(message, field):
    return {'status':'needs_clarification', 'recipe_ids':[], 'message':message,
            'missing_field':field}


def validate_request(request):
    """Helper for ReAct BEFORE search. Return clarification or None."""
    if not isinstance(request, dict):
        return clarification('Provide a structured request.', 'request')
    if type(request.get('servings')) is not int or request['servings'] <= 0:
        return clarification('How many servings are needed?', 'servings')
    if not isinstance(request.get('pantry'), list):
        return clarification('Provide the pantry list; [] means empty.', 'pantry')
    prefs = request.get('preferences')
    if not isinstance(prefs, dict):
        return clarification('Provide dietary_restrictions and likes arrays.', 'preferences')
    for field in ('dietary_restrictions','likes'):
        if not isinstance(prefs.get(field), list) or any(not isinstance(x,str) for x in prefs[field]):
            return clarification(f'Provide preferences.{field} as a string array.', f'preferences.{field}')
    if any(x not in RESTRICTIONS for x in prefs['dietary_restrictions']):
        return clarification('This prototype does not support one of the restrictions; clarify it.',
                             'preferences.dietary_restrictions')
    try:
        date.fromisoformat(request['as_of_date'])
    except (KeyError,TypeError,ValueError):
        return clarification('Provide a valid as_of_date in YYYY-MM-DD format.', 'as_of_date')
    for item in request['pantry']:
        if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not item['name'].strip():
            return clarification('Provide an ingredient name.', 'pantry.name')
        q = item.get('quantity')
        if type(q) not in (int,float) or not math.isfinite(q) or q < 0:
            return clarification(f"What quantity of {item['name']} is available?", 'pantry.quantity')
        if item.get('unit') not in UNITS:
            return clarification(f"Provide a supported unit for {item['name']}; do not assume cups-to-grams.", 'pantry.unit')
        if item.get('expires_on') is not None:
            try:
                date.fromisoformat(item['expires_on'])
            except (TypeError,ValueError):
                return clarification('Provide a valid expires_on date or null.', 'pantry.expires_on')
    return None


def get_pantry(request):
    return deepcopy(request['pantry'])


def check_recipe(request, recipe_id, recipes=None):
    """Internal diagnostic helper; search_recipes applies it before returning candidates."""
    issue = validate_request(request)
    if issue:
        return issue
    recipes = load_recipes(request) if recipes is None else recipes
    recipe = next((r for r in recipes if r['id']==recipe_id), None)
    if recipe is None:
        return {'status':'error','error_code':'UNKNOWN_RECIPE'}
    if recipe.get('quantity_verified') is False:
        return {'recipe_id':recipe_id, 'feasible':False, 'unverified':True}
    stock, banned, units_by_name = {}, set(), {}
    for item in request['pantry']:
        name = normalize_name(item['name'])
        if item.get('expires_on') and item['expires_on'] < request['as_of_date']:
            continue
        unit,factor = UNITS[item['unit']]
        stock[(name,unit)] = stock.get((name,unit),0) + item['quantity']*factor
        if item['quantity']>0:
            units_by_name.setdefault(name,set()).add(unit)
    for restriction in request['preferences']['dietary_restrictions']:
        banned.update(RESTRICTIONS[restriction])
    amounts,missing,insufficient,conflicts,conversion,unknown_diet = [],[],[],[],[],[]
    if recipe.get('source')=='RecipeNLG/Gathered':
        flags=recipe.get('dietary_compatibility',{})
        for restriction in request['preferences']['dietary_restrictions']:
            if flags.get(restriction) is False:
                conflicts.append(restriction)
            elif flags.get(restriction) is not True:
                unknown_diet.append(restriction)
    for item in recipe['ingredients']:
        name,unit = item['name'],item['unit']
        needed = round(item['quantity']*request['servings']/recipe['servings'],6)
        amounts.append({'name':name,'quantity':needed,'unit':unit})
        if name == 'water':
            continue
        if name in banned:
            conflicts.append(name)
        available = stock.get((name,unit),0)
        if available<=0:
            if name in units_by_name and unit not in units_by_name[name]:
                conversion.append(name)
            else:
                missing.append(name)
        elif available+1e-9<needed:
            insufficient.append(name)
    return {'recipe_id':recipe_id,'feasible':not (missing or insufficient or conflicts or conversion or unknown_diet),
            'missing_ingredients':missing,'insufficient_quantities':insufficient,
            'dietary_conflicts':conflicts,'unknown_dietary_checks':unknown_diet,'unknown_conversions':conversion,
            'scaled_ingredients':amounts}


def prioritize_recipes(request, recipe_ids, recipes=None):
    recipes = load_recipes(request) if recipes is None else recipes
    expiry = {}
    for item in request['pantry']:
        value=item.get('expires_on')
        if value and value>=request['as_of_date'] and item['quantity']>0:
            name=normalize_name(item['name'])
            expiry[name]=min(expiry.get(name,value),value)
    likes={normalize_name(x) for x in request['preferences']['likes']}
    ranked=[]
    for rid in recipe_ids:
        check=check_recipe(request,rid,recipes)
        if not check.get('feasible'):
            continue
        names={x['name'] for x in check['scaled_ingredients']} - {'oil','salt','soy sauce'}
        earliest=min((expiry[n] for n in names if n in expiry),default='9999-12-31')
        ranked.append((earliest,-len(names & likes),rid))
    return [rid for _,_,rid in sorted(ranked)]


def search_recipes(pantry, servings, preferences, as_of_date, *, recipes=None):
    """Official interface: fully matched, scaled found/no_match/error candidates."""
    request={'pantry':pantry,'servings':servings,'preferences':preferences,'as_of_date':as_of_date}
    issue=validate_request(request)
    if issue:
        # Guard only: the ReAct should call validate_request before matching.
        # It must map INPUT_INCOMPLETE to needs_clarification, not tool_error.
        return {'status':'error','candidates':[], 'error_code':'INPUT_INCOMPLETE',
                'message':issue['message'],'missing_field':issue['missing_field']}
    try:
        recipes=load_recipes(request) if recipes is None else recipes
        unverified=[r for r in recipes if r.get('quantity_verified') is False]
        recipes=[r for r in recipes if r.get('quantity_verified') is not False]
        found=[]
        possible_unknown=[]
        dietary_unknown=[]
        for recipe in recipes:
            check=check_recipe(request,recipe['id'],recipes)
            if check['feasible']:
                found.append({'recipe_id':recipe['id'],'title':recipe['title'],
                    'servings':servings,'ingredients':check['scaled_ingredients'],
                    'steps':deepcopy(recipe['steps'])})
            elif (check.get('unknown_dietary_checks') and not check['missing_ingredients']
                  and not check['insufficient_quantities'] and not check['dietary_conflicts']):
                dietary_unknown.extend(check['unknown_dietary_checks'])
            elif (check['unknown_conversions'] and not check['missing_ingredients']
                  and not check['insufficient_quantities'] and not check['dietary_conflicts']):
                possible_unknown.extend(check['unknown_conversions'])
        if not found and dietary_unknown:
            return {'status':'error','candidates':[], 'error_code':'INPUT_INCOMPLETE',
                    'message':'Check packaged ingredient labels for: '+', '.join(sorted(set(dietary_unknown))),
                    'missing_field':'pantry.dietary_labels'}
        if not found and possible_unknown:
            return {'status':'error','candidates':[], 'error_code':'INPUT_INCOMPLETE',
                    'message':'Clarify the weight or a reliable unit conversion for: '+', '.join(sorted(set(possible_unknown))),
                    'missing_field':'pantry.unit'}
        if found:
            order=prioritize_recipes(request,[r['recipe_id'] for r in found],recipes)
            found=sorted(found,key=lambda r:order.index(r['recipe_id']))
            return {'status':'found','candidates':found,'error_code':None}
        if unverified:
            return {'status':'error','candidates':[], 'error_code':'RECIPE_DETAILS_UNVERIFIED',
                    'message':'No reviewed match. Raw retrieval hits require verification of yield, all ingredients and dietary suitability; do not guess.',
                    'retrieved_candidates':deepcopy(unverified)}
        if not os.environ.get('FRIDGE_RECIPE_FILE') and not recipes:
            return {'status':'error','candidates':[], 'error_code':'NO_RETRIEVAL_MATCH',
                    'message':'Retrieval produced no records; this is not proof no feasible recipe exists.'}
        if not os.environ.get('FRIDGE_RECIPE_FILE') and recipes:
            return {'status':'no_match','candidates':[], 'error_code':None,
                    'scope':'Reviewed local subset only; not an exhaustive search of RecipeNLG.'}
        return {'status':'no_match','candidates':[], 'error_code':None}
    except Exception:
        return {'status':'error','candidates':[],'error_code':'RECIPE_SEARCH_FAILED'}


def make_tool_registry(request, context):
    """Search accepts the agreed four fields; enforce the authoritative current state."""
    def bound_search(pantry, servings, preferences, as_of_date):
        supplied={'pantry':pantry,'servings':servings,'preferences':preferences,'as_of_date':as_of_date}
        if any(supplied[k]!=request.get(k) for k in supplied):
            return {'status':'error','candidates':[],'error_code':'REQUEST_STATE_MISMATCH',
                    'message':'Use the unchanged current request fields; do not invent inventory.'}
        return search_recipes(**supplied, recipes=context['recipes'])
    schemas=[{'type':'function','function':{'name':'search_recipes',
        'description':'Match the current pantry, servings and dietary restrictions. Returns found with scaled candidates, no_match, or error. Validate missing inputs before calling. RECIPE_DETAILS_UNVERIFIED returns raw retrieved_candidates; ask for recipe detail verification, never claim these are feasible. NO_RETRIEVAL_MATCH is not proof of infeasibility.',
        'parameters':{'type':'object','properties':{
            'pantry':{'type':'array','items':{'type':'object','properties':{
                'name':{'type':'string'},'quantity':{'type':'number'},'unit':{'type':'string'},
                'expires_on':{'type':['string','null']}},'required':['name','quantity','unit']}},
            'servings':{'type':'integer','minimum':1},
            'preferences':{'type':'object','properties':{
                'dietary_restrictions':{'type':'array','items':{'type':'string'}},
                'likes':{'type':'array','items':{'type':'string'}}},'required':['dietary_restrictions','likes']},
            'as_of_date':{'type':'string'}},
            'required':['pantry','servings','preferences','as_of_date'],'additionalProperties':False}}}]
    return {'search_recipes':bound_search},schemas
