# Conversation evaluation and optional LLM review

This is a new local evaluation, separate from the old single-request 200-task
benchmark. It does not overwrite old results, certify cooking safety, or prove
that an agent must outperform a baseline.

## Dataset and fairness

`eval/conversation/cases.jsonl` starts with 7 author-known scenarios / 18 turns:
serving changes, resolving an unknown chicken amount, choosing use-now versus
save-for-later, preserving dietary restrictions, removing ingredients, missing
servings, and requesting missing ingredients for an original recipe.
`catalogue.json` freezes 8 actual RecipeNLG source records, including reviewed
records and raw egg recipes with unspecified yields. These are controlled source
subsets, not a test of recall across all 1.6 million recipes. Add more manually
checked scenarios before drawing general conclusions.

Both versions receive the same initial state, current user utterance, and frozen
raw sources. Later reference states are held out. Baseline gets its own previous
answers/history and makes one call per user turn, without tools. ReAct runs the
actual MealSessions implementation, including extraction, stock editing,
meal-choice clarification, source lookup and adaptation. Program-maintained
state versus model-maintained state is an explicit whole-system difference.

Every trial starts a fresh session. The order of variants is varied reproducibly.
Do not treat three conversation turns as three independent reruns.

## Separate scores

- Turn rule pass: correct stock, units, dates, portions, dietary restrictions,
  selected ingredients and pending questions; valid sourced response contract.
  Explicit step quantities and known dietary terms have bounded code checks.
- Conversation rule pass: every turn passes. pass^3 requires the entire
  conversation to pass in all three independent reruns; pass@3 needs one.
- Conditional recommendation score: for an original-recipe gap request, source
  IDs and missing-ingredient lists must match the held-out source facts, be
  visible in the response, and be labeled not ready to cook. It is not scored
  as a failed ready-meal request. A case with a known feasible dish still
  requires an actual recommendation. Unknown units and amounts must not be guessed.
- LLM quality: context handling, helpfulness, consistency, each 0–2. The judge
  cannot override a hard-rule failure. Report both sets of scores separately.

The original-recipe-gap scenario is deliberately allowed to expose missing
product behavior: do not remove or weaken a case just because a version fails.
Reference state checks do not fully interpret arbitrary cooking prose; unresolved
semantics, completeness and actual cooking quality need judge/human review.

## Judge safeguards

Architecture names, tool traces, costs and previous grades are removed from the
judge input. Both variants use the same prompt and evidence format. Response
style can still hint at the architecture. Each deduction cites an existing
response evidence ID. Invalid judgment JSON or nonexistent citations are retried
once, then left unscored; uncertainty is queued for human review. A severity is
mapped mechanically to 2/1/0; there is no numeric/severity disagreement to ignore.

The current judge uses the configured DeepSeek model; using the same model family
as the generator can correlate errors. This is supplementary assessment, not an
independent human gold standard. Inspect a sample and all disputed deductions.
A request for one serving does not automatically require exact proportional
scaling or minimal ingredient usage unless the user says so. Stock is not
consumed by a recommendation.

## Commands

Validate inputs without model calls:

```sh
python -m eval.conversation.evaluate --check-only
```

Small actual comparison plus judge (new output directory):

```sh
python -m eval.conversation.evaluate --limit 1 --trials 1 --judge --out results/conversation_smoke
```

Full starter set, three independent trials (run explicitly when ready):

```sh
python -m eval.conversation.evaluate --trials 3 --judge --out results/conversation_01
```

Review saved answers without rerunning either assistant:

```sh
python -m eval.conversation.evaluate --judge-only results/conversation_smoke/runs.jsonl --out results/conversation_review_02
```

Transparent, hand-authored judge conformance probes (not benchmark results):

```sh
python -m eval.conversation.calibrate --out results/judge_calibration
```

Configure DEEPSEEK_API_KEY and DEEPSEEK_MODEL locally. Judge calls cost tokens too;
the report keeps their usage separate. Never upload credentials, the external
full CSV/index, or raw results unless explicitly requested.

## Evidence and current validation

New result directories retain reference data, own conversation histories,
responses, rule failures, usage, source/code hashes and judge rubric. Blind IDs
map back to variants only in a separate mapping file. Original raw reviews remain
unchanged when the rubric is revised. The November 24 pilot used one three-turn
scenario, one trial per version; it cannot establish pass^3 or overall accuracy.
An initial judge deduction incorrectly required a one-person meal to halve egg
usage. Its scores were retained and flagged; a universal rubric clarification and
removal of future scenario-level goals were applied to both systems in a separate
judge-only re-review. This was a post-hoc protocol audit, not a fresh blind result.
