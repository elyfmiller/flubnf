#!/usr/bin/env bash
# Tier-B engine setup: PyBNF fork (fit_type=pf) + bngsim. Lab-member edition.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

PYBNF_REMOTE="${FLUBNF_PYBNF_REMOTE:-git@github.com:elyfmiller/PyBNF-Private.git}"
PYBNF="${FLUBNF_PYBNF:-$HOME/Documents/GitHub/PyBNF-pf}"
BNGSIM_REMOTE="${FLUBNF_BNGSIM_REMOTE:-https://github.com/elyfmiller/bngsim}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)

say "fork access"
if git ls-remote "$PYBNF_REMOTE" HEAD >/dev/null 2>&1; then
  ok "can reach $PYBNF_REMOTE"
else
  warn "cannot authenticate to $PYBNF_REMOTE"
  warn "1) ask Ely for a collaborator invite to PyBNF-Private"
  warn "2) add an SSH key: ssh-keygen -t ed25519; then paste ~/.ssh/id_ed25519.pub"
  warn "   at github.com -> Settings -> SSH and GPG keys -> New SSH key"
  warn "3) re-run this script"
  exit 1
fi

say "PyBNF fork (feature/particle-filter)"
if [ -d "$PYBNF/.git" ]; then
  ok "checkout present: $PYBNF"
else
  git clone -b feature/particle-filter "$PYBNF_REMOTE" "$PYBNF" && ok "cloned"
fi

say "engine venv"
[ -d "$ENGINE_VENV" ] || $PY -m venv "$ENGINE_VENV"
# numpy<2: the fork predates NumPy 2 and the historical fixes were venv-local
# patches, not commits. Pinning is the reproducible answer.
"$ENGINE_VENV/bin/pip" install -q "numpy<2" scipy pandas && ok "numpy<2 + scipy + pandas"

say "bngsim"
if "$ENGINE_VENV/bin/python" -c "import bngsim" 2>/dev/null; then
  ok "bngsim already importable"
else
  # wheels from the lab fork's releases first; source build as fallback
  if ! "$ENGINE_VENV/bin/pip" install -q bngsim 2>/dev/null; then
    warn "no PyPI/wheel match -- building from source (needs a C++ toolchain;"
    warn "on macOS: xcode-select --install). This takes ~10 minutes."
    "$ENGINE_VENV/bin/pip" install "git+$BNGSIM_REMOTE" || { warn "bngsim build failed"; exit 1; }
  fi
  ok "bngsim installed: $("$ENGINE_VENV/bin/python" -c 'import bngsim; print(bngsim.__version__)')"
fi

say "PyBNF install"
"$ENGINE_VENV/bin/pip" install -q -e "$PYBNF" && ok "pybnf (fork) installed editable"

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
