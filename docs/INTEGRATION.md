# Compatibility with the repository README

The root `react_agent.run_agent` now uses Yangyang's search tool. The evaluator calls it through `eval.agent_adapter:run`. See the [root README](../README.md) for commands to run both from the project root.

## Compatible boundary

The real search function accepts exactly the documented keyword arguments:

```python
from agent.tools.recipe_search import search_recipes

# Inside the teammate's Agent integration:
run = run_agent(request, model=model, search=search_recipes)
```

`found`, `no_match`, and genuine `RECIPE_SEARCH_FAILED` responses follow the agreed shared interface. Ingredients in `found` are already scaled to the requested servings. For deterministic testing without the full CSV, bind the reviewed catalogue:

```python
from functools import partial
from pathlib import Path
from agent.tools.recipe_search import load_recipes, search_recipes

recipes = load_recipes(recipe_file=Path('data/recipes_recipenlg.json'))
real_search = partial(search_recipes, recipes=recipes)
run = run_agent(request, model=model, search=real_search)
```

The spinach/tofu example in `examples/example_request_mock.json` belongs to the mock/legacy catalogue, so it is not expected to return the same ID from the new real-source catalogue. Use `examples/example_request_real.json` for the checked real-source example.

## Differences that must be handled in the Agent

- `INPUT_INCOMPLETE`: return `needs_clarification`, not `tool_error`.
- `RECIPE_DETAILS_UNVERIFIED`: raw recipe information requires checking; return clarification, never invent yield or claim feasibility.
- `NO_RETRIEVAL_MATCH`: return `needs_clarification` and explain that retrieval found no records.
- `REQUEST_STATE_MISMATCH`: the bound registry prevents model-invented pantry changes.
- The root Agent should validate unknown serving count before calling the tool, as its README already describes. Dietary labels and unit conversions can require further clarification after a tool call.

The ReAct runner distinguishes these cases by error code. A genuine search failure can be retried once.

## Evaluation envelope

The root README documents `{result, metrics, tool_trace}`. The adapter maps it to what `evaluate.py` expects:

| Root runner | Evaluation runner |
|---|---|
| result | answer |
| metrics | metrics |
| tool_trace | trace |

Metrics record actual `model_calls`, `input_tokens`, `output_tokens` and `total_tokens`. Missing token counts remain unknown. The adapter binds `context['recipes']` so both runners see the same candidate collection.

## Running from the project root

See the [offline checks](README.md#run-without-the-full-dataset-or-api-credentials) and [root README](../README.md).
