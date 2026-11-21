"""Command-line entry point for Yangyang's plan-and-replan Agent."""
import argparse
from functools import partial
import json
from pathlib import Path
import sys
from agent.plan_replan import run_agent
from agent.tools.recipe_search import load_recipes,search_recipes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request',type=Path)
    parser.add_argument('--recipe-file',type=Path,default=Path(__file__).resolve().parent/'data/recipes_expanded.json')
    parser.add_argument('--trace',action='store_true')
    args=parser.parse_args()
    try:
        request=json.loads(args.request.read_text(encoding='utf-8-sig'))
        search=partial(search_recipes,recipes=load_recipes(recipe_file=args.recipe_file))
        run=run_agent(request,search=search)
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        if args.trace and hasattr(exc,'trace'):
            print(json.dumps({'metrics':getattr(exc,'metrics',{}),'trace':exc.trace}),file=sys.stderr)
        return 1
    print(json.dumps(run['result'],ensure_ascii=False))
    if args.trace:print(json.dumps({'metrics':run['metrics'],'trace':run['tool_trace']}),file=sys.stderr)
    return 0

if __name__=='__main__':raise SystemExit(main())
