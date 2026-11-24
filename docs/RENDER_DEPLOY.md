# Render deployment with the full recipe catalogue

This setup uses the existing complete RecipeNLG/Gathered corpus without a persistent disk. It does not upload the CSV, SQLite index or credentials to GitHub. It prepares the data during the build, not when a user opens the app. The ordinary `python web_app.py` command still uses the historical reviewed catalogue.

## Existing Render web service

Connect branch `main` of `Misaka999/Fridge-to-Meal`. In **Settings**, set:

| Setting | Value |
|---|---|
| Build Command | `pip install -r requirements.txt && python -m scripts.render_data build` |
| Start Command | `python -m scripts.render_data start` |
| Health Check Path | `/` |

Changing `render.yaml` in GitHub does not automatically change these fields for a manually created service. Update them in the dashboard. A new Blueprint uses the supplied YAML.

In **Environment**, set:

| Variable | Value |
|---|---|
| `DEEPSEEK_API_KEY` | Your actual key, stored only in Render |
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `PYTHONUNBUFFERED` | `1` |

Delete any old `FRIDGE_RECIPE_CSV=/var/data/...` and `FRIDGE_RECIPE_INDEX=/var/data/...` entries. Leave `FRIDGE_RECIPE_DATA_DIR` unset. Data defaults to `data/` inside the project build artifact; `/var/data` is not mounted. Render supplies `PORT`, which the launcher forwards to the app.

Choose **Manual Deploy → Deploy latest commit**. Inspect the logs until they show all three stages:

1. `Downloading the pinned full RecipeNLG CSV` (or reuse of an already verified build).
2. `Build ready: 1,642,756 Gathered recipes.`
3. `Starting full-catalogue web app with 1,642,756 indexed recipes.`

The public home page should display the full indexed-record count. If the full-data build fails, the service does not quietly switch to the three-recipe catalogue.

## Source and build verification

The default public download is the user-provided Drive file `1f0Ump2DMYNxauNsNnt3oCcm3GYeb4OQB`. Anonymous access and a range read of its CSV header were verified when this script was added. The complete cloud download has not been verified until your Render build succeeds.

The pinned source is 2,294,981,083 bytes with SHA-256:

```text
f376ee0bb9f99f323761abf6270d453f4eff2002c3625d04cabcf8b57dca0803
```

Downloads stream to a temporary file. HTML login/quota pages, partial HTTP responses, unexpected sizes and checksum mismatches are rejected before replacing the CSV. The existing streaming index builder selects all valid Gathered records, with an exact expected count of 1,642,756. It does not cap the corpus at 20 recipes. Recipe lookup still uses a bounded per-request shortlist; not every corpus recipe is evaluated for every query.

The generated manifest pins CSV and index hashes. Stable whole-second timestamps avoid needless checks after packaging. If the build and runtime paths or timestamps differ, the launcher verifies the hashes before rebinding the index's source metadata. It never changes source metadata just to bypass a mismatch.

The build also creates a lookup index for original source IDs. Existing seed-provenance and source-detail queries can then resolve those IDs without scanning every source payload during a cold request. This changes lookup speed, not which recipes pass pantry checks.

## Temporary storage and restarts

The CSV and index are generated build artifacts, not user-created runtime uploads. They need several GB of build/artifact space. An ordinary startup reads the prepared files and does not download or rebuild them. A new clean deploy may need another download/build. Conversation memory remains temporary and can be cleared on restart; this deployment does not add long-term conversation storage.

If the runtime lacks the prepared artifact, startup fails with a build-command error rather than trying to download several GB before opening its HTTP port. Do not run indexing from a web request.

## Before recording

- Confirm the cloud URL works from another device.
- Confirm the full-corpus record count and run two meal examples, a follow-up and a safety example on that URL.
- Open the service before recording and leave it ready. Free Render services can sleep after 15 idle minutes and can restart; warming up does not guarantee uninterrupted availability.
- Verify the actual deploy's memory, disk and build-time limits. A successful small-fixture test does not establish that the free instance can build or query the complete corpus within its resource limits.
- Check Drive sharing and download quota if the build reports HTML or a download error. Keep the source accessible for clean redeploys. Avoid triggering extra deploys immediately before the demonstration.

Local verification command (synthetic data, no model calls or real CSV download):

```sh
python -m unittest discover -s tests -p test_render_data.py -v
```

Render documentation: https://render.com/docs/free and https://render.com/docs/deploys.
