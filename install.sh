#!/usr/bin/env bash
# One-line install:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
# The public engine instead of the private one (opt-in until the cutover):
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | FLUBNF_ENGINE=public bash
set -e
DEST="${FLUBNF_DIR:-$HOME/GitHub/flubnf}"   # not Documents: macOS keeps FluBNF.app out of it
if [ ! -d "$DEST/.git" ]; then
  echo "Cloning flubnf to $DEST…"
  git clone https://github.com/elyfmiller/flubnf "$DEST"
fi
cd "$DEST" && ./setup.sh
if [ "${FLUBNF_ENGINE:-}" = public ]; then
  # Recorded in .flubnf.env (--public), so the launchers follow it.
  ./setup_engine.sh --public \
    || echo "The public engine did not install (see above); the console still runs."
  echo
  echo "Done. Launch with:  open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
  exit 0
fi
echo
echo "Done. Launch with:  open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
echo
echo "That console runs the analogue member. The particle filter member needs"
echo "a private PyBNF fork, which is the one step that can ask for a GitHub"
echo "account. If the lab gave you an engine file (pybnf-pf-XXXX.tar.gz or"
echo "pybnf.bundle), save it in your Downloads folder exactly as it is; the"
echo "next launch installs the engine from it, with no account and no network."
