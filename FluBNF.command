#!/usr/bin/env bash
# Double-click me. Sets up on first run, then launches the console.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/flubnf ]; then
  echo "First run — setting up (a few minutes)…"
  ./setup.sh || { echo; echo "Setup hit a problem (see above). Press enter to close."; read -r; exit 1; }
fi
[ -f .flubnf.env ] && . ./.flubnf.env
echo "FluBNF console starting — a window (or browser tab) will open. Ctrl-C here to stop."
exec .venv/bin/flubnf app
