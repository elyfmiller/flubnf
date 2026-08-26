#!/usr/bin/env bash
# Tier-B engine setup: PyBNF fork (fit_type=pf) + bngsim. Lab-member edition.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

# HTTPS by default so a credential helper can answer; set FLUBNF_PYBNF_REMOTE
# to the git@ form if you have an SSH key and prefer it.
PYBNF_REMOTE="${FLUBNF_PYBNF_REMOTE:-https://github.com/elyfmiller/PyBNF-Private.git}"
PYBNF="${FLUBNF_PYBNF:-$HOME/Documents/GitHub/PyBNF-pf}"
BNGSIM_REMOTE="${FLUBNF_BNGSIM_REMOTE:-https://github.com/elyfmiller/bngsim}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)

say "PyBNF fork (feature/particle-filter)"
if [ -d "$PYBNF/.git" ]; then
  # An existing checkout needs NO remote auth -- use what is on disk.
  ok "checkout present: $PYBNF"
  BR=$(git -C "$PYBNF" branch --show-current)
  if [ "$BR" != "feature/particle-filter" ]; then
    if git -C "$PYBNF" rev-parse --verify feature/particle-filter >/dev/null 2>&1        || git -C "$PYBNF" rev-parse --verify origin/feature/particle-filter >/dev/null 2>&1; then
      git -C "$PYBNF" checkout -q feature/particle-filter         && ok "switched to feature/particle-filter (was $BR)"         || { warn "could not switch branch (uncommitted changes?) -- on '$BR'"; exit 1; }
    else
      warn "branch feature/particle-filter not found in $PYBNF"
      warn "re-clone with: git clone -b feature/particle-filter $PYBNF_REMOTE $PYBNF"
      exit 1
    fi
  else
    ok "on feature/particle-filter"
  fi
else
  say "fork access (needed to clone)"
  if git ls-remote "$PYBNF_REMOTE" HEAD >/dev/null 2>&1; then
    git clone -b feature/particle-filter "$PYBNF_REMOTE" "$PYBNF" && ok "cloned"
  else
    warn "cannot authenticate to $PYBNF_REMOTE and no local checkout exists"
    warn "1) ask Ely for a collaborator invite to PyBNF-Private"
    warn "2) authenticate: GitHub Desktop or `gh auth login` installs a"
    warn "   credential helper that answers this HTTPS clone. For SSH instead,"
    warn "   set FLUBNF_PYBNF_REMOTE=git@github.com:elyfmiller/PyBNF-Private.git"
    warn "3) re-run this script  (or clone by any means and re-run)"
    exit 1
  fi
fi

say "engine venv"
[ -d "$ENGINE_VENV" ] || $PY -m venv "$ENGINE_VENV"
# numpy<2: the fork predates NumPy 2 and the historical fixes were venv-local
# patches, not commits. Pinning is the reproducible answer.
# The runtime set, installed explicitly so the fork can go in with
# --no-deps below. PyBNF pins msgpack==0.6.2 (2019), which has no wheel
# for a modern Python on any platform and must otherwise be compiled.
# This list is what the PF path actually imports, traced 2026-08-25;
# PyBNF also declares nose and paramiko, which it never imports.
"$ENGINE_VENV/bin/pip" install -q "numpy<2" scipy pandas "dask==2022.12.1" \
  "distributed==2022.12.1" msgpack pyparsing tornado libroadrunner \
  python-libsbml && ok "runtime dependencies installed"

say "bngsim"
if "$ENGINE_VENV/bin/python" -c "import bngsim" 2>/dev/null; then
  ok "bngsim already importable"
else
  # wheels from the lab fork's releases first; source build as fallback
  # PINNED. Every published FluBNF number was produced by a bngsim built
  # from a local checkout whose pyproject reported "0.13.0" while sitting 50
  # commits past that tag, on a branch present in no upstream. So
  # `bngsim==0.13.0` would NOT reproduce the seal. 0.15.1 was measured on
  # 2026-08-25 to be BIT-IDENTICAL to that build across three cells, at the
  # ODE, the filter and the WIS: max abs and max rel difference exactly 0.
  # It is a real published version anyone can install, so it is the pin.
  if ! "$ENGINE_VENV/bin/pip" install -q "bngsim==0.15.1" 2>/dev/null; then
    warn "no PyPI/wheel match -- building from source (needs a C++ toolchain;"
    warn "on macOS: xcode-select --install). This takes ~10 minutes."
    "$ENGINE_VENV/bin/pip" install "git+$BNGSIM_REMOTE" || { warn "bngsim build failed"; exit 1; }
  fi
  ok "bngsim installed: $("$ENGINE_VENV/bin/python" -c 'import bngsim; print(bngsim.__version__)')"
fi

say "PyBNF install"
# --no-deps: the runtime set is installed above, and resolving the fork's
# own install_requires would drag in the unbuildable msgpack pin.
"$ENGINE_VENV/bin/pip" install -q -e "$PYBNF" --no-deps \
  && ok "pybnf (fork) installed editable"

say "verify"
"$ENGINE_VENV/bin/python" - <<'PYEOF'
import bngsim, pybnf
from pybnf.pf import ParticleFilter  # the point of the whole exercise
print(f"  + pybnf with fit_type=pf, bngsim {bngsim.__version__} -- engine ready")
PYEOF
ENVF="$(cd "$(dirname "$0")" && pwd)/.flubnf.env"
grep -q FLUBNF_PY_ENGINE "$ENVF" 2>/dev/null || {
  echo "export FLUBNF_PY_ENGINE=\"$ENGINE_VENV/bin/python\"" >> "$ENVF"
  echo "export FLUBNF_PYBNF=\"$PYBNF\"" >> "$ENVF"; }
ok "environment recorded in $ENVF"
