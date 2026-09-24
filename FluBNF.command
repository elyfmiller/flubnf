#!/usr/bin/env bash
# Double-click me. Self-updates, sets up on first run, launches the console.
cd "$(dirname "$0")"

# Stay current (lab-share mode). Fast-forward only, so a real edit is never
# silently overwritten. Say which cause blocks an update: stray tracked edits
# (usually accidents) are stashed (git stash list) and fast-forwarded over;
# local commits are never touched (the reset command is printed instead).
# FLUBNF_UPDATE=off skips; FLUBNF_UPDATE=force resets to origin, discarding both.
if [ -d .git ] && [ "${FLUBNF_UPDATE:-}" != "off" ]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  UP="$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null)"
  [ -n "$UP" ] || UP="origin/${BRANCH:-main}"
  RESET="git -C \"$PWD\" fetch origin && git -C \"$PWD\" reset --hard $UP"
  if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ]; then
    echo "· not on a branch, running the copy on disk"
  elif ! git fetch -q origin 2>/dev/null; then
    echo "· offline (origin unreachable), running the copy on disk"
  elif [ "${FLUBNF_UPDATE:-}" = "force" ]; then
    if git reset --hard -q "$UP" 2>/dev/null; then
      echo "· forced to $UP: local edits and commits discarded"
    else
      echo "· could not reset to $UP, running the copy on disk"
    fi
  elif FF="$(git merge --ff-only "$UP" 2>&1)"; then
    echo "· up to date with origin"
  else
    AHEAD="$(git rev-list --count "$UP..HEAD" 2>/dev/null || echo 0)"
    DIRTY="$(git status --porcelain --untracked-files=no 2>/dev/null)"
    if [ "${AHEAD:-0}" != "0" ]; then
      echo "· this clone has $AHEAD commit(s) origin does not, so it cannot"
      echo "  fast-forward. Nothing here will discard them. Running as-is. To"
      echo "  take origin's copy and throw this clone's work away:"
      echo "      $RESET"
    elif [ -n "$DIRTY" ]; then
      echo "· local edits are blocking the update:"
      printf '%s\n' "$DIRTY" | sed 's/^/    /'
      if git stash push -q -m "FluBNF update $(date '+%Y-%m-%d %H:%M')" 2>/dev/null \
         && git merge --ff-only -q "$UP" 2>/dev/null; then
        echo "· updated anyway; those edits were set aside, not lost. In this"
        echo "  folder, git stash list shows them and git stash pop puts them"
        echo "  back."
      else
        git stash pop -q 2>/dev/null
        echo "· could not update around them, running the copy on disk. To"
        echo "  take origin's copy and discard the edits above:"
        echo "      $RESET"
      fi
    else
      echo "· could not update, running the copy on disk:"
      printf '%s\n' "$FF" | sed 's/^/    /' | head -6
      echo "  To take origin's copy whatever is in the way:"
      echo "      $RESET"
    fi
  fi
fi

# Dependency refresh policy: the package is editable, so pip runs only when
# pyproject.toml differs from the last good install's stamp. Never reinstall
# on every open (slow, and an interrupted reinstall left no .venv/bin/flubnf);
# keep errors visible and check the launcher exists before using it.
STAMP=".venv/.pyproject.stamp"
if [ ! -x .venv/bin/flubnf ]; then
  echo "First run, setting up (a few minutes)..."
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
  # PF engine missing: install it now (one time). Failure never blocks the
  # launch (analogue only). A checkout OR an unpacked archive (no .git) counts,
  # the same test as setup_engine.sh.
  CHECKOUT=""
  for c in "${FLUBNF_PYBNF:-}" "$HOME/Documents/GitHub/PyBNF-pf" \
           "$HOME/Documents/GitHub/PyBNF-Private" "$HOME/Documents/PyBNF-Private" \
           "$HOME/PyBNF-Private"; do
    [ -n "$c" ] || continue
    if [ -d "$c/.git" ] || { [ -f "$c/pybnf/pf.py" ] && [ -f "$c/setup.py" ]; }; then
      CHECKOUT="$c"; break
    fi
  done
  # A failed attempt is stamped with a fingerprint so a doomed setup does not
  # re-run on every open. It keys on the setup_engine.sh hash, the checkout
  # and the offline bundle (searched by setup_engine.sh, the only copy), so a
  # new checkout, bundle or script earns a retry.
  BUNDLE="$(./setup_engine.sh --print-bundle 2>/dev/null)"
  # The bundle's SIZE too: a truncated copy replaced under the same name must
  # retry. `wc -c`, not stat (flags differ between macOS and Linux).
  BUNDLESZ=""
  [ -n "$BUNDLE" ] && BUNDLESZ="$(wc -c < "$BUNDLE" 2>/dev/null | tr -d ' ')"
  ATTEMPT=".venv/.engine-attempt"
  FP="$(shasum setup_engine.sh 2>/dev/null | cut -c1-16):${CHECKOUT:-none}:${BUNDLE:-none}:${BUNDLESZ:-0}"
  # Honor the stamp only when nothing local exists (the doomed GitHub-wall
  # case); with a bundle or checkout present, always retry (a transient
  # failure must not stamp a machine into analogue-only).
  if [ -z "$BUNDLE$CHECKOUT" ] && [ "$(cat "$ATTEMPT" 2>/dev/null)" = "$FP" ]; then
    echo "· PF engine still not installed: the last attempt found no engine to"
    echo "  install from, so it is not retried on every open. The one-file fix,"
    echo "  no GitHub account needed: ask the lab for pybnf-pf-<sha>.tar.gz, put"
    echo "  it in your Downloads folder, and open this again; it installs itself."
    echo "  Or double-click SetupEngine.command to try now and see what it finds."
    echo "  Analogue forecasts work in the meantime."
  else
    echo "· PF engine not installed yet, setting it up now (one time, a few minutes)"
    [ -n "$BUNDLE" ] && echo "  using the offline bundle $BUNDLE (no GitHub account needed)"
    if FLUBNF_PYBNF="$CHECKOUT" ./setup_engine.sh; then
      rm -f "$ATTEMPT"
      [ -f .flubnf.env ] && . ./.flubnf.env
      echo "· PF engine ready"
    else
      echo "$FP" > "$ATTEMPT"
      echo "· engine setup did not finish (see messages above). The console still"
      echo "  runs, analogue forecasts only. With the engine file in your Downloads"
      echo "  folder the next open tries again by itself; to try right now without"
      echo "  waiting, double-click SetupEngine.command. The shortcut past the"
      echo "  whole GitHub question is pybnf-pf-<sha>.tar.gz in Downloads."
    fi
  fi
fi

echo "FluBNF console starting. A window (or browser tab) will open. Ctrl-C here to stop."
.venv/bin/flubnf app
STATUS=$?

# Clean exit (incl. Ctrl-C): close only this tty's Terminal window, after the
# shell exits (no "process still running" prompt). On error, keep it open.
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
