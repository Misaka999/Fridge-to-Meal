"""Request-aware full-index search for the local web app.

The index is searched through a bounded lexical shortlist. Unresolved records
are diagnostic leads, never feasible recommendations. No recipe data is invented.
"""
from contextlib import closing
import json
import sqlite3
import re

from .recipe_search import load_recipes, search_recipes, check_recipe, validate_request
from .recipenlg_store import index_path, source_path, signature


def source_batch_checks(request,raw_ingredients):
    """Compare independently readable source amounts, without assuming a yield."""
    from .ingredient_names import ALIASES,normalize_name
    from .recipe_parser import parse_ingredient,Unresolved
    from .recipe_search import UNITS
    stock={}
    for item in request['pantry']:
        if item.get('expires_on') and item['expires_on']<request['as_of_date']:continue
        unit,factor=UNITS[item['unit']];key=(normalize_name(item['name']),unit)
        stock[key]=stock.get(key,0)+item['quantity']*factor
    required={}
    for i,line in enumerate(raw_ingredients):
        text=line.lower()
        for alias,canonical in sorted(ALIASES.items(),key=lambda x:-len(x[0])):
            text=re.sub(r'\b'+re.escape(alias)+r'\b',canonical,text)
        try:part=parse_ingredient(text,i)
        except Unresolved:continue
        key=(part['name'],part['unit']);required[key]=required.get(key,0)+part['quantity']
    return [{'ingredient':name,'required_source_amount':round(amount,6),
             'available_amount':round(stock.get((name,unit),0),6),'unit':unit,
             'shortfall':round(max(0,amount-stock.get((name,unit),0)),6),
             'basis':'Unscaled source batch only; not verified for the requested servings.'}
            for (name,unit),amount in required.items() if name!='water']


def conditional_options(request,recipes,limit=6):
    """Helpful closest dishes, never labeled as pantry-feasible recommendations."""
    from .ingredient_names import retrieval_name
    from .dietary import detected_conflicts, preparation_conflicts
    pantry={retrieval_name(x['name']) for x in request['pantry'] if x['quantity']>0 and
            (not x.get('expires_on') or x['expires_on']>=request['as_of_date'])}
    restrictions=request['preferences']['dietary_restrictions']
    ranked=[]
    for recipe in recipes:
        title=recipe['title']
        if re.search(r'\b(?:freezing|storage|preserving)\b|^to clarify',title,re.I):continue
        raw=recipe.get('quantity_verified') is False
        if raw:
            if detected_conflicts(recipe.get('raw_ingredients',[]),restrictions) or preparation_conflicts(recipe.get('steps',[]),restrictions):continue
            names={retrieval_name(x) for x in recipe.get('ingredient_names',[])}-{'water'}
            # Reject conspicuous title/ingredient contradictions, without
            # pretending this is a general source-completeness validator.
            from .recipe_parser import CATEGORIES
            title_foods={retrieval_name(x) for x in CATEGORIES
                         if len(x)>2 and re.search(r'\b'+re.escape(x)+r'(?:s|es)?\b',title,re.I)}
            raw_text=' ; '.join(recipe.get('raw_ingredients',[])).lower()
            if any(not re.search(r'\b'+re.escape(x)+r'(?:s|es)?\b',raw_text,re.I) for x in title_foods):continue
            matched=names&pantry
            if not matched:continue
            missing=sorted(names-pantry)
            option={'recipe_id':recipe['id'],'title':title[:160],
                    'verification':'Source recipe idea; quantities, servings and dietary suitability are not confirmed.',
                    'possible_missing_ingredients':missing[:12],
                    'uncertainty':recipe.get('parse_issue','Source details require checking.'),
                    'raw_ingredients':recipe.get('raw_ingredients',[])[:30],
                    'source_batch_checks':source_batch_checks(request,recipe.get('raw_ingredients',[])),
                    'source_direction_excerpts':recipe.get('steps',[])[:20],
                    'directions_shortened':len(recipe.get('steps',[]))>20,
                    'source_url':recipe.get('source_url','')[:300]}
            score=(len(missing),-len(matched),1,len(recipe.get('raw_ingredients',[])),recipe['id'])
        else:
            check=check_recipe(request,recipe['id'],recipes)
            if check.get('dietary_conflicts') or check.get('unknown_dietary_checks'):continue
            names={retrieval_name(x['name']) for x in recipe['ingredients']}-{'water'}
            matched=names&pantry
            if not matched or check.get('feasible'):continue
            missing=check.get('missing_ingredients',[])
            option={'recipe_id':recipe['id'],'title':title[:160],
                    'verification':'Checked recipe, but pantry requirements are not satisfied.',
                    'missing_ingredients':missing,
                    'insufficient_quantities':check.get('insufficient_quantities',[]),
                    'unknown_conversions':check.get('unknown_conversions',[]),
                    'required_ingredients':check.get('scaled_ingredients',[]),
                    'source_url':recipe.get('source_url','')[:300]}
            score=(sum(len(check.get(k,[])) for k in ['missing_ingredients','insufficient_quantities','unknown_conversions']),-len(matched),0,len(recipe['ingredients']),recipe['id'])
        ranked.append((score,option))
    return [option for _,option in sorted(ranked,key=lambda x:x[0])[:limit]]


def catalogue_info():
    path=index_path()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        metadata=json.loads(conn.execute('SELECT value FROM metadata').fetchone()[0])
    if any(metadata.get(k)!=v for k,v in signature(source_path()).items()):
        raise ValueError('Recipe source changed; its index must be rebuilt.')
    return {'mode':'full_index','indexed_records':metadata['recipes'],
            'description':f"Searches {metadata['recipes']:,} RecipeNLG/Gathered records. "
                          'Results use a bounded shortlist; uncertain quantities require clarification.'}


def read_source_recipe(recipe_id):
    """Read one source record; the session must authorize its candidate ID first."""
    import re
    if not isinstance(recipe_id,str) or not re.fullmatch(r'recipenlg_\d+',recipe_id):
        raise ValueError('Invalid RecipeNLG record ID.')
    catalogue_info()
    with closing(sqlite3.connect(index_path().resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        row=conn.execute("SELECT payload FROM recipes WHERE json_extract(payload,'$.id')=? LIMIT 1",(recipe_id,)).fetchone()
    if not row:raise LookupError('Source recipe was not found.')
    return json.loads(row[0])


def full_search_recipes(pantry,servings,preferences,as_of_date,*,meal_ingredients=None):
    request=dict(pantry=pantry,servings=servings,preferences=preferences,as_of_date=as_of_date)
    if meal_ingredients:request['meal_ingredients']=list(meal_ingredients)
    issue=validate_request(request)
    if issue:
        return {'status':'error','candidates':[],'error_code':'INPUT_INCOMPLETE',
                'message':issue['message'],'missing_field':issue['missing_field']}
    try:
        info=catalogue_info()
        recipes=load_recipes(request,full_index=True)
        if meal_ingredients:
            from .ingredient_names import retrieval_name
            focus={retrieval_name(name) for name in meal_ingredients}
            def contains_focus(recipe):
                values=recipe.get('ingredient_names',[]) if recipe.get('quantity_verified') is False else [i['name'] for i in recipe['ingredients']]
                return focus<={retrieval_name(name) for name in values}
            recipes=[recipe for recipe in recipes if contains_focus(recipe)]
        result=search_recipes(pantry,servings,preferences,as_of_date,recipes=recipes)
        unresolved=[r for r in recipes if r.get('quantity_verified') is False]
        result['retrieval']={**info,'candidate_records_checked':len(recipes),
                             'unresolved_records':len(unresolved),'meal_ingredients':list(meal_ingredients or [])}
        result['scope']='Bounded retrieval from the full RecipeNLG/Gathered index plus source-verified seed records; not an exhaustive feasibility search.'
        # Preserve useful evidence without sending arbitrary raw steps to the model.
        leads=[]
        for recipe in unresolved[:3]:
            leads.append({'recipe_id':recipe['id'],'title':recipe['title'][:160],
                          'source_url':recipe.get('source_url','')[:300],
                          'reason':recipe.get('parse_issue','Unverified source details.')[:300],
                          'missing_ingredient_names':recipe.get('unmatched_ingredient_names',[])[:12]})
        result['retrieved_candidates']=leads
        result['source_references']=[{'recipe_id':r['id'],'title':r['title'][:160]} for r in unresolved[:24]]
        if result['status']!='found':
            result['alternatives']=conditional_options(request,recipes)
            near=[]
            for recipe in recipes:
                if recipe.get('quantity_verified') is False:continue
                check=check_recipe(request,recipe['id'],recipes)
                if check.get('dietary_conflicts') or check.get('unknown_dietary_checks'):continue
                gaps={k:check.get(k,[]) for k in ['missing_ingredients','insufficient_quantities','unknown_conversions']}
                count=sum(len(v) for v in gaps.values())
                if count:
                    near.append((count,recipe['id'],{'recipe_id':recipe['id'],'title':recipe['title'][:160],**gaps}))
            result['near_matches']=[x[2] for x in sorted(near,key=lambda x:x[:2])[:3]]
            if result.get('error_code')=='RECIPE_DETAILS_UNVERIFIED':
                descriptions='; '.join(f"{r['title']}: {r['reason']}" for r in leads)
                gaps='; '.join(x['title']+': missing '+', '.join(x['missing_ingredients']) for x in result['near_matches'] if x['missing_ingredients'])
                result['message']='Search found related recipes, but none has been confirmed feasible for this pantry and serving size. '+descriptions+' Please confirm the missing source details; these are not ready-to-cook recommendations. No extra ingredients are assumed.'
                if gaps:result['message']+=' Other checked recipes need additional ingredients: '+gaps+'.'
            elif result['status']=='no_match':
                result['message']='No feasible recipe was confirmed in the retrieved shortlist. This does not prove no recipe exists in the full dataset.'
            if result.get('alternatives'):
                result['status']='error'
                result['error_code']='RECIPE_DETAILS_UNVERIFIED'
                result['message']='Offer the closest recipe options listed in alternatives. Clearly distinguish conditional ideas from dishes already feasible with this pantry. Explain missing ingredients or unverified amounts, and ask one useful next question. Do not invent quantities, source facts or substitutions. Storage-only records are not meal suggestions.'
        return result
    except Exception:
        return {'status':'error','candidates':[],'error_code':'RECIPE_SEARCH_FAILED',
                'message':'The full RecipeNLG index could not be read. Check the local data and index; recipe feasibility is unknown.'}
