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
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
$PY -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null \
  || { warn "python >= 3.11 required (found $($PY -V 2>&1))"; exit 1; }
ok "$($PY -V) at $PY"

say "analysis venv (.venv) + package"
[ -d "$HERE/.venv" ] || $PY -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q -e "$HERE[app,dev]" && ok "flubnf installed editable"
"$HERE/.venv/bin/pip" install -q bionetgen && ok "bionetgen (BNG2.pl) installed"

say "FluSight hub data"
# The directories the app reads. Named once: the repair of an existing clone
# and the fresh clone after it both work from this list.
HUB_DIRS="auxiliary-data target-data model-output/FluSight-baseline model-output/FluSight-ensemble"
missing_hub_dirs() {
  _m=""
  for _d in $HUB_DIRS; do [ -d "$HUB/$_d" ] || _m="$_m $_d"; done
  printf '%s' "$_m"
}
if [ -d "$HUB/.git" ]; then
  ok "hub present: $HUB"
  # `git clone --sparse` checks out the repository ROOT and nothing else, so
  # a hub cloned by hand is a valid checkout holding no data at all, and
  # "hub present" was the last word this script said about it. Widen the
  # cone with `add`: it is idempotent, and on a full non-sparse clone it
  # fails harmlessly ("no sparse-checkout to add to") instead of pruning
  # every directory not named, which `set` does. Both measured on git 2.39.5.
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
  # No questions: sparse checkout pulls ONLY the data directories the app
  # reads (~10x smaller than the full hub, which is mostly other teams'
  # forecast files).
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
  # Deliberately NOT run from here. This script is the console's first-run
  # setup and finishes in a couple of minutes; the engine adds several more
  # and a large download, and FluBNF.command runs setup_engine.sh straight
  # after this anyway. Printing the route beats a surprise.
  warn "With GitHub access instead, ./setup_engine.sh clones it for you and"
  warn "explains, in detail, whatever stops it."
  warn "Without the engine: the console, analogue engine, and reports still work."
fi

say "git hooks"
# Point git at the tracked hooks directory so a contributor's push runs the
# suite the way CI runs it (no hub clone, no engine venv) before it can turn
# main red. Idempotent, and only inside a real checkout.
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
