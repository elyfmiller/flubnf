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
