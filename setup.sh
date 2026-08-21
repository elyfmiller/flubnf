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
if [ -d "$HUB/.git" ]; then
  ok "hub present: $HUB"
elif [ "${FLUBNF_NO_DATA:-0}" = "1" ]; then
  warn "data skipped (FLUBNF_NO_DATA=1) -- set FLUBNF_HUB later"
else
  # No questions: sparse checkout pulls ONLY the data directories the app
  # reads (~10x smaller than the full hub, which is mostly other teams'
  # forecast files).
  echo "  fetching FluSight data (sparse, ~150 MB)…"
  git clone --filter=blob:none --sparse --depth 1 \
      https://github.com/cdcepi/FluSight-forecast-hub "$HUB" 2>/dev/null \
    && (cd "$HUB" && git sparse-checkout set auxiliary-data target-data model-output/FluSight-baseline model-output/FluSight-ensemble) \
    && ok "hub data ready (sparse): $HUB" \
    || warn "data fetch failed (offline?) -- rerun setup.sh when connected"
fi

say "engine venv (pybnf + bngsim)"
if [ -x "$ENGINE_VENV/bin/python" ] \
   && "$ENGINE_VENV/bin/python" -c "import pybnf, bngsim" 2>/dev/null; then
  ok "engine venv ready: $ENGINE_VENV"
else
  warn "engine venv not ready. The PF engine (fit_type=pf) needs a PyBNF fork"
  warn "that is not yet public. If you have access:"
  warn "  git clone -b feature/particle-filter <your PyBNF fork> $PYBNF"
  warn "  $PY -m venv $ENGINE_VENV"
  warn "  $ENGINE_VENV/bin/pip install numpy scipy pandas bngsim"
  warn "  export FLUBNF_PY_ENGINE=$ENGINE_VENV/bin/python FLUBNF_PYBNF=$PYBNF"
  warn "Without it: the console, analogue engine, and reports still work."
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
