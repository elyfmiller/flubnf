#!/usr/bin/env bash
# Double-click me. Self-updates, sets up on first run, launches the console.
cd "$(dirname "$0")"

# stay current (lab-share mode): fast-forward only, never clobbers local edits
if [ -d .git ]; then
  git pull --ff-only -q 2>/dev/null && echo "· up to date with origin" \
    || echo "· offline or local changes — running as-is"
fi

if [ ! -x .venv/bin/flubnf ]; then
  echo "First run — setting up (a few minutes)…"
  ./setup.sh || { echo; echo "Setup hit a problem (see above). Press enter to close."; read -r; exit 1; }
else
  # keep deps in sync with the pulled code (fast when nothing changed)
  .venv/bin/pip install -q -e ".[app,dev]" 2>/dev/null
fi

[ -f .flubnf.env ] && . ./.flubnf.env
if [ ! -x "${FLUBNF_PY_ENGINE:-/nonexistent}" ]; then
  for c in "$HOME/Documents/GitHub/PyBNF-Private" "$HOME/Documents/GitHub/PyBNF-pf" \
           "$HOME/Documents/PyBNF-Private" "$HOME/PyBNF-Private"; do
    if [ -d "$c/.git" ]; then
      echo "· PyBNF checkout found at $c — double-click SetupEngine.command to enable the PF engine"
      break
    fi
  done
fi

echo "FluBNF console starting — a window (or browser tab) will open. Ctrl-C here to stop."
exec .venv/bin/flubnf app
