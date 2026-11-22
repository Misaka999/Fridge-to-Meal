#!/bin/bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
printf 'Offline tools demo: no model API calls.\n\nVegan lentils and rice:\n'
python3 -m scripts.tools_cli --recipe-file data/recipes_expanded.json --request examples/example_request_expanded_lentils.json
STATUS=$?
if [ "$STATUS" -eq 0 ]; then
  printf '\nBeef and potato recipe:\n'
  python3 -m scripts.tools_cli --recipe-file data/recipes_expanded.json --request examples/example_request_expanded_beef.json
  STATUS=$?
fi
if [ -t 0 ]; then read -r -p 'Press Enter to close. ' REPLY; fi
exit "$STATUS"
