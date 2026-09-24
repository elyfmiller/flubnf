#!/usr/bin/env bash
# Reinstall FluBNF from scratch on a lab machine whose copy is stale or broken.
#
#   curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash
#
# A stale lab machine is several problems at once (launcher cannot
# fast-forward, engine venv present so a new archive is never installed, an old
# archive wins newest-by-mtime, an old console holds port 8710). This fixes
# them in order and prints each step.
#
# Checks first, nothing changes until they pass: git/curl/tar/pgrep, Python
# 3.11/3.12 or conda, no console running and port 8710 free, GitHub reachable,
# a VALID engine archive where setup looks, no developer setup. Then the old
# install is SET ASIDE, never deleted (renamed -old-<stamp>; old launchers
# chmod -x; other engine files moved to Downloads/old-engine-files), and:
# clone, setup.sh, setup_engine.sh with the chosen archive, open the console.
# If no new console exists when it stops, the old copies are put back.
#
# Refuses a machine already current, a checkout with uncommitted work, or a
# shell exporting FluBNF settings; FLUBNF_REINSTALL_FORCE=1 overrides all three.
#
# KNOBS, all optional:
#   FLUBNF_DIR                   where the clone goes (default ~/Documents/GitHub/flubnf)
#   FLUBNF_ENGINE_VENV           where the engine venv goes (default ~/.venvs/flubnf-engine)
#   FLUBNF_REPO                  clone URL (default the public GitHub repository)
#   FLUBNF_REINSTALL_YES=1       do not wait for Return before changing anything
#   FLUBNF_REINSTALL_FORCE=1     reinstall even when the machine is already current
#   FLUBNF_REINSTALL_NO_INSTALL=1  stop after setting the old install aside (tests)
#   FLUBNF_REINSTALL_NO_OPEN=1   do not open the console at the end (tests, ssh)
#   FLUBNF_REINSTALL_IGNORE_RUNNING=1  skip the running-console and port checks
#                                (tests on a developer machine whose console is up)
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

DEST="${FLUBNF_DIR:-$HOME/Documents/GitHub/flubnf}"
DEST="${DEST%/}"   # a trailing slash would put the rename target inside DEST
REPO="${FLUBNF_REPO:-https://github.com/elyfmiller/flubnf}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
ENGINE_VENV="${ENGINE_VENV%/}"
STAMP="$(date +%Y%m%d-%H%M%S)"
PARENT="$(dirname "$DEST")"
KEEP="$HOME/Downloads/old-engine-files"
LINE='curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash'
CHANGED=""
DONE=""
SET_ASIDE=()

stop() {
  warn "$*"
  echo
  [ -n "$CHANGED" ] || echo "Nothing on this machine was changed."
  exit 1
}

# Runs on every exit. Set aside but no new clone yet: put the old copies back.
# Clone exists: say where things are (the launcher retries setup.sh itself).
on_exit() {
  _rc=$?
  trap - EXIT
  [ -n "$CHANGED" ] && [ -z "$DONE" ] || exit "$_rc"
  echo
  if [ ! -e "$DEST" ]; then
    echo "The install did not finish, so the old copies go back where they were:"
    if [ ${#SET_ASIDE[@]} -gt 0 ]; then
      for d in "${SET_ASIDE[@]}"; do
        _orig="${d%-old-$STAMP}"
        mv "$d" "$_orig" && echo "    put back: $_orig"
      done
    fi
    for l in FluBNF.command SetupEngine.command; do
      [ -f "$DEST/$l" ] && chmod a+x "$DEST/$l"
    done
    echo "Your previous FluBNF is as it was. Paste the line again when ready."
  else
    echo "The install did not finish. The new copy is at $DEST; open"
    echo "$DEST/FluBNF.command to let setup finish, or send Ely this window."
    if [ ${#SET_ASIDE[@]} -gt 0 ]; then
      echo "The old copies are still here, renamed:"
      for d in "${SET_ASIDE[@]}"; do echo "    $d"; done
    fi
  fi
  exit "$_rc"
}

# The folders setup_engine.sh searches (keep in step), deduplicated: the sweep
# must cover them all or a leftover file still wins newest-by-mtime.
engine_dirs() {
  printf '%s\n' "$PARENT" "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" | awk '!seen[$0]++'
}

# An engine archive has one top folder holding pybnf/pf.py and setup.py
# (as cut_engine_archive.sh writes); a same-named review package does not.
is_engine_archive() {
  _l="$(tar -tzf "$1" 2>/dev/null)" || return 1
  _t="$(printf '%s\n' "$_l" | grep -m1 -E '^[^/]+/pybnf/pf\.py$' | cut -d/ -f1)"
  [ -n "$_t" ] && printf '%s\n' "$_l" | grep -q -x -F "$_t/setup.py"
}

# Line N of the VERSION file inside an archive (1 = "<ref> <sha>", 2 = "cut
# <date> from <remote>"), without unpacking it.
archive_version_line() {
  _m="$(tar -tzf "$1" 2>/dev/null | grep -m1 -E '(^|/)VERSION$')" || return 0
  [ -n "$_m" ] && tar -xzOf "$1" "$_m" 2>/dev/null | sed -n "${2}p"
}

main() {
say "checks (nothing is changed yet)"
[ "$(id -u)" -ne 0 ] || stop "do not run this as root or with sudo; run it as yourself"
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) stop "this script is for macOS and Linux; on Windows follow the guide's Windows steps" ;;
esac
for t in git curl tar pgrep; do
  command -v "$t" >/dev/null 2>&1 \
    || stop "$t is not installed. On a Mac, paste this into Terminal: xcode-select --install" \
            "then click Install, wait for it to finish, and paste the line again."
done
ok "git, curl, tar and pgrep are present"

# Exported FLUBNF_* settings mean a development setup: the setup scripts would
# follow them to folders never set aside. Documented knobs are exempt.
STRAY="$(env | grep '^FLUBNF_' | grep -v -E '^FLUBNF_(REINSTALL_[A-Z_]*|REPO|DIR|ENGINE_VENV|HUB)=' || true)"
if [ -n "$STRAY" ] && [ -z "${FLUBNF_REINSTALL_FORCE:-}" ]; then
  printf '%s\n' "$STRAY" | sed 's/^/      /'
  stop "this Terminal has FluBNF settings exported (above), so this is not a plain lab" \
       "install. Open a new Terminal window without them, or run with FLUBNF_REINSTALL_FORCE=1."
fi

# Engine needs 3.11/3.12 (numpy<2 wheels); same candidates as setup_engine.sh,
# checked before anything moves, then put first on PATH so setup.sh probes the
# same interpreter.
PY=""
for c in python3.12 python3.11 python3; do
  cand=$(command -v "$c" 2>/dev/null) || continue
  "$cand" -c 'import sys; assert sys.version_info[:2] in ((3,11),(3,12))' 2>/dev/null \
    && { PY="$cand"; break; }
done
if [ -z "$PY" ]; then
  for cand in /opt/anaconda3/bin/python3.12 "$HOME/anaconda3/bin/python3.12" \
              /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
              /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 \
              /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12; do
    [ -x "$cand" ] && { PY="$cand"; break; }
  done
fi
if [ -n "$PY" ]; then
  ok "$("$PY" -V 2>&1) at $PY"
  PATH="$(dirname "$PY"):$PATH"; export PATH
else
  CONDA=$(command -v conda 2>/dev/null)
  [ -z "$CONDA" ] && for c in /opt/anaconda3/bin/conda "$HOME/anaconda3/bin/conda" \
                              "$HOME/miniconda3/bin/conda"; do
    [ -x "$c" ] && { CONDA="$c"; break; }
  done
  if [ -n "$CONDA" ]; then
    ok "no Python 3.11/3.12 on PATH; conda at $CONDA will make one"
  else
    stop "Python 3.12 is not installed. Install Anaconda (anaconda.com/download, defaults" \
         "are fine) or Python 3.12 from python.org/downloads (not 3.13 or 3.14), open a" \
         "new Terminal window, and paste the line again."
  fi
fi

# A running console holds port 8710 and is the reader's to quit (another
# account's shows only as the port being taken).
if [ -z "${FLUBNF_REINSTALL_IGNORE_RUNNING:-}" ]; then
  if pgrep -U "$(id -u)" -f 'flubnf (app|window)' >/dev/null 2>&1; then
    stop "FluBNF is still running. Quit it (or restart the computer), then paste the line again."
  fi
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8710 -sTCP:LISTEN >/dev/null 2>&1; then
    stop "something is already serving port 8710 (another account's FluBNF?). Restart the" \
         "computer, then paste the line again."
  fi
  ok "no FluBNF console is running"
fi

# GitHub must be reachable BEFORE anything is set aside.
REMOTE_SHA="$(git ls-remote "$REPO" refs/heads/main 2>/dev/null | cut -c1-40)"
[ -n "$REMOTE_SHA" ] || stop "cannot reach $REPO (no internet, or a VPN in the way). Connect and paste the line again."
ok "GitHub is reachable; latest FluBNF is ${REMOTE_SHA:0:7}"

# As setup_engine.sh searches, plus a content check: the newest VALID archive
# wins; every other engine file (only the names setup searches) is swept below.
ARCHIVE=""
OTHERS=()
while IFS= read -r d; do
  [ -d "$d" ] || continue
  for f in "$d"/pybnf*.tar.gz "$d"/PyBNF*.tar.gz "$d"/pybnf*.bundle "$d"/PyBNF*.bundle; do
    [ -f "$f" ] || continue
    if [ -n "$ARCHIVE" ] && [ "$f" -ef "$ARCHIVE" ]; then continue; fi
    case "$f" in
      *.tar.gz)
        if is_engine_archive "$f"; then
          if [ -z "$ARCHIVE" ]; then ARCHIVE="$f"
          elif [ "$f" -nt "$ARCHIVE" ]; then OTHERS+=("$ARCHIVE"); ARCHIVE="$f"
          else OTHERS+=("$f"); fi
        else
          OTHERS+=("$f")
        fi ;;
      *) OTHERS+=("$f") ;;
    esac
  done
done < <(engine_dirs)
if [ -z "$ARCHIVE" ]; then
  stop "no engine file found. Save the pybnf-pf-<sha>.tar.gz you were sent in your Downloads" \
       "folder (do not unzip or rename it), then paste the line again. If Downloads holds a" \
       "pybnf-pf-<sha>.tar or a PyBNF-Private folder instead, the file was unpacked: ask for it again."
fi
STAMP_NEW="$(archive_version_line "$ARCHIVE" 1)"
CUT_NEW="$(archive_version_line "$ARCHIVE" 2 | awk '{print $2}')"
ok "engine file: $ARCHIVE"
[ -n "$STAMP_NEW" ] && ok "its version stamp: $STAMP_NEW"

# Installed stamp, read in a subshell so .flubnf.env's FLUBNF_* do not leak
# into the setup scripts below.
INSTALLED_STAMP="$(
  [ -f "$DEST/.flubnf.env" ] || exit 0
  # shellcheck disable=SC1091
  . "$DEST/.flubnf.env"
  [ -f "${FLUBNF_PYBNF:-/nonexistent}/VERSION" ] && head -1 "$FLUBNF_PYBNF/VERSION"
)"
INSTALLED_CUT="$(
  [ -f "$DEST/.flubnf.env" ] || exit 0
  # shellcheck disable=SC1091
  . "$DEST/.flubnf.env"
  [ -f "${FLUBNF_PYBNF:-/nonexistent}/VERSION" ] && sed -n 2p "$FLUBNF_PYBNF/VERSION" | awk '{print $2}'
)"

# Refuse a silent downgrade here: setup_engine.sh's guard needs the installed
# copy in place, which the rename below removes.
if [ -z "${FLUBNF_REINSTALL_FORCE:-}" ] && [ -n "$CUT_NEW" ] && [ -n "$INSTALLED_CUT" ] \
   && [ "$STAMP_NEW" != "$INSTALLED_STAMP" ] && [ "$CUT_NEW" \< "$INSTALLED_CUT" ]; then
  stop "the engine file in Downloads ($STAMP_NEW, cut $CUT_NEW) is OLDER than the engine" \
       "already installed ($INSTALLED_STAMP, cut $INSTALLED_CUT). Ask for the current file, or" \
       "run with FLUBNF_REINSTALL_FORCE=1 to install the older one anyway."
fi

# Already current (latest main, clean, console imports, this archive's engine
# imports)? Then pasting the line twice must not set it aside.
if [ -z "${FLUBNF_REINSTALL_FORCE:-}" ] && [ -d "$DEST/.git" ] && [ -x "$DEST/.venv/bin/flubnf" ]; then
  LOCAL_SHA="$(git -C "$DEST" rev-parse HEAD 2>/dev/null)"
  CLEAN="$([ -z "$(git -C "$DEST" status --porcelain --untracked-files=no 2>/dev/null)" ] && echo 1)"
  CONSOLE_OK="$("$DEST/.venv/bin/python" -c 'import flubnf' 2>/dev/null && echo 1)"
  ENGINE_OK="$(
    [ -f "$DEST/.flubnf.env" ] || exit 0
    # shellcheck disable=SC1091
    . "$DEST/.flubnf.env"
    [ -x "${FLUBNF_PY_ENGINE:-/nonexistent}" ] || exit 0
    [ "$INSTALLED_STAMP" = "$STAMP_NEW" ] || exit 0
    "$FLUBNF_PY_ENGINE" -c 'import bngsim; from pybnf.pf import ParticleFilter' 2>/dev/null && echo 1
  )"
  if [ "$REMOTE_SHA" = "$LOCAL_SHA" ] && [ -n "$CLEAN" ] && [ -n "$CONSOLE_OK" ] && [ -n "$ENGINE_OK" ]; then
    say "already current"
    ok "$DEST is at the latest FluBNF and already has this engine"
    ok "nothing to reinstall. If the console is still broken, paste this line instead:"
    echo "      ${LINE% | bash} | FLUBNF_REINSTALL_FORCE=1 bash"
    if [ -z "${FLUBNF_REINSTALL_NO_OPEN:-}" ] && [ "$(uname -s)" = Darwin ]; then
      open "$DEST/FluBNF.command"
    fi
    exit 0
  fi
fi

# A checkout about to be renamed: unpushed or uncommitted work stops the
# script (a developer's, updated by git pull); a clean one is named first.
CANDIDATES=("$DEST" "$ENGINE_VENV" "$PARENT/PyBNF-Private" "$PARENT/PyBNF-pf"
            "$HOME/Documents/PyBNF-Private" "$HOME/PyBNF-Private")
for d in "${CANDIDATES[@]}"; do
  [ -d "$d/.git" ] || continue
  # tracked changes only: a console clone always has untracked state
  dirty="$(git -C "$d" status --porcelain --untracked-files=no 2>/dev/null | head -1)"
  ahead="$(git -C "$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
  linked="$(git -C "$d" worktree list 2>/dev/null | sed 1d)"
  if [ -z "${FLUBNF_REINSTALL_FORCE:-}" ] && { [ -n "$dirty" ] || [ "${ahead:-0}" != 0 ] || [ -n "$linked" ]; }; then
    stop "$d is a git checkout with uncommitted or unpushed work, or linked worktrees." \
         "This line is for lab machines, where the engine comes from the archive; a checkout" \
         "updates with git pull. FLUBNF_REINSTALL_FORCE=1 sets it aside anyway."
  fi
  [ "$d" = "$DEST" ] || warn "$d is a git checkout and will be set aside like an unpacked copy"
done

echo
echo "About to install FluBNF fresh into $DEST. Anything already there (the"
echo "FluBNF folder, the engine, old engine files) is set aside: renamed, not deleted."
if [ -z "${FLUBNF_REINSTALL_YES:-}" ]; then
  # No terminal: nobody can answer, so stop rather than proceed.
  { : < /dev/tty; } 2>/dev/null \
    || stop "no terminal to ask on. Set FLUBNF_REINSTALL_YES=1 to run without the question."
  printf 'Press Return to continue, or Control-C to stop. '
  read -r _ < /dev/tty || stop "stopped."
fi

# From here on, something may have changed; on_exit puts it back if no new
# console gets made. INT and TERM become exits so the trap runs.
trap on_exit EXIT
trap 'exit 130' INT TERM

say "setting the old install aside"
for d in "${CANDIDATES[@]}"; do
  [ -e "$d" ] || continue
  if mv "$d" "$d-old-$STAMP"; then
    CHANGED=1
    SET_ASIDE+=("$d-old-$STAMP")
    ok "set aside: $d  (now $d-old-$STAMP)"
  else
    stop "could not rename $d. Close anything using it and paste the line again."
  fi
done
# Old launchers must not run: the old .venv's scripts hold absolute paths now
# owned by the new venv (measured 2026-09-23); Dock icons follow the rename.
for l in FluBNF.command SetupEngine.command; do
  [ -f "$DEST-old-$STAMP/$l" ] && chmod a-x "$DEST-old-$STAMP/$l"
done
[ ${#SET_ASIDE[@]} -eq 0 ] && ok "no old install found; nothing to set aside"
[ -d "$HOME/.venvs/flubnf" ] && ok "$HOME/.venvs/flubnf was left alone; the console uses the engine installed below"

say "old engine files"
if [ ${#OTHERS[@]} -gt 0 ]; then
  mkdir -p "$KEEP"
  for f in "${OTHERS[@]}"; do
    [ -f "$f" ] || continue
    dst="$KEEP/$(basename "$f")"
    # A name already swept on an earlier run must not leave this copy where
    # setup's newest-wins search still finds it: keep both, distinct names.
    [ -e "$dst" ] && dst="$KEEP/$STAMP-$(basename "$f")"
    if mv "$f" "$dst" && [ ! -e "$f" ]; then
      CHANGED=1
      ok "moved to $KEEP: $(basename "$dst")"
    else
      warn "could not move $f; delete it by hand before opening FluBNF, or setup may install it"
    fi
  done
  ok "those are your old engine files; delete $KEEP once the new console works"
else
  ok "no old engine files to move"
fi

if [ -n "${FLUBNF_REINSTALL_NO_INSTALL:-}" ]; then
  DONE=1
  echo; echo "FLUBNF_REINSTALL_NO_INSTALL is set: stopping before the install."; exit 0
fi

# Quieter child scripts: no pip upgrade notice, no SyntaxWarnings from the
# fork's regexes (they read as errors).
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::SyntaxWarning}"

say "installing FluBNF (about five minutes)"
mkdir -p "$PARENT"
git clone "$REPO" "$DEST" || stop "the clone failed (no internet?). Connect and paste the line again."
( cd "$DEST" && ./setup.sh ) || {
  warn "setup.sh did not finish (see above)."
  exit 1
}
DONE=1

say "installing the engine"
# The archive the checks chose is the one installed, whatever else the
# newest-by-mtime search in setup_engine.sh would find.
( cd "$DEST" && FLUBNF_PYBNF_BUNDLE="$ARCHIVE" ./setup_engine.sh ) || {
  warn "the engine did not install (see above). The console still runs without it;"
  warn "double-click $DEST/SetupEngine.command to try again, or send Ely this window."
}

say "done"
if [ ${#SET_ASIDE[@]} -gt 0 ]; then
  for d in "${SET_ASIDE[@]}"; do ok "old copy kept at $d"; done
  OLD_STATE="$DEST-old-$STAMP/app/state"
  [ -d "$OLD_STATE" ] && ok "your previous runs are in $OLD_STATE; the new console starts without them"
fi
INSTALLED_STAMP="$(
  [ -f "$DEST/.flubnf.env" ] || exit 0
  # shellcheck disable=SC1091
  . "$DEST/.flubnf.env"
  [ -f "${FLUBNF_PYBNF:-/nonexistent}/VERSION" ] && head -1 "$FLUBNF_PYBNF/VERSION"
)"
[ -n "$INSTALLED_STAMP" ] && ok "engine version stamp: $INSTALLED_STAMP"
echo
echo "Once the new console works, the -old-$STAMP folders and $KEEP"
echo "(your old engine .tar.gz files) can go in the Trash."
if [ ${#SET_ASIDE[@]} -gt 0 ]; then
  echo "If FluBNF sits in your Dock, remove that icon and drag $DEST/FluBNF.app"
  echo "there instead; the old icon points at the renamed copy and will not open."
fi
if [ -z "${FLUBNF_REINSTALL_NO_OPEN:-}" ]; then
  if [ "$(uname -s)" = Darwin ]; then
    echo "Opening FluBNF."
    open "$DEST/FluBNF.command"
  else
    echo "Start the console with:  $DEST/FluBNF.command"
  fi
fi
}

# Parse the whole file before running any: a truncated download fails cleanly.
main "$@"
