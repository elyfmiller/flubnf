"""What this computer lacks for a Sandbox fit, said apart from the model
(app/core/sandbox.py machine_problems, preflight, bng_selftest,
engine_import_problem; sandbox_check.check), and the pf.conf a Sandbox
run writes, which names no folder.

The preflight checks the pieces in the order a student fixes them and
collects every failure: the engine folder, the engine's Python, that
Python loading the engine (doctor's ENGINE_PROBE, cached), Perl, BNG2.pl,
and BNG2.pl starting (`perl BNG2.pl -v`). A BNG2.pl run that stops before
BioNetGen's banner is the computer's failure, never the model's.

pf.conf: the engine's conf grammar reads ASCII only and splits the model
line at the first '.con', '.exp' or '.xml', so a profile folder named
José or m.contreras failed every fit while the conf named the cell. The
engines' own parsers are run where they are installed: the fork the
console uses (settings.PYBNF with settings.PY_ENGINE), or every pair in
FLUBNF_TEST_PARSERS, a JSON list of [engine checkout, its Python].
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import types
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from flubnf import settings                              # noqa: E402

EXAMPLE = (Path(__file__).resolve().parents[2] / "flubnf"
           / "sandbox_examples" / "kinetics_example")
#: the probes as written (sandbox_root answers "ready" for both), and the
#: subprocess.run sandbox_root's fake BNG2.pl stands in for
REAL_IMPORT_PROBLEM = sb.engine_import_problem
REAL_BNG_PROBLEM = sb.bng_problem
REAL_RUN = subprocess.run
#: profile folders whose names broke the conf when it named the cell:
#: non-ASCII, a '.con' segment (twice), a space
FOLDERS = ["José", "m.contreras", "j.con", "Jane Doe"]


@pytest.fixture
def import_probe(sandbox_root, monkeypatch):
    """sandbox_root with the real engine-import probe, nothing remembered."""
    monkeypatch.setattr(sb, "engine_import_problem", REAL_IMPORT_PROBLEM)
    monkeypatch.setattr(sb, "_ENGINE_PROBES", {})
    return sandbox_root


@pytest.fixture
def bng_probe(sandbox_root, monkeypatch):
    """sandbox_root with the real BNG2.pl checks, nothing remembered."""
    monkeypatch.setattr(sb, "bng_problem", REAL_BNG_PROBLEM)
    monkeypatch.setattr(sb, "_BNG_SELFTESTS", {})
    monkeypatch.delenv("FLUBNF_BNG", raising=False)
    return sandbox_root


@pytest.fixture
def bundle():
    """This platform's BioNetGen folder from the installed bionetgen;
    skipped when there is none, or no perl that can run it."""
    try:
        import bionetgen
    except ImportError:
        pytest.skip("bionetgen is not installed")
    p = Path(bionetgen.__file__).parent / settings.bng_platform_dirs()[0]
    if not (p / "BNG2.pl").is_file() or not settings.resolve_perl():
        pytest.skip("no BNG2.pl bundle for this platform, or no perl")
    return p


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ------------------------------------------------- pf.conf names no folder

@pytest.mark.parametrize("folder", FOLDERS)
def test_pf_conf_names_no_folder_under_any_profile_name(sandbox_root,
                                                        tmp_path, monkeypatch,
                                                        folder):
    box = tmp_path / folder / "AppData" / "Local" / "FluBNF" / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", box)
    monkeypatch.setattr(sb, "MODELS", box / "models")
    monkeypatch.setattr(sb, "RUNS", box / "runs")
    sb.add_example("kinetics_example")
    assert sb.machine_problem() == ""            # no folder name is refused
    w = sb.prepare("kinetics_example")
    conf = (w / "kinetics_example_r0" / "pf.conf").read_text(encoding="utf-8")
    assert conf.isascii() and folder not in conf and str(tmp_path) not in conf
    lines = conf.splitlines()
    assert lines[:2] == ["model = m.bngl : kin.exp", "output_dir = out"]
    # the engine finds BNG2.pl under the BNGPATH the run hands it
    assert not any(ln.startswith("bng_command") for ln in lines)


def _parsers() -> list:
    """(engine checkout, its Python) pairs whose parser can be run here."""
    raw = os.environ.get("FLUBNF_TEST_PARSERS", "").strip()
    pairs = (json.loads(raw) if raw
             else [[str(settings.PYBNF), str(settings.PY_ENGINE)]])
    return [(Path(c), Path(p)) for c, p in pairs
            if (Path(c) / "pybnf" / "parse.py").is_file() and Path(p).exists()]


#: parses each line on its own with the engine's ploop, as load_config
#: reads a conf: {"line": ["ok", what it read] | ["error", the message]}
_PARSE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from pybnf.parse import ploop
out = {}
for line in json.loads(sys.stdin.read()):
    try:
        got = ploop([line + "\n"])
        out[line] = ["ok", {k: sorted(v) if isinstance(v, (set, list)) else v
                            for k, v in got.items()}]
    except Exception as e:
        out[line] = ["error", str(getattr(e, "message", None) or e)[:300]]
print(json.dumps(out))
"""


def test_the_engines_own_parser_reads_the_conf_under_every_folder(
        sandbox_root, tmp_path, monkeypatch):
    """The conf a run writes parses under each folder name with the
    engine's own grammar (the fork, and the public PR when it is given),
    and the conf the Sandbox wrote before, naming the cell, does not: the
    control that shows this test can tell them apart."""
    parsers = _parsers()
    if not parsers:
        pytest.skip("no engine parser here (set FLUBNF_TEST_PARSERS)")
    lines, old = [], []
    for folder in FOLDERS:
        box = tmp_path / folder / "sandbox"
        monkeypatch.setattr(sb, "MODELS", box / "models")
        monkeypatch.setattr(sb, "RUNS", box / "runs")
        sb.add_example("kinetics_example")
        cell = sb.prepare("kinetics_example") / "kinetics_example_r0"
        conf = (cell / "pf.conf").read_text(encoding="utf-8").splitlines()
        lines += [ln for ln in conf if ln.split("=")[0].strip()
                  in ("model", "output_dir")]
        # what prepare wrote at 7e8390a: the cell's absolute path
        old += [f"model = {cell}/m.bngl : {cell}/kin.exp",
                f"output_dir = {cell}/out"]
    lines = sorted(set(lines))
    assert lines == ["model = m.bngl : kin.exp", "output_dir = out"]
    for checkout, python in parsers:
        r = REAL_RUN([str(python), "-c", _PARSE, str(checkout)],
                     input=json.dumps(lines + old), capture_output=True,
                     text=True, encoding="utf-8", timeout=300)
        if r.returncode != 0:
            pytest.skip(f"the parser at {checkout} does not load with "
                        f"{python}: {r.stderr.strip()[-200:]}")
        said = json.loads(r.stdout)
        assert said["model = m.bngl : kin.exp"] == [
            "ok", {"exp_data": ["kin.exp"], "m.bngl": ["kin.exp"],
                   "models": ["m.bngl"]}], (checkout, said)
        ok, got = said["output_dir = out"]
        assert ok == "ok" and got["output_dir"] == "out", (checkout, said)
        for folder in FOLDERS:
            # every old pair has one line the grammar refuses
            pair = [ln for ln in old if f"{os.sep}{folder}{os.sep}" in ln]
            assert any(said[ln][0] == "error" for ln in pair), (
                checkout, folder, {ln: said[ln] for ln in pair})


def test_a_run_download_names_bng2pl_for_a_conf_without_one(tmp_path):
    cell = tmp_path / "Jane Doe" / "r" / "m_r0"
    new = "model = m.bngl : kin.exp\noutput_dir = out\npf_particles = 200\n"
    from app.core import sandbox_export as se
    assert se._relative_conf(new, cell).splitlines()[:3] == [
        "bng_command = BNG2.pl", "model = m.bngl : kin.exp", "output_dir = out"]
    # a run made before keeps its own line, its paths made relative
    old = (f"bng_command = /x/BNG2.pl\nmodel = {cell}/m.bngl : {cell}/kin.exp\n"
           f"output_dir = {cell}/out\n")
    assert se._relative_conf(old, cell) == (
        "bng_command = BNG2.pl\nmodel = m.bngl : kin.exp\noutput_dir = out\n")


# --------------------------------------- the engine's Python, as it loads

def test_a_bare_venv_names_the_missing_import(import_probe, tmp_path,
                                              monkeypatch):
    """A venv whose pip install never ran (a dropped connection, a window
    closed during pip): at 7e8390a the page said nothing, and every cell
    failed on "No module named ..."."""
    root = tmp_path / "bare-engine"
    venv.create(root, with_pip=False)
    monkeypatch.setattr(pf, "PY310", _venv_python(root))
    sb.add_example("kinetics_example")
    assert sb.engine_import_problem(wait=60)        # let the probe finish
    notice, tip = sb.split_reason(sb.machine_problem())
    assert notice == ("The engine's Python cannot load the engine "
                      "(ModuleNotFoundError: No module named 'bngsim'), so "
                      "no fit can start.")
    assert str(pf.PY310) in tip and "tries again" in tip
    with pytest.raises(sb.SandboxError, match="No module named 'bngsim'"):
        sb.prepare("kinetics_example")
    assert not any((sb.RUNS).iterdir())
    # Check says it beside the model, not as one of the model's problems
    r = sb.check(sb.read_model("kinetics_example"))
    assert r["facts"]["machine"] == notice and r["problems"] == []


def test_the_probe_refuses_only_once_it_finished_and_is_cached(import_probe,
                                                               monkeypatch):
    calls, release = [], threading.Event()

    def probe(cmd, **kw):
        calls.append(cmd)
        release.wait(10)
        return types.SimpleNamespace(
            returncode=1, stdout="",
            stderr="Traceback ...\nImportError: DLL load failed while "
                   "importing _roadrunner\n")
    monkeypatch.setattr(sb, "_probe_run", probe)
    # still running: nothing is said, the page does not wait for it
    assert sb.engine_import_problem(wait=0.05) == ""
    release.set()
    said = sb.engine_import_problem(wait=10)
    assert said.startswith("The engine's Python cannot load the engine "
                           "(ImportError: DLL load failed while importing "
                           "_roadrunner)")
    assert sb.engine_import_problem() == said and len(calls) == 1
    # a pip install touches the venv, so the key changes: asked again
    monkeypatch.setattr(sb, "_engine_probe_key",
                        lambda: ("py", "fork", ("touched",)))
    sb.engine_import_problem(wait=10)
    assert len(calls) == 2


def test_a_probe_that_times_out_never_refuses_and_is_asked_again(
        import_probe, monkeypatch):
    calls = []

    def slow(cmd, **kw):
        calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(sb, "_probe_run", slow)
    assert sb.engine_import_problem(wait=10) == ""
    assert sb.engine_import_problem(wait=10) == "" and len(calls) == 2
    assert sb.machine_problem() == ""
    # a finished success says nothing either
    monkeypatch.setattr(sb, "_probe_run", lambda cmd, **kw: types.SimpleNamespace(
        returncode=0, stdout="0.15.1\n", stderr=""))
    assert sb.engine_import_problem(wait=10) == ""


def test_without_msvcp140_the_visual_cpp_runtime_is_named():
    said = "ImportError: DLL load failed while importing _bngsim"
    msg = sb.engine_import_message(said, _platform="win32", _vc_missing=True)
    notice, tip = sb.split_reason(msg)
    assert said in notice
    assert "Microsoft Visual C++ runtime" in msg and "msvcp140.dll" in msg
    assert "https://aka.ms/vs/17/release/vc_redist.x64.exe" in tip
    msg = sb.engine_import_message(said, _platform="win32", _vc_missing=False)
    assert "Visual C++" not in msg
    assert "open FluBNF.bat again" in msg
    assert "Engine setup did not finish" in msg
    # never on macOS or Linux
    assert "Visual C++" not in sb.engine_import_message(
        said, _platform="darwin", _vc_missing=True)


def test_engine_messages_tell_a_failed_install_from_no_engine_file(
        sandbox_root, monkeypatch):
    monkeypatch.setattr(pf, "PY310", Path("/nonexistent/bin/python"))
    on_disk = sb.engine_python_missing_message("win32")
    assert on_disk.startswith("The engine's Python is missing")
    assert f"The engine is unpacked at {pf.PYBNF_PF}" in on_disk
    assert "Engine setup did not finish" in on_disk
    assert "Downloads" not in on_disk
    # with no engine file, that file's own message is the one that names
    # it (test_the_checks_run_in_the_order_a_student_fixes_them)
    assert "Downloads" in pf.engine_missing_message("win32")


def test_a_run_that_dies_loading_the_engine_says_how_to_finish(sandbox_root,
                                                               monkeypatch):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    monkeypatch.setattr(pf, "execute", lambda root, width=1, env=None: {
        "kinetics_example_r0": "FAIL: No module named 'numpy'"})
    meta = sb.run(w)
    assert meta["error"].startswith("FAIL: No module named 'numpy'\n\n")
    assert ("The engine's Python cannot load the engine (No module named "
            "'numpy')") in meta["error"]
    # an engine refusal of the model is left as the engine said it
    said = "FAIL: \"'Cobs' is not an observable of the model\""
    monkeypatch.setattr(pf, "execute", lambda root, width=1, env=None: {
        "kinetics_example_r0": said})
    assert sb.run(sb.prepare("kinetics_example"))["error"] == said


# ------------------------------------------------------- BNG2.pl itself

def test_a_missing_bng2pl_is_refused_and_named(bng_probe, tmp_path,
                                               monkeypatch):
    gone = tmp_path / "nowhere" / "BNG2.pl"
    monkeypatch.setattr(sb, "BNG", str(gone))
    sb.add_example("kinetics_example")
    notice, tip = sb.split_reason(sb.machine_problem())
    assert notice == (f"BioNetGen's BNG2.pl is not at {gone}, so no fit can "
                      "start: every run generates its network with it.")
    assert "pip install bionetgen" in tip
    with pytest.raises(sb.SandboxError, match="BNG2.pl is not at"):
        sb.prepare("kinetics_example")
    r = sb.check(sb.read_model("kinetics_example"))
    assert r["facts"]["machine"] == notice
    assert r["facts"]["network"] == "not checked (BNG2.pl not found)"
    # FLUBNF_BNG decides the path, so it is what the remedy names
    monkeypatch.setenv("FLUBNF_BNG", str(gone))
    assert "FLUBNF_BNG names that path" in sb.machine_problem()
    # Windows: the launcher, or the console's own pip
    monkeypatch.delenv("FLUBNF_BNG")
    win = pf.bng_missing_message(gone, "win32")
    assert "open FluBNF.bat again" in win
    assert f'"{sys.executable}" -m pip install bionetgen' in win


def test_a_bng2pl_without_its_modules_fails_the_self_test_and_check_says_machine(
        bng_probe, bundle, tmp_path, monkeypatch):
    """BNG2.pl copied without Perl2 (a damaged install) dies at compile
    time, before the banner: the self-test refuses, and Check files it
    as this computer's problem, not one of the model's."""
    copy = tmp_path / "bng-copy"
    copy.mkdir()
    shutil.copy(bundle / "BNG2.pl", copy / "BNG2.pl")
    monkeypatch.setattr(sb, "BNG", str(copy / "BNG2.pl"))
    monkeypatch.setattr(cm, "BNG", str(copy / "BNG2.pl"))
    monkeypatch.setattr(subprocess, "run", REAL_RUN)    # the real BNG2.pl
    said = sb.bng_selftest()
    assert said.startswith("Can't locate BNGUtils.pm")
    notice, tip = sb.split_reason(sb.machine_problem())
    assert notice == ("BioNetGen's BNG2.pl does not start on this computer, "
                      "so no network can be generated and no fit can start.")
    assert "This is the computer, not the model." in tip
    assert "Perl said: Can't locate BNGUtils.pm" in tip
    assert "--force-reinstall --no-deps bionetgen" in tip
    files = {n: (EXAMPLE / n).read_text() for n in sb.REQUIRED}
    r = sb.check(files, work=tmp_path / "check")
    assert r["ok"] and r["problems"] == []
    assert r["facts"]["machine"] == notice
    assert r["facts"]["network"] == "not checked (BNG2.pl does not start here)"
    # with no self-test to go by, Check's own run is read by its banner
    monkeypatch.setattr(sb, "bng_problem", lambda: "")
    r = sb.check(files, work=tmp_path / "check")
    assert r["ok"] and r["problems"] == []
    assert r["facts"]["network"] == "not checked (BNG2.pl did not start)"
    assert r["facts"]["machine"] == notice
    assert "Can't locate BNGUtils.pm" in r["facts"]["machine_tip"]
    # and a run's own network generation says the same
    cell = tmp_path / "cell"
    cell.mkdir()
    shutil.copy(EXAMPLE / "model.bngl", cell / "m.bngl")
    with pytest.raises(sb.SandboxError) as e:
        sb._netgen(cell)
    assert sb.split_reason(str(e.value))[0] == notice


def test_the_installed_bng2pl_passes_the_self_test_once(bng_probe, bundle,
                                                       monkeypatch):
    monkeypatch.setattr(sb, "BNG", str(bundle / "BNG2.pl"))
    calls = []
    real = sb._probe_run

    def counted(cmd, **kw):
        calls.append(cmd)
        return real(cmd, **kw)
    monkeypatch.setattr(sb, "_probe_run", counted)
    assert sb.bng_selftest() == "" and sb.bng_problem() == ""
    assert sb.bng_selftest() == "" and len(calls) == 1
    assert calls[0][-1] == "-v"


def test_a_self_test_that_times_out_says_nothing(bng_probe, tmp_path,
                                                 monkeypatch):
    stub = tmp_path / "BNG2.pl"
    stub.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(stub))

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(sb, "_probe_run", slow)
    assert sb.bng_selftest() == "" and sb._BNG_SELFTESTS == {}


def test_check_keeps_a_model_failure_after_the_banner_as_the_models(
        sandbox_root, tmp_path, monkeypatch):
    stub = tmp_path / "BNG2.pl"
    stub.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(stub))
    out = "BioNetGen version 2.9.3\n" + "Read 3 parameters.\n" * 40

    def fails(cmd, **kw):
        return types.SimpleNamespace(stdout=out, returncode=1,
                                     stderr="ABORT: Molecule Q not defined\n")
    monkeypatch.setattr(cm.subprocess, "run", fails)
    files = {n: (EXAMPLE / n).read_text() for n in sb.REQUIRED}
    r = sb.check(files, work=tmp_path / "check")
    assert r["facts"]["network"] == "fails" and r["facts"]["machine"] == ""
    assert r["problems"][0].startswith("BNG2.pl could not generate the "
                                       "network:\nABORT: Molecule Q")
    # the banner is kept although the tail cut it: the run reached the model
    assert pf.bng_started(r["problems"][0])


# ------------------------------------------------- everything, in order

def test_perl_and_the_engine_both_missing_are_both_named(sandbox_root,
                                                         monkeypatch):
    """At 7e8390a only Perl was named, and the engine came up after
    Perl was installed and the console restarted."""
    monkeypatch.setattr(pf, "perl_available", lambda: False)
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    msg = sb.machine_problem()
    notice, tip = sb.split_reason(msg)
    assert notice.startswith(f"The PyBNF fork at {pf.PYBNF_PF} does not "
                             "provide fit_type = pf")
    assert "1 more thing to fix after that: (2) Perl was not found" in tip
    r = sb.check({n: (EXAMPLE / n).read_text() for n in sb.REQUIRED})
    assert r["facts"]["machine"] == notice
    assert "Perl was not found" in r["facts"]["machine_tip"]
    sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    assert str(e.value) == msg


def test_the_checks_run_in_the_order_a_student_fixes_them(bng_probe, tmp_path,
                                                          monkeypatch):
    """With no engine file the engine's Python is not counted: installing
    the file is what makes it, and its "open FluBNF.bat again, or point
    FLUBNF_PY_ENGINE at it" was a dead end listed as one more thing."""
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    monkeypatch.setattr(pf, "PY310", Path("/nonexistent/bin/python"))
    monkeypatch.setattr(pf, "perl_available", lambda: False)
    monkeypatch.setattr(sb, "BNG", str(tmp_path / "gone" / "BNG2.pl"))
    msg = sb.machine_problem()
    at = [msg.index(s) for s in ("does not provide fit_type = pf",
                                 "(2) Perl was not found",
                                 "(3) BioNetGen's BNG2.pl is not at")]
    assert at == sorted(at)
    assert "2 more things to fix after that" in msg
    assert "The engine's Python is missing" not in msg
    # every one named, and the tip still holds the last remedy whole
    _, tip = sb.split_reason(msg)
    last = pf.bng_missing_message(sb.BNG)
    assert tip.endswith(last[last.index("To fix it, "):])
    # an engine there but older than the console, whose Python is gone: the
    # Python comes second, with the retry, not the engine file
    monkeypatch.setattr(pf, "engine_available", lambda: True)
    monkeypatch.setattr(pf, "engine_current", lambda: False)
    msg = sb.machine_problem()
    at = [msg.index(s) for s in ("is older than this console",
                                 "(2) The engine's Python is missing",
                                 "(3) Perl was not found",
                                 "(4) BioNetGen's BNG2.pl is not at")]
    assert at == sorted(at)
    assert "3 more things to fix after that" in msg
    assert "its Python environment was never made" in msg


# ---------------------------------------- where the engine's Python is

def test_on_windows_the_engine_python_is_the_launchers_venv(monkeypatch):
    monkeypatch.delenv("FLUBNF_ENGINE_VENV", raising=False)
    win = settings._engine_python_candidates(windows=True)
    assert win == ("~/.venvs/flubnf-engine/Scripts/python.exe",
                   "~/.venvs/flubnf/Scripts/python.exe")
    monkeypatch.setenv("FLUBNF_ENGINE_VENV", "D:\\venvs\\flubnf-engine\\")
    assert settings._engine_python_candidates(windows=True)[0] == \
        "D:\\venvs\\flubnf-engine/Scripts/python.exe"
    # macOS and Linux look where they always did
    assert settings._engine_python_candidates(windows=False) == (
        "~/.venvs/flubnf/bin/python", "~/.venvs/flubnf-engine/bin/python",
        "~/.venvs/flubnf/Scripts/python.exe",
        "~/.venvs/flubnf-engine/Scripts/python.exe")


def test_on_windows_the_bng2pl_named_when_none_exists_is_one_that_can(
        monkeypatch):
    first = next(settings._bng_candidates("win32")).replace("\\", "/")
    assert "/.venv/Lib/site-packages/bionetgen/bng-win/BNG2.pl" in first
    first = next(settings._bng_candidates("linux")).replace("\\", "/")
    assert "/.venv/lib/python3." in first and "/bng-linux/" in first
