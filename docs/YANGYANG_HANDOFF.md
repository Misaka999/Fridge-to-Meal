# Yangyang implementation handoff

This is Yangyang’s implementation contribution based on repository commit `be8b08fbc03208a4c690cfccea941e1c6cbe6466`. The teammate-owned `react_agent.py` is unchanged.

## What is implemented

- RecipeNLG search and conservative source parsing, quantity and compatible-unit checks, dietary filtering, and expiry-priority matching. The original three-record catalogue is preserved; the expanded catalogue has 20 source-linked records, not full coverage of RecipeNLG.
- An actual plan-and-replan Agent: model-generated action sequence, common tool execution, observations, revised plans, bounded retry/format repair, and traces. Caller-supplied request snapshots support replanning without implementing the teammate's conversational session layer.
- FoodKeeper lookup using a pinned, provenance-recorded 661-product archive. It distinguishes storage conditions and reference events, asks for missing details, and does not convert guidance into invented expiration dates.
- A single-call baseline and evaluation adapters, 100 functional tasks (25 historical plus 75 new), 25 safety cases (23 attacks and 2 benign controls), and reproducible evaluation scripts.
- Grounded output formatting and canonical priority order for the Plan Agent. These are additional pipeline controls; experiments do not isolate planning alone.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Set the local DeepSeek credentials in .env.
.venv/bin/python plan_replan_agent.py examples/example_request_expanded_pasta.json --trace
.venv/bin/python -m unittest discover -s tests -q
```

The included small catalogue is enough for the documented structured examples and evaluations. Full-CSV search additionally needs the separately downloaded RecipeNLG data and local index; neither large file is bundled. Tests that specifically need that index may skip without it. Never commit `.env`.

`run_project_with_api.command` evaluates baseline and Plan Agent on 100 tasks, three trials each. `run_safety_with_api.command` evaluates the same two versions on 25 safety cases once each. These launchers consume API credit and create new result folders. Recorded results do not need to be rerun just to read them.

## Integration interface

The Plan Agent returns `result`, `metrics`, and `trace`; the result follows `{status, recipe_ids, message}`. The evaluation adapter converts this to `{answer, metrics, trace}`. See `docs/INTEGRATION.md` for the detailed contracts. Requests are authoritative structured inputs. Retrieved recipe text cannot authorize pantry updates.

## Evaluation outputs

Evaluation scripts save raw runs, summaries and metadata to a new local `results/` folder. Results are intentionally not included in this code contribution. Errors remain unscored in safety evaluation; qualitative narrative review is separate from structural checks. Do not report read-only tests as evidence of deployed database isolation or external-write authorization.

## Joint work still required

Shuhua's ReAct, persistent inventory/conversation UI, deployment, and her task partition must be integrated and evaluated against the same final tools. The team still needs to reconcile its complete 200 functional / 50 safety cases, combine results honestly, and produce the hosted demo, presentation/video, and joint final report. This handoff supplies Yangyang's implementation and member test partition; it does not claim those team deliverables are finished.
