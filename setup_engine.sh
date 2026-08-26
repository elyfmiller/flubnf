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
    warn "NOTE: git's password prompt does NOT accept your GitHub account"
    warn "password (GitHub retired password auth in 2021), so being a"
    warn "collaborator is not enough by itself. Pick one:"
    warn "a) EASIEST: open GitHub Desktop, sign in, and clone"
    warn "   elyfmiller/PyBNF-Private from inside Desktop. Its default clone"
    warn "   location (~/Documents/GitHub/PyBNF-Private) is exactly where this"
    warn "   setup looks, and an on-disk checkout needs no terminal login at"
    warn "   all. Then reopen FluBNF.command. (Signing in to Desktop WITHOUT"
    warn "   cloning does not help: Desktop does not share its login with"
    warn "   terminal git.)"
    warn "b) run 'gh auth login' (GitHub CLI) once, then re-run this script."
    warn "c) paste a Personal Access Token at the password prompt in place of"
    warn "   your password (github.com > Settings > Developer settings)."
    warn "For SSH keys: set FLUBNF_PYBNF_REMOTE=git@github.com:elyfmiller/PyBNF-Private.git"
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
  python-libsbml && ok "runtime dependencies installed" \
  || { warn "dependency install failed (see pip's output above)"; exit 1; }

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
# own install_requires would drag in the unbuildable msgpack pin. A failed
# editable install is a warning, not an error: every generated runner (and
# the app's version probe) loads pybnf from the checkout via sys.path, so
# the verify below is the real gate. (The editable install is known to
# fail on Windows and to work on macOS.)
"$ENGINE_VENV/bin/pip" install -q -e "$PYBNF" --no-deps \
  && ok "pybnf (fork) installed editable" \
  || warn "editable install failed -- harmless if the verify below passes"

say "verify"
# Mirrors exactly what every generated runner does: the checkout first on
# sys.path, then import. A verify failure aborts BEFORE the environment is
# recorded, so a broken setup can never present itself as a finished one.
if ! "$ENGINE_VENV/bin/python" - "$PYBNF" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import bngsim, pybnf
from pybnf.pf import ParticleFilter  # the point of the whole exercise
print(f"  + pybnf with fit_type=pf, bngsim {bngsim.__version__} -- engine ready")
PYEOF
then
  warn "verification failed -- the engine is NOT ready (see the error above)"
  exit 1
fi
ENVF="$(cd "$(dirname "$0")" && pwd)/.flubnf.env"
# rewrite, don't skip: a stale entry from an earlier layout must not
# outlive the setup that just verified the real one
TMPF="$ENVF.tmp.$$"
grep -v -e FLUBNF_PY_ENGINE -e FLUBNF_PYBNF "$ENVF" 2>/dev/null > "$TMPF" || true
{
  echo "export FLUBNF_PY_ENGINE=\"$ENGINE_VENV/bin/python\""
  echo "export FLUBNF_PYBNF=\"$PYBNF\""
} >> "$TMPF"
mv "$TMPF" "$ENVF"
ok "environment recorded in $ENVF"
