#!/usr/bin/env bash
# Double-click me to install the PF engine (Tier B). Finds your PyBNF
# checkout, or an offline engine bundle, automatically; no typing needed.
cd "$(dirname "$0")"
# A checkout OR an unpacked archive (no .git), same test as setup_engine.sh.
FOUND=""
for c in "${FLUBNF_PYBNF:-}" "$HOME/Documents/GitHub/PyBNF-Private" \
         "$HOME/Documents/GitHub/PyBNF-pf" "$HOME/Documents/PyBNF-Private" \
         "$HOME/PyBNF-Private"; do
  [ -n "$c" ] || continue
  if [ -d "$c/.git" ] || { [ -f "$c/pybnf/pf.py" ] && [ -f "$c/setup.py" ]; }; then
    FOUND="$c"; break
  fi
done
if [ -n "$FOUND" ]; then
  echo "Using PyBNF checkout: $FOUND"
  FLUBNF_PYBNF="$FOUND" ./setup_engine.sh
else
  # No checkout: ask setup_engine.sh (which owns the search) for an offline
  # bundle before any GitHub advice.
  BUNDLE="$(./setup_engine.sh --print-bundle 2>/dev/null)"
  if [ -n "$BUNDLE" ]; then
    echo "No PyBNF checkout yet, but there is an offline engine bundle:"
    echo "  $BUNDLE"
    echo "Installing from it. No GitHub account is needed."
  else
    echo "No PyBNF checkout found in the usual places, and no engine bundle."
    echo "Two ways forward, and the first needs no GitHub account at all:"
    echo "  1. Ask anyone who already has the fork for pybnf.bundle (they run"
    echo "     'git bundle create pybnf.bundle feature/particle-filter'), put"
    echo "     it in your Downloads folder, and double-click me again."
    echo "  2. Clone the fork yourself (branch feature/particle-filter) into"
    echo "     ~/Documents/GitHub/PyBNF-Private, then double-click me again."
    echo "The setup below lists everywhere it looked and how to fix access."
  fi
  ./setup_engine.sh
fi
echo
echo "Done (or see messages above). Press enter to close."
read -r
