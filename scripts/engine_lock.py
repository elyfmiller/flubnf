"""The public engine's lock file, engine-requirements.txt, read for the
installers and CI.

The engine lane writes the lock: every package the public engine needs,
each pinned with its hashes, plus one line for the PyBNF wheel (built from
lanl/PyBNF 8410f794 and attached to a release on elyfmiller/flubnf). The
installers read the wheel's URL and sha256 (ENGINE_WHEEL_URL and
ENGINE_WHEEL_SHA256) from that line, here and nowhere else, so the real
values arrive with the lock and no installer is edited for them. Stdlib
only: it runs under whichever Python an installer has in hand, the new
venv's included.

    python scripts/engine_lock.py wheel [LOCK]  the wheel's URL, then its sha256
    python scripts/engine_lock.py deps [LOCK]   the lock without the wheel (CI)
    python scripts/engine_lock.py check [LOCK]  under the public venv's Python:
                                                does the venv hold what the
                                                lock names?

LOCK defaults to FLUBNF_ENGINE_LOCK, else engine-requirements.txt at the
repository root. Exit 0 when all is well; 2 when the lock is missing or has
no usable wheel line; 1 when `check` finds the venv does not match it. The
reason goes to stderr, in words someone at the launcher can act on.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHEEL = "pybnf"


class LockError(Exception):
    """The lock cannot be used (exit 2)."""


class Mismatch(Exception):
    """The venv does not hold what the lock names (exit 1)."""


def lock_path(arg: str | None = None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("FLUBNF_ENGINE_LOCK", "").strip()
    return Path(env) if env else ROOT / "engine-requirements.txt"


def _name(line: str) -> str:
    """A requirement's project name, normalized as pip compares them; ""
    for an option line (--index-url ...) or anything else."""
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
    return re.sub(r"[-_.]+", "-", m.group(1)).lower() if m else ""


def logical_lines(text: str) -> list[str]:
    """The lock as pip reads it: a trailing backslash continues the line, and
    a # at the start or after a space opens a comment (pip-compile writes
    '# via ...' under each pin)."""
    out, cur = [], ""
    for raw in text.splitlines():
        raw = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if raw.endswith("\\"):
            cur += raw[:-1] + " "
            continue
        cur += raw
        if cur.strip():
            out.append(" ".join(cur.split()))
        cur = ""
    if cur.strip():
        out.append(" ".join(cur.split()))
    return out


def read_lock(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LockError(
            f"the public engine's lock file is not here: {path}. The engine "
            "lane posts it (docs/team/engine.md); until then only the private "
            "engine installs.") from None
    except OSError as e:
        raise LockError(f"could not read {path}: {e}") from None
    return logical_lines(text)


def wheel(lines: list[str], path: Path) -> tuple[str, str]:
    """ENGINE_WHEEL_URL and ENGINE_WHEEL_SHA256, from the lock's one PyBNF
    line: `pybnf @ https://.../pybnf-....whl --hash=sha256:<64 hex>`."""
    found = [ln for ln in lines if _name(ln) == WHEEL]
    if not found:
        raise LockError(f"{path} has no line for the PyBNF wheel "
                        f"('{WHEEL} @ https://...whl --hash=sha256:...').")
    if len(found) > 1:
        raise LockError(f"{path} names PyBNF {len(found)} times; it must "
                        "name one wheel once.")
    line = found[0]
    m = re.search(r"@\s*(\S+)", line)
    url = m.group(1) if m else ""
    if not (url.startswith("https://") and url.split("#")[0].endswith(".whl")):
        raise LockError(f"{path}: PyBNF must come from a wheel at an https "
                        f"address, and its line reads: {line}")
    shas = re.findall(r"--hash[= ]sha256:([0-9a-fA-F]{64})\b", line)
    if len(shas) != 1:
        raise LockError(f"{path}: the PyBNF line must carry exactly one "
                        f"--hash=sha256 (it carries {len(shas)}).")
    return url, shas[0].lower()


def pinned(lines: list[str], name: str) -> str | None:
    """The version the lock pins for `name` (extras allowed), or None."""
    for ln in lines:
        if _name(ln) == name:
            m = re.match(r"\s*[^=<>!~ ;@]+==\s*([^\s;\\]+)", ln)
            return m.group(1) if m else None
    return None


def deps(lines: list[str]) -> list[str]:
    """Every line but the wheel's, hashes kept: what CI fetches as Windows
    wheels (the PyBNF wheel is pure Python and lives on a release page)."""
    return [ln for ln in lines if _name(ln) != WHEEL]


def check(lines: list[str], path: Path) -> str:
    """Run by the public venv's Python after pip: the Liu-West filter
    imports, bngsim is the version the lock pins, and the installed pybnf
    came from the lock's wheel (pip records where, PEP 610). Returns the
    line to print; raises Mismatch with the reason."""
    import importlib.metadata as md

    url, sha = wheel(lines, path)
    try:
        import bngsim  # noqa: F401  (a compiled extension: load it for real)
        from pybnf.algorithms.filters.liu_west import LiuWestFilter  # noqa: F401
    except Exception as e:  # noqa: BLE001  (any failure means not ready)
        raise Mismatch("the public engine does not load in this venv "
                       f"({type(e).__name__}: {e})") from None
    try:
        dist = md.distribution(WHEEL)
    except md.PackageNotFoundError:
        raise Mismatch("pybnf imports but is not installed as a package "
                       "here: a checkout on PYTHONPATH shadows it") from None
    raw = dist.read_text("direct_url.json")
    if not raw:
        raise Mismatch(f"pybnf {dist.version} here was not installed from a "
                       "wheel address, so it is not the lock's wheel")
    info = json.loads(raw)
    got = info.get("url", "")
    if got != url:
        raise Mismatch(f"pybnf here came from {got}; the lock names {url}")
    arch = info.get("archive_info") or {}
    got_sha = (arch.get("hashes") or {}).get("sha256") \
        or str(arch.get("hash", "")).partition("sha256=")[2]
    if got_sha and got_sha.lower() != sha:
        raise Mismatch(f"pybnf's wheel here has sha256 {got_sha}; the lock "
                       f"names {sha}")
    want = pinned(lines, "bngsim")
    have = md.version("bngsim")
    if want and have != want:
        raise Mismatch(f"bngsim here is {have}; the lock pins {want}")
    return (f"  + public engine ready: pybnf {dist.version} from "
            f"{url.rsplit('/', 1)[-1]}, bngsim {have}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("wheel", "deps", "check"):
        print(__doc__.split("\n\n")[2], file=sys.stderr)
        return 2
    path = lock_path(argv[1] if len(argv) > 1 else None)
    try:
        lines = read_lock(path)
        if argv[0] == "wheel":
            print("\n".join(wheel(lines, path)))
        elif argv[0] == "deps":
            print("\n".join(deps(lines)))
        else:
            print(check(lines, path))
    except LockError as e:
        print(f"  ! {e}", file=sys.stderr)
        return 2
    except Mismatch as e:
        print(f"  ! {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
