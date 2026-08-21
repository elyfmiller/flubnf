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
