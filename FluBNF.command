#!/usr/bin/env bash
# Double-click me. Self-updates, sets up on first run, launches the console.
cd "$(dirname "$0")"

# Stay current (lab-share mode). Fast-forward only, so a real edit is never
# silently overwritten.
#
# What this used to say was "offline or local changes, running as-is", which
# names two causes with opposite remedies and tells the reader which of them
# it is not. On a lab machine one of the two is almost always an accident: a
# stray save, a line ending, a file left open in an editor. That machine then
# runs a month old console against a current engine and nobody knows why. So:
# say which cause it is, name the files, and repair the accidental one by
# STASHING those edits (git stash list has them afterwards, nothing is
# destroyed) and fast-forwarding over them.
#
# Local COMMITS are a different matter and are never touched here: a clone
# with real work on it is not this script to reset. It prints the command
# instead and runs what is on disk.
#
# FLUBNF_UPDATE=off skips the whole block. FLUBNF_UPDATE=force resets to
# origin, discarding local edits AND local commits, for the case where the
# only thing that matters is that this machine matches the lab.
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
  # PF engine missing: install it automatically, right here (one time).
  # The app runs without it (analogue only), so a setup failure never
  # blocks the launch. A failed attempt is stamped so a broken setup does
  # not re-run on every open; the stamp keys on the script, the checkout path
  # and the offline bundle, so cloning the fork, being handed a bundle, or a
  # setup_engine.sh update all earn a retry.
  # A checkout OR a plain unpacked copy. Those came apart the moment the lab
  # started handing students a `git archive` tarball instead of a clone
  # (scripts/cut_engine_archive.sh, docs/INSTALL-STUDENTS.md): that folder has
  # no .git in it, so a test for ".git is there" answered "no engine" about a
  # perfectly good engine, this loop passed FLUBNF_PYBNF="" to setup_engine.sh,
  # and the student who had done exactly what the install page told them to do
  # got the GitHub credentials wall instead. setup_engine.sh accepts the plain
  # copy (it only ever needs an importable package, never git), so the gate
  # here has to ask the same question it does.
  CHECKOUT=""
  for c in "${FLUBNF_PYBNF:-}" "$HOME/Documents/GitHub/PyBNF-Private" \
           "$HOME/Documents/GitHub/PyBNF-pf" "$HOME/Documents/PyBNF-Private" \
           "$HOME/PyBNF-Private"; do
    [ -n "$c" ] || continue
    if [ -d "$c/.git" ] || { [ -f "$c/pybnf/pf.py" ] && [ -f "$c/setup.py" ]; }; then
      CHECKOUT="$c"; break
    fi
  done
  # The offline engine bundle counts as a change of circumstances, and the
  # search for it lives in setup_engine.sh so there is only ever one copy of
  # it. This is the sequence it has to survive: a first run fails for want of
  # GitHub access and stamps itself, someone hands the student pybnf.bundle,
  # they drop it in Downloads and open the app again. Without the bundle in
  # the fingerprint the stamp would suppress exactly the run that would now
  # succeed, and the student would be told to fix an access problem they no
  # longer have.
  BUNDLE="$(./setup_engine.sh --print-bundle 2>/dev/null)"
  # The bundle's SIZE, not just its path. The failure setup_engine.sh says is
  # the realistic one -- "a copy that did not finish ... compare its size with
  # the copy you were given and fetch it again" -- is repaired by writing a
  # good file over the bad one, under the same name, in the same folder. A
  # fingerprint made of the path alone does not move when that happens, so the
  # stamp suppressed the retry the message had just asked for, and the student
  # was told to fix a failure they had already fixed. MEASURED 2026-08-31: a
  # 300-byte truncated pybnf.bundle replaced by the whole file in ~/Downloads
  # produced a byte-identical fingerprint. `wc -c` rather than `stat`, whose
  # flags differ between macOS and Linux; empty when there is no bundle.
  BUNDLESZ=""
  [ -n "$BUNDLE" ] && BUNDLESZ="$(wc -c < "$BUNDLE" 2>/dev/null | tr -d ' ')"
  ATTEMPT=".venv/.engine-attempt"
  FP="$(shasum setup_engine.sh 2>/dev/null | cut -c1-16):${CHECKOUT:-none}:${BUNDLE:-none}:${BUNDLESZ:-0}"
  # The stamp exists only to stop re-running a DOOMED attempt on every open,
  # and the only doomed attempt is the one with nothing local to install from:
  # no bundle, no checkout, so it walks into the GitHub credentials wall every
  # time. When a bundle or a checkout IS present the attempt is not doomed, it
  # is a local install that a transient first failure (a network blip, a conda
  # hiccup during the heavier first run) should not suppress. MEASURED
  # 2026-09-02 on a lab machine: the engine file sat in Downloads the whole
  # time, so its fingerprint never changed, and a single transient failure
  # stamped the machine into analogue-only until SetupEngine.command was
  # double-clicked. So: honor the stamp ONLY when there is nothing local to
  # try; otherwise always retry.
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
