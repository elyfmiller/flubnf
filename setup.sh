#!/usr/bin/env bash
# flubnf one-command setup. Idempotent: re-running fixes what's missing.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

HERE="$(cd "$(dirname "$0")" && pwd)"
HUB="${FLUBNF_HUB:-$HOME/Documents/GitHub/FluSight-forecast-hub}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
PYBNF="${FLUBNF_PYBNF:-$HOME/Documents/GitHub/PyBNF-pf}"

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
[ -d "$HERE/.venv" ] || $PY -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q -e "$HERE[app,dev]" && ok "flubnf installed editable"
"$HERE/.venv/bin/pip" install -q bionetgen && ok "bionetgen (BNG2.pl) installed"

say "FluSight hub data"
# The directories the app reads; both the repair and the fresh clone use this list.
HUB_DIRS="auxiliary-data target-data model-output/FluSight-baseline model-output/FluSight-ensemble"
missing_hub_dirs() {
  _m=""
  for _d in $HUB_DIRS; do [ -d "$HUB/$_d" ] || _m="$_m $_d"; done
  printf '%s' "$_m"
}
if [ -d "$HUB/.git" ]; then
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
else
  # Sparse: only the directories the app reads (~10x smaller than the full hub).
  echo "  fetching FluSight data (sparse, ~150 MB)…"
  git clone --filter=blob:none --sparse --depth 1 \
      https://github.com/cdcepi/FluSight-forecast-hub "$HUB" 2>/dev/null \
    && (cd "$HUB" && git sparse-checkout set $HUB_DIRS) \
    && ok "hub data ready (sparse): $HUB" \
    || warn "data fetch failed (offline?) -- rerun setup.sh when connected"
fi

say "engine venv (pybnf + bngsim)"
if [ -x "$ENGINE_VENV/bin/python" ] \
   && "$ENGINE_VENV/bin/python" -c "import pybnf, bngsim" 2>/dev/null; then
  ok "engine venv ready: $ENGINE_VENV"
else
  warn "engine venv not ready. The PF engine (fit_type=pf) needs a PyBNF fork"
  warn "that is not yet public, so it is the one part of this install that can"
  warn "ask who you are. ./setup_engine.sh does the whole thing -- the clone,"
  warn "the venv, the pinned dependencies -- and it tries an offline bundle"
  warn "BEFORE it tries GitHub. So the shortest route needs no account:"
  warn "  someone who has the fork runs, once:"
  warn "    git bundle create pybnf.bundle feature/particle-filter"
  warn "  you put that one file in ~/Downloads (or beside this folder), then:"
  warn "    ./setup_engine.sh"
  # Not run from here (minutes more, a large download): FluBNF.command runs
  # setup_engine.sh right after this.
  warn "With GitHub access instead, ./setup_engine.sh clones it for you and"
  warn "explains, in detail, whatever stops it."
  warn "Without the engine: the console, analogue engine, and reports still work."
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
  echo "export FLUBNF_PYBNF=\"$PYBNF\""; } > "$ENVF"
ok "wrote $ENVF  (source it, or add to your shell profile)"

say "doctor"
# shellcheck disable=SC1090
. "$ENVF"
"$HERE/.venv/bin/python" -c "from flubnf.settings import check; import sys; sys.exit(1 if check() else 0)" \
  && ok "all externals present -- you are ready: .venv/bin/flubnf app" \
  || warn "some externals missing (listed above) -- console still runs: .venv/bin/flubnf app"
