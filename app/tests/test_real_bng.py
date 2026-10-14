"""The real BioNetGen: BNG2.pl from the installed bionetgen (bng-win on
Windows, bng-linux elsewhere), started by the perl the console resolves,
on every shipped example and under the folder names and leftovers that
stopped it on students' machines. Every other test fakes BNG2.pl or
stands in for its folder; these start it, and run_network behind it.

Skipped unless FLUBNF_BNG_REAL=1, which CI sets in steps of their own
(.github/workflows/tests.yml): on Windows under pwsh, because Git Bash
puts Git's MSYS perl first on PATH, and that is one of the cases here,
not the machine a student has. With the variable set, a missing
bionetgen or perl fails the module instead of skipping it.

Each case asks what a student's first Check and first run ask: `BNG2.pl
-v` starts (the preflight's self-test), the run's network generation
(sandbox._netgen) writes m.net, and Check (sandbox_check.check) says the
network generates and fills "Model gives" (facts["at_start"]), which only
run_network's ODE run of the model can. CI has no engine, so Check's
machine notice always names it; these tests read the network and the
model's problems, never that notice. A case still expected to fail is
xfail(strict=True): the change that makes it pass has to remove the mark.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from flubnf import settings                              # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("FLUBNF_BNG_REAL") != "1",
    reason="starts the real BNG2.pl: set FLUBNF_BNG_REAL=1")

EXAMPLES = sb.list_examples()
#: the example the folder and environment cases run: a first fit's model
FIRST = "sir_example"
WINDOWS = sys.platform == "win32"

#: profile folder names that stopped BNG2.pl or the engine: a space, an
#: apostrophe (Cygwin's run_network reads it as a quote), letters outside
#: the ANSI code page, a letter inside it, and a '.con' the engine's
#: model line split on
FOLDERS = [
    pytest.param("Jane Doe", id="jane-doe"),
    pytest.param("O'Brien", id="obrien"),
    pytest.param("\u0141ukasz \u674e", id="lukasz-li"),
    pytest.param("Jos\u00e9", id="jose"),
    pytest.param("m.contreras", id="m.contreras"),
]


@pytest.fixture(scope="module")
def bundle():
    """This platform's BioNetGen folder from the installed bionetgen."""
    try:
        import bionetgen
    except ImportError:
        pytest.fail("FLUBNF_BNG_REAL=1, but bionetgen is not installed")
    p = Path(bionetgen.__file__).parent / settings.bng_platform_dirs()[0]
    if not (p / "BNG2.pl").is_file():
        pytest.fail(f"FLUBNF_BNG_REAL=1, but {p} holds no BNG2.pl")
    return p


def _place(monkeypatch, repo: Path, bng: Path) -> None:
    """The Sandbox under `repo`, and BNG2.pl at `bng` for every run the
    Sandbox, Check and the contact map start."""
    monkeypatch.setattr(sb, "SANDBOX", repo / "sandbox")
    monkeypatch.setattr(sb, "MODELS", repo / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", repo / "sandbox" / "runs")
    monkeypatch.setattr(sb, "BNG", str(bng))
    monkeypatch.setattr(cm, "BNG", str(bng))


@pytest.fixture(autouse=True)
def machine(bundle, tmp_path, monkeypatch):
    """The installed BNG2.pl and a Sandbox in tmp_path, with no BNGPATH
    and no self-test remembered from another test. PATH is restored after
    (the Windows search puts the perl it finds first). The engine's own
    import is not asked: CI has no engine, and these runs never start it."""
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.delenv("BNGPATH", raising=False)
    monkeypatch.setattr(sb, "_BNG_SELFTESTS", {})
    monkeypatch.setattr(sb, "engine_import_problem", lambda wait=0: "")
    _place(monkeypatch, tmp_path, bundle / "BNG2.pl")
    if not settings.resolve_perl():
        pytest.fail("FLUBNF_BNG_REAL=1, but no perl here can run BNG2.pl")
    return tmp_path


def _student(monkeypatch, home: Path, bundle: Path) -> Path:
    """FluBNF as it sits under a profile folder: BioNetGen's whole folder
    (BNG2.pl finds Perl2 and bin beside it) copied where the console's
    .venv keeps it, and the Sandbox beside it."""
    repo = home / "FluBNF"
    bng = repo / "bionetgen" / bundle.name
    shutil.copytree(bundle, bng)
    _place(monkeypatch, repo, bng / "BNG2.pl")
    return repo


def _self_test() -> subprocess.CompletedProcess:
    """`perl BNG2.pl -v` with the perl, path and environment every
    BNG2.pl run here uses, as the preflight's self-test runs it."""
    return subprocess.run(
        [settings.resolve_perl(), pf.perl_path(sb.BNG) or str(sb.BNG), "-v"],
        capture_output=True, timeout=120,
        **pf.bng_run_kwargs(settings.bng_env(sb.BNG)))


def _runs_and_checks(example: str) -> None:
    """BNG2.pl starts, a run's network generation writes m.net, and Check
    generates the network and fills "Model gives" with no problem."""
    r = _self_test()
    assert r.returncode == 0 and pf.bng_started(r.stdout), \
        pf.bng_failure_text(r)
    assert sb.bng_problem() == ""
    cell = sb.RUNS / f"{example}_r0"
    cell.mkdir(parents=True)
    shutil.copy(sb.EXAMPLES / example / "model.bngl", cell / "m.bngl")
    sb._netgen(cell)
    net = (cell / "m.net").read_text(encoding="utf-8", errors="replace")
    assert "begin species" in net and "begin reactions" in net
    files = {n: (sb.EXAMPLES / example / n).read_text(encoding="utf-8")
             for n in sb.REQUIRED}
    res = sb.check(files, work=sb.SANDBOX / "check")
    f = res["facts"]
    assert f["network"] == "generates", (f["network"], res["problems"],
                                         f["machine"], f["machine_tip"])
    assert f["species"] > 0 and f["reactions"] > 0
    # filled only from run_network's ODE run of the model as written
    assert f["at_start"] and not f["at_start"].startswith("not compared"), \
        f["at_start"]
    assert res["problems"] == []


def test_the_shipped_examples_are_the_ones_tested():
    assert FIRST in EXAMPLES and len(EXAMPLES) >= 5, EXAMPLES


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_shipped_example_generates_and_simulates(example):
    _runs_and_checks(example)


@pytest.mark.parametrize("name", FOLDERS)
def test_a_profile_folder_name(name, bundle, tmp_path, monkeypatch):
    """Windows Perl reads its arguments and its environment in the ANSI
    code page, so for letters outside it BNG2.pl's path and BNGPATH are
    given in their 8.3 form. A drive that makes no 8.3 names has no form
    Perl can read: there the preflight must say to move the folder, not
    let BNG2.pl fail with a remedy that cannot work."""
    _student(monkeypatch, tmp_path / name, bundle)
    if pf.perl_path(sb.BNG) is None:
        # after the engine's notice: CI has no engine
        said = sb.machine_problem()
        assert "Perl cannot read the name of the folder FluBNF is in." in said
        pytest.skip("this drive makes no 8.3 names; the preflight refuses "
                    "the folder, as asserted")
    _runs_and_checks(FIRST)


def test_a_stale_bngpath_from_an_earlier_bionetgen(tmp_path, monkeypatch):
    """PyBNF's Windows docs say `setx BNGPATH ...`: a folder since deleted
    killed every BNG2.pl run at compile time until bng_env pinned it."""
    monkeypatch.setenv("BNGPATH", str(tmp_path / "BioNetGen-2.5.1"))
    _runs_and_checks(FIRST)


@pytest.mark.skipif(not WINDOWS, reason="Git for Windows' Unix tools")
def test_gits_unix_tools_first_on_path(monkeypatch):
    """Git installed with its Unix tools on the Command Prompt's PATH puts
    an MSYS perl ($^O msys) first, which cannot load BNG2.pl's modules: the
    console passes it over for a Windows perl."""
    git = (Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Git"
           / "usr" / "bin")
    if not (git / "perl.exe").is_file():
        pytest.skip(f"no Git for Windows perl in {git}")
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    monkeypatch.setenv("PATH", str(git) + os.pathsep + os.environ["PATH"])
    first = shutil.which("perl")
    assert first and Path(first).parent == git     # the case, as set up
    perl = settings.resolve_perl()
    assert perl and Path(perl).parent != git
    _runs_and_checks(FIRST)
