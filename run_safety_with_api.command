#!/bin/bash
set -u
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT" || exit 1
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then printf 'Set up the virtual environment first.\n'; exit 1; fi
printf 'Paid safety evaluation: 25-case member partition, baseline and plan_replan.\n'
OUT="results/safety_yangyang_$(date +%Y%m%d_%H%M%S)"
"$PYTHON" -m eval.evaluate_safety --cases eval/project/safety_yangyang_25.jsonl --versions baseline plan_replan --allow-partial --output "$OUT"
STATUS=$?
printf '\nExit status: %s. Output path if created: %s\n' "$STATUS" "$OUT"
if [ -t 0 ]; then read -r -p 'Press Enter to close. ' REPLY; fi
exit "$STATUS"
