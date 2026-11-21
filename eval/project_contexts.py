"""Shared datasets and bounded raw storage references, never held-out answers."""
import hashlib
import json
from pathlib import Path
from agent.tools.recipe_search import load_recipes
from agent.tools.foodkeeper import load_products,norm

ROOT=Path(__file__).resolve().parents[1]


def contexts_for(tasks,recipe_file=None,catalogue_map=None):
    cache={};scopes={}
    if recipe_file:
        cache['uniform']=load_recipes(recipe_file=recipe_file)
    else:
        mapfile=Path(catalogue_map or ROOT/'data/catalogues.json')
        mapping=json.loads(mapfile.read_text())
        for scope,relative in mapping.items():
            path=(mapfile.parent/relative).resolve()
            cache[scope]=load_recipes(recipe_file=path);scopes[scope]=str(path)
    products=None;contexts={}
    for task in tasks:
        key='uniform' if recipe_file else task.get('catalogue_scope')
        if key not in cache:raise ValueError('Unknown catalogue scope: '+str(key))
        context={'recipes':cache[key]}
        metadata=[x['storage'] for x in task['request'].get('pantry',[]) if isinstance(x,dict) and isinstance(x.get('storage'),dict)]
        if metadata:
            if products is None:products,_=load_products()
            selected=set(str(x['product_id']) for x in metadata if x.get('product_id') is not None)
            names={norm(x['name']) for x in task['request']['pantry'] if 'storage' in x}
            context['storage_reference']=[p for p in products if p['id'] in selected or norm(p['name']) in names][:12]
            context['storage_reference_notice']='Pinned mirror; general storage guidance only, not guaranteed expiry.'
        contexts[task['id']]=context
    return contexts,{'recipe_file':str(Path(recipe_file).resolve()) if recipe_file else None,
                     'catalogues':scopes,'context_sha256':hashlib.sha256(json.dumps(contexts,sort_keys=True).encode()).hexdigest()}
