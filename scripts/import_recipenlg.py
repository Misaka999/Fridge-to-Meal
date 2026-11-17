"""Import a legally obtained local RecipeNLG CSV without guessing quantities/servings."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path


def list_field(value):
    try:
        result=json.loads(value)
    except (ValueError,TypeError):
        result=ast.literal_eval(value)
    if not isinstance(result,list) or any(not isinstance(x,str) for x in result):
        raise ValueError('Expected a list of strings.')
    return result


def import_csv(source, output, limit=100, scan_limit=100000):
    if limit<=0 or scan_limit<=0:
        raise ValueError('Limits must be positive.')
    source,output=Path(source).expanduser(),Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    selected=scanned=skipped=0
    ids=set()
    with source.open(encoding='utf-8-sig',newline='') as stream, output.open('x') as dest:
        reader=csv.DictReader(stream)
        required={'title','ingredients','directions','source','link'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV is missing official RecipeNLG columns: '+str(sorted(required)))
        for row_index,row in enumerate(reader):
            scanned+=1
            if row.get('source') not in ('Gathered','0'):
                if scanned>=scan_limit:break
                continue
            try:
                raw_id=row.get('id') or row.get('') or row.get('Unnamed: 0') or str(row_index)
                rid='recipenlg_'+str(raw_id)
                ingredients=list_field(row['ingredients'])
                directions=list_field(row['directions'])
                if not ingredients or not directions or not row['title'].strip() or rid in ids:
                    raise ValueError('Empty/duplicate record.')
                record={'id':rid,'title':row['title'],'source':'RecipeNLG/Gathered',
                        'original_row_id':str(raw_id),'original_source':row['source'],
                        'source_url':row['link'],
                        'source_row_sha256':hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest(),
                        'raw_ingredients':ingredients,'raw_directions':directions,
                        'raw_ner':list_field(row.get('NER') or row.get('ner') or '[]'),
                        'servings':None,'servings_source':None,'ingredients':[],
                        'dietary_compatibility':{},'review_status':'pending','review_notes':''}
                dest.write(json.dumps(record,ensure_ascii=False)+'\n')
                ids.add(rid);selected+=1
            except (ValueError,SyntaxError,TypeError):
                skipped+=1
            if selected>=limit or scanned>=scan_limit:break
    stats={'source_file':str(source.resolve()),'source_bytes':source.stat().st_size,
           'scanned':scanned,'selected_gathered':selected,'malformed_skipped':skipped,
           'purpose':'Review queue only; not yet a quantity-checked recipe database.'}
    output.with_suffix(output.suffix+'.manifest.json').write_text(json.dumps(stats,indent=2)+'\n')
    return stats


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--csv',required=True,help='Your downloaded full_dataset.csv')
    parser.add_argument('--output',default=Path(__file__).resolve().parents[1] / 'data/recipenlg_review.jsonl')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--scan-limit',type=int,default=100000)
    args=parser.parse_args()
    print(json.dumps(import_csv(args.csv,args.output,args.limit,args.scan_limit),indent=2))
