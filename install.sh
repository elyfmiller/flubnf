#!/usr/bin/env bash
# One-line install:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
# The private engine (the fallback; it needs the lab's engine file) instead of
# the public one, the default:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | FLUBNF_ENGINE=private bash
set -e
DEST="${FLUBNF_DIR:-$HOME/GitHub/flubnf}"   # not Documents: macOS keeps FluBNF.app out of it
# Which engine, checked before anything is cloned: private, or public (empty
# is public). Quotes, surrounding spaces and case do not count; any other
# value stops here, because this is about to install something.
ROUTE="$(printf '%s' "${FLUBNF_ENGINE:-}" | tr -d '"' | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
case "$ROUTE" in
  private) ;;
  ""|public) ROUTE=public ;;
  *) echo "FLUBNF_ENGINE is \"$FLUBNF_ENGINE\"; it must be private or public (or unset, for the public engine, the default). Nothing was installed."
     exit 2 ;;
esac
if [ ! -d "$DEST/.git" ]; then
  echo "Cloning flubnf to $DEST…"
  git clone https://github.com/elyfmiller/flubnf "$DEST"
fi
cd "$DEST" && ./setup.sh
if [ "$ROUTE" = private ]; then
  # Recorded in .flubnf.env (--private), so the launchers read it.
  ./setup_engine.sh --private \
    || echo "The private engine did not install (see above); the console still runs, and FluBNF.command tries again with the engine file in Downloads."
  echo
  echo "Done. Launch with:  open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
  echo
  echo "That console runs the analogue member. The particle filter member needs"
  echo "a private PyBNF fork, which is the one step that can ask for a GitHub"
  echo "account. If the lab gave you an engine file (pybnf-pf-XXXX.tar.gz or"
  echo "pybnf.bundle), save it in your Downloads folder exactly as it is; the"
  echo "next launch installs the engine from it, with no account and no network."
  exit 0
fi
# Recorded in .flubnf.env (--public), so the launchers read it.
./setup_engine.sh --public \
  || echo "The public engine did not install (see above); the console still runs, and FluBNF.command tries again on its next open."
echo
echo "Done. Launch with:  open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
