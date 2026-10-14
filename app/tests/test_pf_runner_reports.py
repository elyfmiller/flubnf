"""What a fit runner reports when a cell fails, and that it keeps going.

The engine stops a cell three ways the runners used to report badly: its
exit(1) after a failed network generation (SystemExit got past `except
Exception`, so the shard died and every cell left read "shard 0 reported
no result"), a PybnfError (str() of it is a tuple of both of its
messages, cut at 200 characters inside the second), and, on Windows, a
status replace refused while a reader holds the file. And Python 3.12
prints a SyntaxWarning for every invalid escape in the engine's source
into the Sandbox's Engine messages fold. Subprocess tests run the
GENERATED runners against a stub pybnf, as test_pf_shards.py does.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import retro                               # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402

#: the engine's PybnfError (pybnf/printing.py), as it is: no
#: super().__init__, so its args are both messages
_PYBNF_ERROR = (
    "class PybnfError(RuntimeError):\n"
    "    def __init__(self, log_message, user_message=None):\n"
    "        self.log_message = log_message\n"
    "        self.message = user_message or log_message\n")

#: what BNG2.pl leaves in <cell>/out/Initialize/m_gen_net.log when it fails
_NETGEN_LOG = (
    "BioNetGen version 2.9.3\n"
    "Reading from file m_gen_net.bngl (level 0)\n"
    "Read 9 parameters.\n"
    "ABORT: Molecule type Flu is not defined in line 41\n")

#: a failure the engine words for people at more than the old 200 cut
_USER_MESSAGE = ("The parameter r__FREE is missing from the model. The PF "
                 "fit samples the negative binomial dispersion as r__FREE, "
                 "so the model must declare it in its parameters block. "
                 + "Add it with a starting value, as the shipped examples "
                 "do. " * 10)


def _fake_pybnf(root: Path, body: str, parse_head: str = "") -> Path:
    """A pybnf whose ParticleFilter.run does whatever the test needs;
    `parse_head` runs when the runner imports pybnf.parse."""
    pkg = root / "fake_pybnf" / "pybnf"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "parse.py").write_text(parse_head
                                  + "def load_config(p):\n    return p\n")
    (pkg / "pf.py").write_text(
        "import os, time\n" + _PYBNF_ERROR +
        "class ParticleFilter:\n"
        "    def __init__(self, cfg):\n"
        "        self.cfg = cfg\n"
        "    def run(self, _):\n" + body)
    return root / "fake_pybnf"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """The engine venv, faked: this interpreter and a stub pybnf."""
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    monkeypatch.setattr(pf, "_sleep", lambda _s: time.sleep(0.02))

    def install(body, parse_head=""):
        monkeypatch.setattr(pf, "PYBNF_PF",
                            _fake_pybnf(tmp_path, body, parse_head))
    return install


def _grid(w: Path, n: int) -> list:
    cells = []
    for i in range(n):
        d = w / f"cell_{i}"
        d.mkdir(parents=True)
        (d / "pf.conf").write_text("")
        cells.append({"key": f"cell_{i}", "dir": str(d), "n_obs": 1,
                      "particles": 100})
    (w / "cells.json").write_text(json.dumps(cells))
    return cells


#: the stub's run for _three_ways: cell_0 fails network generation the
#: way the engine does (log, then exit(1)), cell_1 exits with no log,
#: cell_2 raises a PybnfError, cell_3 fits
_THREE_WAYS = (
    "        here = os.path.basename(os.getcwd())\n"
    "        if here == 'cell_0':\n"
    "            init = os.path.join('out', 'Initialize')\n"
    "            os.makedirs(init)\n"
    "            with open(os.path.join(init, 'm_gen_net.log'), 'w') as fh:\n"
    f"                fh.write({_NETGEN_LOG!r})\n"
    "            raise SystemExit(1)\n"
    "        if here == 'cell_1':\n"
    "            raise SystemExit(2)\n"
    "        if here == 'cell_2':\n"
    "            raise PybnfError('Missing r__FREE in model',\n"
    f"                             {_USER_MESSAGE!r})\n")


# ------------------------------------------------ a failed cell, reported

def test_an_engine_exit_and_a_pybnf_error_are_recorded_and_the_shard_goes_on(
        engine, tmp_path):
    """One shard: the engine's exit(1) no longer ends it, the exit names
    the end of the network-generation log, and PybnfError reads as its
    sentence for people, not a tuple."""
    engine(_THREE_WAYS)
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    out = pf.execute(w, width=1)

    assert out["cell_3"] == "ok"                 # the shard went on
    exit_1 = out["cell_0"]
    assert exit_1.startswith("FAIL: the engine stopped (exit code 1); "
                             "the end of ")
    assert os.path.join("out", "Initialize", "m_gen_net.log") in exit_1
    assert exit_1.endswith("ABORT: Molecule type Flu is not defined in "
                           "line 41")
    assert "shard 0 reported no result" not in exit_1
    assert out["cell_1"] == "FAIL: the engine stopped (exit code 2)"
    # the sentence for people, cut at 600 characters, never the tuple
    assert out["cell_2"] == ("FAIL: " + _USER_MESSAGE)[:600]
    assert len(_USER_MESSAGE) > 600 and "('" not in out["cell_2"]

    # the whole of every reason is in the runner's stderr, the Sandbox's
    # Engine messages fold
    err = (w / "pf_runner_0.err").read_text()
    assert "cell_0 failed: the engine stopped (exit code 1)" in err
    assert "ABORT: Molecule type Flu is not defined" in err
    assert f"cell_2 failed: {_USER_MESSAGE}" in err


def test_a_long_netgen_log_keeps_its_end_in_the_status(engine, tmp_path):
    """The status keeps the start of a reason; the log's end is what names
    the cause, so the tail it carries is short enough to fit."""
    engine("        init = os.path.join('out', 'Initialize')\n"
           "        os.makedirs(init)\n"
           "        log = os.path.join(init, 'm_gen_net.log')\n"
           "        with open(log, 'w') as fh:\n"
           "            for i in range(40):\n"
           "                fh.write('Read line %d of a long model, and a '\n"
           "                         'long way from the cause\\n' % i)\n"
           "            fh.write('ABORT: the cause\\n')\n"
           "        raise SystemExit(1)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 1)
    status = pf.execute(w, width=1)["cell_0"]
    assert len(status) <= 600
    assert status.endswith("ABORT: the cause")
    assert "line 39" in status and "line 0 " not in status


def test_a_successful_run_writes_the_status_it_always_wrote(engine, tmp_path):
    """Production's record of a good grid: the same bytes json.dump wrote
    before, a finished progress file, nothing on stderr and no leftovers."""
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 3)
    out = pf.execute(w, width=1)
    assert out == {"cell_0": "ok", "cell_1": "ok", "cell_2": "ok"}
    assert (w / "pf_status_0.json").read_bytes() == json.dumps(
        {"cell_0": "ok", "cell_1": "ok", "cell_2": "ok"}).encode()
    prog = json.loads((w / "pf_status_0.json.prog").read_text())
    assert sorted(prog) == ["done", "now", "t0", "total"]
    assert prog["done"] == prog["total"] == 3
    assert (w / "pf_runner_0.err").read_text() == ""
    assert not list(w.glob("*.tmp"))
    assert json.loads((w / "pf_status.json").read_text()) == out


# --------------------------------------------- a replace Windows refuses

#: the stub's run, first cell only: from now on os.replace in this runner
#: refuses `times` calls on paths ending in `which` (PermissionError, as
#: MoveFileEx's sharing violation reaches Python), counting each in
#: <workroot>/refusals
_REFUSE = (
    "        if os.path.basename(os.getcwd()) == 'cell_0':\n"
    "            real, left = os.replace, [{times}]\n"
    "            tally = os.path.join(os.path.dirname(os.getcwd()),\n"
    "                                 'refusals')\n"
    "            def flaky(src, dst):\n"
    "                if left[0] and str(dst).endswith({which!r}):\n"
    "                    left[0] -= 1\n"
    "                    with open(tally, 'a') as fh:\n"
    "                        fh.write(str(dst) + '\\n')\n"
    "                    raise PermissionError(13, 'in use', str(dst))\n"
    "                return real(src, dst)\n"
    "            os.replace = flaky\n")


def test_a_status_replace_refused_twice_is_tried_again(engine, tmp_path):
    engine(_REFUSE.format(times=2, which="pf_status_0.json"))
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    out = pf.execute(w, width=1)
    assert out == {"cell_0": "ok", "cell_1": "ok"}
    assert len((w / "refusals").read_text().splitlines()) == 2
    assert (w / "pf_runner_0.err").read_text() == ""


def test_a_status_never_released_is_written_in_place_at_the_end(engine,
                                                                tmp_path):
    """Every replace of the status refused: the runner still fits every
    cell, and its status is written in place when it is done."""
    engine(_REFUSE.format(times=10_000, which="pf_status_0.json"))
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    out = pf.execute(w, width=1)
    assert out == {"cell_0": "ok", "cell_1": "ok"}
    assert "status not written after 1 cell(s)" in (
        w / "pf_runner_0.err").read_text()


def test_a_progress_replace_never_released_costs_nothing(engine, tmp_path):
    """The .prog file is best effort: refusing it ends neither the runner
    nor the status."""
    engine(_REFUSE.format(times=10_000, which=".prog"))
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    assert pf.execute(w, width=1) == {"cell_0": "ok", "cell_1": "ok"}
    assert (w / "pf_runner_0.err").read_text() == ""


def test_a_reader_holding_the_status_open_does_not_end_the_runner(
        engine, tmp_path):
    """The Forecast page's poll, played by the first cell: it opens the
    shard's status file and lets go 150 ms later. On Windows the replace
    after the cell is refused until then (the case this guards); elsewhere
    it passes at once."""
    engine("        import threading\n"
           "        if os.path.basename(os.getcwd()) == 'cell_0':\n"
           "            fh = open(os.path.join(os.path.dirname(os.getcwd()),\n"
           "                                   'pf_status_0.json'))\n"
           "            threading.Timer(0.15, fh.close).start()\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    assert pf.execute(w, width=1) == {"cell_0": "ok", "cell_1": "ok"}
    assert "status not written" not in (w / "pf_runner_0.err").read_text()


@pytest.fixture
def refusing_replace(monkeypatch):
    """os.replace refusing its first `n` calls, as Windows does while a
    reader holds the target; returns the list of calls made."""
    real = os.replace
    calls = []

    def install(n):
        def flaky(src, dst):
            calls.append(dst)
            if len(calls) <= n:
                raise PermissionError(13, "in use", str(dst))
            return real(src, dst)
        monkeypatch.setattr(os, "replace", flaky)
        return calls
    return install


def test_replace_file_waits_out_two_refusals(tmp_path, refusing_replace):
    calls = refusing_replace(2)
    tmp, dst = tmp_path / "x.tmp", tmp_path / "x"
    tmp.write_text("new")
    dst.write_text("old")
    pf.replace_file(tmp, dst)
    assert dst.read_text() == "new" and not tmp.exists()
    assert len(calls) == 3


def test_replace_file_gives_up_after_its_tries(tmp_path, refusing_replace):
    calls = refusing_replace(10_000)
    tmp = tmp_path / "x.tmp"
    tmp.write_text("new")
    with pytest.raises(PermissionError):
        pf.replace_file(tmp, tmp_path / "x")
    assert len(calls) == pf.REPLACE_TRIES


def test_replace_file_raises_any_other_error_at_once(tmp_path):
    with pytest.raises(FileNotFoundError):
        pf.replace_file(tmp_path / "absent.tmp", tmp_path / "x")


def test_the_sandbox_meta_and_the_runner_registry_wait_out_a_reader(
        tmp_path, refusing_replace):
    calls = refusing_replace(2)
    sb._write_meta(tmp_path, {"status": "running"})
    assert json.loads((tmp_path / "meta.json").read_text()) == {
        "status": "running"}
    assert len(calls) == 3
    calls.clear()
    reg = tmp_path / "pf_runners.json"
    pf._write_registry(reg, {"123": {"pgid": None, "runner": "r.py"}})
    assert json.loads(reg.read_text()) == {
        "123": {"pgid": None, "runner": "r.py"}}
    assert len(calls) == 3


# ------------------------------------------- the engine's SyntaxWarnings

#: what Python 3.12 says compiling the engine's config.py: an invalid
#: escape (a SyntaxWarning only from 3.12, so it is also raised by hand)
_INVALID_ESCAPE = ('import re, warnings\n'
                   '_DOT = re.compile("\\.")\n'
                   'warnings.warn("invalid escape sequence \'\\\\.\'", '
                   'SyntaxWarning)\n')


def test_the_engine_s_syntax_warnings_stay_out_of_the_runner_s_stderr(
        engine, tmp_path):
    engine("        pass\n", parse_head=_INVALID_ESCAPE)
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 1)
    assert pf.execute(w, width=1) == {"cell_0": "ok"}
    assert (w / "pf_runner_0.err").read_text() == ""


def test_both_runners_start_with_syntax_warnings_ignored(tmp_path,
                                                         monkeypatch):
    """The forecast runner and retro's runner come through runner_cmd."""
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    assert pf.runner_cmd(tmp_path / "r.py") == [
        sys.executable, "-W", "ignore::SyntaxWarning", str(tmp_path / "r.py")]
    made = []
    real = subprocess.Popen

    def spy(cmd, *a, **k):
        made.append([str(c) for c in cmd])
        return real(cmd, *a, **k)

    monkeypatch.setattr(retro.subprocess, "Popen", spy)
    wd = tmp_path / "wk"
    wd.mkdir()
    halt = wd / "HALT"
    halt.touch()                    # the launched runner exits at once
    procs = retro._launch_runners(wd, [[{"key": "c0", "dir": str(wd)}]],
                                  halt)
    try:
        for p in procs:
            p.wait(20)
    finally:
        pf.unrecord_runner_pids(procs)
    assert len(made) == 1
    i = made[0].index(sys.executable)
    assert made[0][i:i + 3] == [sys.executable, "-W", "ignore::SyntaxWarning"]
    assert made[0][i + 3].endswith("runner_0.py")
    assert [p.returncode for p in procs] == [0]


# ------------------------------------------------------ the retro runner

def test_the_retro_runner_marks_an_engine_exit_and_goes_on(tmp_path,
                                                           monkeypatch):
    """Retro's runner records failures as the forecast runner does; before,
    an exit(1) ended its shard with no marker, and the round raised."""
    monkeypatch.setattr(retro.pf_engine, "PYBNF_PF",
                        _fake_pybnf(tmp_path, _THREE_WAYS))
    monkeypatch.setattr(retro.pf_engine, "PY310", Path(sys.executable))
    monkeypatch.setattr(retro, "_sleep", lambda _s: time.sleep(0.05))
    root = tmp_path / "2098-99"
    wd = root / "weeks" / "2098-11-07"
    cells = []
    for i in range(4):
        d = wd / f"cell_{i}"
        d.mkdir(parents=True)
        cells.append({"key": f"cell_{i}", "dir": str(d)})
    retro._run_round(root, wd, cells, width=1)        # one shard
    done = retro._cell_done_dir(wd)
    assert retro.cells_done(wd) == {f"cell_{i}" for i in range(4)}
    status = {k: json.loads((done / f"{k}.json").read_text())["status"]
              for k in retro.cells_done(wd)}
    assert status["cell_0"].startswith("FAIL: the engine stopped (exit "
                                       "code 1); the end of ")
    assert status["cell_0"].endswith("ABORT: Molecule type Flu is not "
                                      "defined in line 41")
    assert status["cell_1"] == "FAIL: the engine stopped (exit code 2)"
    assert status["cell_2"] == ("FAIL: " + _USER_MESSAGE)[:600]
    # a fitted cell's marker is the bytes it always was
    assert (done / "cell_3.json").read_text() == json.dumps(
        {"key": "cell_3", "status": "ok"})
