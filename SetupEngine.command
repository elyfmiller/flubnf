#!/usr/bin/env bash
# Double-click me to install the PF engine (Tier B). Finds your PyBNF
# checkout automatically; no typing needed.
cd "$(dirname "$0")"
FOUND=""
for c in "${FLUBNF_PYBNF:-}" "$HOME/Documents/GitHub/PyBNF-Private" \
         "$HOME/Documents/GitHub/PyBNF-pf" "$HOME/Documents/PyBNF-Private" \
         "$HOME/PyBNF-Private"; do
  [ -n "$c" ] && [ -d "$c/.git" ] && { FOUND="$c"; break; }
done
if [ -n "$FOUND" ]; then
  echo "Using PyBNF checkout: $FOUND"
  FLUBNF_PYBNF="$FOUND" ./setup_engine.sh
else
  echo "No PyBNF checkout found in the usual places."
  echo "Clone your fork (branch feature/particle-filter) somewhere like:"
  echo "  ~/Documents/GitHub/PyBNF-Private"
  echo "then double-click me again. (setup_engine.sh can also clone it for"
  echo "you if your SSH key is set up — it will guide you.)"
  ./setup_engine.sh
fi
echo
echo "Done (or see messages above). Press enter to close."
read -r
