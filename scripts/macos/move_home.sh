#!/bin/bash
# Move a FluBNF clone out of the folders macOS guards, into ~/GitHub.
#
#   move_home.sh            run from the clone's root (FluBNF.command does)
#   move_home.sh --check    exit 0 when this clone should move, 1 when not
#   move_home.sh --relink   point the paths at where things are now, after
#                           any move (this one, or one made by hand)
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
# local work move with it.
#
# RELINK. Then every path that named an old place is rewritten: .flubnf.env,
# the clone's .venv and app/state, and the engine venv. The old places come
# from what was recorded, not from the move: the venv's activate script
# names the folder the venv was made in, and a hub or PyBNF path in
# .flubnf.env that is gone but has a namesake in ~/GitHub moved there. So
# FluBNF.command runs this on every open, and a clone moved by hand is
# repaired too. Whole names only, text files only, never through a symlink.
# When the venv still cannot import flubnf, it is reinstalled into (pip,
# no dependencies).
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

# The hub, PyBNF and the engine, as .flubnf.env names them
envval() { ( . ./.flubnf.env >/dev/null 2>&1; eval "printf '%s' \"\${$1:-}\"" ); }

# Rewrite old<TAB>new pairs (PAIRS, one per line) in the text files under
# each argument (logs/ folders aside: they record what was); prints how
# many files changed
rewrite() {
  PAIRS="$PAIRS" perl -e '
    use File::Find;
    my @p = map { [split /\t/, $_, 2] } grep { /\t/ } split /\n/, $ENV{PAIRS};
    my $n = 0;
    my $fix = sub {
      my $f = $File::Find::name;
      return if -l $f;
      if (-d $f && $f =~ m{/logs$}) { $File::Find::prune = 1; return; }
      return unless -f $f && -s $f && -s $f < 50_000_000 && -T $f;
      open(my $in, "<", $f) or return;
      local $/; my $t = <$in>; close $in;
      my $u = $t;
      $u =~ s/\Q$_->[0]\E(?![\w.-])/$_->[1]/g for @p;
      return if $u eq $t;
      open(my $out, ">", $f) or return;
      print $out $u; close $out; $n++;
    };
    find({ wanted => $fix, no_chdir => 1 }, grep { -e } @ARGV);
    print "$n\n";
  ' "$@"
}

relink() {
  local rec here pairs="" v old engine n
  here="$(pwd -P)"
  rec="$(sed -n "s/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}VIRTUAL_ENV=[\"']\{0,1\}\(\/[^\"']*\)[\"']\{0,1\}[[:space:]]*\$/\2/p" \
         .venv/bin/activate 2>/dev/null | head -1)"
  rec="${rec%/}"
  if [ -n "$rec" ] && [ "$rec" != "$here/.venv" ] \
     && [ "$(cd "$rec" 2>/dev/null && pwd -P)" != "$here/.venv" ]; then
    pairs="${rec%/.venv}	$here
"
  fi
  for v in FLUBNF_HUB FLUBNF_PYBNF; do
    old="$(envval "$v")"
    [ -n "$old" ] && [ ! -e "$old" ] && [ -d "$DEST_ROOT/${old##*/}" ] || continue
    pairs="$pairs$old	$DEST_ROOT/${old##*/}
"
  done
  [ -n "$pairs" ] || return 1
  PAIRS="$pairs"
  engine="$(envval FLUBNF_PY_ENGINE)"; engine="${engine%/bin/python}"
  case "$engine/" in /|"$here/"*) engine="" ;; esac
  n="$(rewrite .flubnf.env .venv app/state ${engine:+"$engine"})"
  printf '%s' "$pairs" | while IFS='	' read -r old v; do
    [ -n "$old" ] && say "now at $(short "$v"): paths to $(short "$old") updated"
  done
  { mkdir -p app/state/logs && printf '=== %s relinked %s file(s):\n%s' \
      "$(date '+%Y-%m-%d %H:%M:%S')" "${n:-0}" "$pairs" >> app/state/logs/launch.log; } 2>/dev/null
  if [ -x .venv/bin/python ] && ! (cd / && "$here/.venv/bin/python" -c 'import flubnf' >/dev/null 2>&1); then
    if [ -n "${FLUBNF_PREPARE_ONLY:-}" ]; then
      say "the venv still cannot load FluBNF"
      return 3
    fi
    say "reinstalling FluBNF into its venv (it still could not load it)"
    .venv/bin/python -m pip install -q --no-deps -e . >&2 \
      || say "that failed too: run ./setup.sh in $(short "$here") to rebuild the venv"
  fi
  return 0
}

if [ "${1:-}" = --relink ]; then
  relink
  exit $?
fi

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

HUBP="$(envval FLUBNF_HUB)"
PYBNFP="$(envval FLUBNF_PYBNF)"

move() {       # move <what> <old>
  local new="$DEST_ROOT/${2##*/}"
  if [ -e "$new" ]; then
    say "the $1 stays in $(short "$2"): $(short "$new") already exists"
    return 1
  fi
  if mv "$2" "$new" 2>/dev/null; then
    say "moved the $1 to $(short "$new")"
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

cd "$NEWREPO" || exit 2
{ mkdir -p app/state/logs \
  && echo "=== $(date '+%Y-%m-%d %H:%M:%S') moved here from $REPO" >> app/state/logs/launch.log; } 2>/dev/null
relink
say "done. GitHub Desktop will say it cannot find these folders: choose"
say "  Locate... and pick them in $(short "$DEST_ROOT"). If FluBNF's Dock icon shows a"
say "  question mark, remove it, open $(short "$NEWREPO")/FluBNF.app, and Keep in Dock."
echo "$NEWREPO"
