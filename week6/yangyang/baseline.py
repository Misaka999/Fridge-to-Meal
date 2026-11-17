"""Non-agentic baseline: same input and raw candidates, one model call, no tools."""
import argparse
import json
from pathlib import Path
try:
    from .contracts import ANSWER_INSTRUCTIONS
except ImportError:
    from contracts import ANSWER_INSTRUCTIONS
try:
    from .model_client import complete_json
except ImportError:
    from model_client import complete_json
try:
    from .tools import load_recipes
except ImportError:
    from tools import load_recipes


def run(request, context):
    answer, metrics, trace = complete_json([
        {'role': 'system', 'content': ANSWER_INSTRUCTIONS},
        {'role': 'user', 'content': json.dumps({'request': request, 'context': context})}
    ])
    return {'answer': answer, 'metrics': metrics, 'trace': trace}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', default=str(Path(__file__).resolve().parent / 'data/example_request.json'))
    parser.add_argument('--recipe-file', help='Optional reviewed JSON catalogue.')
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text())
    result = run(request, {'recipes': load_recipes(request,recipe_file=args.recipe_file)})
    print(json.dumps(result, indent=2))
