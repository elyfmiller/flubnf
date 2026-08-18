#!/usr/bin/env bash
# Double-click me. Sets up on first run, then launches the console.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/flubnf ]; then
  echo "First run — setting up (a few minutes)…"
  ./setup.sh || { echo; echo "Setup hit a problem (see above). Press enter to close."; read -r; exit 1; }
fi
[ -f .flubnf.env ] && . ./.flubnf.env
( sleep 2; open "http://localhost:8710" ) &
echo "FluBNF console starting — your browser will open. Ctrl-C here to stop."
exec .venv/bin/flubnf app
