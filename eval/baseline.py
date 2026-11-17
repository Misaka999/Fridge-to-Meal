"""Non-agentic baseline: same input and raw candidates, one model call, no tools."""
import argparse
import json
from pathlib import Path
from agent.contracts import ANSWER_INSTRUCTIONS
from agent.model_client import complete_json
from agent.tools.recipe_search import load_recipes


def run(request, context):
    answer, metrics, trace = complete_json([
        {'role': 'system', 'content': ANSWER_INSTRUCTIONS},
        {'role': 'user', 'content': json.dumps({'request': request, 'context': context})}
    ])
    return {'answer': answer, 'metrics': metrics, 'trace': trace}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', default=str(Path(__file__).resolve().parents[1] / 'examples/example_request_real.json'))
    parser.add_argument('--recipe-file', help='Optional reviewed JSON catalogue.')
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    result = run(request, {'recipes': load_recipes(request,recipe_file=args.recipe_file)})
    print(json.dumps(result, indent=2))
