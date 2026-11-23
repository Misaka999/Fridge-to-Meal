# Full RecipeNLG web search

The default web startup uses the reviewed catalogue, preserving existing deployments. Enable the full catalogue explicitly after configuring the external dataset and index.

## Start

Place your RecipeNLG CSV at `data/RecipeNLG_dataset.csv`, then build its read-only search index:

```sh
.venv/bin/python -m agent.tools.recipenlg_store --build --csv data/RecipeNLG_dataset.csv --index data/recipenlg.sqlite3
.venv/bin/python web_app.py --port 8766 --recipe-source full
```

For external locations, set `FRIDGE_RECIPE_CSV` and `FRIDGE_RECIPE_INDEX` to the matching CSV and index paths. Build the index in its target environment; source metadata is validated. Set `DEEPSEEK_API_KEY` in the environment or ignored `.env`. The CSV, index and credentials must be configured separately on a hosted server.

Open http://127.0.0.1:8766. The page states the indexed record count. Keep the files and recorded source metadata together; changed sources require rebuilding the index. Credentials remain in ignored .env.

## What changed

- The web entry point injects request-aware full-index search into MealSessions, rather than using the ReAct default three-record catalogue. Updates and follow-ups search from the current state.
- Supported raw records are conservatively parsed. The 20 source-hash-matched records remain useful seed candidates, but do not limit the raw index retrieval.
- Candidate lookup uses a bounded lexical shortlist, not exhaustive checking of all 1,642,756 records. Strict source recommendations require confirmed amounts, servings, pantry availability and dietary constraints. Separately labeled adaptations use model-proposed portions checked against the pantry.
- Unresolved search leads are separate from feasible candidates. The ReAct schema preserves their reasons and checked near-match ingredient gaps. Missing data, no match and index failure remain distinct.
- Seed provenance lookups use one cached source-versioned scan instead of a full-table scan for every seed ID. The large index is read-only.

## Try

For two servings, enter 4 eggs (count) and 600 ml flour, with no expired dates. This can match Homemade Pasta, which is outside the original three-record catalogue. The source is a pasta preparation component, not an already cooked complete meal.

Entering only eggs may retrieve egg recipes but return needs_clarification when source yield or other facts cannot be confirmed. The program does not fabricate servings or assume salt/oil are available. The model can now offer conditional closest-dish ideas with missing ingredient information, without asserting verified scaled servings. Recipe-name follow-ups resolve to known per-session IDs and read actual source ingredients/directions. Storage-only records can be read as sources but are not offered as meals. Source-confirmation replies still do not rewrite dataset facts.

The old evaluation results do not describe this new retrieval configuration. Full-index lookup adds latency, particularly on its first source validation; the local single-session backend can queue other requests during a turn. Hosted full-index operation requires separately provisioning the data and enabling `--recipe-source full`.


## Natural-language pantry updates

An explicit statement such as “I also have oil and tomatoes” creates pending additions. Missing quantities and units prompt ordinary-language questions; users do not need JSON. Replying with “2 tablespoons of oil and 3 tomatoes” supplies those facts, validates the complete batch, updates the current inventory and reruns recommendations. No quantity is invented. Pending edits can be cancelled and remain separate from actual stock until valid. Preferences, servings and unrelated stock are preserved. This is local in-memory conversation state; restarting the service clears it.

The model interprets the user statement; code validates and applies edits atomically. Raw pantry replacement is still not accepted from unrestricted model output. Source-batch quantity comparisons are computed separately and do not imply a verified yield.


## Pantry-constrained recipe adaptations

The local full-index web mode now enables structured model-generated adaptations. After retrieval the model proposes ingredient amounts, serving count, steps and changes, using source recipes as inspiration. Code checks source IDs, positive finite amounts, unique ingredients, known unit conversions, unexpired stock, hard dietary flags and common unlisted ingredients in steps. Each alternative has its own inventory budget; inventory is not consumed. Water is a disclosed cooking utility. A failed proposal gets at most one correction attempt, then remains unconfirmed rather than being shown as feasible.

Displayed amounts are suggested meal portions, not inferred original RecipeNLG yields or nutritional adequacy measurements. The checker verifies recorded constraints, not arbitrary cooking correctness. Historical CLI/evaluation mode keeps adaptation disabled by default, so prior benchmark results do not describe this new web behavior. Named follow-ups show the stored adjusted recipe rather than silently reverting to original source quantities; stale adaptations are rechecked against current stock and servings.

Regression tests cover volume conversions, pantry limits, missing source yields and adapted recipe follow-ups.


## Fridge availability versus this meal

When a natural-language addition has no explicit use-now intent, quantities are collected and stock is saved first. The assistant then asks whether to use the new food in this meal or keep the current meal. Keeping the meal does not remove the new stock or rerun recommendations. Choosing use-now creates a separate per-meal ingredient requirement; focused full-index retrieval and adaptation validation both enforce it. A chicken-focused recipe must actually contain positive chicken within the recorded stock. Existing hard dietary restrictions remain active; conflicts require an explicit user preference change.
