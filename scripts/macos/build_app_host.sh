#!/usr/bin/env bash
# Build FluBNF.app/Contents/MacOS/FluBNF, the in-bundle Python host that makes
# the console window a FluBNF app in the Dock (scripts/macos/flubnf_host.c).
#
#   scripts/macos/build_app_host.sh           build if missing or stale (quiet when current)
#   scripts/macos/build_app_host.sh --force   rebuild, even after a failed attempt
#   scripts/macos/build_app_host.sh --check   no build: 0 current, 1 build due, 2 known to fail
#
# Exit 0: the host is current, or a rebuild failed and the host already
# installed still loads, so it stays in use (stamped "kept"). Nonzero: there
# is no usable host, and FluBNF.app opens the console through Terminal
# (FluBNF.command) instead.
#
# Stale means the fingerprint changed. The fingerprint covers the C source,
# this script, Info.plist, .venv/pyvenv.cfg (a recreated venv or a new base
# Python), the installed packages and the machine. A failed build is stamped
# with its fingerprint and the compiler it had, so a doomed build is not
# retried on every Dock launch, while installing the Command Line Tools
# earns a retry.
#
# Everything it writes is untracked: the host (gitignored), its stamp in
# .venv, and a scratch folder under $TMPDIR. A build therefore never blocks
# FluBNF.command's git fast-forward.
#
# Links the libpython the venv was made from:
#   - framework (python.org, Homebrew): <base_prefix>/Python, which records an
#     absolute install name;
#   - shared (pyenv --enable-shared, uv): LIBDIR/LDLIBRARY, with an rpath;
#   - Anaconda/conda-forge (static interpreter): the libpython3.x.dylib they
#     ship beside it, with an rpath.
# A static-only Python (pyenv's default) has no library to embed and is
# refused.
#
# Signing: ad hoc (codesign -s -), which is all a program built and run on
# the same Mac needs. Apple Silicon runs only signed arm64 code; the linker
# already signs ad hoc, and codesign redoes it under a stable identifier.
# No hardened runtime: its library validation would refuse conda's and
# python.org's libpython. Gatekeeper checks only quarantined files, and a
# file compiled here carries no quarantine flag.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP="$REPO/FluBNF.app"
SRC="$HERE/flubnf_host.c"
HOST="$APP/Contents/MacOS/FluBNF"
VPY="$REPO/.venv/bin/python"
CFG="$REPO/.venv/pyvenv.cfg"
STAMP="$REPO/.venv/.app-host.stamp"
SELF="$HERE/$(basename "$0")"
MODE="${1:-}"
WORK=""     # our own scratch folder; never $TMP, which a shell may export
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT

say() { printf '%s\n' "· $*"; }

sha() { { shasum 2>/dev/null || sha1sum; } | cut -c1-16; }

MAC=""
[ "$(uname -s)" = Darwin ] && MAC=1
# Only macOS gets a host. FLUBNF_HOST_ANY_OS=1 lets the Linux tests build it.
if [ -z "$MAC" ] && [ -z "${FLUBNF_HOST_ANY_OS:-}" ]; then
  [ "$MODE" = --check ] || say "FluBNF.app's host is built on macOS only"
  exit 2
fi
if [ ! -x "$VPY" ] || [ ! -f "$CFG" ] || [ ! -f "$SRC" ]; then
  [ "$MODE" = --check ] || say "no .venv yet: FluBNF.app opens through Terminal until setup has run"
  exit 1
fi

# The package listing moves with any install or refresh, so a build that
# failed on a broken venv is retried once the venv is repaired. Info.plist is
# in it so that an edit to it re-registers the app (lsregister, below).
FP="$({ cat "$SRC" "$SELF" "$CFG" "$APP/Contents/Info.plist" 2>/dev/null
        ls "$REPO"/.venv/lib/python*/site-packages 2>/dev/null; uname -m; } | sha)"
# The compiler this machine has. Not in the fingerprint: removing the
# Command Line Tools must not discard a host that works. xcode-select -p
# only reads a setting; /usr/bin/cc without the tools would open an install
# dialog instead.
if [ -n "$MAC" ]; then
  TOOLS="$(xcode-select -p 2>/dev/null)"
else
  TOOLS="$(command -v cc || command -v gcc || command -v clang)"
fi
LAST="$(head -1 "$STAMP" 2>/dev/null)"
WHY="$(sed -n 2p "$STAMP" 2>/dev/null)"
# The load test (about 0.1 s): the installed host starts this venv's
# Python. It catches a libpython that moved or was removed, a venv of
# another Python, and an x86_64 host with no Rosetta. Any of them would
# otherwise end a Dock launch in silence.
loads() {
  [ -x "$HOST" ] && FLUBNF_HOST_FALLBACK="" "$HOST" -c "" >/dev/null 2>&1
}
# Current = built for this fingerprint AND still loads.
current() { [ "$LAST" = "ok $FP" ] && loads; }
known_failure() { [ "$LAST" = "fail $FP $TOOLS" ]; }
# A rebuild for this fingerprint failed with this compiler, and the host it
# would have replaced still loads: that host stays in use (see fail).
kept() { [ "$LAST" = "kept $FP $TOOLS" ] && loads; }

case "$MODE" in
  --check)
    current && exit 0
    kept && exit 0
    known_failure && exit 2
    exit 1 ;;
  --force) ;;
  "")
    current && exit 0
    if kept; then
      say "FluBNF.app keeps its earlier host: the rebuild failed (${WHY:-no reason recorded})."
      say "scripts/macos/build_app_host.sh --force tries again and shows the details."
      exit 0
    fi
    if known_failure; then
      say "FluBNF.app opens the console through Terminal: ${WHY:-its host did not build}."
      say "scripts/macos/build_app_host.sh --force tries again and shows the details."
      exit 1
    fi ;;
  *) echo "usage: $0 [--force|--check]" >&2; exit 64 ;;
esac

fail() {
  say "FluBNF.app's host was not built: $1"
  # A failed REbuild keeps a host that still loads: the fingerprint moves
  # with every package install, and the compiler can go away (the Command
  # Line Tools removed by a macOS upgrade, an Xcode licence not accepted
  # again). Stamped "kept" like a failure, so it is not retried on every
  # launch, and a new compiler or fingerprint earns the retry.
  if loads; then
    say "The host already installed still starts this venv's Python; FluBNF.app keeps using it."
    printf 'kept %s %s\n%s\n' "$FP" "$TOOLS" "$1" > "$STAMP" 2>/dev/null
    exit 0
  fi
  say "FluBNF.app opens the console through Terminal until it is."
  printf 'fail %s %s\n%s\n' "$FP" "$TOOLS" "$1" > "$STAMP" 2>/dev/null
  exit 1
}

if [ -n "$MAC" ]; then
  [ -n "$TOOLS" ] && [ -d "$TOOLS" ] \
    || fail "the Command Line Tools are not installed; run xcode-select --install, then open FluBNF.app again"
  # through xcrun, which hands the compiler the macOS SDK. Its own words
  # when it refuses (an Xcode licence not yet accepted, say).
  XE="$(xcrun --find cc 2>&1)" \
    || fail "xcrun found no C compiler in $TOOLS ($(printf '%s\n' "$XE" | head -1 | cut -c1-200))"
  CC=(xcrun cc)
else
  [ -n "$TOOLS" ] || fail "no C compiler (cc, gcc or clang)"
  CC=("$TOOLS")
fi

# What the venv's own interpreter says about the libpython to embed. A -c
# string, not a heredoc inside $(...), which macOS's bash 3.2 can misparse.
DESCRIBE='
import os, platform, shlex, sys, sysconfig
v = sysconfig.get_config_var
inc = v("INCLUDEPY") or sysconfig.get_paths()["include"]
fw = v("PYTHONFRAMEWORK") or ""
if fw:
    lib, rpath, kind = sys.base_prefix + "/" + fw, "", "framework"
elif v("Py_ENABLE_SHARED"):
    lib, rpath, kind = str(v("LIBDIR")) + "/" + str(v("LDLIBRARY")), v("LIBDIR"), "shared"
else:
    # Anaconda / conda-forge: the interpreter is static (Py_ENABLE_SHARED=0)
    # but lib/ also ships libpython3.x.dylib for embedding.
    d, ver = str(v("LIBDIR")), str(v("LDVERSION") or v("VERSION"))
    hits = [p for p in (d + "/libpython" + ver + ".dylib", d + "/libpython" + ver + ".so")
            if os.path.isfile(p)]
    lib, rpath, kind = (hits[0], d, "shared beside static") if hits else ("", "", "static")
for k, val in (("PYINC", inc), ("PYLIB", lib), ("PYRPATH", rpath),
               ("PYKIND", kind), ("PYARCH", platform.machine()),
               ("PYVER", "%d.%d" % sys.version_info[:2])):
    print(k + "=" + shlex.quote(str(val)))
'
PYINC="" PYLIB="" PYRPATH="" PYKIND="" PYARCH="" PYVER=""
DESC="$("$VPY" -c "$DESCRIBE" 2>/dev/null)" || fail "the venv's python did not run (.venv/bin/python)"
# only our own assignments: a stray line (a sitecustomize, a warning) is not code
eval "$(printf '%s\n' "$DESC" | grep -E '^PY(INC|LIB|RPATH|KIND|ARCH|VER)=')"

[ -n "$PYVER" ] || fail "the venv's python did not say which libpython it uses"
[ "$PYKIND" != static ] || fail "Python $PYVER here has no shared libpython to embed (a static-only build)"
[ -f "$PYINC/Python.h" ] || fail "no Python.h under $PYINC"
[ -f "$PYLIB" ] || fail "no libpython at $PYLIB"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/flubnf-host.XXXXXX")" || fail "could not make a scratch folder"
OUT="$WORK/FluBNF"
ARGS=(-O2 -Wall -I"$PYINC" -o "$OUT" "$SRC" "$PYLIB")
[ -n "$PYRPATH" ] && ARGS+=("-Wl,-rpath,$PYRPATH")
[ -n "$MAC" ] && ARGS=(-arch "$PYARCH" "${ARGS[@]}")
if ! ERR="$("${CC[@]}" "${ARGS[@]}" 2>&1)"; then
  printf '%s\n' "$ERR" | head -20
  fail "the compile failed (Python $PYVER, $PYKIND): $(printf '%s\n' "$ERR" | grep -m1 -i 'error' | cut -c1-200)"
fi
if [ -n "$MAC" ]; then
  if ! codesign --force --sign - --identifier edu.nau.flubnf.host "$OUT" >/dev/null 2>&1; then
    # an x86_64 host runs unsigned; arm64 needs the linker's signature at least
    [ "$PYARCH" = x86_64 ] || codesign --verify "$OUT" >/dev/null 2>&1 \
      || fail "codesign could not sign the host, and Apple Silicon runs only signed code"
  fi
fi

# Smoke test before installing. The host finds its repo from its own path,
# so run it from a scratch bundle laid out like FluBNF.app (same Info.plist)
# whose .venv is this repo's venv. On macOS it also checks the premise of
# the whole host: a program in <Name>.app/Contents/MacOS belongs to that
# bundle, even though Info.plist names flubnf-launch as the executable.
mkdir -p "$WORK/t/Probe.app/Contents/MacOS"
cp "$OUT" "$WORK/t/Probe.app/Contents/MacOS/FluBNF"
cp "$APP/Contents/Info.plist" "$WORK/t/Probe.app/Contents/Info.plist" 2>/dev/null
ln -s "$REPO/.venv" "$WORK/t/.venv"
PROBE='import os, sys
import flubnf, webview
assert os.path.realpath(sys.prefix) == os.path.realpath(sys.argv[1]), (sys.prefix, sys.argv[1])
assert sys.executable.endswith("/.venv/bin/python"), sys.executable
if sys.platform == "darwin":
    # CoreFoundation directly (what NSBundle.mainBundle reads), so the check
    # needs nothing from the venv
    import ctypes, ctypes.util
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    cf.CFBundleGetMainBundle.restype = ctypes.c_void_p
    cf.CFBundleGetIdentifier.restype = ctypes.c_void_p
    cf.CFBundleGetIdentifier.argtypes = [ctypes.c_void_p]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                      ctypes.c_long, ctypes.c_uint32]
    main = cf.CFBundleGetMainBundle()
    ident = cf.CFBundleGetIdentifier(main) if main else None
    buf = ctypes.create_string_buffer(256)
    got = (buf.value.decode() if ident and cf.CFStringGetCString(
        ident, buf, 256, 0x08000100) else None)          # UTF-8
    assert got == "edu.nau.flubnf", "main bundle %r, not FluBNF.app" % (got,)
print("ok", sys.version.split()[0], sys.prefix)'
if ! GOT="$(FLUBNF_HOST_FALLBACK="" "$WORK/t/Probe.app/Contents/MacOS/FluBNF" -c "$PROBE" "$REPO/.venv" 2>&1)"; then
  printf '%s\n' "$GOT" | tail -8
  fail "the built host failed its test run (it must import flubnf and webview from .venv): $(printf '%s\n' "$GOT" | tail -1 | cut -c1-200)"
fi

# a new file, then a rename: a running host keeps its own copy, and Apple
# Silicon never sees a signed file change under it
cp "$OUT" "$HOST.new" && mv -f "$HOST.new" "$HOST" || fail "could not install $HOST"
printf 'ok %s\n' "$FP" > "$STAMP"
if [ -n "$MAC" ]; then
  # LaunchServices re-reads Info.plist and the icon
  touch "$APP"
  LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  [ -x "$LSREG" ] && "$LSREG" -f "$APP" >/dev/null 2>&1
fi
say "FluBNF.app's host is built for Python $PYVER ($PYKIND): FluBNF.app opens as FluBNF in the Dock"
exit 0
