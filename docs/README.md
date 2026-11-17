# Yangyang: Week 6 tools, baseline, and evaluation

Yangyang Hu contributed the recipe tools, baseline and evaluation code. `agent_adapter.py` connects the evaluator to Shuhua's ReAct Agent.

## Run without the full dataset or API credentials

Use Python 3.11 or newer and install the root requirements before running the tests. Run these commands from the project root:

```sh
python3 -m unittest discover -s tests -v
python -m scripts.tools_cli --recipe-file data/recipes_recipenlg.json
python -m eval.evaluate --tasks eval/week6/tasks_recipenlg_yangyang.jsonl --check-only
```

The downloaded-index provenance test is skipped if the full index is absent. Other tests use small checked-in data and synthetic fixtures. No model API calls are made by these commands.

## What is included

- CSV retrieval: `recipenlg_store.py` builds an SQLite FTS5 index of RecipeNLG `source=Gathered` records.
- Matching: `agent/tools/recipe_search.py`, `ingredient_names.py`, and `dietary.py` preserve quantity and serving checks, distinguish mass from volume, and treat uncertain dietary labels conservatively.
- Data preparation: `import_recipenlg.py` and `compile_recipenlg.py` preserve source evidence rather than inventing yields.
- Baseline: `baseline.py` and `model_client.py` perform one actual model call when configured and explicitly executed.
- Evaluation: `evaluate.py`, `grading.py`, 25 functional references in `tasks_recipenlg_yangyang.jsonl`, and 5 smoke cases.
- Safety: 25 draft cases in `safety_yangyang_draft.jsonl`, separate from the functional benchmark.
- Legacy fixtures and their tests remain solely for regression coverage; current real-source task IDs start with `RN`.

## Full CSV retrieval

The 2.29 GB CSV and generated SQLite index are deliberately excluded. See [data/README.md](../data/README.md) for download and provenance details.

After downloading and placing `RecipeNLG_dataset.csv` in `data/`:

```sh
python -m agent.tools.recipenlg_store --build
python -m scripts.tools_cli --retrieve
python -m scripts.tools_cli
```

The index needs SQLite FTS5 support and several GB of free disk space. Alternate locations can be selected with `FRIDGE_RECIPE_CSV` and `FRIDGE_RECIPE_INDEX`. File paths and modification times are local cache checks, not published identity checks. Reviewed records are linked to indexed original payload hashes, so another machine's local path is not required.

See [INTEGRATION.md](INTEGRATION.md) for the exact compatibility boundary and required state/error translations with the root README.

## Week 6 integration

The agreed shared interface is copied in `interface_alignment.md`. Extensions and caveats are in [CSV使用说明.md](CSV使用说明.md).

The adapter calls ReAct and returns `{answer, metrics, trace}`. The evaluation context contains the same recipe pool for both runners. Candidate contexts are prepared before runner timing; metadata records that latency scope. Run the live commands below from the project root.

Configure `DEEPSEEK_API_KEY` locally and set `DEEPSEEK_MODEL` to an ID actually available in your account. Do not commit credentials.:

```sh
python3 -m eval.evaluate --tasks eval/week6/tasks_recipenlg_smoke.jsonl --recipe-file data/recipes_recipenlg.json --agent eval.agent_adapter:run --agent-trials 1 --output results/smoke_01
python3 -m eval.evaluate --tasks eval/week6/tasks_recipenlg_yangyang.jsonl --recipe-file data/recipes_recipenlg.json --agent eval.agent_adapter:run --agent-trials 3 --output results/yangyang_01
```

Merge and review both members' cases to reach the required 50 before the final team evaluation. Real token counts, accuracy, pass@3, pass^3 and a failure analysis still require actual model runs. None are fabricated here.

## Limits

The reviewed real-source catalogue has three side dishes with explicit yields, not a complete meal dataset. The 25 functional cases evaluate only that subset; they do not measure full-CSV performance. Most CSV hits lack verified structured quantities or yield; `RECIPE_DETAILS_UNVERIFIED` must not be reported as a feasible recipe or as proof no recipe exists. Broad lexical retrieval is not exhaustive feasibility search. Dietary checks are ingredient-level, not allergen or cross-contact certification. Free-form state updates, inventory writes, FoodKeeper and a full Agent are outside this contribution.

DeepSeek protocol reference for integration: https://api-docs.deepseek.com/guides/tool_calls/
