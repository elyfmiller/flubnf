"""A hashed lock for CI's real install of the public engine, from a PyBNF
wheel the job built itself.

    python scripts/make_test_lock.py WHEEL OUT [--url=https://localhost:8443/]

Never the engine lane's lock: engine-requirements.txt at the repo root is
theirs, and this one exists so CI can run the public route's real install
(tests/test_public_engine_real.py) before it does. Run it with the Python
3.12 the lock is for. In OUT:

    wheels/<wheel>, wheels/v2/<wheel>   what the test serves over https
    engine-requirements.txt   bngsim[antimony]==0.15.1 and everything the
                              wheel needs, resolved here as wheels only, each
                              pin with the sha256 of every file PyPI has for
                              it, then the wheel's own line
    lock-v2.txt               the same, the wheel at wheels/v2/ (a new lock)
    lock-tampered.txt         the same, the wheel's sha256 wrong

Resolved on this machine, as the engine lane resolves theirs on the lab
Mac: a package only another platform needs is missing from the lock, and
the install there fails on it, which is the point.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

BNGSIM = "bngsim[antimony]==0.15.1"


def _name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def resolve(wheel: Path) -> list[dict]:
    """pip's report of what installs with the wheel and bngsim, wheels only."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
             "--ignore-installed", "--disable-pip-version-check",
             "--only-binary", ":all:", "--report", str(report),
             str(wheel), BNGSIM], check=True)
        return json.loads(report.read_text())["install"]


def pypi_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=60) as r:
        files = json.load(r)["urls"]
    return sorted({f["digests"]["sha256"] for f in files})


def entry(line: str, shas: list[str]) -> str:
    return " \\\n".join([line] + [f"    --hash=sha256:{s}" for s in shas])


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--url")]
    url = next((a.split("=", 1)[1] for a in argv if a.startswith("--url=")),
               "https://localhost:8443/")
    if len(args) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    wheel, out = Path(args[0]), Path(args[1])
    url = url.rstrip("/") + "/"
    (out / "wheels" / "v2").mkdir(parents=True, exist_ok=True)
    shutil.copy(wheel, out / "wheels" / wheel.name)
    shutil.copy(wheel, out / "wheels" / "v2" / wheel.name)
    sha = hashlib.sha256(wheel.read_bytes()).hexdigest()

    pins = []
    for item in resolve(wheel):
        meta = item["metadata"]
        name = _name(meta["name"])
        if name == "pybnf":
            continue
        extras = item.get("requested_extras") or []
        spec = f"{name}[{','.join(extras)}]" if extras else name
        pins.append(entry(f"{spec}=={meta['version']}",
                          pypi_hashes(name, meta["version"])))
        print(f"  {spec}=={meta['version']}")
    head = ("#\n# Written by scripts/make_test_lock.py for CI's real install; "
            "not the engine lane's lock.\n#\n")

    def lock(wheel_url: str, wheel_sha: str) -> str:
        return head + "\n".join(
            sorted(pins) + [entry(f"pybnf @ {wheel_url}", [wheel_sha])]) + "\n"

    (out / "engine-requirements.txt").write_text(lock(url + wheel.name, sha))
    (out / "lock-v2.txt").write_text(lock(url + "v2/" + wheel.name, sha))
    (out / "lock-tampered.txt").write_text(
        lock(url + wheel.name, hashlib.sha256(b"tampered").hexdigest()))
    print(f"  pybnf @ {url}{wheel.name} ({len(pins)} other packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
