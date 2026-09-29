#!/bin/bash
# Move a FluBNF clone out of the folders macOS guards, into ~/GitHub.
#
#   move_home.sh            run from the clone's root (FluBNF.command does)
#   move_home.sh --check    exit 0 when this clone should move, 1 when not
#
# WHY. macOS keeps Documents, Desktop and Downloads from any app that has
# not been allowed in, and FluBNF.app cannot be: it starts as a shell
# script, so macOS asks whether /bin/bash may read the folder (not FluBNF),
# and the answer is no, whatever Full Disk Access says. Terminal is allowed,
# which is why FluBNF.command still worked. The rest of the home folder is
# open to every app, so a clone in ~/GitHub opens from the Dock as it
# should.
#
# WHAT MOVES, each only when it sits in a guarded folder:
#   - this clone, to ~/GitHub/<its folder name>;
#   - the FluSight hub and the PyBNF checkout named in .flubnf.env, beside
#     it (the console reads the hub, and the engine imports PyBNF from its
#     checkout, so both must be readable too).
# Each is one rename on the same disk: nothing is copied, git history and
# local work move with it. Then every path that named an old place is
# rewritten: .flubnf.env, the clone's .venv and app/state, and the engine
# venv. Symlinks and binary files are left alone.
#
# WHEN IT DOES NOT MOVE (it says why, and FluBNF runs in place, through
# Terminal, as before):
#   - FLUBNF_MOVE=off;
#   - the new folder already exists;
#   - FluBNF is running from this clone (quit it, then open it again);
#   - ~/GitHub is on another disk (a move there would be a copy).
# A hub or PyBNF whose new folder already exists stays where it is.
#
# Prints the clone's new path on stdout when it moved; messages go to
# stderr. Status 0 moved, 1 nothing to do, 2 it should move but cannot.
set -u
say()  { echo "· $*" >&2; }
short() { case "$1" in "$HOMEP"/*) printf '~/%s' "${1#"$HOMEP"/}" ;; *) printf '%s' "$1" ;; esac; }

HOMEP="$(cd "$HOME" 2>/dev/null && pwd -P)" || exit 1
DEST_ROOT="${FLUBNF_HOME_DIR:-$HOMEP/GitHub}"
REPO="$(pwd -P)"

guarded() {
  case "$1/" in
    "$HOMEP/Documents/"*|"$HOMEP/Desktop/"*|"$HOMEP/Downloads/"*) return 0 ;;
  esac
  return 1
}

[ "${FLUBNF_MOVE:-}" != off ] || exit 1
guarded "$REPO" || exit 1
[ "${1:-}" != --check ] || exit 0

NEWREPO="$DEST_ROOT/${REPO##*/}"
say "FluBNF is in $(short "$REPO"). macOS does not let FluBNF.app read"
say "  Documents, Desktop or Downloads, so it moves to $(short "$NEWREPO")."
if [ -e "$NEWREPO" ]; then
  say "not moving: $(short "$NEWREPO") already exists. Rename or remove it,"
  say "  then open FluBNF.command again. Until then FluBNF runs through Terminal."
  exit 2
fi
pid="$(cat app/state/app.pid 2>/dev/null)"
case "$pid" in ''|*[!0-9]*) ;; *)
  case "$(ps -o command= -p "$pid" 2>/dev/null)" in
    *"flubnf app"*|*"flubnf window"*)
      say "not moving while FluBNF is running from this folder. Quit it"
      say "  (Cmd-Q), then open FluBNF.command again."
      exit 2 ;;
  esac ;;
esac
dev() { stat -c %d "$1" 2>/dev/null || stat -f %d "$1" 2>/dev/null; }
mkdir -p "$DEST_ROOT" 2>/dev/null || { say "not moving: cannot make $DEST_ROOT"; exit 2; }
if [ "$(dev "$REPO")" != "$(dev "$DEST_ROOT")" ]; then
  say "not moving: $DEST_ROOT is on another disk. Move this folder there"
  say "  yourself, or set FLUBNF_HOME_DIR to a folder on this disk."
  exit 2
fi

# The hub and PyBNF, as .flubnf.env names them
envval() { ( . ./.flubnf.env >/dev/null 2>&1; eval "printf '%s' \"\${$1:-}\"" ); }
HUBP="$(envval FLUBNF_HUB)"
PYBNFP="$(envval FLUBNF_PYBNF)"
ENGINE="$(envval FLUBNF_PY_ENGINE)"
ENGINE="${ENGINE%/bin/python}"

# old<TAB>new pairs, rewritten once everything has moved
PAIRS=""
move() {       # move <what> <old>; adds the pair when it moved
  local new="$DEST_ROOT/${2##*/}"
  if [ -e "$new" ]; then
    say "the $1 stays in $(short "$2"): $(short "$new") already exists"
    return 1
  fi
  if mv "$2" "$new" 2>/dev/null; then
    say "moved the $1 to $(short "$new")"
    PAIRS="$PAIRS$2	$new
"
    return 0
  fi
  say "could not move the $1 ($(short "$2")); it stays there"
  return 1
}
for pair in "FluSight hub:$HUBP" "PyBNF checkout:$PYBNFP"; do
  what="${pair%%:*}"; p="${pair#*:}"
  [ -n "$p" ] && [ -d "$p" ] || continue
  p="$(cd "$p" && pwd -P)"
  guarded "$p" || continue
  case "$p/" in "$REPO/"*) continue ;; esac
  move "$what" "$p"
done
move "FluBNF folder" "$REPO" || exit 2

# Paths that named the old places: whole names only (flubnf, not
# flubnf-old-...), text files only, never through a symlink
rewrite() {    # rewrite <file or folder>
  [ -e "$1" ] || return 0
  printf '%s' "$PAIRS" | while IFS='	' read -r old new; do
    [ -n "$old" ] || continue
    grep -rlIF -- "$old" "$1" 2>/dev/null | while IFS= read -r f; do
      [ -L "$f" ] && continue
      OLD="$old" NEW="$new" perl -pi -e 's/\Q$ENV{OLD}\E(?![\w.-])/$ENV{NEW}/g' "$f" 2>/dev/null
    done
  done
}
rewrite "$NEWREPO/.flubnf.env"
rewrite "$NEWREPO/.venv"
rewrite "$NEWREPO/app/state"
if [ -n "$ENGINE" ] && [ -d "$ENGINE" ]; then
  case "$ENGINE/" in "$REPO/"*) ;; *) rewrite "$ENGINE" ;; esac
fi
{ mkdir -p "$NEWREPO/app/state/logs" \
  && echo "=== $(date '+%Y-%m-%d %H:%M:%S') moved here from $REPO" >> "$NEWREPO/app/state/logs/launch.log"; } 2>/dev/null

if [ -x "$NEWREPO/.venv/bin/python" ] \
   && ! (cd / && "$NEWREPO/.venv/bin/python" -c 'import flubnf' >/dev/null 2>&1); then
  say "the venv did not follow the move; run ./setup.sh in $(short "$NEWREPO") to rebuild it"
fi
say "done. GitHub Desktop will say it cannot find these folders: choose"
say "  Locate... and pick them in $(short "$DEST_ROOT"). If FluBNF's Dock icon shows a"
say "  question mark, remove it, open $(short "$NEWREPO")/FluBNF.app, and Keep in Dock."
echo "$NEWREPO"
