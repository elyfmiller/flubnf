#!/usr/bin/env bash
# flubnf one-command setup. Idempotent: re-running fixes what's missing.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

HERE="$(cd "$(dirname "$0")" && pwd)"
# How to run this again, as the user can type it. The one-line install
# (install.sh) runs this in its folder while the user's shell stays where it
# was, and says so (FLUBNF_SETUP_FROM=install): there the way back is the
# install line, which also goes on to the engine.
if [ "${FLUBNF_SETUP_FROM:-}" = install ]; then
  again="paste the install line again"; Again="Paste the install line again"
else
  again="run ./setup.sh again"; Again="Run ./setup.sh again"
fi
# Checkouts live in ~/GitHub: macOS keeps FluBNF.app out of Documents
# (FluBNF.command moves an older setup's). One already in ~/Documents/GitHub,
# and none in ~/GitHub, is used where it is.
checkout() {
  if [ ! -e "$HOME/GitHub/$1" ] && [ -e "$HOME/Documents/GitHub/$1" ]; then
    printf '%s' "$HOME/Documents/GitHub/$1"
  else
    printf '%s' "$HOME/GitHub/$1"
  fi
}
HUB="${FLUBNF_HUB:-$(checkout FluSight-forecast-hub)}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
PYBNF="${FLUBNF_PYBNF:-$(checkout PyBNF-pf)}"

say "python"
# PATH first, then where macOS Pythons live off PATH: a double-clicked .command
# may lack conda's PATH edits, and Apple's CLT python3 is 3.9.
PY=""
for c in python3.12 python3.11 python3; do
  cand=$(command -v "$c" 2>/dev/null) || continue
  "$cand" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null \
    && { PY="$cand"; break; }
done
if [ -z "$PY" ]; then
  for cand in /opt/anaconda3/bin/python3 "$HOME/anaconda3/bin/python3" \
              "$HOME/miniconda3/bin/python3" /opt/homebrew/bin/python3 \
              /usr/local/bin/python3 \
              /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
              /Library/Frameworks/Python.framework/Versions/3.11/bin/python3; do
    [ -x "$cand" ] || continue
    "$cand" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null \
      && { PY="$cand"; break; }
  done
fi
if [ -z "$PY" ]; then
  warn "python >= 3.11 required and none was found on PATH or in the usual"
  warn "install locations. The easy route is Anaconda (anaconda.com/download,"
  warn "defaults are fine: this setup finds it with nothing added to PATH)."
  exit 1
fi
ok "$($PY -V) at $PY"

say "analysis venv (.venv) + package"
VENV="$HERE/.venv"
# The venv's scripts folder: bin, or Scripts in a venv a Windows Python made
# (setup.ps1's, or this script's own under Git Bash).
venv_bin() {
  if [ ! -d "$VENV/bin" ] && [ -d "$VENV/Scripts" ]; then
    printf '%s' Scripts
  else
    printf '%s' bin
  fi
}
# One of the venv's programs by its file: a Windows venv holds python.exe,
# pip.exe and flubnf.exe only, so the .exe is named when it is there (Git
# Bash would find it without the suffix; this does not rely on that).
vexe() {
  if [ -f "$VENV/$VB/$1.exe" ]; then
    printf '%s' "$VENV/$VB/$1.exe"
  else
    printf '%s' "$VENV/$VB/$1"
  fi
}
runs_pip() { "$(vexe python)" -m pip --version >/dev/null 2>&1; }
runs_console() {
  [ -x "$(vexe flubnf)" ] && "$(vexe flubnf)" --help >/dev/null 2>&1
}
VB="$(venv_bin)"
NOPIP=""
ASIDE=""
if [ -d "$VENV" ] && ! runs_pip; then
  if runs_console; then
    # No pip (uv makes such venvs, as does venv --without-pip), but the
    # console runs from it: kept. A new venv needs the network for FluBNF's
    # packages, so setting this one aside offline left no console at all.
    NOPIP=1
  else
    # Neither runs (made where the venv module came without pip, or left by a
    # Python since removed): set aside, never deleted, and made again.
    BROKEN="$HERE/.venv.broken-$(date +%Y%m%d-%H%M%S)"
    [ ! -e "$BROKEN" ] || BROKEN="$BROKEN-$$"
    if mv "$VENV" "$BROKEN"; then
      ASIDE="$BROKEN"
      warn "the venv in .venv runs neither pip nor the console: it is kept as $(basename "$BROKEN") and made again"
    else
      warn "the venv in .venv runs neither pip nor the console, and it could not be moved aside."
      warn "Move or delete \"$VENV\" and then $again."
      exit 1
    fi
  fi
fi
if [ ! -d "$VENV" ]; then
  # What venv says goes to stderr as ever, and is kept: it tells a missing
  # venv module or ensurepip from a full disk or a folder that cannot be
  # written to.
  { VENV_ERR="$("$PY" -m venv "$VENV" 2>&1 1>&3)"; VENV_RC=$?; } 3>&1
  [ -z "$VENV_ERR" ] || printf '%s\n' "$VENV_ERR" >&2
  if [ "$VENV_RC" -ne 0 ]; then
    warn "$PY could not make the venv (see above)."
    if [ -n "$ASIDE" ]; then
      # A failed try leaves things as they were: the half-made venv this run
      # made goes, and the one set aside comes back (one more
      # .venv.broken-<stamp> per failed try otherwise).
      if rm -rf "$VENV" && mv "$ASIDE" "$VENV"; then
        warn "The old venv is back in .venv."
      fi
    fi
    if printf '%s' "$VENV_ERR" | tr -s '[:space:]' ' ' | grep -q \
         -e 'ensurepip is not available' -e 'No module named venv' \
         -e 'No module named ensurepip'; then
      if command -v apt-get >/dev/null 2>&1; then
        PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
        warn "On Debian and Ubuntu the venv module is its own package:"
        warn "  sudo apt install python${PYV:-3}-venv"
        warn "then $again."
      else
        warn "Install a Python that has its venv module (Anaconda does:"
        warn "anaconda.com/download), then $again."
      fi
    else
      warn "$Again once the problem above is fixed."
    fi
    exit 1
  fi
  VB="$(venv_bin)"
fi
VPY="$(vexe python)"
# pip's own script when the venv has it, else pip as a module (a venv given
# pip by hand with ensurepip has pip3 but no pip).
if [ -x "$(vexe pip)" ]; then PIP=("$(vexe pip)"); else PIP=("$VPY" -m pip); fi
if [ -n "$NOPIP" ]; then
  warn "the venv in .venv has no pip (a venv made by uv, say), so FluBNF's"
  warn "packages and BioNetGen were not updated. The console runs with what is"
  warn "installed. For setup to update them: \"$VPY\" -m ensurepip, then $again."
elif "${PIP[@]}" install -q -e "$HERE[app,dev]"; then
  ok "flubnf installed editable"
elif [ -x "$(vexe flubnf)" ]; then
  # an earlier install is there: an offline re-run keeps it
  warn "FluBNF's packages did not update (see above; offline?). The console"
  warn "runs with what is installed."
else
  warn "FluBNF did not install into .venv (see above; offline?). The console"
  warn "needs it: $again once the problem above is fixed."
  exit 1
fi
# BioNetGen is not needed to open the console, so a failure here is a warning.
if [ -z "$NOPIP" ]; then
  if "${PIP[@]}" install -q bionetgen; then
    ok "bionetgen (BNG2.pl) installed"
  else
    warn "BioNetGen (BNG2.pl) did not install (see above). The console still"
    warn "runs; fits need it. $Again to retry."
  fi
fi

if [ "$(uname -s)" = Darwin ]; then
  say "FluBNF.app (FluBNF in the Dock)"
  # The host that runs the console window as FluBNF.app, not as "Python",
  # built for this venv (scripts/macos/flubnf_host.c). Without it FluBNF.app
  # still opens the console, through Terminal.
  if /bin/bash "$HERE/scripts/macos/build_app_host.sh" --force; then
    ok "to keep FluBNF in the Dock: open FluBNF.app, right-click its Dock icon, Options > Keep in Dock"
  else
    warn "FluBNF.app will open the console through Terminal (reason above)"
  fi
fi

say "FluSight hub data"
# The directories the app reads; both the repair and the fresh clone use this list.
HUB_DIRS="auxiliary-data target-data model-output/FluSight-baseline model-output/FluSight-ensemble"
# What must be there after it, inside them too: doctor fails a clone without
# the vintages' archive (flubnf/doctor.py HUB_DATA_DIRS), so a cone that holds
# auxiliary-data but not its archive is widened as well.
HUB_NEEDS="$HUB_DIRS auxiliary-data/target-data-archive"
missing_hub_dirs() {
  _m=""
  for _d in $HUB_NEEDS; do [ -d "$HUB/$_d" ] || _m="$_m $_d"; done
  printf '%s' "$_m"
}
# A clone is a folder git takes as its own top level. Its .git can be a
# file (a worktree or a submodule); an empty or broken .git folder is no
# clone, and git then answers for any repository around the folder.
# Without git to ask, a .git there counts, as before.
hub_is_clone() {
  [ -e "$HUB/.git" ] || return 1
  command -v git >/dev/null 2>&1 || return 0
  _top="$(git -C "$HUB" rev-parse --show-toplevel 2>/dev/null)" || return 1
  [ -n "$_top" ] && [ "$_top" -ef "$HUB" ]
}
if hub_is_clone; then
  ok "hub present: $HUB"
  # A by-hand `clone --sparse` holds only the root. Widen with `add`: it is
  # idempotent and fails harmlessly on a full clone, where `set` would prune
  # every unnamed directory (git 2.39.5).
  need="$(missing_hub_dirs)"
  if [ -n "$need" ]; then
    warn "this clone does not contain:$need"
    # shellcheck disable=SC2086
    if (cd "$HUB" && git sparse-checkout add $HUB_DIRS); then
      still="$(missing_hub_dirs)"
      if [ -n "$still" ]; then
        warn "still absent:$still -- the console will open with no vintages"
      else
        ok "sparse checkout widened to the directories the app reads"
      fi
    else
      warn "could not widen the sparse checkout (offline, or a full clone"
      warn "whose upstream no longer has one of those directories)"
    fi
  fi
elif [ "${FLUBNF_NO_DATA:-0}" = "1" ]; then
  warn "data skipped (FLUBNF_NO_DATA=1) -- set FLUBNF_HUB later"
elif [ -e "$HUB" ] \
     && { [ ! -d "$HUB" ] || [ -n "$(ls -A "$HUB" 2>/dev/null)" ]; }; then
  # Something there that is not a clone: git clone would fail on it, and
  # git -C would reach any repository around it.
  warn "\"$HUB\" is there but is not a git clone, so no data was fetched"
  warn "into it. Move or rename it (or set FLUBNF_HUB to an existing clone),"
  warn "then $again."
else
  # Sparse: only the directories the app reads (~10x smaller than the full hub).
  echo "  fetching FluSight data (sparse, ~150 MB)…"
  git clone --filter=blob:none --sparse --depth 1 \
      https://github.com/cdcepi/FluSight-forecast-hub "$HUB" 2>/dev/null \
    && (cd "$HUB" && git sparse-checkout set $HUB_DIRS) \
    && ok "hub data ready (sparse): $HUB" \
    || warn "data fetch failed (offline?) -- $again when connected"
fi

say "engine venv (pybnf + bngsim)"
# The engine record (setup_engine.sh --public or --private; docs/ENGINE.md)
# is kept through the rewrite of .flubnf.env below, and says which engine to
# report on: FLUBNF_ENGINE from this shell first, else the record. Quotes,
# surrounding spaces and case do not count; anything but private is the
# public engine, the default.
KEPT="$(grep -E '(^|[[:space:]])(FLUBNF_ENGINE|FLUBNF_PY_ENGINE_PUBLIC)=' "$HERE/.flubnf.env" 2>/dev/null)"
RAW="${FLUBNF_ENGINE:-$( [ -f "$HERE/.flubnf.env" ] && . "$HERE/.flubnf.env" >/dev/null 2>&1; printf '%s' "${FLUBNF_ENGINE:-}" )}"
ROUTE="$(printf '%s' "$RAW" | tr -d '"' | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
case "$ROUTE" in
  private|public|"") ;;
  *) warn "FLUBNF_ENGINE is \"$RAW\", which is neither private nor public: the public engine, the default, is checked" ;;
esac
PUBPY="${FLUBNF_PY_ENGINE_PUBLIC:-$( [ -f "$HERE/.flubnf.env" ] && . "$HERE/.flubnf.env" >/dev/null 2>&1; printf '%s' "${FLUBNF_PY_ENGINE_PUBLIC:-}" )}"
PUBPY="${PUBPY:-$HOME/.venvs/flubnf-public/bin/python}"
if [ "$ROUTE" != private ]; then
  if [ -x "$PUBPY" ] && "$PUBPY" "$HERE/scripts/engine_lock.py" check >/dev/null 2>&1; then
    ok "public engine venv ready (the default): ${PUBPY%/bin/python}"
  else
    warn "the public engine (the default) is not installed yet; FluBNF.command installs it on its next open (./setup_engine.sh does it now)"
  fi
elif [ -x "$ENGINE_VENV/bin/python" ] \
   && "$ENGINE_VENV/bin/python" -c "import pybnf, bngsim" 2>/dev/null; then
  ok "this copy is set to the private engine (the fallback); its venv is ready: $ENGINE_VENV"
else
  warn "this copy is set to the private engine (the fallback)"
  warn "engine venv not ready. The private engine (fit_type=pf) needs the lab's"
  warn "PyBNF fork, which is private, so it is the one part of this install that"
  warn "can ask who you are. ./setup_engine.sh --private does the whole thing --"
  warn "the clone, the venv, the pinned dependencies -- and it tries an offline"
  warn "bundle BEFORE it tries GitHub. So the shortest route needs no account:"
  warn "  someone who has the fork runs, once:"
  warn "    git bundle create pybnf.bundle feature/particle-filter"
  warn "  you put that one file in ~/Downloads (or beside this folder), then:"
  warn "    ./setup_engine.sh --private"
  # Not run from here (minutes more, a large download): FluBNF.command runs
  # setup_engine.sh right after this.
  warn "With GitHub access instead, ./setup_engine.sh --private clones it for"
  warn "you and explains, in detail, whatever stops it."
  warn "Without the engine: the console, analogue engine, and reports still work."
  warn "./setup_engine.sh --public goes back to the public engine, the default."
fi

say "git hooks"
# Tracked hooks: a push to main first runs the suite under CI conditions.
if [ -d "$HERE/.git" ] && [ -d "$HERE/.githooks" ]; then
  git -C "$HERE" config core.hooksPath .githooks \
    && ok "pre-push runs the suite under CI conditions (bypass: --no-verify)" \
    || warn "could not set core.hooksPath; pushes will not be pre-checked"
fi

say "environment"
ENVF="$HERE/.flubnf.env"
{ echo "export FLUBNF_HUB=\"$HUB\""
  echo "export FLUBNF_PY_ENGINE=\"$ENGINE_VENV/bin/python\""
  echo "export FLUBNF_PYBNF=\"$PYBNF\""
  [ -z "$KEPT" ] || printf '%s\n' "$KEPT"; } > "$ENVF"
ok "wrote $ENVF  (source it, or add to your shell profile)"

say "doctor"
# shellcheck disable=SC1090
. "$ENVF"
if [ ! -x "$(vexe flubnf)" ]; then
  warn "the console is not installed: .venv/$VB/flubnf is missing. $Again."
  exit 1
fi
"$VPY" -c "from flubnf.settings import check; import sys; sys.exit(1 if check() else 0)" \
  && ok "all externals present -- you are ready: .venv/$VB/flubnf app" \
  || warn "some externals missing (listed above) -- console still runs: .venv/$VB/flubnf app"
