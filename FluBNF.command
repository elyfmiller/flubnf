#!/usr/bin/env bash
# Double-click me. Self-updates, sets up on first run, launches the console.
cd "$(dirname "$0")"

# stay current (lab-share mode): fast-forward only, never clobbers local edits
if [ -d .git ]; then
  git pull --ff-only -q 2>/dev/null && echo "· up to date with origin" \
    || echo "· offline or local changes — running as-is"
fi

# Dependency refresh policy (regression fix, 2026-08-22): the package is
# installed EDITABLE, so pulled code changes are live without any reinstall;
# pip is needed only when the project metadata (pyproject.toml) changes.
# The old unconditional quiet reinstall here (a) uninstalled and reinstalled
# the package on EVERY open, adding half a minute to each launch, and
# (b) had a window between uninstall and reinstall in which .venv/bin/flubnf
# did not exist, with all errors hidden: an interrupted or failed open left
# the app unlaunchable until the NEXT open fell into full setup. That is the
# "open, close, open again" failure. Now: install only when pyproject.toml
# differs from the stamp of the last successful install, say so out loud,
# never hide the errors, and verify the launcher exists before using it.
STAMP=".venv/.pyproject.stamp"
if [ ! -x .venv/bin/flubnf ]; then
  echo "First run — setting up (a few minutes)…"
  ./setup.sh || { echo; echo "Setup hit a problem (see above). Press enter to close."; read -r; exit 1; }
  cp pyproject.toml "$STAMP" 2>/dev/null
elif ! cmp -s pyproject.toml "$STAMP" 2>/dev/null; then
  echo "· project dependencies changed, refreshing (about a minute)"
  if .venv/bin/pip install -q -e ".[app,dev]"; then
    cp pyproject.toml "$STAMP" 2>/dev/null
  else
    echo "· dependency refresh failed (offline?), running with what is installed"
  fi
fi

if [ ! -x .venv/bin/flubnf ]; then
  echo
  echo "The FluBNF launcher is missing from .venv: setup did not finish."
  echo "Double-click me again with the network up, or run ./setup.sh in"
  echo "Terminal to see the full output. Press enter to close."
  read -r
  exit 1
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
.venv/bin/flubnf app
STATUS=$?

# On a clean exit (including Ctrl-C), close this Terminal window rather than
# leaving a dead one behind. On a real error, hold the window open so the
# message can be read. The osascript targets only the window whose tab owns
# this tty, and the shell exits before it fires, so Terminal closes without
# a "process still running" prompt.
case "$STATUS" in
  0|130|143)
    if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
      THIS_TTY=$(tty)
      ( sleep 0.3; osascript -e "tell application \"Terminal\" to close (every window whose selected tab's tty is \"$THIS_TTY\") saving no" ) >/dev/null 2>&1 &
    fi
    ;;
  *)
    echo
    echo "FluBNF exited with an error (code $STATUS). Press enter to close."
    read -r
    ;;
esac
exit "$STATUS"
