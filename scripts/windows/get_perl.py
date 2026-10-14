"""FluBNF's own Perl on Windows, for BNG2.pl: conda-forge's repack of
Strawberry Perl 5.32.1.1, unpacked under %LOCALAPPDATA%\\FluBNF\\perl by
FluBNF.bat. No administrator, no installer, no conda.

Standard library only, and it never writes a file: FluBNF.bat writes with
Windows' own tar.exe. A Microsoft Store Python sends its writes under
AppData to a private copy that cmd.exe never sees, so the files must not
come from Python.

  python -I get_perl.py fetch [--from FILE] | tar.exe -xf - -C <root>
      the package, downloaded into memory (the proxy and certificates pip
      used) and checked against its pinned size and SHA-256 before a byte
      goes out, then bzip2-decompressed to stdout as a plain tar: Windows
      10's tar.exe has no bzip2 of its own. Exit 1, with nothing on stdout,
      when the download fails or does not match. FLUBNF_PERL_FROM names a
      local copy of the package, as --from does.
  python -I get_perl.py verify <root>
      every file the package lists in info/paths.json is there with its
      size and SHA-256. Exit 0 only then; FluBNF.bat writes its marker
      after this, so a marker always means a complete unpack.
"""
import bz2
import hashlib
import json
import os
import sys
import urllib.request

PACKAGE = "perl-5.32.1.1-2_h57928b3_strawberry.tar.bz2"
URL = "https://conda.anaconda.org/conda-forge/win-64/" + PACKAGE
SHA256 = "69a7fd4fcab0a9224a484923b9e88380a8cdfa7b03b9b9dd235f117006e83d92"
SIZE = 31366784
CHUNK = 1 << 20


def say(msg):
    print(f"  {msg}", file=sys.stderr, flush=True)


def _download():
    """The package's bytes, read at most SIZE + 1 (a larger file is not
    the pinned one), with a line on stderr every 8 MB so a slow network
    does not look like a hang."""
    data = bytearray()
    shown = 0
    # proxy from the environment or Windows' Internet settings, and
    # Windows' certificate store: the same road pip took
    with urllib.request.urlopen(URL, timeout=60) as r:
        while len(data) <= SIZE:
            block = r.read(min(CHUNK, SIZE + 1 - len(data)))
            if not block:
                break
            data += block
            if len(data) - shown >= 8 * CHUNK:
                shown = len(data)
                say(f"downloaded {shown >> 20} of {SIZE >> 20} MB")
    return bytes(data)


def fetch(src=None):
    src = src or os.environ.get("FLUBNF_PERL_FROM") or None
    try:
        if src:
            with open(src, "rb") as f:
                data = f.read(SIZE + 1)
        else:
            data = _download()
    except Exception as e:  # noqa: BLE001 - any failure: no Perl, said why
        say(f"Perl's package could not be downloaded: {e}")
        return 1
    got = hashlib.sha256(data).hexdigest()
    if len(data) != SIZE or got != SHA256:
        say(f"Perl's package is not the one FluBNF pins "
            f"({len(data)} bytes, SHA-256 {got})")
        return 1
    out = sys.stdout.buffer
    d = bz2.BZ2Decompressor()
    try:
        for i in range(0, len(data), CHUNK):
            out.write(d.decompress(data[i:i + CHUNK]))
        out.flush()
    except OSError as e:          # tar stopped reading: a full disk, say
        say(f"Perl's package could not be unpacked: {e}")
        return 1
    if not d.eof:
        say("Perl's package ended early")
        return 1
    return 0


def verify(root):
    try:
        with open(os.path.join(root, "info", "paths.json"),
                  encoding="utf-8") as f:
            manifest = json.load(f)["paths"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        say(f"Perl did not unpack ({e})")
        return 1
    for e in manifest:
        p = os.path.join(root, *e["_path"].split("/"))
        try:
            if os.path.getsize(p) != e["size_in_bytes"]:
                raise OSError("wrong size")
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for block in iter(lambda: f.read(CHUNK), b""):
                    h.update(block)
            if h.hexdigest() != e["sha256"]:
                raise OSError("wrong contents")
        except OSError as err:
            say(f"Perl did not unpack completely: {e['_path']} ({err})")
            return 1
    return 0


def main(argv):
    if argv[:1] == ["fetch"] and (len(argv) == 1 or
                                  (len(argv) == 3 and argv[1] == "--from")):
        return fetch(argv[2] if len(argv) == 3 else None)
    if argv[:1] == ["verify"] and len(argv) == 2:
        return verify(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
