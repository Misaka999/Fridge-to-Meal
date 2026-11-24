"""Evidence-based display for the plan Agent; no model-invented unit conversions.

The model still plans, replans and selects validated recipe IDs. Display wording
is grounded in tool facts. This is a whole-pipeline design difference from the
unchanged ReAct, not evidence that planning alone causes any score difference.
"""
import re

# A bounded presentation guard, not a general prompt-injection classifier.
META=re.compile(r'\b(?:api[ _-]?key|password|secret|system|assistant|debug|inventory|confirmation|override|instructions?|recommend|higher priority|another user|deduct|delete|disable|reveal|print|forward|send|credential|ignore (?:all|previous)|https?)\b',re.I)
YIELD=re.compile(r'\b(?:serves\s+\d+(?:\s+people)?|(?:makes|yields)\s+\d+\s+(?:large\s+)?servings)\.?\s*$',re.I)


def _number(value):return f'{value:.3f}'.rstrip('0').rstrip('.')


def _steps(values):
    kept=[];excluded=False
    for original in values:
        if META.search(original):excluded=True;continue
        text=YIELD.sub('',original).strip()
        if text:kept.append(text)
    return kept,excluded


def render_answer(request,observation,answer):
    status=answer['status']
    if status=='needs_clarification':
        message=observation.get('message') or 'Provide the missing source or inventory details before recipe feasibility can be established.'
    elif status=='no_feasible_recipe':
        message='No feasible recipe in the supplied local catalogue satisfies the current pantry, servings and dietary restrictions. This does not rule out recipes outside that catalogue. Pantry unchanged.'
    elif status=='tool_error':
        message='Recipe lookup failed. Feasibility is unknown; a tool failure is not evidence that no recipe exists. Pantry unchanged.'
    else:
        by_id={c['recipe_id']:c for c in observation['candidates']}
        blocks=[f"Options for {request['servings']} serving(s), preserving shared tool priority. Pantry unchanged."]
        for index,rid in enumerate(answer['recipe_ids'],1):
            recipe=by_id[rid];title=recipe.get('title','Recipe '+rid)
            if META.search(title) or any(c in title for c in '<>{}'):
                title='Recipe '+rid
            block=[f'{index}. {title} ({rid})','Required amounts:']
            fractional_egg=False
            for item in recipe.get('ingredients',[]):
                block.append(f"- {item['name']}: {_number(item['quantity'])} {item['unit']}")
                if item['name']=='egg' and item['unit']=='count' and not float(item['quantity']).is_integer():fractional_egg=True
            if fractional_egg:block.append('Fractional egg counts refer to whole eggs; no yolk or white substitution is assumed.')
            steps,excluded=_steps(recipe.get('steps',[]))
            block.append('Source preparation steps:')
            block.extend(f'{i}. {step}' for i,step in enumerate(steps,1))
            if excluded:block.append('Non-cooking source text was excluded; source details still require review.')
            if recipe.get('original_servings'):
                block.append(f"Original source yield: {recipe['original_servings']}; the amounts above are scaled to {request['servings']}. Cooking times and piece sizes have not been recalculated.")
            if recipe.get('storage_guidance'):block.append('Any storage window is general guidance, not an expiration date or a safety guarantee.')
            blocks.append('\n'.join(block))
        blocks.append('Recipes may be sides or preparation components. Source instructions are not a complete-meal, cooking-safety or allergen certification.')
        message='\n\n'.join(blocks)
    return {'status':status,'recipe_ids':list(answer['recipe_ids']),'message':message}


def render_closest_options(observation, *, include_records=False):
    """Keep the closest dishes and their gaps visible when adaptation fails."""
    from .adaptation_checks import safe_source_title, control_directive
    options = observation.get('alternatives') or observation.get('near_matches') or observation.get('retrieved_candidates') or []
    blocks = ['Closest recipe options (not yet confirmed ready to cook):']
    seen = set()
    records = []
    def names(values):
        return ', '.join(x for x in values if isinstance(x,str) and not control_directive(x))
    for recipe in options:
        rid = recipe.get('recipe_id')
        if not isinstance(rid,str) or rid in seen:
            continue
        title = safe_source_title(recipe.get('title'),rid)
        title_key = title.strip().casefold()
        if title_key in seen:
            continue
        seen.update((rid,title_key))
        block = [str(len(blocks))+'. '+title]
        missing = names(recipe.get('missing_ingredients') or recipe.get('possible_missing_ingredients') or recipe.get('missing_ingredient_names') or [])
        short = names(recipe.get('insufficient_quantities') or [])
        conversions = names(recipe.get('unknown_conversions') or [])
        if missing:block.append('Missing ingredients: '+missing+'.')
        if short:block.append('Not enough in the pantry: '+short+'.')
        if conversions:block.append('Amounts cannot yet be compared for: '+conversions+'.')
        raw = [x for x in recipe.get('raw_ingredients',[]) if isinstance(x,str) and not control_directive(x)]
        if raw:block.append('Original source ingredient list: '+'; '.join(raw[:12])+'.')
        uncertain = bool(recipe.get('uncertainty') or recipe.get('reason') or recipe.get('raw_ingredients'))
        if uncertain:
            block.append('Source portions are unverified. The original batch is not the amount required for your meal; extra ingredients in the directions may need to be omitted or supplied.')
        elif not (missing or short or conversions):
            block.append('Recipe quantities and suitability still need checking.')
        records.append({'recipe_id':rid,'title':title,'ready_to_cook':False,
                        'missing_ingredients':[x for x in (recipe.get('missing_ingredients') or recipe.get('possible_missing_ingredients') or recipe.get('missing_ingredient_names') or []) if isinstance(x,str) and not control_directive(x)],
                        'insufficient_quantities':recipe.get('insufficient_quantities',[]),
                        'unknown_conversions':recipe.get('unknown_conversions',[]),
                        'unverified_quantities':uncertain})
        blocks.append('\n'.join(block))
        if len(blocks)==4:break
    if len(blocks)==1:return ('',[]) if include_records else ''
    blocks.append('Which option would you like to adapt or see the original recipes for? Your pantry is unchanged.')
    message='\n\n'.join(blocks)
    return (message,records) if include_records else message


def render_react_answer(request, observation, answer):
    """Render checked tool facts rather than unchecked model-written claims."""
    from .adaptation_checks import safe_source_title, control_directive
    from copy import deepcopy
    evidence = deepcopy(observation)
    if answer['status'] == 'recommended':
        for candidate in evidence['candidates']:
            candidate['title'] = safe_source_title(candidate.get('title'), candidate['recipe_id'])
        return render_answer(request, evidence, answer)
    if answer['status'] == 'tool_error':
        message = 'Recipe lookup failed. Recipe feasibility is unknown. Your pantry is unchanged; please try again.'
    elif answer['status'] == 'no_feasible_recipe':
        message = 'No feasible recipe was confirmed in the searched catalogue. This does not rule out recipes outside the retrieved results. Your pantry is unchanged.'
    else:
        # Some tool messages instruct the model how to compose its response;
        # those instructions must not become the user-facing answer verbatim.
        options = evidence.get('alternatives') or evidence.get('retrieved_candidates') or []
        if options:
            message = render_closest_options(evidence)
        else:
            value = evidence.get('message')
            message = value if isinstance(value,str) and value.strip() and not control_directive(value) else 'Recipe suitability could not be confirmed. Check the recipe details or adjust your request. Your pantry is unchanged.'
    return {'status':answer['status'], 'recipe_ids':list(answer['recipe_ids']), 'message':message}
