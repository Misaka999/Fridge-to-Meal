"""Offline diagnostic for the agreed search tool; not an agent."""
import argparse
import json
from pathlib import Path
try:
    from .tools import search_recipes, validate_request, load_recipes
except ImportError:
    from tools import search_recipes, validate_request, load_recipes

parser=argparse.ArgumentParser()
parser.add_argument('--request',default=str(Path(__file__).resolve().parent/'data/example_request_real.json'))
parser.add_argument('--recipe-file', help='Restrict diagnostics to an explicit reviewed JSON catalogue.')
parser.add_argument('--retrieve', action='store_true', help='Show original CSV retrieval hits without claiming pantry feasibility.')
args=parser.parse_args()
request=json.loads(Path(args.request).read_text())
issue=validate_request(request)
if args.retrieve:
    result=issue or {'source':'RecipeNLG/Gathered', 'retrieved_candidates':load_recipes(request,recipe_file=args.recipe_file),
                     'note':'Retrieval only: yield, quantities and dietary suitability are unverified.'}
else:
    result=issue or search_recipes(**{key:request[key] for key in
        ('pantry','servings','preferences','as_of_date')},
        recipes=load_recipes(request,recipe_file=args.recipe_file) if args.recipe_file else None)
print(json.dumps(result,indent=2))
