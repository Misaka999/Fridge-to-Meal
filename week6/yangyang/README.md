# Yangyang: Week 6 tools, baseline, and evaluation

This directory contains Yangyang Hu's contribution. It does not implement or replace Shuhua's Agent. `agent_adapter.py` is intentionally a placeholder.

## Run without the full dataset or API credentials

Use Python 3.11 or newer. This contribution has no third-party Python dependencies.
From this directory:

```sh
python3 -m unittest discover -s tests -v
python3 tools_cli.py --recipe-file data/recipes_recipenlg.json
python3 evaluate.py --tasks tasks_recipenlg_yangyang.jsonl --check-only
```

The downloaded-index provenance test is skipped if the full index is absent. Other tests use small checked-in data and synthetic fixtures. No model API calls are made by these commands.

## What is included

- CSV retrieval: `recipenlg_store.py` builds an SQLite FTS5 index of RecipeNLG `source=Gathered` records.
- Matching: `tools.py`, `ingredient_names.py`, and `dietary.py` preserve quantity and serving checks, distinguish mass from volume, and treat uncertain dietary labels conservatively.
- Data preparation: `import_recipenlg.py` and `compile_recipenlg.py` preserve source evidence rather than inventing yields.
- Baseline: `baseline.py` and `model_client.py` perform one actual model call when configured and explicitly executed.
- Evaluation: `evaluate.py`, `grading.py`, 25 functional references in `tasks_recipenlg_yangyang.jsonl`, and 5 smoke cases.
- Safety: 25 draft cases in `safety_yangyang_draft.jsonl`, separate from the functional benchmark.
- Legacy fixtures and their tests remain solely for regression coverage; current real-source task IDs start with `RN`.

## Full CSV retrieval

The 2.29 GB CSV and generated SQLite index are deliberately excluded. See [data/README.md](data/README.md) for download and provenance details.

After downloading and placing `RecipeNLG_dataset.csv` in `data/`:

```sh
python3 recipenlg_store.py --build
python3 tools_cli.py --retrieve
python3 tools_cli.py
```

The index needs SQLite FTS5 support and several GB of free disk space. Alternate locations can be selected with `FRIDGE_RECIPE_CSV` and `FRIDGE_RECIPE_INDEX`. File paths and modification times are local cache checks, not published identity checks. Reviewed records are linked to indexed original payload hashes, so another machine's local path is not required.

See [INTEGRATION.md](INTEGRATION.md) for the exact compatibility boundary and required state/error translations with the root README. The root Agent source is not yet present in the repository, so full integration is unverified.

## Week 6 integration

The agreed shared interface is copied in `interface_alignment.md`. Extensions and caveats are in [CSV使用说明.md](CSV使用说明.md).

Shuhua should connect her real implementation to `agent_adapter.run(request, context)` and return `{answer, metrics, trace}`. The evaluation context contains the same recipe pool for both runners. Candidate contexts are prepared before runner timing; metadata records that latency scope.

Configure `DEEPSEEK_API_KEY` locally and set `DEEPSEEK_MODEL` to an ID actually available in your account. Do not commit credentials. After the Agent is connected:

```sh
python3 evaluate.py --tasks tasks_recipenlg_smoke.jsonl --recipe-file data/recipes_recipenlg.json --agent agent_adapter:run --agent-trials 1 --output results/smoke_01
python3 evaluate.py --tasks tasks_recipenlg_yangyang.jsonl --recipe-file data/recipes_recipenlg.json --agent agent_adapter:run --agent-trials 3 --output results/yangyang_01
```

The runner rejects the placeholder Agent. Merge and review both members' cases to reach the required 50 before the final team evaluation. Real token counts, accuracy, pass@3, pass^3 and a failure analysis still require actual model runs. None are fabricated here.

## Limits

The reviewed real-source catalogue has three side dishes with explicit yields, not a complete meal dataset. The 25 functional cases evaluate only that subset; they do not measure full-CSV performance. Most CSV hits lack verified structured quantities or yield; `RECIPE_DETAILS_UNVERIFIED` must not be reported as a feasible recipe or as proof no recipe exists. Broad lexical retrieval is not exhaustive feasibility search. Dietary checks are ingredient-level, not allergen or cross-contact certification. Free-form state updates, inventory writes, FoodKeeper and a full Agent are outside this contribution.

DeepSeek protocol reference for integration: https://api-docs.deepseek.com/guides/tool_calls/
