"""The public engine's install for real, as an open does it: FluBNF.bat's
public block run by cmd.exe on Windows, setup_engine.sh --public elsewhere,
with real pip, real PyPI and a real Python 3.12, into a venv under a
folder named with a space, an apostrophe and parentheses. The PyBNF wheel
and its lock come from the public-engine-wheel CI job
(scripts/make_test_lock.py), served here over https on localhost, so this
runs before the engine lane's lock exists.

Five steps, in order: a fresh install; an open with nothing to do; a new
lock (the wheel at another address), which puts the lock's wheel back
without reinstalling everything; a wheel whose sha256 does not match,
refused; then PyBNF's own lesson 50 (job_type = lwf) in the venv.

Only in the public-engine-install CI job: FLUBNF_PUBLIC_REAL names the
wheel job's folder. tests/test_engine_public.py and
tests/test_windows_setup_engine.py run the same code with stand-ins on
every run.
"""
from __future__ import annotations

import functools
import http.server
import importlib.util
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PUB = Path(os.environ.get("FLUBNF_PUBLIC_REAL") or "/nonexistent")
WIN = os.name == "nt"
WHEEL = "pybnf-1.8.1-py3-none-any.whl"

pytestmark = pytest.mark.skipif(
    not os.environ.get("FLUBNF_PUBLIC_REAL"),
    reason="FLUBNF_PUBLIC_REAL names the public-engine-wheel job's folder")


@pytest.fixture(scope="module", autouse=True)
def served():
    """The wheels over https on localhost:8443, as the release will serve
    them; pip is told to trust the host (PIP_TRUSTED_HOST in _open)."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(PUB / "wheels"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8443), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(PUB / "cert.pem", PUB / "key.pem")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield
    srv.shutdown()


@pytest.fixture(scope="module")
def pc(tmp_path_factory):
    """A FluBNF folder holding what the public route reads, and where the
    venv goes: the open itself (a FluBNF.bat whose console start says so and
    stops, or setup_engine.sh), scripts/engine_lock.py and, on Windows, the
    console's .venv, whose Python reads the lock."""
    home = tmp_path_factory.mktemp("x") / "Jane O'Brien (Lab)"
    folder = home / "FluBNF"
    (folder / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "engine_lock.py", folder / "scripts")
    if WIN:
        subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                        str(folder / ".venv")], check=True)
        (folder / ".venv" / "perl-offer.txt").write_bytes(b'"not asked in CI"\r\n')
        bat = (REPO / "FluBNF.bat").read_bytes().decode("ascii").replace("\r\n", "\n")
        body = bat.replace("\n:startconsole\n", "\n:startconsole_real\n")
        assert body != bat and "\n:engineupdated\n" in body
        # From the engine block on, as an open reaches it; every way out of
        # the public block ends at :startconsole, here the one at the top.
        text = ("@echo off\nsetlocal\ngoto :engineupdated\n"
                ":startconsole\necho THE CONSOLE STARTS HERE\nexit /b 0\n\n" + body)
        (folder / "FluBNF.bat").write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    else:
        shutil.copy(REPO / "setup_engine.sh", folder)
    return folder, home / "venv-public"


def _open(pc, lock: str, venv: Path | None = None):
    folder, default = pc
    env = {**os.environ, "FLUBNF_ENGINE": "public",
           "FLUBNF_ENGINE_LOCK": str(PUB / lock),
           "FLUBNF_PUBLIC_VENV": str(venv or default),
           "PIP_TRUSTED_HOST": "localhost"}
    cmd = (["cmd", "/d", "/c", str(folder / "FluBNF.bat")] if WIN
           else ["bash", str(folder / "setup_engine.sh"), "--public"])
    t0 = time.monotonic()
    r = subprocess.run(cmd, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace", timeout=1500, check=False)
    took = time.monotonic() - t0
    print(f"\n----- {lock}: exit {r.returncode} in {took:.0f} s -----\n{r.stdout}")
    return r, took


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WIN else "bin/python")


def _check(venv: Path, lock: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(_python(venv)), str(REPO / "scripts" / "engine_lock.py"), "check",
         str(PUB / lock)], capture_output=True, text=True, check=False)


def _wheel_url(venv: Path) -> str:
    code = ("import importlib.metadata as m, json; "
            "print(json.loads(m.distribution('pybnf').read_text('direct_url.json'))['url'])")
    return subprocess.run([str(_python(venv)), "-c", code], capture_output=True,
                          text=True, check=True).stdout.strip()


def _installs(out: str) -> bool:
    return ("Installing the public engine" if WIN
            else "public engine packages") in out


def test_a_fresh_install(pc):
    r, _ = _open(pc, "engine-requirements.txt")
    assert r.returncode == 0, r.stdout
    assert _installs(r.stdout)
    assert f"public engine ready: pybnf 1.8.1 from {WHEEL}, bngsim 0.15.1" in r.stdout
    if WIN:
        assert "THE CONSOLE STARTS HERE" in r.stdout
    assert _check(pc[1], "engine-requirements.txt").returncode == 0
    assert _wheel_url(pc[1]) == f"https://localhost:8443/{WHEEL}"


def test_an_open_with_nothing_to_do(pc):
    r, _ = _open(pc, "engine-requirements.txt")
    assert r.returncode == 0, r.stdout
    assert not _installs(r.stdout)
    assert "Collecting" not in r.stdout and "already satisfied" not in r.stdout
    if WIN:
        assert "THE CONSOLE STARTS HERE" in r.stdout


def test_a_new_lock_puts_back_its_wheel_alone(pc):
    r, _ = _open(pc, "lock-v2.txt")
    assert r.returncode == 0, r.stdout
    assert _installs(r.stdout)
    # pybnf alone, not every package (--force-reinstall took minutes)
    assert "installing every package again" not in r.stdout
    assert _check(pc[1], "lock-v2.txt").returncode == 0
    assert _wheel_url(pc[1]) == f"https://localhost:8443/v2/{WHEEL}"


def test_a_wheel_that_does_not_match_its_hash_is_refused(pc):
    venv = pc[1].parent / "venv-tampered"
    r, _ = _open(pc, "lock-tampered.txt", venv)
    assert "DO NOT MATCH THE HASHES" in r.stdout
    if WIN:
        assert "The public engine did not install" in r.stdout
        assert "THE CONSOLE STARTS HERE" in r.stdout
    else:
        assert r.returncode == 1
        assert "Hashes that do not match" in r.stdout
    assert _check(venv, "lock-tampered.txt").returncode != 0


def test_lesson_50_runs_in_the_venv(pc, tmp_path):
    lesson = tmp_path / "lesson 50"
    shutil.copytree(PUB / "lesson50", lesson)
    conf = lesson / "liu_west_filter.conf"
    conf.write_text(conf.read_text().replace("lwf_particles = 2000",
                                             "lwf_particles = 500"))
    # PyBNF asks for BNG2.pl even with bngsim simulating: the one pip's
    # bionetgen brings (the job installs it, as the test jobs do)
    spec = importlib.util.find_spec("bionetgen")
    assert spec, "pip install bionetgen beside pytest"
    plat = "bng-win" if WIN else "bng-mac" if sys.platform == "darwin" else "bng-linux"
    bng = Path(spec.submodule_search_locations[0]) / plat
    assert (bng / "BNG2.pl").is_file(), bng
    env = {**os.environ, "BNGPATH": str(bng),
           # as the console runs it on Windows (app/core/engines/pf.py)
           **({"BNGSIM_NO_CODEGEN": "1"} if WIN else {})}
    exe = pc[1] / ("Scripts/pybnf.exe" if WIN else "bin/pybnf")
    t0 = time.monotonic()
    r = subprocess.run([str(exe), "-c", conf.name], cwd=lesson, env=env,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace",
                       timeout=900, check=False)
    print(f"\n----- lesson 50: exit {r.returncode} in {time.monotonic() - t0:.0f} s"
          f" -----\n{r.stdout[-3000:]}")
    assert r.returncode == 0, r.stdout[-3000:]
    results = lesson / "output" / "liu_west_filter" / "Results" / "LWF"
    assert results.is_dir() and any(results.iterdir()), sorted(
        p.relative_to(lesson).as_posix() for p in lesson.rglob("*"))
    print("Results/LWF:", sorted(p.name for p in results.iterdir()))
