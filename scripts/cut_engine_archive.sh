#!/usr/bin/env bash
# Cut the small engine archive that students install from.
# The fork is private; this ~130 KB archive (pybnf/ + setup.py, which reads
# README.md, + VERSION) installs the engine with no account or network. bngsim
# comes from PyPI, so the rest of the 627 MB checkout is not needed.
# `git archive`, not tar: it packs the named ref, never whatever branch or
# half-finished edit is checked out (tar once shipped an archive with no pf.py).
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

# VERSION answers "which build" for a copy with no .git; setup_engine.sh prints it.
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

# Verify pf.py is inside before handing the file over.
tar tzf "$STAMP" | grep -q 'PyBNF-Private/pybnf/pf.py' \
  || { echo "REFUSING: $STAMP has no pybnf/pf.py. Wrong ref?" >&2; rm -f "$STAMP"; exit 1; }

echo "wrote $STAMP  ($(du -h "$STAMP" | cut -f1), $(tar tzf "$STAMP" | wc -l | tr -d ' ') files)"
echo "stamp: $(git -C "$FORK" log -1 --format='%h %s' "$REF")"
echo
# No placement instructions: setup on both platforms finds the file in
# Downloads (or Desktop, Documents, beside the app) and places it itself.
echo "Send it with one instruction:"
echo "  save this file in your Downloads folder, then open FluBNF"
echo "  (FluBNF.command on macOS, FluBNF.bat on Windows)"
