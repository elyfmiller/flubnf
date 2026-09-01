#!/usr/bin/env bash
# One-line install:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
set -e
DEST="${FLUBNF_DIR:-$HOME/Documents/GitHub/flubnf}"
if [ ! -d "$DEST/.git" ]; then
  echo "Cloning flubnf to $DEST…"
  git clone https://github.com/elyfmiller/flubnf "$DEST"
fi
cd "$DEST" && ./setup.sh
echo
echo "Done. Launch with:  open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
echo
echo "That console runs the analogue member. The particle filter member needs"
echo "a private PyBNF fork, which is the one step that can ask for a GitHub"
echo "account. If the lab gave you an engine file (pybnf-pf-XXXX.tar.gz or"
echo "pybnf.bundle), save it in your Downloads folder exactly as it is; the"
echo "next launch installs the engine from it, with no account and no network."
