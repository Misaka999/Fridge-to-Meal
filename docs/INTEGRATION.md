# Local integration: Yangyang contribution and unchanged ReAct

## Shared tools and source pools

`agent.tools.recipe_search.search_recipes` takes the agreed four keyword fields:
`pantry`, `servings`, `preferences`, `as_of_date`. Found candidates already have
scaled ingredient amounts. The source pool may be the original three-record
Week 6 catalogue or the 20-record expanded catalogue; a comparison must give
both versions the same pool for each case.

```python
from functools import partial
from agent.tools.recipe_search import load_recipes, search_recipes

recipes = load_recipes(recipe_file='data/recipes_expanded.json')
search = partial(search_recipes, recipes=recipes)
```

## Agent boundaries

The teammate's `react_agent.py` remains unchanged. Its default three-record
catalogue is preserved; pass the real search above or use --recipe-file to
select another source pool.

```python
from react_agent import run_agent as run_react
from agent.plan_replan import run_agent as run_plan

react_run = run_react(request, search=search)
plan_run = run_plan(request, context={'recipes': recipes})
```

Both return `{result, metrics, tool_trace}`. Final result fields are `status`,
`recipe_ids`, `message`. Evaluation adapters map them to `{answer, metrics, trace}`.
The ReAct trace mainly contains tools; plan traces also include explicit plans,
model usage, validation and any display-order normalization.

## Clarification and source limits

- INPUT_INCOMPLETE: missing inventory, incompatible units, unknown labels or storage metadata.
- RECIPE_DETAILS_UNVERIFIED: raw source details cannot be reliably established.
- NO_RETRIEVAL_MATCH: bounded search missed records; not proof no recipe exists.
- FOODKEEPER_UNAVAILABLE: genuine storage-source failure.
- RECIPE_SEARCH_FAILED: genuine recipe-tool failure.

Clarification and operational failure remain distinct. The teammate already
handles the common clarification codes; do not modify ReAct silently to hide
model-format failures. Its known missing-message behavior is documented.

## Optional storage metadata

A pantry item may include storage fields:

```json
{
  "name": "eggs",
  "quantity": 6,
  "unit": "count",
  "expires_on": null,
  "storage": {
    "product_id": "21",
    "condition": "refrigerator",
    "stage": "purchase",
    "reference_date": "2026-11-01",
    "stored_as_directed": true
  }
}
```

Use actual user-confirmed values; this is an illustrative input, not a real
pantry record or an assurance of safety. Missing variety, condition, stage or
date leads to clarification. Explicit expires_on is not overwritten. Quality
guidance can inform priority but is not stored as an expiry date. Official
FoodKeeper fetch returned 403; the local archive provenance is explicit.

## Current state versus persistent sessions

Plan-and-replan can receive explicit full request_updates snapshots from a
caller and invalidates old candidates before searching revised conditions.
It does not implement Shuhua's natural-language update parsing, authentication,
persistent inventory or hosted UI. Recipe text never authorizes a pantry write.

## Display and experiment interpretation

The plan Agent uses validated tool facts for quantities and clarification
wording. Baseline and unchanged ReAct produce their own prose. This comparison
is of whole pipelines, not an isolated causal study of the planning pattern.
Narrative/cooking completeness still requires review. Do not interpret a
structured-grader pass rate as full meal-planning quality.
