#!/usr/bin/env bash
# Double-click me to install the PF engine (Tier B). Finds your PyBNF
# checkout, or an offline engine bundle, automatically; no typing needed.
cd "$(dirname "$0")"
# A checkout OR a plain unpacked copy, the same question FluBNF.command and
# setup_engine.sh ask. The lab's engine archive unpacks without a .git
# directory, and the installer never needed one: it pip-installs the folder.
# Testing for .git here sent a student who had followed the install page
# exactly on to the GitHub credentials advice below.
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
  # No checkout. Before saying anything about GitHub, ask setup_engine.sh
  # whether an offline bundle is lying around: that route needs no account,
  # no invitation and no network, so a student who has the file should never
  # read the credentials advice at all. The search itself lives in
  # setup_engine.sh; asking it keeps one copy of the answer.
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
