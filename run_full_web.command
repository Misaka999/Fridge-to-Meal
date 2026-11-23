#!/bin/bash
set -eu
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" web_app.py --port 8766 --recipe-source full
