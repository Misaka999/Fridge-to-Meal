#!/bin/bash
set -u
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT" || exit 1
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then printf 'Set up the virtual environment first.\n'; exit 1; fi
printf 'Paid model evaluation: Yangyang 100-case partition, baseline and plan_replan, 3 trials.\n'
OUT="results/project_yangyang_$(date +%Y%m%d_%H%M%S)"
"$PYTHON" -m eval.evaluate_project --tasks eval/project/tasks_yangyang_100.jsonl --trials 3 --versions baseline plan_replan --workers 3 --allow-partial --output "$OUT"
STATUS=$?
printf '\nExit status: %s. Output path if created: %s\n' "$STATUS" "$OUT"
if [ -t 0 ]; then read -r -p 'Press Enter to close. ' REPLY; fi
exit "$STATUS"
