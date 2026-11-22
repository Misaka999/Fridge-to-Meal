"""Disk-backed retrieval of original RecipeNLG/Gathered records.

Retrieval is not verification of quantities, yield, allergies, or pantry feasibility.
"""
import argparse
import ast
import csv
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = ROOT / 'data/RecipeNLG_dataset.csv'
DEFAULT_INDEX = ROOT / 'data/recipenlg.sqlite3'
INDEX_VERSION = '1'


def source_path():
    return Path(os.environ.get('FRIDGE_RECIPE_CSV', DEFAULT_CSV)).expanduser()


def index_path():
    return Path(os.environ.get('FRIDGE_RECIPE_INDEX', DEFAULT_INDEX)).expanduser()


def parse_list(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        value = ast.literal_eval(text)
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError('Expected a list of strings.')
    return value


def signature(path):
    stat = path.stat()
    return {'source': str(path.resolve()), 'bytes': stat.st_size,
            'mtime_ns': stat.st_mtime_ns, 'version': INDEX_VERSION}


def build_index(csv_path=None, destination=None):
    csv_path = Path(csv_path) if csv_path else source_path()
    destination = Path(destination) if destination else index_path()
    if destination.exists():
        raise FileExistsError(f'Index already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.building')
    if temporary.exists():
        raise FileExistsError(f'Unfinished index exists: {temporary}')
    conn = sqlite3.connect(temporary)
    selected = skipped = 0
    try:
        conn.execute('PRAGMA journal_mode=OFF')
        conn.execute('CREATE TABLE recipes (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        conn.execute("CREATE VIRTUAL TABLE terms USING fts5(ingredients, title, content='')")
        conn.execute('CREATE TABLE metadata (value TEXT NOT NULL)')
        csv.field_size_limit(20_000_000)
        with csv_path.open(newline='', encoding='utf-8-sig') as stream:
            rows = csv.DictReader(stream)
            required = {'title', 'ingredients', 'directions', 'source', 'link'}
            if not required.issubset(rows.fieldnames or []):
                raise ValueError('Missing required RecipeNLG columns.')
            for row_number, row in enumerate(rows):
                if row['source'].strip() not in ('Gathered', '0'):
                    continue
                try:
                    ingredients = parse_list(row['ingredients'])
                    steps = parse_list(row['directions'])
                    names = parse_list(row.get('NER', row.get('ner', '[]')))
                    if not ingredients or not steps or not names:
                        raise ValueError('Empty recipe field.')
                except (ValueError, SyntaxError, TypeError):
                    skipped += 1
                    continue
                raw_id = row.get('id') or row.get('') or row.get('Unnamed: 0') or str(row_number)
                recipe = {'id': 'recipenlg_' + raw_id, 'title': row['title'],
                          'source': 'RecipeNLG/Gathered', 'source_url': row['link'],
                          'raw_ingredients': ingredients, 'ingredient_names': names,
                          'steps': steps, 'servings': None, 'quantity_verified': False,
                          'dietary_verified': False}
                cursor = conn.execute('INSERT INTO recipes(payload) VALUES (?)',
                                      (json.dumps(recipe, ensure_ascii=False),))
                conn.execute('INSERT INTO terms(rowid, ingredients, title) VALUES (?,?,?)',
                             (cursor.lastrowid, ' ; '.join(names), row['title']))
                selected += 1
                if selected % 100000 == 0:
                    conn.commit()
                    print(f'Indexed {selected:,} Gathered recipes', flush=True)
        metadata = {**signature(csv_path), 'recipes': selected, 'malformed_skipped': skipped}
        if not selected:
            raise ValueError('No Gathered recipes found.')
        conn.execute('INSERT INTO metadata VALUES (?)', (json.dumps(metadata),))
        conn.commit()
        conn.close()
        temporary.rename(destination)
        return metadata
    except BaseException:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise


def retrieve(request, limit=8):
    path = index_path()
    if not path.exists():
        raise FileNotFoundError('Build the CSV index first: python -m agent.tools.recipenlg_store --build')
    from .ingredient_names import normalize_name, retrieval_name
    names = sorted({retrieval_name(item['name']) for item in request.get('pantry', [])
                    if item.get('quantity', 0) > 0 and
                    (not item.get('expires_on') or item['expires_on'] >= request['as_of_date'])})
    if not names:
        return []
    expression = ' OR '.join('"' + name.replace('"', '""') + '"' for name in names)
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        metadata = json.loads(conn.execute('SELECT value FROM metadata').fetchone()[0])
        if any(metadata.get(key) != value for key, value in signature(source_path()).items()):
            raise ValueError('CSV changed; rebuild its index with a new output path.')
        hits = conn.execute('SELECT r.payload FROM terms JOIN recipes r ON r.id=terms.rowid '
                            'WHERE terms MATCH ? ORDER BY bm25(terms, 1.0, 0.0) LIMIT 200',
                            (expression,)).fetchall()
    ranked = []
    pantry = set(names)
    from .dietary import detected_conflicts
    for (payload,) in hits:
        recipe = json.loads(payload)
        ingredients = {retrieval_name(n) for n in recipe['ingredient_names']}
        matched = ingredients & pantry
        recipe['name_matching_scope'] = 'Lexical retrieval only; subtype equivalence is not verified.'
        missing = ingredients - pantry - {'water'}
        recipe['detected_dietary_conflicts'] = detected_conflicts(
            recipe['raw_ingredients'], request.get('preferences',{}).get('dietary_restrictions',[]))
        recipe['matched_ingredient_names'] = sorted(matched)
        recipe['unmatched_ingredient_names'] = sorted(missing)
        ranked.append((len(missing), -len(matched), recipe['id'], recipe))
    # This is lexical retrieval over a bounded shortlist, not exhaustive feasibility search.
    return [item[-1] for item in sorted(ranked, key=lambda x: x[:3])[:limit]]


def matching_reviewed_records(records):
    """Match original payload hashes; independent of another machine's file paths."""
    path = index_path()
    if not path.exists():
        raise FileNotFoundError('Build the CSV index first, or explicitly use the reviewed JSON catalogue.')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        metadata = json.loads(conn.execute('SELECT value FROM metadata').fetchone()[0])
        if any(metadata.get(key) != value for key, value in signature(source_path()).items()):
            raise ValueError('CSV changed; rebuild the index.')
        import hashlib
        matched = []
        for record in records:
            row = conn.execute("SELECT payload FROM recipes WHERE json_extract(payload, '$.id')=? LIMIT 1",
                               (record['id'],)).fetchone()
            if not row:
                continue
            raw_match=hashlib.sha256(row[0].encode()).hexdigest()==record.get('raw_record_sha256')
            parsed_match=hashlib.sha256(json.dumps(json.loads(row[0]),sort_keys=True).encode()).hexdigest()==record.get('source_record_sha256')
            if raw_match or parsed_match:
                matched.append(record)
        return matched


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV)
    parser.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    if args.build:
        print(json.dumps(build_index(args.csv, args.index), indent=2))
    else:
        parser.error('Use --build to build the local search index.')
