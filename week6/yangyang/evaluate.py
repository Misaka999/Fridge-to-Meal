"""Evaluate a real agent and a single-call baseline, preserving every trial."""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import statistics
import time

try:
    from .grading import grade
except ImportError:
    from grading import grade
try:
    from .tools import load_recipes
    from .model_client import load_project_env
except ImportError:
    from tools import load_recipes
    from model_client import load_project_env


def load_tasks(path):
    tasks = [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if not tasks or len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Task IDs must be unique and the file cannot be empty.')
    for task in tasks:
        if not isinstance(task.get('request'), dict) or not isinstance(task.get('expected'), dict):
            raise ValueError(f"{task['id']}: missing request/expected object.")
        e = task['expected']
        if e.get('status') == 'recommended' and not e.get('allowed_recipe_ids'):
            raise ValueError(f"{task['id']}: missing independently reviewed allowed recipe IDs.")
    return tasks


def load_runner(spec):
    module, name = spec.split(':', 1)
    fn = getattr(importlib.import_module(module), name)
    if not callable(fn):
        raise TypeError('Runner must be callable.')
    if module == 'agent_adapter':
        import inspect
        if "raise NotImplementedError(" in inspect.getsource(fn):
            raise ValueError('Connect Shuhua\'s real agent before live evaluation.')
    return fn


def checked_metrics(metrics):
    metrics = metrics if isinstance(metrics, dict) else {}
    result = {}
    for field in ['model_calls', 'input_tokens', 'output_tokens', 'total_tokens']:
        value = metrics.get(field)
        result[field] = value if type(value) is int and value >= 0 else None
    result['model'] = metrics.get('model')
    return result


def run_one(fn, request, context):
    started = time.perf_counter()
    try:
        result = fn(deepcopy(request), deepcopy(context))
        if not isinstance(result, dict) or not all(k in result for k in ['answer', 'metrics', 'trace']):
            raise ValueError('Runner must return answer, metrics, trace.')
        return {**result, 'metrics': checked_metrics(result['metrics']),
                'seconds': time.perf_counter() - started, 'error': None}
    except Exception as exc:
        return {'answer': None, 'metrics': checked_metrics(getattr(exc, 'metrics', {})),
                'trace': getattr(exc, 'trace', []), 'seconds': time.perf_counter() - started,
                'error': f'{type(exc).__name__}: {exc}'}


def mean_known(values):
    values = list(values)
    return statistics.mean(values) if values and all(v is not None for v in values) else None


def summary(rows):
    seconds = sorted(r['seconds'] for r in rows)
    return {'tasks': len(rows), 'accuracy': statistics.mean(r['passed'] for r in rows),
            'avg_turns': mean_known(r['metrics']['model_calls'] for r in rows),
            'avg_latency_seconds': statistics.mean(seconds),
            'p95_latency_seconds': seconds[math.ceil(.95 * len(seconds)) - 1],
            'avg_tokens': mean_known(r['metrics']['total_tokens'] for r in rows),
            'rows_with_missing_metrics': sum(any(r['metrics'][k] is None for k in
                 ['model_calls', 'input_tokens', 'output_tokens', 'total_tokens']) for r in rows),
            'errors': sum(r['error'] is not None for r in rows)}


def reliability(rows, tasks, trials):
    by_id = {t['id']: [r['passed'] for r in rows if r['task_id'] == t['id']] for t in tasks}
    if any(len(v) != trials for v in by_id.values()):
        raise ValueError('Incomplete trials; do not report reliability yet.')
    return {'trials_per_task': trials,
            f'pass@{trials}': statistics.mean(any(v) for v in by_id.values()),
            f'pass^{trials}': statistics.mean(all(v) for v in by_id.values()),
            'flipping_tasks': [key for key, v in by_id.items() if any(v) and not all(v)],
            'outcomes': by_id}


def report_text(results):
    def fmt(v): return 'N/A' if v is None else f'{v:.2f}' if isinstance(v, float) else str(v)
    lines = ['# Week 6 evaluation results', '',
             'Side-by-side metrics use trial 1 only; reliability uses all agent trials.', '',
             '| Version | Tasks | Accuracy | Avg turns | Avg seconds | p95 seconds | Avg tokens |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for name, item in results['comparison_trial_1'].items():
        lines.append('| ' + ' | '.join([name, str(item['tasks']), f"{item['accuracy']:.1%}",
            fmt(item['avg_turns']), fmt(item['avg_latency_seconds']),
            fmt(item['p95_latency_seconds']), fmt(item['avg_tokens'])]) + ' |')
    lines += ['', '## Agent repeatability', '', '```json',
              json.dumps(results['agent_repeatability'], indent=2), '```', '',
              '## Limits', '',
              '- N/A means provider metrics were missing; no token usage was invented.',
              '- Statuses, valid recipe IDs and ranking are code-graded against task-side references.',
              '- Message presence is checked; its quantities, cooking steps and explanations require manual review.',
              '- Dataset scope and source hashes are recorded in metadata.json; FoodKeeper is not implemented.',
              '- Shared retrieval contexts are prepared before timing model runners; latency excludes that setup.',
              '- Review at least one failed trace and write your own evidence-based failure paragraph.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks', default=str(Path(__file__).resolve().parent / 'tasks_yangyang.jsonl'))
    parser.add_argument('--agent', help='Example: shuhua_adapter:run')
    parser.add_argument('--baseline', default=f'{__package__}.baseline:run' if __package__ else 'baseline:run')
    parser.add_argument('--agent-trials', type=int, default=3)
    parser.add_argument('--output', default='results/live_run_01')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--recipe-file', help='Explicit reviewed JSON catalogue for fixed-catalogue evaluation; otherwise CSV retrieval per task.')
    args = parser.parse_args()
    tasks = load_tasks(args.tasks)
    print(f"Tasks: {len(tasks)}; edge: {sum('edge' in t.get('tags',[]) for t in tasks)}; "
          f"unanswerable: {sum('unanswerable' in t.get('tags',[]) for t in tasks)}")
    if len(tasks) != 50:
        print('NOTE: this is a partial team set. Merge and review both members\' tasks for the required 50.')
    if args.check_only:
        print('Task format valid. No models were called.')
        return
    if not args.agent or args.agent_trials < 1:
        parser.error('Supply a real --agent module:function and a positive trial count.')
    load_project_env()
    if not os.environ.get('DEEPSEEK_API_KEY') or not os.environ.get('DEEPSEEK_MODEL'):
        parser.error('Set DEEPSEEK_API_KEY and DEEPSEEK_MODEL first.')
    agent, baseline = load_runner(args.agent), load_runner(args.baseline)
    if args.agent == args.baseline:
        parser.error('Agent and baseline cannot be the same runner.')
    catalogue = args.recipe_file or os.environ.get('FRIDGE_RECIPE_FILE')
    if any(t.get('catalogue_scope') == 'reviewed_recipenlg_subset' for t in tasks) and not catalogue:
        parser.error('These references cover the reviewed subset only. Supply --recipe-file data/recipes_recipenlg.json.')
    fixed = {'recipes': load_recipes(recipe_file=catalogue)} if catalogue else None
    contexts = {task['id']: fixed if fixed is not None else {'recipes': load_recipes(task['request'])}
                for task in tasks}
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    metadata = {'task_file': str(Path(args.tasks).resolve()),
                'tasks_sha256': hashlib.sha256(Path(args.tasks).read_bytes()).hexdigest(),
                'recipes_sha256': hashlib.sha256(json.dumps(contexts, sort_keys=True).encode()).hexdigest(),
                'model_requested': os.environ['DEEPSEEK_MODEL'], 'agent': args.agent,
                'baseline': args.baseline, 'agent_trials': args.agent_trials,
                'scope': 'Fixed catalogue shared by both versions.' if catalogue else 'Same per-task CSV retrieval pool shared by both versions; retrieval setup excluded from latency.',
                'recipe_file': str(Path(catalogue).resolve()) if catalogue else None}
    (out/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    rows = []
    with (out/'runs.jsonl').open('w', encoding='utf-8') as stream:
        for version, fn, trials in [('baseline', baseline, 1), ('agent', agent, args.agent_trials)]:
            for trial in range(1, trials + 1):
                for task in tasks:
                    # Send request only, NEVER the expected answers/tags/description.
                    run = run_one(fn, task['request'], contexts[task['id']])
                    grading = grade(run['answer'], task['expected'])
                    row = {'version': version, 'trial': trial, 'task_id': task['id'],
                           **run, **grading}
                    rows.append(row)
                    stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                    stream.flush()
                    print(version, trial, task['id'], 'PASS' if row['passed'] else 'FAIL', flush=True)
    results = {'comparison_trial_1': {
        name: summary([r for r in rows if r['version']==name and r['trial']==1])
        for name in ['agent','baseline']},
        'agent_repeatability': reliability([r for r in rows if r['version']=='agent'],tasks,args.agent_trials)}
    (out/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
    (out/'results.md').write_text(report_text(results), encoding='utf-8')
    failures = [r for r in rows if r['version']=='agent' and not r['passed']]
    (out/'failed_runs.json').write_text(json.dumps(failures, indent=2)+'\n')
    print(f'Results saved to {out}. Select a genuine failure from failed_runs.json for analysis.')


if __name__ == '__main__':
    main()
