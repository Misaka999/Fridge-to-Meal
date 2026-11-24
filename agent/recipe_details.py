"""Plain-text source details, distinct from a verified meal recommendation."""
import re
from .grounded_messages import META
from .adaptation_checks import safe_source_url


def format_source_details(recipe):
    title=recipe.get('title','Untitled source record')
    if META.search(title):title='Selected source record'
    lines=[title,'Source details only; this is not a verified recommendation for your pantry or serving size.']
    if re.search(r'\b(?:freezing|preserving|storage)\b',title,re.I):
        lines.append('This record describes food storage or preservation, not a ready-to-eat meal.')
    amounts=recipe.get('raw_ingredients',[])
    lines+=['','Original ingredient list:']
    lines.extend('- '+value for value in amounts[:40] if isinstance(value,str) and not META.search(value))
    lines+=['','Original source directions:']
    steps=[value for value in recipe.get('steps',[])[:40] if isinstance(value,str) and not META.search(value)]
    lines.extend(f'{i}. {value}' for i,value in enumerate(steps,1))
    if len(recipe.get('steps',[]))>40 or len(amounts)>40:lines.append('Long source record shortened; consult the original source for the complete text.')
    lines+=['','The source yield and quantities have not been confirmed for your requested serving size. No quantities were invented or scaled. Pantry unchanged.']
    url=safe_source_url(recipe.get('source_url'))
    if url:lines+=['Source: '+url[:300]]
    return '\n'.join(lines)
