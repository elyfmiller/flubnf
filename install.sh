#!/usr/bin/env bash
# One-line install:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
# The private engine (the fallback; it needs the lab's engine file) instead of
# the public one, the default:
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | FLUBNF_ENGINE=private bash
# Pasted again on a copy that records the private engine, the plain line
# keeps it; FLUBNF_ENGINE=public chooses the default again.
set -e
DEST="${FLUBNF_DIR:-$HOME/GitHub/flubnf}"   # not Documents: macOS keeps FluBNF.app out of it
# Which engine, checked before anything is cloned: private, or public (empty
# is public). Quotes, surrounding spaces and case do not count; any other
# value stops here, because this is about to install something.
norm() {
  printf '%s' "$1" | tr -d '"' | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}
ROUTE="$(norm "${FLUBNF_ENGINE:-}")"
case "$ROUTE" in
  private) ;;
  ""|public) ;;
  *) echo "FLUBNF_ENGINE is \"$FLUBNF_ENGINE\"; it must be private or public (or unset, for the public engine, the default). Nothing was installed."
     exit 2 ;;
esac
# Nothing named here: a copy already there keeps the private engine when its
# .flubnf.env records it (read in a subshell; the rest of the file changes
# nothing here). Anything else, or no copy yet, is the public engine.
if [ -z "$ROUTE" ]; then
  ROUTE=public
  if [ -f "$DEST/.flubnf.env" ] \
     && [ "$(norm "$( . "$DEST/.flubnf.env" >/dev/null 2>&1; printf '%s' "${FLUBNF_ENGINE:-}" )")" = private ]; then
    ROUTE=private
    echo "This copy is set to the private engine (the fallback) in its .flubnf.env, and it stays so; ./setup_engine.sh --public in $DEST goes back to the default."
  fi
fi
if [ ! -d "$DEST/.git" ]; then
  echo "Cloning flubnf to $DEST…"
  git clone https://github.com/elyfmiller/flubnf "$DEST"
fi
cd "$DEST" && ./setup.sh
# FluBNF.app and FluBNF.command are macOS's. Elsewhere the console starts from
# its venv, and opens in the browser when there is no GTK or Qt for a window.
if [ "$(uname -s)" = Darwin ]; then
  LAUNCH="open \"$DEST/FluBNF.app\"   (or double-click FluBNF.command)"
else
  LAUNCH="\"$DEST/.venv/bin/flubnf\" app"
fi
if [ "$ROUTE" = private ]; then
  # Recorded in .flubnf.env (--private), so the launchers read it.
  PRIVATE_OK=""
  if ./setup_engine.sh --private; then
    PRIVATE_OK=1
  else
    echo "The private engine did not install (see above); the console still runs, and FluBNF.command tries again with the engine file in Downloads."
  fi
  echo
  echo "Done. Launch with:  $LAUNCH"
  echo
  if [ -n "$PRIVATE_OK" ]; then
    echo "This copy runs the private engine (the fallback). Installed from an"
    echo "engine file, it is replaced by a newer one (pybnf-pf-XXXX.tar.gz) saved"
    echo "in your Downloads folder the next time ./setup_engine.sh --private runs."
    echo "./setup_engine.sh --public goes back to the public engine, the default."
    exit 0
  fi
  echo "That console runs the analogue member. The particle filter member needs"
  echo "a private PyBNF fork, which is the one step that can ask for a GitHub"
  echo "account. If the lab gave you an engine file (pybnf-pf-XXXX.tar.gz or"
  echo "pybnf.bundle), save it in your Downloads folder exactly as it is; the"
  echo "next launch installs the engine from it, with no account and no network."
  exit 0
fi
# Recorded in .flubnf.env (--public), so the launchers read it.
./setup_engine.sh --public \
  || echo "The public engine did not install (see above); the console still runs. ./setup_engine.sh tries again (on a Mac, the next open of FluBNF does it)."
echo
echo "Done. Launch with:  $LAUNCH"
