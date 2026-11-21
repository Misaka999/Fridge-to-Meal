"""Summarize completed real member runs; never invent missing evaluations."""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(folder):
    folder=Path(folder)
    summary=json.loads((folder/'summary.json').read_text())
    metadata=json.loads((folder/'metadata.json').read_text())
    rows=[json.loads(s) for s in (folder/'runs.jsonl').read_text().splitlines() if s.strip()]
    tasks=[json.loads(s) for s in Path('eval/project/tasks_yangyang_100.jsonl').read_text().splitlines()]
    lookup={t['id']:t for t in tasks}
    def value(x):return 'N/A' if x is None else f'{x:.2f}' if isinstance(x,float) else str(x)
    lines=['# Yangyang member functional results','',
           'Actual saved runs. ReAct was intentionally excluded from this member run and its implementation was not changed.',
           f"Tasks: {summary['tasks']}; trials per version: {metadata['trials']}; concurrent workers: {metadata.get('workers',1)}.",
           'Compare latency only under the same load. This is a member partition, not the complete 200-task team benchmark.','',
           '| Version | Trial-1 pass | All-trial pass | Avg calls | Avg tokens | Mean seconds | p95 seconds | pass@3 | pass^3 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,r in summary['comparison_trial_1'].items():
        selected=[x for x in rows if x['version']==name]
        first=[x for x in selected if x['trial']==1]
        repeat=summary['repeatability'][name]
        lines.append('| '+' | '.join([name,f"{sum(x['passed'] for x in first)}/{len(first)}",f"{sum(x['passed'] for x in selected)}/{len(selected)}",value(r['avg_turns']),value(r['avg_tokens']),value(r['avg_latency_seconds']),value(r['p95_latency_seconds']),f"{repeat['pass@3']:.1%}",f"{repeat['pass^3']:.1%}"])+' |')
    lines+=['','## Reliability flips','']
    for name,repeat in summary['repeatability'].items():
        lines.append(f"- {name}: "+(', '.join(repeat['flipping_tasks']) or 'None'))
    lines+=['','## First-trial accuracy by source pool','',
            '| Version | Source pool | Passed / tasks |','|---|---|---:|']
    for name in summary['comparison_trial_1']:
        for scope in sorted({t['catalogue_scope'] for t in tasks}):
            selected=[r for r in rows if r['version']==name and r['trial']==1 and lookup[r['task_id']]['catalogue_scope']==scope]
            lines.append(f"| {name} | {scope} | {sum(r['passed'] for r in selected)}/{len(selected)} |")
    lines+=['','## Errors and grading limits','']
    for name in summary['comparison_trial_1']:
        selected=[r for r in rows if r['version']==name]
        errors=Counter(r['error'].split(':',1)[0] for r in selected if r.get('error'))
        lines.append(f'- {name} recorded errors: '+json.dumps(errors))
    lines+=['','The plan Agent uses evidence-grounded display. Baseline generates prose; the unchanged ReAct also generates prose. Any difference is a whole-pipeline effect, not proof that planning alone caused it.',
            'Structured grading checks status, IDs and priority, not arbitrary cooking completeness. The benchmark is narrow, uses fixed dates and includes three-record historical cases plus a 20-record expanded pool.',
            'Safety and hosted conversational behavior are separate evaluations. Missing metrics remain N/A.','']
    target=folder/'member_report.md';target.write_text('\n'.join(lines),encoding='utf-8')
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    print(summarize(args.folder))
