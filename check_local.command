#!/bin/bash
set -u
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT" || exit 1
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then printf 'Set up the project virtual environment first.\n'; exit 1; fi
export LANGSMITH_TRACING=false
"$PYTHON" -m unittest discover -s tests -q
STATUS=$?
if [ "$STATUS" -eq 0 ]; then
 "$PYTHON" -m eval.evaluate_project --check-only
 STATUS=$?
fi
if [ "$STATUS" -eq 0 ]; then
 "$PYTHON" -m eval.evaluate_safety --check-only
 STATUS=$?
fi
printf '\nOffline checks finished. No paid model calls were made.\n'
if [ -t 0 ]; then read -r -p 'Press Enter to close. ' REPLY; fi
exit "$STATUS"
