"""Publish only reviewed original records in the tool's existing recipe format."""
import argparse
import json
import math
from pathlib import Path
try:
    from .tools import RESTRICTIONS,normalize_name
except ImportError:
    from tools import RESTRICTIONS,normalize_name


def compile_records(review_file,output):
    recipes=[];ids=set();pending=0
    for line_no,line in enumerate(Path(review_file).read_text().splitlines(),1):
        if not line.strip():continue
        row=json.loads(line)
        if row.get('review_status')!='approved':
            pending+=1;continue
        prefix=f'Line {line_no}: '
        if row.get('source')!='RecipeNLG/Gathered' or not str(row.get('id','')).startswith('recipenlg_'):
            raise ValueError(prefix+'not an original RecipeNLG/Gathered record.')
        if row['id'] in ids:raise ValueError(prefix+'duplicate ID.')
        if not row.get('source_url') or not row.get('source_row_sha256') or not row.get('raw_ingredients') or not row.get('raw_directions'):
            raise ValueError(prefix+'missing provenance or raw recipe text.')
        servings=row.get('servings')
        if type(servings) not in (int,float) or not math.isfinite(servings) or servings<=0 or not row.get('servings_source'):
            raise ValueError(prefix+'verified servings and its source are required; no default servings.')
        flags=row.get('dietary_compatibility',{})
        if any(k not in flags or (flags[k] is not None and type(flags[k]) is not bool) for k in RESTRICTIONS):
            raise ValueError(prefix+'review all supported dietary compatibility flags.')
        if not row.get('ingredients'):raise ValueError(prefix+'normalized quantities are missing.')
        covered=set();names=set();ingredients=[]
        for item in row['ingredients']:
            name=normalize_name(item.get('name',''))
            q=item.get('quantity');unit=item.get('unit')
            if (not name or name in names or type(q) not in (int,float)
                    or not math.isfinite(q) or q<=0 or unit not in ('g','ml','count')
                    or not item.get('quantity_basis')):
                raise ValueError(prefix+'invalid/duplicate normalized ingredient or missing quantity basis.')
            indices=item.get('raw_indices',[])
            if not indices or any(type(i) is not int or not 0<=i<len(row['raw_ingredients']) for i in indices):
                raise ValueError(prefix+'each normalized ingredient must reference raw ingredient indices.')
            covered.update(indices);names.add(name)
            ingredients.append({'name':name,'quantity':q,'unit':unit})
        if covered!=set(range(len(row['raw_ingredients']))):
            raise ValueError(prefix+'some raw ingredients were omitted; do not silently drop seasonings.')
        recipes.append({'id':row['id'],'title':row['title'],'servings':servings,
            'ingredients':ingredients,'steps':row['raw_directions'],
            'source':row['source'],'source_url':row['source_url'],
            'original_row_id':row['original_row_id'],'source_row_sha256':row['source_row_sha256'],
            'dietary_compatibility':flags,
            'review':{'servings_source':row['servings_source'],
                      'ingredients':row['ingredients'],'notes':row.get('review_notes','')}})
        ids.add(row['id'])
    if not recipes:raise ValueError('No approved records; nothing was published.')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(recipes,stream,indent=2,ensure_ascii=False)
    return {'published':len(recipes),'pending':pending,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--review',default='data/recipenlg_review.jsonl')
    parser.add_argument('--output',default='data/recipes_recipenlg.json')
    args=parser.parse_args()
    print(json.dumps(compile_records(args.review,args.output),indent=2))
