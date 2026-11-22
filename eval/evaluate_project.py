"""Three-variant project evaluation, distinct from the preserved Week 6 harness."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from agent.model_client import load_project_env
from .evaluate import load_tasks,load_runner,run_one,summary,reliability
from .grading import grade
from .project_contexts import contexts_for

DEFAULTS={'baseline':'eval.baseline:run','react':'eval.agent_adapter:run','plan_replan':'eval.plan_replan_adapter:run'}


def report(result):
    def fmt(x):return 'N/A' if x is None else f'{x:.2f}' if isinstance(x,float) else str(x)
    trials=next(iter(result['repeatability'].values()))['trials_per_task']
    lines=['# Project comparison','',
           'Comparison uses trial 1; reliability and all-trial accuracy use every recorded trial.',
           'Dataset scope is recorded per task. Context setup is excluded from runner latency. See metadata for worker concurrency; compare latency under the same load.','',
           f'| Version | Tasks | Trial-1 accuracy | Avg calls | Avg tokens | Avg seconds | p95 seconds | pass@{trials} | pass^{trials} |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,row in result['comparison_trial_1'].items():
        repeat=result['repeatability'][name];n=repeat['trials_per_task']
        lines.append('| '+' | '.join([name,str(row['tasks']),f"{row['accuracy']:.1%}",fmt(row['avg_turns']),fmt(row['avg_tokens']),fmt(row['avg_latency_seconds']),fmt(row['p95_latency_seconds']),f"{repeat[f'pass@{n}']:.1%}",f"{repeat[f'pass^{n}']:.1%}"])+' |')
    lines+=['','Reliability labels use the actual requested trial count; use 3 for presentation.',
            'Narrative quantities, cooking instructions and completeness still require manual review.',
            'Missing metrics are N/A; no paid-model results are fabricated.',
            'Inspect failures and report one source trace, fix, and rerun; do not cherry-pick only successes.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks',default='eval/project/tasks_yangyang_100.jsonl')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--recipe-file');group.add_argument('--catalogue-map')
    parser.add_argument('--trials',type=int,default=3)
    parser.add_argument('--versions',nargs='+',choices=list(DEFAULTS),default=list(DEFAULTS),help='Select variants for targeted retests; default compares all three.')
    parser.add_argument('--output',default='results/project_01')
    parser.add_argument('--workers',type=int,default=1,help='Bounded independent runners; concurrent load affects latency.')
    parser.add_argument('--allow-partial',action='store_true')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    tasks=load_tasks(args.tasks)
    if args.trials<1:parser.error('Trials must be positive.')
    if not 1<=args.workers<=4:parser.error('Use 1-4 workers.')
    contexts,meta=contexts_for(tasks,args.recipe_file,args.catalogue_map)
    print(f'{len(tasks)} tasks; shared catalogue contexts ready; {args.trials} trial(s) per version.')
    if args.check_only:
        print('Check only: no model calls. Three runners:',', '.join(DEFAULTS));return
    if len(tasks)<200 and not args.allow_partial:parser.error('Presentation requires >=200 tasks; explicitly use --allow-partial for a member subset or smoke run.')
    load_project_env()
    if not os.getenv('DEEPSEEK_API_KEY') or not os.getenv('DEEPSEEK_MODEL'):parser.error('Configure local DEEPSEEK_API_KEY and DEEPSEEK_MODEL.')
    selected={name:DEFAULTS[name] for name in args.versions}
    runners={name:load_runner(spec) for name,spec in selected.items()}
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    metadata={**meta,'tasks':len(tasks),'tasks_sha256':hashlib.sha256(Path(args.tasks).read_bytes()).hexdigest(),
              'code_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('react_agent.py'),Path('plan_replan_agent.py'),*sorted(Path('agent').rglob('*.py')),*sorted(Path('eval').glob('*.py'))]},
              'runners':selected,'trials':args.trials,'workers':args.workers,'model_requested':os.environ['DEEPSEEK_MODEL'],
              'latency_scope':'Shared data context setup excluded; full runner execution included.',
              'rendering_scope':'Plan Agent uses evidence-grounded display; unchanged ReAct and baseline generate prose. Whole-pipeline comparison, not an isolated planning-only causal test.'}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    rows=[]
    with (out/'runs.jsonl').open('w',encoding='utf-8') as stream:
        jobs=[(trial,task,name,fn) for trial in range(1,args.trials+1) for task in tasks for name,fn in runners.items()]
        def execute(job):
            trial,task,name,fn=job
            run=run_one(fn,task['request'],contexts[task['id']])
            return {'version':name,'trial':trial,'task_id':task['id'],**run,**grade(run['answer'],task['expected'])}
        pool=ThreadPoolExecutor(max_workers=args.workers)
        try:
            for row in pool.map(execute,jobs):
                rows.append(row);stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                print(row['version'],row['trial'],row['task_id'],'PASS' if row['passed'] else 'FAIL',flush=True)
        except BaseException:
            pool.shutdown(wait=False,cancel_futures=True)
            raise
        else:pool.shutdown(wait=True)
    result={'tasks':len(tasks),'comparison_trial_1':{},'repeatability':{},'all_trials_accuracy':{}}
    for name in runners:
        selected=[r for r in rows if r['version']==name]
        result['comparison_trial_1'][name]=summary([r for r in selected if r['trial']==1])
        result['repeatability'][name]=reliability(selected,tasks,args.trials)
        result['all_trials_accuracy'][name]=sum(r['passed'] for r in selected)/len(selected)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'results.md').write_text(report(result),encoding='utf-8')
    (out/'failed_runs.json').write_text(json.dumps([r for r in rows if not r['passed']],indent=2)+'\n')
    print('Saved actual model results to',out)

if __name__=='__main__':main()
