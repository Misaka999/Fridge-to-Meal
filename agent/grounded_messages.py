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
            recipe=by_id[rid];title=recipe['title']
            if META.search(title) or any(c in title for c in '<>{}'):
                title='Recipe '+rid
            block=[f'{index}. {title} ({rid})','Required amounts:']
            fractional_egg=False
            for item in recipe['ingredients']:
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
