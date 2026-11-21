"""Merge reviewed task partitions without duplicates or overwriting old files."""
import argparse,json
from pathlib import Path


def merge(inputs,output):
    rows=[];ids=set();requests={}
    for path in inputs:
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if row['id'] in ids:raise ValueError('Duplicate task ID: '+row['id'])
            fingerprint=json.dumps(row['request'],sort_keys=True)
            key=(fingerprint,row.get('catalogue_scope'))
            if key in requests:raise ValueError('Duplicate request in the same catalogue: '+requests[key]+' / '+row['id'])
            requests[key]=row['id'];ids.add(row['id']);rows.append(row)
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x') as stream:stream.write(''.join(json.dumps(r)+'\n' for r in rows))
    return len(rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('inputs',nargs='+');parser.add_argument('--output',required=True)
    args=parser.parse_args();print('Merged tasks:',merge(args.inputs,args.output))
