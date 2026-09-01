#!/usr/bin/env bash
# Tier-B engine setup: PyBNF fork (fit_type=pf) + bngsim. Lab-member edition.
set -u
say()  { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
ok()   { printf "  \033[32m+\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

# HTTPS by default so a credential helper can answer; set FLUBNF_PYBNF_REMOTE
# to the git@ form if you have an SSH key and prefer it.
PYBNF_REMOTE="${FLUBNF_PYBNF_REMOTE:-https://github.com/elyfmiller/PyBNF-Private.git}"
# PyBNF-pf is the DEVELOPMENT HOST's name for the fork and nothing else's. On
# every other machine the fork arrives as PyBNF-Private: that is the
# repository's real name, it is what GitHub Desktop and a plain `git clone`
# produce, and it is the prefix the lab's engine archive unpacks under
# (scripts/cut_engine_archive.sh writes --prefix=PyBNF-Private/). Both of the
# other two files that resolve this path already know that -- flubnf/settings.py
# does it in _first_checkout(), setup.ps1 in the PyBNF-Private fallback beside
# Resolve-Checkout -- and this line did not, so `./setup_engine.sh` run by hand
# walked past a perfectly good ~/Documents/GitHub/PyBNF-Private and demanded
# GitHub credentials. MEASURED 2026-08-31: with a real checkout sitting there
# and no FLUBNF_PYBNF set, the script reached the access wall and exited 1,
# while its own diagnostic block below correctly reported the checkout and then
# blamed FLUBNF_PYBNF, which was not set. Same order as settings.py: an
# existing PyBNF-pf first (the dev host keeps working untouched), then an
# existing PyBNF-Private, then PyBNF-pf as the name to clone into.
#
# "Exists" is the directory, not .git: an unpacked archive is a supported way
# to get the engine (see the plain-copy branch below) and has no .git at all.
if [ -n "${FLUBNF_PYBNF:-}" ]; then
  PYBNF="$FLUBNF_PYBNF"
elif [ -d "$HOME/Documents/GitHub/PyBNF-pf" ]; then
  PYBNF="$HOME/Documents/GitHub/PyBNF-pf"
elif [ -d "$HOME/Documents/GitHub/PyBNF-Private" ]; then
  PYBNF="$HOME/Documents/GitHub/PyBNF-Private"
else
  # nothing exists yet: create under the repository's REAL name, which is
  # also the archive's prefix and what every doc shows. PyBNF-pf remains the
  # dev host's name only (the elif above keeps that machine untouched).
  PYBNF="$HOME/Documents/GitHub/PyBNF-Private"
fi
BNGSIM_REMOTE="${FLUBNF_BNGSIM_REMOTE:-https://github.com/elyfmiller/bngsim}"
ENGINE_VENV="${FLUBNF_ENGINE_VENV:-$HOME/.venvs/flubnf-engine}"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
HERE="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# THE OFFLINE ENGINE BUNDLE
#
# Cloning the fork is the ONE step of a FluBNF install that needs a GitHub
# account, because that repository is private. Everything else -- this repo,
# the FluSight hub, BioNetGen, both venvs -- is public and already automatic,
# which is why so much of the text below this point is about credentials for
# a single clone.
#
# `git bundle` removes that step entirely. On a machine that already has the
# fork:
#
#   git bundle create pybnf.bundle feature/particle-filter
#
# produces one ordinary file (about 140 MB), and git clones from that file
# with no network, no account, no invitation to accept and nothing to
# install:
#
#   git clone -b feature/particle-filter pybnf.bundle <destination>
#
# The result is a normal checkout, which is what the branch above already
# knows how to use. So a student handed one file on a shared drive or a USB
# stick gets the engine with no authentication story at all.
#
# The search therefore runs BEFORE the authentication attempt: a file sitting
# beside you always beats a network round trip that may end at a password
# prompt no student can answer. The folders searched are the ones a student
# actually drops a downloaded file into, not the ones a developer would pick.
engine_bundle_dirs() {
  printf '%s\n' "$HERE" "$(dirname "$HERE")" \
                "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents"
}

find_engine_bundle() {
  # Prints the path of the bundle this machine would use, or nothing at all.
  # Nothing else may reach stdout: `--print-bundle` hands this straight to
  # the launchers, so a stray diagnostic would become a filename. Complaints
  # go to stderr.
  if [ -n "${FLUBNF_PYBNF_BUNDLE:-}" ]; then
    if [ -f "$FLUBNF_PYBNF_BUNDLE" ]; then
      printf '%s\n' "$FLUBNF_PYBNF_BUNDLE"
      return 0
    fi
    warn "FLUBNF_PYBNF_BUNDLE names a file that is not there:" >&2
    warn "  $FLUBNF_PYBNF_BUNDLE" >&2
    warn "looking in the usual places instead" >&2
  fi
  # Split the list on newlines only, not on spaces. A home directory with a
  # space in it is not this project's problem to create, but it is this
  # loop's problem to survive, and "/Users/Jane Doe/Downloads" would
  # otherwise arrive here as two directories that both do not exist.
  _oifs=$IFS
  IFS='
'
  # shellcheck disable=SC2046
  set -- $(engine_bundle_dirs)
  IFS=$_oifs
  for d in "$@"; do
    [ -d "$d" ] || continue
    # Both artifact shapes, one search. The lab hands out either a git bundle
    # or the small pybnf-pf-<sha>.tar.gz that scripts/cut_engine_archive.sh
    # cuts, and a student should not have to know which one they were given,
    # or where it belongs: whatever landed in Downloads is the engine. The
    # extract branch below tells them apart by suffix.
    for f in "$d"/pybnf*.bundle "$d"/PyBNF*.bundle \
             "$d"/pybnf*.tar.gz "$d"/PyBNF*.tar.gz; do
      # -f, not -e. On macOS ".bundle" is also a DIRECTORY type (plug-ins and
      # frameworks are shipped that way) and ~/Downloads is exactly where one
      # turns up. A directory named *.bundle is not a git bundle.
      [ -f "$f" ] && { printf '%s\n' "$f"; return 0; }
    done
  done
  return 0
}

install_engine_archive() {
  # Unpack a pybnf-pf tarball into $PYBNF, from wherever the student saved
  # it. THE STUDENT NEVER PLACES THIS BY HAND: the earlier design had the
  # install doc walking students to ~/Documents/GitHub (macOS) or the
  # Windows launcher's app-data folder, locations they had no reason to
  # know, to do a move this function does in three lines. The internal
  # location still matters (on Windows, Documents is Defender-protected,
  # which is why FluBNF.bat extracts under app data), but that is the
  # installer's concern, not the reader's.
  _arc="$1"
  _tmp="$(mktemp -d)" || return 1
  if ! tar -xzf "$_arc" -C "$_tmp" 2>/dev/null; then
    warn "could not unpack $_arc (a copy that did not finish?)"
    rm -rf "$_tmp"; return 1
  fi
  # The archive unpacks under one top-level folder (PyBNF-Private/). Find it
  # by content, not by name, so a re-rolled archive with a different prefix
  # still installs.
  _src=""
  for c in "$_tmp"/*/; do
    [ -f "${c}pybnf/pf.py" ] && [ -f "${c}setup.py" ] && { _src="${c%/}"; break; }
  done
  if [ -z "$_src" ]; then
    warn "$_arc unpacked, but no pybnf/pf.py inside: not the engine archive"
    rm -rf "$_tmp"; return 1
  fi
  mkdir -p "$(dirname "$PYBNF")"
  # mv into an EXISTING directory does not replace it, it NESTS the source
  # inside it, so a leftover folder at $PYBNF (a half-finished unpack, or an
  # empty folder someone made by hand; anything with pf.py was caught by the
  # gates above) would swallow the engine one level too deep while this
  # function reported success. Measured, not assumed. An empty leftover is
  # removed (rmdir refuses anything non-empty, so this cannot destroy data);
  # a non-empty one is refused out loud, because a folder this script did
  # not create is not this script's to delete.
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
    # The launchers call this so the search lives in exactly one file.
    # FluBNF.command needs to know whether a bundle has appeared since the
    # last failed attempt (otherwise its "do not retry a broken setup on
    # every open" stamp would suppress the retry that would now succeed),
    # and a second copy of the search would be a second thing to keep in
    # step with this one.
    find_engine_bundle
    exit 0 ;;
esac

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
  # A PLAIN UNZIPPED COPY, no .git at all.
  #
  # The engine does not need git. It needs an importable package, and the
  # install below is `pip install -e "$PYBNF" --no-deps`, which is perfectly
  # happy with an ordinary directory. Git was only ever used to confirm the
  # branch. So the whole particle filter travels as a 129 KB archive cut with
  #   git archive feature/particle-filter pybnf setup.py README.md
  # which is small enough to email, and that is the route students actually
  # get. Rejecting it for lacking a .git directory would be refusing to
  # install over a detail the installer does not use.
  #
  # The cost is real and is stated out loud rather than hidden: an unzipped
  # copy has no version identity and cannot be updated in place. `git archive`
  # writes the commit into .git_archival.txt when the repository is configured
  # for it, and whoever cuts the archive can drop a VERSION file in beside the
  # package; either is printed here if present, because the first question
  # when one student's forecast differs from another's is which copy they are
  # running, and an unversioned directory cannot answer it.
  ok "unpacked copy present (no git): $PYBNF"
  PFVER=""
  for v in "$PYBNF/VERSION" "$PYBNF/.git_archival.txt" "$PYBNF/PF_VERSION"; do
    [ -f "$v" ] && { PFVER="$(head -1 "$v" 2>/dev/null)"; break; }
  done
  if [ -n "$PFVER" ]; then
    ok "version stamp: $PFVER"
  else
    warn "no version stamp in this copy, so 'which build am I running' has no"
    warn "answer. Whoever cut the archive should include one. Harmless for a"
    warn "single machine, awkward the moment two people compare forecasts."
  fi
  warn "this copy cannot be updated with git pull. A newer engine means a"
  warn "newer archive, unzipped over the same folder."
else
  # --- the offline bundle, tried before anything that needs an account -----
  say "offline engine bundle"
  BUNDLE="$(find_engine_bundle)"
  ARCHIVE_DONE=""
  case "$BUNDLE" in
    *.tar.gz)
      # The archive shape: unpack it ourselves, wherever the student saved
      # it. If the unpack fails the file stays where it is and the GitHub
      # route below still runs, so a bad download never strands anyone.
      ok "found: $BUNDLE"
      install_engine_archive "$BUNDLE" && ARCHIVE_DONE=1
      BUNDLE="" ;;
  esac
  if [ -n "$ARCHIVE_DONE" ]; then
    : # engine is on disk now; the have_pybnf gate below sees it and skips auth
  elif [ -n "$BUNDLE" ]; then
    ok "found: $BUNDLE"
    # Verify first, but do not expect much of it. MEASURED on git 2.39.5:
    # `git bundle verify` accepts a bundle truncated to HALF its bytes -- it
    # reads the header and the prerequisites, not the pack -- and the clone
    # then dies with "fatal: early EOF / error: index-pack died". So verify
    # catches only the file that is not a bundle at all (a browser that saved
    # an error page under the name pybnf.bundle is the realistic one), and
    # the CLONE failure has to carry the truncation message itself. Both
    # branches say which of the two happened, because the remedy differs:
    # one needs a different file, the other needs the same file copied again.
    if git bundle verify "$BUNDLE" >/dev/null 2>&1; then
      if git clone -b feature/particle-filter "$BUNDLE" "$PYBNF"; then
        ok "cloned from the bundle into $PYBNF"
        ok "no GitHub account, invitation or network was needed"
        # `git clone` records the bundle FILE as origin, and that file is
        # often on a stick that is about to be unplugged. Point origin at the
        # real remote so a later `git pull` fails with something a person can
        # act on instead of "repository not found:
        # /Volumes/LAB/pybnf.bundle". Nothing in FluBNF ever pulls this
        # checkout, so this is for the human, not for the code.
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
        # Deliberately NOT cleaned up here. git removes its own half-made
        # clone, and the one case where something is left behind is a
        # destination that already existed with other things in it -- which
        # is a directory this script did not create and must not delete.
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

# The bundle above may have produced the checkout. Test the disk rather than
# a flag: the ground truth for "do we still need GitHub" is whether a
# checkout exists, and a flag can only ever disagree with it.
#
# "Exists" means THE CODE IS THERE, not ".git is there". Those came apart the
# moment an unzipped archive became a supported way to get the engine: a plain
# copy was accepted at the top of this script and then sent to authenticate
# anyway by this line, so a student with a perfectly good engine on disk was
# still asked for GitHub credentials. The install below only ever needs an
# importable package, so that is what both gates now ask for.
have_pybnf() {
  [ -d "$PYBNF/.git" ] || { [ -f "$PYBNF/pybnf/pf.py" ] && [ -f "$PYBNF/setup.py" ]; }
}
if ! have_pybnf; then
  say "fork access (needed to clone)"
  # GIT_TERMINAL_PROMPT=0 is load-bearing, not tidiness. Without it this probe
  # asks for a GitHub Username and Password ON THE TERMINAL, and a
  # double-clicked .command opens a real one, so git gets a TTY and prompts.
  # The `2>&1` below hides git's error text but CANNOT hide that prompt: it is
  # written straight to the terminal. A PI hit exactly this -- typed the
  # account password, which GitHub has rejected since 2021, and never reached
  # the four options spelled out under `warn` -- so the failure has to be
  # immediate and silent for that advice to be the thing the reader sees.
  # A prompt here can never succeed anyway: passwords are dead, and every
  # route that does work (Desktop, gh, a token, SSH) is set up elsewhere.
  if GIT_TERMINAL_PROMPT=0 git ls-remote "$PYBNF_REMOTE" HEAD >/dev/null 2>&1; then
    git clone -b feature/particle-filter "$PYBNF_REMOTE" "$PYBNF" && ok "cloned"
  else
    warn "cannot authenticate to $PYBNF_REMOTE and no local checkout exists"
    # WHY THIS BLOCK EXISTS. Twice now this failure has been debugged by
    # guessing from a menu of causes, and twice the guess was wrong: a PI had
    # accepted the invite and was a confirmed collaborator, and had GitHub
    # Desktop installed and signed in to the right account, and it still did
    # not work. A menu cannot distinguish "wrong identity cached", "cloned to
    # a path we do not search", "no network" and "genuinely no access". So
    # report what this machine can actually see BEFORE offering advice, and
    # keep every probe non-interactive so none of them can hang.
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
    # Report only checkouts the automatic search would MISS. Listing one that
    # is already probed reads as "we found it and ignored it", which sends the
    # reader off to fix the wrong thing.
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
      # Only blame FLUBNF_PYBNF when FLUBNF_PYBNF is actually set. It was an
      # unconditional line, and the first thing it did was give a reader with
      # a good checkout at ~/Documents/GitHub/PyBNF-Private a dead end: the
      # variable was not set, so "re-run without it" changed nothing and the
      # advice below it was never reached. SEARCHED above is the LAUNCHERS'
      # list, which is wider than the two names this script resolves on its
      # own, so the two can still legitimately disagree -- but only the
      # remaining locations, and only with the remedy that fits each.
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
    # The bundle goes FIRST because it is the only option on this list that
    # needs nothing from the reader's machine: no account, no invitation, no
    # network, no software to install, and no administrator rights on a
    # managed laptop. Every option below it has cost someone a debugging
    # session.
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
    # Option (b) used to say "run gh auth login" flatly, which is useless
    # advice on a machine without the GitHub CLI: a PI ran it and got
    # "command not found". Check before recommending, and say how to get it.
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
  # Stop once the checkout exists. tests/test_engine_bundle.py runs the real
  # script against a real bundle and needs to see the clone happen; building
  # the venv after it would cost minutes and a network it does not have, and
  # is not what that test is about. Useful by hand too, when all you want is
  # the fork on disk.
  ok "stopping after the checkout (FLUBNF_ENGINE_CHECKOUT_ONLY=1)"
  exit 0
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
ENVF="$HERE/.flubnf.env"
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
