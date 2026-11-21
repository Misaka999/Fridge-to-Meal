"""Combine a full unchanged baseline cohort with a full versioned plan retest.

No best-of selection and no changed grading: preserve all original trials from
one complete source run per version. Validate inputs and baseline code identity.
"""
import argparse,json
from pathlib import Path
from eval.evaluate import summary,reliability,load_tasks
from eval.evaluate_project import report


def assemble(baseline_folder,plan_folder,output,tasks_path):
    baseline_folder=Path(baseline_folder);plan_folder=Path(plan_folder)
    first=json.loads((baseline_folder/'metadata.json').read_text())
    second=json.loads((plan_folder/'metadata.json').read_text())
    for key in ['tasks_sha256','context_sha256','model_requested','trials','workers']:
        if first.get(key)!=second.get(key):raise ValueError('Incompatible run metadata: '+key)
    for path in ['eval/baseline.py','agent/contracts.py','agent/model_client.py','eval/grading.py','eval/project_contexts.py']:
        if first['code_sha256'].get(path)!=second['code_sha256'].get(path):raise ValueError('Baseline dependency changed: '+path)
    rows=[]
    for folder,version in [(baseline_folder,'baseline'),(plan_folder,'plan_replan')]:
        selected=[json.loads(s) for s in (folder/'runs.jsonl').read_text().splitlines() if s.strip()]
        rows.extend(r for r in selected if r['version']==version)
    tasks=load_tasks(tasks_path);trials=first['trials']
    expected={(v,t['id'],i) for v in ['baseline','plan_replan'] for t in tasks for i in range(1,trials+1)}
    actual=[(r['version'],r['task_id'],r['trial']) for r in rows]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:raise ValueError('Sources do not form complete unique cohorts.')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    result={'tasks':len(tasks),'comparison_trial_1':{},'repeatability':{},'all_trials_accuracy':{}}
    for version in ['baseline','plan_replan']:
        selected=[r for r in rows if r['version']==version]
        result['comparison_trial_1'][version]=summary([r for r in selected if r['trial']==1])
        result['repeatability'][version]=reliability(selected,tasks,trials)
        result['all_trials_accuracy'][version]=sum(r['passed'] for r in selected)/len(selected)
    metadata={**second,'source_runs':{'baseline':str(baseline_folder),'plan_replan':str(plan_folder)},
              'assembly_rule':'All trials from one complete source cohort per version; no best-of replacement.',
              'baseline_reuse_validation':'Task/context/model/trials/workers and baseline dependencies match.',
              'timing_note':'Version cohorts were run sequentially in different windows, each at the recorded concurrency. No claim of isolated single-request latency.'}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'failed_runs.json').write_text(json.dumps([r for r in rows if not r['passed']],indent=2)+'\n')
    (out/'results.md').write_text(report(result)+'\nThis report reuses the unchanged full baseline cohort and compares it with a full plan-version retest. See metadata for exact source folders and code checks.\n')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('baseline_folder');parser.add_argument('plan_folder');parser.add_argument('--output',required=True);parser.add_argument('--tasks',default='eval/project/tasks_yangyang_100.jsonl')
    args=parser.parse_args();print(assemble(args.baseline_folder,args.plan_folder,args.output,args.tasks))
