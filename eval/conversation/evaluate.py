"""Multi-turn benchmark with independent rules and optional blinded LLM review."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import statistics
import uuid

from .runners import BaselineSession,AgentSession
from .scoring import grade_turn
from .judge import review,make_payload,DIMENSIONS,visible,PROMPT

ROOT=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows, trials):
    result={}
    for version in sorted({r['version'] for r in rows}):
        selected=[r for r in rows if r['version']==version];sessions={}
        for row in selected:sessions.setdefault((row['case_id'],row['trial']),[]).append(row)
        passed={key:all(r['rules']['passed'] for r in group) for key,group in sessions.items()}
        cases={c for c,t in sessions}
        result[version]={'turns':len(selected),'turn_rule_pass_rate':sum(r['rules']['passed'] for r in selected)/len(selected),
            'conversation_rule_pass_rate':sum(passed.values())/len(passed),'trials_per_case':trials,
            'model_calls':sum(r['output'].get('metrics',{}).get('model_calls',0) or 0 for r in selected),
            'tokens':sum(r['output'].get('metrics',{}).get('total_tokens',0) or 0 for r in selected)}
        metrics=[r['output'].get('metrics',{}) for r in selected]
        for field,label in [('model_calls','model_calls'),('total_tokens','tokens'),('elapsed_seconds','seconds')]:
            values=[m.get(field) for m in metrics]
            complete=all(type(v) in (int,float) for v in values)
            result[version]['missing_'+label+'_turns']=sum(type(v) not in (int,float) for v in values)
            result[version]['avg_'+label+'_per_turn']=statistics.mean(values) if complete else None
            result[version]['avg_'+label+'_per_conversation']=sum(values)/len(sessions) if complete else None
        if all({t for case,t in sessions if case==c}==set(range(1,trials+1)) for c in cases):
            result[version][f'pass^{trials}']=sum(all(passed[(c,t)] for t in range(1,trials+1)) for c in cases)/len(cases)
            result[version][f'pass@{trials}']=sum(any(passed[(c,t)] for t in range(1,trials+1)) for c in cases)/len(cases)
        conditional=[r for r in selected if r['reference']['mode']=='conditional']
        result[version]['conditional_turns']=len(conditional)
        result[version]['conditional_rule_pass_rate']=sum(r['rules']['passed'] for r in conditional)/len(conditional) if conditional else None
    return result


def judge_rows(rows, recipes, out, call=None):
    order=list(range(len(rows)));random.Random(513).shuffle(order);judgments=[];mapping=[]
    with (out/'judge_runs.jsonl').open('w') as stream:
        for index in order:
            row=rows[index];blind_id=uuid.uuid4().hex
            payload=make_payload(row['goal'],row['history'],row['output'],row['reference'],
                                 [r for r in recipes if r['id'] in row['catalogue_ids']])
            reviewed=review(payload,**({'call':call} if call else {}))
            saved={'blind_id':blind_id,'payload':payload,**reviewed};stream.write(json.dumps(saved)+'\n');stream.flush()
            mapping.append({'blind_id':blind_id,'case_id':row['case_id'],'trial':row['trial'],'turn':row['turn'],'version':row['version']})
            judgments.append((row['version'],saved));print('Reviewed',len(judgments),'/',len(rows),flush=True)
    (out/'judge_mapping.json').write_text(json.dumps(mapping,indent=2))
    report={}
    for version in {v for v,_ in judgments}:
        values=[r for v,r in judgments if v==version];valid=[r['judgment'] for r in values if r['judgment'] is not None]
        report[version]={'reviewed_turns':len(valid),'unscored_judge_failures':len(values)-len(valid),
            'human_review_flags':sum(v['needs_human_review'] for v in valid),'dimensions':{}}
        for dim in DIMENSIONS:
            scores=[v['scores'][dim] for v in valid if v['scores'][dim] is not None]
            report[version]['dimensions'][dim]={'mean_0_to_2':statistics.mean(scores) if scores else None,
                'scored_turns':len(scores),'unassessable':len(valid)-len(scores)}
    report['judge_usage']={'model_calls':sum(a.get('metrics',{}).get('model_calls',0) or 0 for _,r in judgments for a in r['attempts']),
                          'tokens':sum(a.get('metrics',{}).get('total_tokens',0) or 0 for _,r in judgments for a in r['attempts'])}
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,default=ROOT/'cases.jsonl');p.add_argument('--catalogue',type=Path,default=ROOT/'catalogue.json')
    p.add_argument('--versions',nargs='+',choices=['baseline','react'],default=['baseline','react'])
    p.add_argument('--trials',type=int,default=3);p.add_argument('--limit',type=int)
    p.add_argument('--out',type=Path);p.add_argument('--judge',action='store_true');p.add_argument('--judge-only',type=Path)
    p.add_argument('--check-only',action='store_true');args=p.parse_args()
    if args.trials<1:p.error('Trials must be positive.')
    if args.limit is not None and args.limit<1:p.error('Limit must be positive.')
    cases=[json.loads(x) for x in args.cases.read_text().splitlines() if x.strip()]
    recipes=json.loads(args.catalogue.read_text())
    if args.limit:cases=cases[:args.limit]
    if len({c['id'] for c in cases})!=len(cases):p.error('Duplicate case IDs.')
    available={r['id'] for r in recipes}
    for c in cases:
        if not set(c['catalogue_ids'])<=available:p.error('Unknown catalogue ID.')
        if not c['turns'] or c['turns'][0].get('message') is not None:p.error('Initial turn must use only the initial request.')
        for i,turn in enumerate(c['turns']):
            if i and (not isinstance(turn.get('message'),str) or not turn['message'].strip()):p.error('Missing user utterance.')
            if not isinstance(turn.get('reference',{}).get('state'),dict):p.error('Missing held-out state.')
    if args.check_only:
        print(json.dumps({'cases':len(cases),'turns':sum(len(c['turns']) for c in cases),'source_records':len(recipes),'model_calls':0}));return
    if args.out is None:p.error('Provide a new --out directory to preserve all earlier results.')
    args.out.mkdir(parents=True,exist_ok=False)
    if args.judge_only:
        original=args.judge_only.parent
        rows=[json.loads(x) for x in args.judge_only.read_text().splitlines() if x.strip()]
        recipes=json.loads((original/'catalogue.json').read_text())
        metadata=json.loads((original/'metadata.json').read_text());trials=metadata['trials']
        metadata={'mode':'judge_only','source_runs_sha256':sha(args.judge_only),'source_metadata':metadata,'trials':trials}
    else:
        trials=args.trials
        code=[*ROOT.glob('*.py'),Path('agent/session.py'),Path('react_agent.py'),Path('agent/recipe_adaptation.py'),Path('agent/tools/full_catalogue.py')]
        metadata={'mode':'conversation','trials':trials,'case_sha256':sha(args.cases),'catalogue_sha256':sha(args.catalogue),
                  'code_sha256':{str(f):sha(f) for f in code},'versions':args.versions,'scope':'Frozen real-source subset; not full-index retrieval or 200 independent tasks.',
                  'limitations':['Author-known scenario variants; no hidden generalization claim.','Baseline has same user inputs, its own history and same raw source catalogue; no oracle state.','Agent uses production MealSessions and bounded source-search/adaptation on that catalogue.','A positive rule score is not complete semantic or cooking verification.','Same model family can create correlated judge errors; manual audits remain necessary.']}
        rows=[]
        with (args.out/'runs.jsonl').open('w') as stream:
            for trial in range(1,trials+1):
                for c in cases:
                    sources=[r for r in recipes if r['id'] in c['catalogue_ids']]
                    versions=list(args.versions);random.Random(trial+sum(map(ord,c['id']))).shuffle(versions)
                    for version in versions:
                        session=(BaselineSession if version=='baseline' else AgentSession)(c['initial'],sources);history=[]
                        for i,turn in enumerate(c['turns']):
                            user={'initial_request':c['initial']} if i==0 else {'message':turn['message']}
                            history.append({'role':'user','content':deepcopy(user)})
                            try:output=session.turn(turn.get('message'))
                            except Exception as exc:output={'error':type(exc).__name__,'metrics':getattr(exc,'metrics',{}),'tool_trace':getattr(exc,'trace',[])}
                            row={'version':version,'case_id':c['id'],'goal':c['goal'],'trial':trial,'turn':i+1,
                                 'catalogue_ids':c['catalogue_ids'],'history':deepcopy(history),'reference':turn['reference'],
                                 'output':output,'rules':grade_turn(output,turn['reference'],sources)}
                            rows.append(row);stream.write(json.dumps(row)+'\n');stream.flush()
                            history.append({'role':'assistant','content':visible(output)})
                            print(version,c['id'],trial,i+1,'PASS' if row['rules']['passed'] else row['rules']['failures'],flush=True)
    (args.out/'metadata.json').write_text(json.dumps(metadata,indent=2));(args.out/'catalogue.json').write_text(json.dumps(recipes,indent=2))
    result={'rules':summarize(rows,trials)}
    if args.judge or args.judge_only:result['quality']=judge_rows(rows,recipes,args.out)
    (args.out/'judge_rubric.txt').write_text(PROMPT)
    (args.out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
