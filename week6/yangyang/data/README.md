# Recipe data

## Checked-in files

- `recipes_recipenlg.json`: three annotated records from the locally downloaded RecipeNLG/Gathered CSV: 68810, 33232 and 55429. Original ingredients, steps, explicit yields, source links and original indexed-payload SHA-256 hashes are retained. All are side dishes. Compatibility flags can be true, false or null; null requires clarification.
- `example_request_real.json`: input for a quantity-checked real-source tool example.
- `recipes.json` and `example_request.json`: hand-authored fixtures for regression tests, explicitly not RecipeNLG records.

US customary mass and volume definitions are used for like-dimension conversions only. No ingredient-density conversions or missing yields are guessed.

## Obtain the full dataset separately

Original project: https://github.com/Glorf/recipenlg
Original download page: https://recipenlg.cs.put.poznan.pl/dataset
Mirror used locally when the original page was unavailable: https://huggingface.co/datasets/SandhyaKilari/RecipeNLG_dataset/tree/main

The downloaded file is `RecipeNLG_dataset.csv`, 2,294,981,083 bytes. Columns include an index, title, ingredients, directions, link, source, and NER. This is provenance to a third-party mirror, not a claim of byte identity with an authenticated original release. Consult the original dataset's applicable terms and recipe-source rights; no new license is asserted here. The original project describes noncommercial research/educational use conditions.

Place the file in this directory, then run from the parent directory:

```sh
python3 recipenlg_store.py --build
```

If the original download supplies `full_dataset.csv`, use `--csv` and set `FRIDGE_RECIPE_CSV` to the same file when running tools. CSV and SQLite files are ignored by Git.

No full dataset, API keys, machine-specific absolute paths, live benchmark results, or private user pantry records are included.
