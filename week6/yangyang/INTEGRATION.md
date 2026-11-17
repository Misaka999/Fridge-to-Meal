# Compatibility with the repository README

The root README describes Shuhua's `react_agent.run_agent` API. The actual `react_agent.py`, `requirements.txt` and root `example_request.json` were not present in the repository when this contribution was prepared. End-to-end integration therefore remains unverified.

## Compatible boundary

The real search function accepts exactly the documented keyword arguments:

```python
from week6.yangyang.tools import search_recipes

# Inside the teammate's Agent integration:
run = run_agent(request, model=model, search=search_recipes)
```

`found`, `no_match`, and genuine `RECIPE_SEARCH_FAILED` responses follow the agreed shared interface. Ingredients in `found` are already scaled to the requested servings. For deterministic testing without the full CSV, bind the reviewed catalogue:

```python
from functools import partial
from pathlib import Path
from week6.yangyang.tools import load_recipes, search_recipes

recipes = load_recipes(recipe_file=Path('week6/yangyang/data/recipes_recipenlg.json'))
real_search = partial(search_recipes, recipes=recipes)
run = run_agent(request, model=model, search=real_search)
```

The root spinach/tofu example belongs to the mock/legacy catalogue, so it is not expected to return the same ID from the new real-source catalogue. Use `week6/yangyang/data/example_request_real.json` for the checked real-source example.

## Differences that must be handled in the Agent

- `INPUT_INCOMPLETE`: return `needs_clarification`, not `tool_error`.
- `RECIPE_DETAILS_UNVERIFIED`: raw recipe information requires checking; return clarification, never invent yield or claim feasibility.
- `NO_RETRIEVAL_MATCH`: no lexical retrieval hits; do not assert no recipe can exist.
- `REQUEST_STATE_MISMATCH`: the bound registry prevents model-invented pantry changes.
- The root Agent should validate unknown serving count before calling the tool, as its README already describes. Dietary labels and unit conversions can require further clarification after a tool call.

If the current Agent maps every `status=error` to `tool_error`, it needs these error-code distinctions before full-CSV testing. Its code is absent, so this contribution cannot claim that change has already been made.

## Evaluation envelope

The root README documents `{result, metrics, tool_trace}`. `evaluate.py` expects `{answer, metrics, trace}` from an adapter. When Shuhua implements `agent_adapter.run`, it should map:

| Root runner | Evaluation runner |
|---|---|
| result | answer |
| metrics | metrics |
| tool_trace | trace |

Metrics should provide actual `model_calls`, `input_tokens`, `output_tokens`, `total_tokens`; missing counts remain unknown, never invented. Use `context['recipes']` in the bound search so the baseline and Agent see the same candidate collection. Do not replace the Agent with the baseline. No Agent loop or adapter implementation is included here, as requested.

## Running from the contribution directory

The root README's LangGraph installation and `react_agent.py` command belong to the teammate implementation. This contribution's offline commands are in `week6/yangyang/README.md`; run them from that directory. Its standard-library tools do not install LangGraph or replace the root requirements.
