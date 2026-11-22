"""Build a source-parsed prototype catalogue without model calls or invented yields."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from agent.tools.recipe_parser import VERSION,parse_recipe
from agent.tools.recipenlg_store import index_path


def expand(index,output,limit=100,scan_limit=20000):
    index=Path(index).resolve();output=Path(output)
    if output.exists() or output.with_suffix('.report.json').exists():
        raise FileExistsError('Choose a new output file; previous catalogues are not overwritten.')
    if limit<=0 or scan_limit<=0:raise ValueError('Limits must be positive.')
    selected=[];reasons=Counter();scanned=0
    with closing(sqlite3.connect(index.as_uri()+'?mode=ro',uri=True)) as conn:
        rows=conn.execute("SELECT payload FROM recipes WHERE json_extract(payload, '$.steps') LIKE '%serves %' OR json_extract(payload, '$.steps') LIKE '%servings%'")
        for (payload,) in rows:
            scanned+=1
            result=parse_recipe(json.loads(payload))
            if result['status']=='parsed':selected.append(result['recipe'])
            else:reasons[result['reason']]+=1
            if len(selected)>=limit or scanned>=scan_limit:break
    report={'kind':'automatic parsing diagnostics, not model evaluation or human verification',
            'parser_version':VERSION,'yield_candidate_rows_scanned':scanned,'recipes_source_parsed':len(selected),
            'requested_limit':limit,'scan_limit':scan_limit,
            'selection':'First matching yield-candidate rows in the local index; not a random or representative sample.',
            'rejection_reasons':dict(reasons.most_common()),
            'scope':'No guessed yields, density conversions or packaged ingredient substitutions; not cooking-safety certification.'}
    if not selected:raise ValueError('No supported complete records; review the parser constraints.')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    output.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=Path,default=index_path())
    parser.add_argument('--output',type=Path,default=Path('data/recipes_expanded.json'))
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--scan-limit',type=int,default=20000)
    args=parser.parse_args()
    print(json.dumps(expand(args.index,args.output,args.limit,args.scan_limit),indent=2))
