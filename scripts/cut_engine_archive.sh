#!/usr/bin/env bash
# Cut the small engine archive that students install from.
#
# WHY THIS EXISTS. The particle filter lives in a PRIVATE fork, and that one
# repository is the only part of a FluBNF install that needs a GitHub account.
# Everything else (this repo, the FluSight hub, BioNetGen, bngsim) is public
# and already automatic. Hand a student this archive and the credentials
# problem disappears entirely: no account, no invitation, no token, no network.
#
# WHY IT IS SO SMALL. The fork's checkout is about 627 MB, but almost none of
# that is the engine: 418 MB is a nested bngsim clone (public on PyPI, and
# setup_engine.sh installs it from there), 147 MB is git history and 59 MB is
# example PDFs. The engine itself is `pybnf/` plus `setup.py` plus `README.md`,
# which setup.py reads at build time. That is about 130 KB, which fits in an
# email.
#
# WHY `git archive` AND NOT `tar`. tar would pack the WORKING TREE, which is
# whatever branch happens to be checked out. That is not hypothetical: the
# first attempt at this produced a perfectly installable archive with no pf.py
# in it at all, because the checkout was sitting on feature/bngsim. `git
# archive` names the branch, so it cannot pick up the wrong one or a
# half-finished edit.
#
# Usage:  scripts/cut_engine_archive.sh [output-dir] [ref]
set -euo pipefail

OUT="${1:-$PWD}"
REF="${2:-feature/particle-filter}"
FORK="${FLUBNF_PYBNF_FORK:-$HOME/Documents/GitHub/PyBNF-Private}"

[ -d "$FORK/.git" ] || { echo "no fork checkout at $FORK (set FLUBNF_PYBNF_FORK)" >&2; exit 1; }
git -C "$FORK" rev-parse --verify "$REF" >/dev/null 2>&1 \
  || { echo "no ref '$REF' in $FORK" >&2; exit 1; }

SHA="$(git -C "$FORK" rev-parse --short "$REF")"
STAMP="$OUT/pybnf-pf-$SHA.tar.gz"
mkdir -p "$OUT"

# The version stamp is the one thing a plain directory cannot supply for
# itself. A git checkout answers "which build am I running" on its own; an
# unpacked archive cannot, and that question is the first one asked the moment
# two people compare forecasts and disagree. setup_engine.sh prints this file
# when it finds one, so the answer travels with the code.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/PyBNF-Private"
{
  printf '%s %s\n' "$REF" "$SHA"
  printf 'cut %s from %s\n' "$(date +%Y-%m-%d)" "$(git -C "$FORK" remote get-url origin)"
  printf 'subject: %s\n' "$(git -C "$FORK" log -1 --format=%s "$REF")"
} > "$TMP/PyBNF-Private/VERSION"

git -C "$FORK" archive --format=tar --prefix=PyBNF-Private/ \
    "$REF" pybnf setup.py README.md > "$TMP/a.tar"
tar rf "$TMP/a.tar" -C "$TMP" PyBNF-Private/VERSION
gzip -9 -c "$TMP/a.tar" > "$STAMP"

# Verify rather than assert. A student cannot debug an archive that unpacks
# without pf.py in it, and that is exactly the failure this script exists to
# prevent, so check for the file by name before handing the archive over.
tar tzf "$STAMP" | grep -q 'PyBNF-Private/pybnf/pf.py' \
  || { echo "REFUSING: $STAMP has no pybnf/pf.py. Wrong ref?" >&2; rm -f "$STAMP"; exit 1; }

echo "wrote $STAMP  ($(du -h "$STAMP" | cut -f1), $(tar tzf "$STAMP" | wc -l | tr -d ' ') files)"
echo "stamp: $(git -C "$FORK" log -1 --format='%h %s' "$REF")"
echo
# The destination DIFFERS BY PLATFORM and getting it wrong is not cosmetic.
# flubnf/settings.py moves the Windows default out of Documents on purpose:
# Defender's Controlled Folder Access protects Documents and blocks untrusted
# programs from writing there, and python.exe is untrusted out of the box, so
# a checkout under Documents is one Python cannot even write __pycache__ into.
# The recorded Defender log line from a real machine is in setup.ps1 line 88.
echo "Send it with these two lines (the folder is NOT the same on both):"
echo "  macOS   1. unzip into  ~/Documents/GitHub/"
echo "             so you get  ~/Documents/GitHub/PyBNF-Private"
echo "          2. open FluBNF.command"
echo "  Windows 1. unzip into  %LOCALAPPDATA%\\FluBNF\\"
echo "             so you get  %LOCALAPPDATA%\\FluBNF\\PyBNF-Private"
echo "             (NOT Documents: Defender blocks Python from writing there)"
echo "          2. open FluBNF.bat"
