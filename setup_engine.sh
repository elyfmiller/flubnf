#!/usr/bin/env bash
# Tier-B engine setup: PyBNF fork (fit_type=pf) + bngsim. Lab-member edition.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

# HTTPS by default so a credential helper can answer; set FLUBNF_PYBNF_REMOTE
# to the git@ form if you have an SSH key and prefer it.
PYBNF_REMOTE="${FLUBNF_PYBNF_REMOTE:-https://github.com/elyfmiller/PyBNF-Private.git}"
# Fork location, same order as flubnf/settings.py (_first_checkout) and
# setup.ps1: an existing PyBNF-pf (the dev host's name only), then an existing
# PyBNF-Private (the repo's real name and the archive's prefix), else create
# PyBNF-Private. Test the directory, not .git: an unpacked archive has none.
if [ -n "${FLUBNF_PYBNF:-}" ]; then
  PYBNF="$FLUBNF_PYBNF"
elif [ -d "$HOME/Documents/GitHub/PyBNF-pf" ]; then
  PYBNF="$HOME/Documents/GitHub/PyBNF-pf"
elif [ -d "$HOME/Documents/GitHub/PyBNF-Private" ]; then
  PYBNF="$HOME/Documents/GitHub/PyBNF-Private"
else
  PYBNF="$HOME/Documents/GitHub/PyBNF-Private"
fi
BNGSIM_REMOTE="${FLUBNF_BNGSIM_REMOTE:-https://github.com/elyfmiller/bngsim}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Offline engine files. The fork is private, so cloning it is the one install
# step that needs a GitHub account; a file needs none. Either a git bundle
# (`git bundle create pybnf.bundle feature/particle-filter`, ~140 MB) or the
# pybnf-pf-<sha>.tar.gz from scripts/cut_engine_archive.sh. Searched BEFORE
# any GitHub auth, in the folders a student saves downloads to.
engine_bundle_dirs() {
  printf '%s\n' "$HERE" "$(dirname "$HERE")" \
                "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents"
}

find_engine_bundle() {
  # Prints the chosen path or nothing. `--print-bundle` hands stdout to the
  # launchers, so every diagnostic goes to stderr.
  if [ -n "${FLUBNF_PYBNF_BUNDLE:-}" ]; then
    if [ -f "$FLUBNF_PYBNF_BUNDLE" ]; then
      printf '%s\n' "$FLUBNF_PYBNF_BUNDLE"
      return 0
    fi
    warn "FLUBNF_PYBNF_BUNDLE names a file that is not there:" >&2
    warn "  $FLUBNF_PYBNF_BUNDLE" >&2
    warn "looking in the usual places instead" >&2
  fi
  # Split on newlines only: a home directory may contain spaces.
  _oifs=$IFS
  IFS='
'
  # shellcheck disable=SC2046
  set -- $(engine_bundle_dirs)
  IFS=$_oifs
  # Both shapes (bundle or tarball; told apart by suffix later). The NEWEST by
  # mtime wins: the sha in the name is hex, so glob order is arbitrary and
  # once installed a weeks-old archive left in Downloads (2026-09-09).
  _best=""
  _seen=0
  for d in "$@"; do
    [ -d "$d" ] || continue
    for f in "$d"/pybnf*.bundle "$d"/PyBNF*.bundle \
             "$d"/pybnf*.tar.gz "$d"/PyBNF*.tar.gz; do
      # -f: on macOS a *.bundle can be a directory (plug-ins, frameworks).
      [ -f "$f" ] || continue
      _seen=$((_seen + 1))
      if [ -z "$_best" ] || [ "$f" -nt "$_best" ]; then
        _best="$f"
      fi
    done
  done
  [ -n "$_best" ] || return 0
  if [ "$_seen" -gt 1 ]; then
    warn "$_seen engine archives found in the usual places; using the newest:" >&2
    warn "  $_best" >&2
    warn "Delete the older ones so there is no doubt what you installed." >&2
  fi
  printf '%s\n' "$_best"
  return 0
}

archive_version_stamp() {
  # The VERSION line inside an engine archive, without unpacking it. Find the
  # member, then extract it by literal name: GNU tar does not glob member
  # names without --wildcards, and bsdtar rejects that flag.
  _av_member="$(tar -tzf "$1" 2>/dev/null | grep -m1 -E '(^|/)VERSION$')" || return 0
  [ -n "$_av_member" ] || return 0
  tar -xzOf "$1" "$_av_member" 2>/dev/null | head -1
}

install_engine_archive() {
  # Unpack a pybnf-pf tarball into $PYBNF from wherever the student saved it;
  # nobody places it by hand.
  _arc="$1"
  _tmp="$(mktemp -d)" || return 1
  if ! tar -xzf "$_arc" -C "$_tmp" 2>/dev/null; then
    warn "could not unpack $_arc (a copy that did not finish?)"
    rm -rf "$_tmp"; return 1
  fi
  # Find the top-level folder by content, not name (the prefix may change).
  _src=""
  for c in "$_tmp"/*/; do
    [ -f "${c}pybnf/pf.py" ] && [ -f "${c}setup.py" ] && { _src="${c%/}"; break; }
  done
  if [ -z "$_src" ]; then
    warn "$_arc unpacked, but no pybnf/pf.py inside: not the engine archive"
    rm -rf "$_tmp"; return 1
  fi
  mkdir -p "$(dirname "$PYBNF")"
  # mv into an existing dir NESTS the source. Remove only an EMPTY leftover
  # (rmdir); refuse anything else rather than delete what we did not create.
  if [ -e "$PYBNF" ] && ! rmdir "$PYBNF" 2>/dev/null; then
    warn "$PYBNF already exists and is not an engine (no pybnf/pf.py),"
    warn "so nothing was touched. Move that folder aside and run this again."
    rm -rf "$_tmp"; return 1
  fi
  if mv "$_src" "$PYBNF" 2>/dev/null; then
    ok "engine unpacked from $(basename "$_arc") into $PYBNF"
    [ -f "$PYBNF/VERSION" ] && ok "version stamp: $(head -1 "$PYBNF/VERSION")"
    rm -rf "$_tmp"; return 0
  fi
  warn "could not move the unpacked engine into $PYBNF"
  rm -rf "$_tmp"; return 1
}

case "${1:-}" in
  --print-bundle)
    # The launchers call this (retry fingerprint) so the search lives only here.
    # Dispatched before the Python probe below: stdout must carry only the path,
    # and the probe can print (or run conda create) on a machine without 3.11/3.12.
    find_engine_bundle
    exit 0 ;;
esac

# The engine needs Python 3.11/3.12: the fork pins numpy<2, whose wheels stop
# at cp312 (newer Pythons build numpy from source and fail). Else conda makes a 3.12.
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
if [ -z "$PY" ]; then
  CONDA=$(command -v conda 2>/dev/null)
  [ -z "$CONDA" ] && for c in /opt/anaconda3/bin/conda "$HOME/anaconda3/bin/conda" \
                              "$HOME/miniconda3/bin/conda"; do
    [ -x "$c" ] && { CONDA="$c"; break; }
  done
  if [ -n "$CONDA" ]; then
    echo "  no Python 3.11/3.12 found; asking conda for one (a few minutes)"
    "$CONDA" create -y -p "$HOME/.venvs/flubnf-engine-py312" python=3.12 >/dev/null \
      && PY="$HOME/.venvs/flubnf-engine-py312/bin/python3"
  fi
fi
if [ -z "$PY" ]; then
  warn "the engine needs Python 3.11 or 3.12 (its numpy pin has no wheels"
  warn "for newer Pythons) and none was found or creatable. Install 3.12"
  warn "(python.org, Homebrew, or conda) and re-run."
  exit 1
fi

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
elif [ -f "$PYBNF/pybnf/pf.py" ] && [ -f "$PYBNF/setup.py" ]; then
  # Plain unpacked copy (no .git): fine, the install is `pip install -e
  # --no-deps` and needs only an importable package. It has no git identity,
  # so print its stamp: 'which build' is the first question when forecasts differ.
  ok "unpacked copy present (no git): $PYBNF"
  PFVER=""
  for v in "$PYBNF/VERSION" "$PYBNF/.git_archival.txt"; do
    [ -f "$v" ] && { PFVER="$(head -1 "$v" 2>/dev/null)"; break; }
  done
  if [ -n "$PFVER" ]; then
    ok "version stamp: $PFVER"
  else
    warn "no version stamp in this copy, so 'which build am I running' has no"
    warn "answer. Whoever cut the archive should include one. Harmless for a"
    warn "single machine, awkward the moment two people compare forecasts."
  fi
  # A newer archive saved since replaces this copy ("save the file, open the
  # app"), but only if its stamp DIFFERS and the file is newer than the
  # installed VERSION: an old download must never downgrade. The old copy is
  # moved aside, never deleted, and put back if the install fails.
  _arc="$(find_engine_bundle 2>/dev/null)"
  _newver=""
  case "$_arc" in
    *.tar.gz) _newver="$(archive_version_stamp "$_arc")" ;;
  esac
  if [ -n "$_newver" ] && [ "$_newver" != "$PFVER" ] \
     && { [ ! -f "$PYBNF/VERSION" ] || [ "$_arc" -nt "$PYBNF/VERSION" ]; }; then
    say "a different engine archive has arrived since this copy was installed"
    ok "on disk:  ${PFVER:-(no stamp)}"
    ok "archive:  $_newver"
    _kept="$PYBNF.replaced-$(date +%Y%m%d%H%M%S)"
    if mv "$PYBNF" "$_kept" 2>/dev/null && install_engine_archive "$_arc"; then
      PFVER="$_newver"
      ok "the previous copy is at $_kept; delete it once you are happy"
    else
      [ -d "$_kept" ] && [ ! -d "$PYBNF" ] && mv "$_kept" "$PYBNF" 2>/dev/null
      warn "could not install $_arc; the copy already on disk is unchanged"
    fi
  else
    warn "this copy cannot be updated with git pull. A newer engine means a"
    warn "newer archive saved where setup looks (Downloads is fine); it is"
    warn "installed over this copy the next time this script runs."
  fi
else
  # The offline file, tried before anything that needs an account.
  say "offline engine bundle"
  BUNDLE="$(find_engine_bundle)"
  ARCHIVE_DONE=""
  case "$BUNDLE" in
    *.tar.gz)
      # Tarball: unpack it; on failure the GitHub route below still runs.
      ok "found: $BUNDLE"
      install_engine_archive "$BUNDLE" && ARCHIVE_DONE=1
      BUNDLE="" ;;
  esac
  if [ -n "$ARCHIVE_DONE" ]; then
    : # engine is on disk now; the have_pybnf gate below sees it and skips auth
  elif [ -n "$BUNDLE" ]; then
    ok "found: $BUNDLE"
    # `git bundle verify` reads only the header, so it accepts a half-truncated
    # file (git 2.39.5); truncation surfaces at clone as 'early EOF'. Report
    # which failure it was: a new file vs the same file copied again.
    if git bundle verify "$BUNDLE" >/dev/null 2>&1; then
      if git clone -b feature/particle-filter "$BUNDLE" "$PYBNF"; then
        ok "cloned from the bundle into $PYBNF"
        ok "no GitHub account, invitation or network was needed"
        # origin = the bundle file (often removable media): name the fork
        # instead, for a human's later `git pull` (FluBNF never pulls it).
        git -C "$PYBNF" remote set-url origin "$PYBNF_REMOTE" 2>/dev/null \
          && ok "origin now names the fork itself (updates need access; the bundle does not)"
      else
        warn "the clone from that bundle FAILED (git's own output is above)."
        warn "The usual cause is a copy that did not finish: git reports that"
        warn "as 'early EOF' or 'index-pack died', which reads like a broken"
        warn "installation and is really a broken file. Compare its size with"
        warn "the copy you were given and fetch it again. The other cause is a"
        warn "bundle made from the wrong branch ('Remote branch"
        warn "feature/particle-filter not found'), which needs a new bundle."
        # No cleanup: git removes its own half clone; a pre-existing dir is not ours.
        if [ -d "$PYBNF" ] && [ ! -d "$PYBNF/.git" ]; then
          warn "note: $PYBNF exists and is not a checkout. git will not clone"
          warn "into it. Move it aside, or point FLUBNF_PYBNF somewhere else."
        fi
      fi
    else
      warn "that file is not a git bundle at all. git said:"
      git bundle verify "$BUNDLE" 2>&1 | sed 's/^/      /'
      warn "A browser that saved an error page under this name does exactly"
      warn "that. Ask for the file again, or move it out of the way, and this"
      warn "setup falls back to the GitHub route below."
    fi
  else
    warn "no engine file found. Looked for pybnf*.tar.gz and pybnf*.bundle in:"
    engine_bundle_dirs | sed 's/^/      /'
    warn "A bundle is ONE file that installs the engine with no GitHub"
    warn "account at all. Anyone who already has the fork creates one with:"
    warn "  git bundle create pybnf.bundle feature/particle-filter"
    warn "Drop it in any folder listed above (Downloads is the easy one) and"
    warn "run this again. Otherwise, the GitHub route follows."
  fi
fi

# Still need GitHub? Test the disk, not a flag. The code being there counts,
# .git or not: an unpacked copy must never be sent to authenticate.
have_pybnf() {
  [ -d "$PYBNF/.git" ] || { [ -f "$PYBNF/pybnf/pf.py" ] && [ -f "$PYBNF/setup.py" ]; }
}
if ! have_pybnf; then
  say "fork access (needed to clone)"
  # GIT_TERMINAL_PROMPT=0 is load-bearing: a double-clicked .command has a TTY,
  # so git would prompt for a password (dead since 2021; 2>&1 cannot hide the
  # prompt) and bury the advice below. Fail fast and silent instead.
  if GIT_TERMINAL_PROMPT=0 git ls-remote "$PYBNF_REMOTE" HEAD >/dev/null 2>&1; then
    git clone -b feature/particle-filter "$PYBNF_REMOTE" "$PYBNF" && ok "cloned"
  else
    warn "cannot authenticate to $PYBNF_REMOTE and no local checkout exists"
    # Report what this machine can see before advising (wrong cached identity,
    # unsearched path, no network, no access look alike); every probe is
    # non-interactive so none can hang.
    say "what this machine can see (paste this if you need help)"
    if GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/cdcepi/FluSight-forecast-hub HEAD >/dev/null 2>&1; then
      ok "github.com reachable (a public repo responds), so this is not the network"
    else
      warn "cannot reach github.com even for a PUBLIC repo. Fix the network or"
      warn "the proxy first: no credential will help until this line changes."
    fi
    if command -v gh >/dev/null 2>&1; then
      GHWHO=$(gh api user --jq .login 2>/dev/null || echo "")
      if [ -n "$GHWHO" ]; then
        ok "gh is signed in as: $GHWHO"
        if gh api "repos/elyfmiller/PyBNF-Private" --jq .full_name >/dev/null 2>&1; then
          ok "and THAT account can see the fork, so run: gh auth setup-git"
          warn "  (gh being signed in does not by itself teach plain git the"
          warn "   credential; 'gh auth setup-git' is the step that does)"
        else
          warn "but that account CANNOT see elyfmiller/PyBNF-Private."
          warn "Either it is the wrong account, or it is not a collaborator."
        fi
      else
        warn "gh is installed but not signed in (run: gh auth login)"
      fi
    else
      warn "gh not installed, so no account identity to report from it"
    fi
    KC=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^username=//p')
    if [ -n "$KC" ]; then
      warn "terminal git will authenticate as: $KC"
      warn "  If that is not the account with access, THAT is the bug: macOS"
      warn "  cached it and reuses it silently. Clear it with the erase line"
      warn "  below, then sign in again as the right account."
    else
      warn "terminal git has no stored github.com credential at all, which is"
      warn "why it cannot clone a private repo. GitHub Desktop does NOT share"
      warn "its login with terminal git; that is the usual surprise here."
    fi
    say "is the fork already on this machine somewhere we do not look?"
    # List as strays only checkouts the automatic search would MISS.
    SEARCHED="$HOME/Documents/GitHub/PyBNF-Private $HOME/Documents/GitHub/PyBNF-pf $HOME/Documents/PyBNF-Private $HOME/PyBNF-Private"
    STRAY=""; INPATH=""
    for g in $(find "$HOME" -maxdepth 5 -type d -name '.git' -path '*PyBNF*' 2>/dev/null | head -8); do
      d=$(dirname "$g")
      case " $SEARCHED " in
        *" $d "*) INPATH="$INPATH $d" ;;
        *)        STRAY="$STRAY $d" ;;
      esac
    done
    if [ -n "$INPATH" ]; then
      ok "a checkout already sits where setup looks:"
      printf '     %s\n' $INPATH
      warn "so nothing needs cloning."
      # Blame FLUBNF_PYBNF only when it is set. SEARCHED is the launchers'
      # list, wider than the two names this script resolves itself.
      if [ -n "${FLUBNF_PYBNF:-}" ]; then
        warn "You reached this message because FLUBNF_PYBNF points somewhere"
        warn "else ($PYBNF). Re-run without it:"
        warn "  unset FLUBNF_PYBNF; ./setup_engine.sh   (or double-click SetupEngine.command)"
      else
        warn "This script looks at PyBNF-pf and PyBNF-Private under"
        warn "~/Documents/GitHub only; the launchers look wider. Point it"
        warn "straight at the one above and it is done:"
        warn "  FLUBNF_PYBNF=<that directory> ./setup_engine.sh"
        warn "  (or double-click SetupEngine.command, which searches them all)"
      fi
    fi
    if [ -n "$STRAY" ]; then
      warn "found a PyBNF checkout the automatic search does NOT cover:"
      printf '     %s\n' $STRAY
      warn "point setup at it directly and you are done:"
      warn "  FLUBNF_PYBNF=<that directory> ./setup_engine.sh"
    fi
    [ -z "$INPATH$STRAY" ] && ok "no PyBNF checkout anywhere under your home directory"
    say "how to fix it"
    warn "NOTE: git's password prompt does NOT accept your GitHub account"
    warn "password (GitHub retired password auth in 2021), so being a"
    warn "collaborator is not enough by itself."
    warn "FIRST, CHECK THE INVITE WAS ACCEPTED. A collaborator invitation has"
    warn "to be accepted before the repository exists for you at all: until"
    warn "then it is invisible everywhere, in Desktop's list, in search and to"
    warn "git, which looks identical to having no access. The repo owner sees"
    warn "pending invites at github.com/elyfmiller/PyBNF-Private/settings/access"
    warn "with an 'Invited' badge; the invitee accepts from their email or"
    warn "from github.com/notifications. Signing in with the right account is"
    warn "NOT the same as having accepted."
    # The bundle goes first: it needs no account, network, install or admin.
    warn "EASIEST OF ALL, AND NEEDS NO GITHUB ACCOUNT AT ALL: ask anyone who"
    warn "already has the fork for an engine bundle. On their machine, once:"
    warn "  git bundle create pybnf.bundle feature/particle-filter"
    warn "They hand you that one file (shared drive or USB stick; it is about"
    warn "140 MB, too big to email). You drop it in Downloads and run this"
    warn "again. The folders searched are listed above under 'offline engine"
    warn "bundle'. No login, no invitation, no network."
    warn "If you would rather go through GitHub, pick one:"
    warn "a) EASIEST: GitHub Desktop, no terminal at all. File > Clone"
    warn "   repository, then THE URL TAB, and paste"
    warn "     elyfmiller/PyBNF-Private"
    warn "   Use the URL tab even though the GitHub.com tab looks right: that"
    warn "   list shows repositories you OWN and your organisations', so a"
    warn "   private repo you are only a COLLABORATOR on is usually missing"
    warn "   from it. Not finding it in the list does not mean you lack"
    warn "   access. Set the local path to"
    warn "     ~/Documents/GitHub/PyBNF-Private"
    warn "   which is where this setup looks, then reopen FluBNF.command."
    warn "   (Signing in to Desktop WITHOUT cloning does not help: Desktop"
    warn "   does not share its login with terminal git.)"
    # Recommend `gh auth login` only when gh exists; else say how to get it.
    if command -v gh >/dev/null 2>&1; then
      warn "b) run 'gh auth login' (you have the GitHub CLI), then re-run this."
    else
      warn "b) the GitHub CLI route, which needs TWO steps because 'gh' is"
      warn "   not installed on this machine (that is why 'gh auth login'"
      warn "   returns command not found):"
      if command -v brew >/dev/null 2>&1; then
        warn "     brew install gh && gh auth login"
      else
        warn "     you have no Homebrew either, so install gh from the .pkg at"
        warn "     https://github.com/cli/cli/releases (pick the macOS .pkg),"
        warn "     then run: gh auth login"
      fi
      warn "   Option (a) needs no install and is faster if you are unsure."
    fi
    warn "c) clone it yourself once, in Terminal, and paste a Personal Access"
    warn "   Token when git asks for the PASSWORD (github.com > Settings >"
    warn "   Developer settings > Personal access tokens). Your own git"
    warn "   command still prompts; only this script's check does not:"
    warn "   git clone -b feature/particle-filter \\"
    warn "     $PYBNF_REMOTE \\"
    warn "     ~/Documents/GitHub/PyBNF-Private"
    warn "   Then reopen FluBNF.command."
    warn "For SSH keys: set FLUBNF_PYBNF_REMOTE=git@github.com:elyfmiller/PyBNF-Private.git"
    warn "ALREADY TRIED AND STILL STUCK? macOS caches the first answer in the"
    warn "keychain, so one wrong entry keeps failing silently. Clear it with"
    warn "  printf 'protocol=https\\nhost=github.com\\n\\n' | git credential-osxkeychain erase"
    warn "then use (a) or (b)."
    exit 1
  fi
fi

if [ "${FLUBNF_ENGINE_CHECKOUT_ONLY:-0}" = "1" ]; then
  # Test hook (tests/test_engine_bundle.py) and manual use: stop after the checkout.
  ok "stopping after the checkout (FLUBNF_ENGINE_CHECKOUT_ONLY=1)"
  exit 0
fi

say "engine venv"
[ -d "$ENGINE_VENV" ] || $PY -m venv "$ENGINE_VENV"
# The runtime set the PF path imports, installed explicitly so the fork can go
# in with --no-deps (its msgpack==0.6.2 pin has no modern wheels; its nose and
# paramiko are never imported). numpy<2: the fork predates NumPy 2.
"$ENGINE_VENV/bin/pip" install -q "numpy<2" scipy pandas "dask==2022.12.1" \
  "distributed==2022.12.1" msgpack pyparsing tornado libroadrunner \
  python-libsbml && ok "runtime dependencies installed" \
  || { warn "dependency install failed (see pip's output above)"; exit 1; }

say "bngsim"
if "$ENGINE_VENV/bin/python" -c "import bngsim" 2>/dev/null; then
  ok "bngsim already importable"
else
  # Wheel first, source build as fallback. Pinned to 0.15.1: measured
  # bit-identical (ODE, filter, WIS) to the unreleased build behind every
  # published number; 0.13.0, the version that build reported, is not.
  if ! "$ENGINE_VENV/bin/pip" install -q "bngsim==0.15.1" 2>/dev/null; then
    warn "no PyPI/wheel match -- building from source (needs a C++ toolchain;"
    warn "on macOS: xcode-select --install). This takes ~10 minutes."
    "$ENGINE_VENV/bin/pip" install "git+$BNGSIM_REMOTE" || { warn "bngsim build failed"; exit 1; }
  fi
  ok "bngsim installed: $("$ENGINE_VENV/bin/python" -c 'import bngsim; print(bngsim.__version__)')"
fi

say "PyBNF install"
# --no-deps: see the runtime set above. A failed editable install is only a
# warning (known on Windows): runners load pybnf from the checkout via
# sys.path, so the verify below is the real gate.
"$ENGINE_VENV/bin/pip" install -q -e "$PYBNF" --no-deps \
  && ok "pybnf (fork) installed editable" \
  || warn "editable install failed -- harmless if the verify below passes"

say "verify"
# Import as every generated runner does (checkout first on sys.path). Failure
# aborts BEFORE the environment is recorded.
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
ENVF="$HERE/.flubnf.env"
# Rewrite, don't skip: a stale entry must not outlive a verified setup.
TMPF="$ENVF.tmp.$$"
grep -v -e FLUBNF_PY_ENGINE -e FLUBNF_PYBNF "$ENVF" 2>/dev/null > "$TMPF" || true
{
  echo "export FLUBNF_PY_ENGINE=\"$ENGINE_VENV/bin/python\""
  echo "export FLUBNF_PYBNF=\"$PYBNF\""
} >> "$TMPF"
mv "$TMPF" "$ENVF"
ok "environment recorded in $ENVF"
