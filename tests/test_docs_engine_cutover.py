"""The docs that describe the engine switch, held to the code they describe.

The public engine (lanl/PyBNF, job_type = lwf) is the default and the
private engine (the lab's fork) the fallback, chosen only by name. These
tests pin what README.md, docs/ENGINE.md, docs/WINDOWS.md,
docs/LAUNCHERS.md, docs/INSTALL-STUDENTS.md, docs/FLUSIGHT-2026-27.md,
docs/ORACLE-SIHRS.md, docs/SANDBOX.md, docs/team/README.md and
scripts/README.md say about it, each against the script, workflow or
module it describes, so the two cannot drift apart unnoticed. Text only,
no launcher or installer is run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "docs/ENGINE.md", "docs/WINDOWS.md", "docs/LAUNCHERS.md",
        "docs/INSTALL-STUDENTS.md", "docs/FLUSIGHT-2026-27.md",
        "docs/ORACLE-SIHRS.md", "docs/SANDBOX.md", "docs/team/README.md",
        "scripts/README.md")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Prose is hard-wrapped, so a phrase may straddle a line break."""
    return " ".join(text.split())


def _heading_anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation other than
    hyphens dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _section(text: str, heading: str) -> str:
    """One section of a doc, up to the next heading of its level or above."""
    level = heading.split(" ", 1)[0]
    start = text.index(f"\n{heading}\n")
    stops = [text.find(f"\n{'#' * n} ", start + 1)
             for n in range(1, len(level) + 1)]
    stops = [s for s in stops if s > 0]
    return text[start:min(stops)] if stops else text[start:]


def _launchers_row(name: str) -> list[str]:
    """docs/LAUNCHERS.md's table row for `name`, as its cells."""
    for line in _read("docs/LAUNCHERS.md").splitlines():
        if line.startswith(f"| `{name}` |"):
            return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
    raise AssertionError(f"docs/LAUNCHERS.md has no row for {name}")


# ------------------------------------------------------------- links


def _anchors(text: str) -> set[str]:
    ids = set(re.findall(r'<a id="([^"]+)"></a>', text))
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        m = re.match(r"(#{1,6}) (.+)", line)
        if m and not fenced:
            ids.add(_heading_anchor(m.group(2)))
    return ids


@pytest.mark.parametrize("rel", DOCS)
def test_every_anchor_these_docs_link_to_exists(rel):
    """A link to a renamed heading lands at the top of the page with no
    word. The public engine's heading changed from "(opt-in)" to "(the
    default)": the old anchor is kept as an alias for links already sent,
    and every link in these docs reaches a heading or an alias."""
    text = _read(rel)
    here = (REPO / rel).parent
    bad = []
    for target, anchor in re.findall(r"\]\(([^)\s#]*)#([\w-]+)\)", text):
        if target.startswith(("http://", "https://")):
            continue
        doc = (here / target) if target else (REPO / rel)
        assert doc.is_file(), f"{rel} links to {target}, which is not there"
        if anchor not in _anchors(doc.read_text(encoding="utf-8")):
            bad.append(f"{target or rel}#{anchor}")
    assert not bad, f"{rel} links to anchors that do not exist: {bad}"


def test_scripts_readme_links_to_the_public_engine_by_its_new_name():
    text = _read("scripts/README.md")
    assert "#the-public-engine-opt-in" not in text
    assert "ENGINE.md#the-public-engine-the-default" in text


# ------------------------------------------- choosing the engine (ENGINE.md)


def test_the_engine_doc_says_the_runner_refuses_a_shell_that_names_the_other_engine(
        monkeypatch):
    """The shell's FLUBNF_ENGINE wins over the record for app, retro, doctor
    and experiment, but `flubnf runner` refuses that start, and the step
    the doc gives is the one the runner prints."""
    pytest.importorskip("app.core.runner")
    from app.core import runner
    from flubnf import settings
    section = _flat(_section(_read("docs/ENGINE.md"), "### Choosing the engine"))
    assert "A value the shell sets wins over the record, for that shell" not in section
    assert ("`flubnf runner` refuses to start when the shell's value names "
            "the other engine than the record") in section
    assert ("`flubnf app`, `retro`, `doctor` and `experiment` follow the "
            "shell's value") in section
    assert ("The launchers (`FluBNF.command`, `FluBNF.app`, `FluBNF.bat`) "
            "follow the record over the shell") in section
    # the runner's own refusal, on each platform, names the step quoted
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setattr(runner, "_recorded_engine", lambda: "private")
    settings.forget_record()
    for windows, step in ((False, "`. ./.flubnf.env`"),
                          (True, "`call .flubnf.env.cmd`")):
        monkeypatch.setattr(settings, "_windows", lambda w=windows: w)
        said = runner._engine_record_problem()
        assert said and step.strip("`") in said, said
        assert step in section, step
    settings.forget_record()


def test_the_windows_switch_is_described_as_the_fixed_setup_ps1_runs_it():
    """setup.ps1 -Engine records the choice before its first pip install,
    and -Engine private stops there (no pip, no network) only when the
    private engine loads and the console's .venv is made; otherwise the
    whole setup follows. The docs say that, not "seconds, no network" for
    every Windows switch."""
    ps1 = _read("setup.ps1").replace("\r\n", "\n")
    record = ps1.index("Set-EnvCmdLines ([ordered]@{ FLUBNF_ENGINE = $Engine })")
    first_pip = ps1.index('@("-m", "pip", "install"')
    assert record < first_pip, "-Engine is no longer recorded before pip runs"
    fast = ps1[ps1.index('if ($Engine -eq "private") {'):]
    fast = fast[:fast.index("\n}\n")]
    assert "Test-Path -LiteralPath $VenvPy" in fast
    assert "Nothing was installed and nothing was fetched." in fast
    assert "exit 0" in fast
    engine = _flat(_section(_read("docs/ENGINE.md"), "### Choosing the engine"))
    assert ("first, before it installs or fetches anything, so a run that "
            "stops early (no network, say) still switches the copy") in engine
    assert ("stops there only on a copy whose console environment (`.venv`) "
            "is already made. Otherwise it goes on with the whole setup, "
            "which takes minutes and the network") in engine
    windows = _flat(_read("docs/WINDOWS.md"))
    assert "It says `Nothing was installed and nothing was fetched.`" in windows
    assert "Otherwise the whole setup follows, which takes minutes and the network" in windows
    flusight = _flat(_read("docs/FLUSIGHT-2026-27.md"))
    assert ("seconds, no network (on Windows, once the console's `.venv` is "
            "made)") in flusight
    assert "With the private engine installed, this takes seconds and needs no network." not in flusight
    guide = _flat(_read("docs/INSTALL-STUDENTS.md"))
    assert ("Either way the line records the choice first, so it holds even "
            "when the rest cannot finish") in guide
    row = _flat(" ".join(_launchers_row("setup.ps1")))
    assert "first, before anything is installed or fetched" in row
    assert "already loads and `.venv` is made" in row


def test_the_launchers_are_said_to_check_the_public_engine_only_on_a_copy_that_runs_it():
    """A copy switched to the private engine checks that one on open, not
    the public one: "on every open" holds only for the copies on the
    default."""
    engine = _flat(_read("docs/ENGINE.md"))
    assert ("On a copy that runs the public engine (every copy not switched "
            "to the private one), the launchers") in engine
    windows = _flat(_read("docs/WINDOWS.md"))
    assert ("On a copy that runs it (every copy not switched to the private "
            "engine), `FluBNF.bat` checks it on every open") in windows
    assert ("On a copy that runs it, every open compares its environment "
            "with `engine-requirements.txt`") in windows


def test_the_engine_doc_says_how_seasons_without_a_readable_build_resume():
    """A season recorded before builds were recorded was the private
    engine's: refused on the public one, resumed on the private one. A
    season whose build could not be read records its engine alone and is
    refused on the other engine."""
    pytest.importorskip("app.core.retro_settings")
    from app.core.retro_settings import engine_build_change
    public = {"engine": "public", "commit": "8410f794" * 5, "dirty": False}
    private = {"commit": "2fdadee0" * 5, "dirty": False}
    old = {"locations": ["AK"]}                  # no engine_build at all
    assert engine_build_change(old, "pf", public)
    assert engine_build_change(old, "pf", private) is None
    unread = {"engine_build": {"engine": "public"}}
    assert engine_build_change(unread, "pf", private)
    assert engine_build_change(unread, "pf", public) is None
    flat = _flat(_read("docs/ENGINE.md"))
    assert "Seasons from before builds were recorded resume as before." not in flat
    assert ("A season from before builds were recorded was fitted by the "
            "private engine: it resumes there as before, and is refused on "
            "the public one.") in flat
    assert ("A season whose build could not be read when it began records "
            "its engine alone, and resumes only on that engine.") in flat


def test_the_private_switch_is_said_to_replace_a_waiting_archive():
    """--private on macOS and Linux stops when the private engine works,
    unless a different archive is waiting for the unpacked copy: then it
    installs that (the fix text sends users there for exactly that)."""
    sh = _read("setup_engine.sh")
    branch = sh[sh.index("# --private: the choice is recorded first"):]
    branch = branch[:branch.index("\nfi\n")]
    assert "replacing_archive" in branch, "--private no longer checks for a waiting archive"
    flat = _flat(_read("docs/ENGINE.md"))
    assert ("When a different engine archive is waiting for an unpacked "
            "private engine (below), it installs that in its place instead "
            "of stopping.") in flat
    assert "in that copy's place, even when the copy on disk works" in flat
    assert ("`./setup_engine.sh --private` tries the engine environment and "
            "checkout this copy records first, then the default ones") in flat
    row = _flat(" ".join(_launchers_row("setup_engine.sh")))
    assert "first the venv and checkout the copy records, then the defaults" in row
    assert ("when a different engine archive is waiting for an unpacked "
            "copy, it installs that in its place instead of stopping") in row


def test_a_conda_that_cannot_make_python_is_said_to_be_retried():
    """Exit 3 (stamped: no retry on every open) is only for no Python 3.12
    and no conda; a conda whose create fails is exit 1, tried again."""
    sh = _read("setup_engine.sh")
    head = _flat(sh[:sh.index("set -u")].replace("\n#", "\n"))
    assert "no conda to make one" in head
    row = _flat(" ".join(_launchers_row("setup_engine.sh")))
    assert "no Python 3.12 found and no conda to make one" in row
    assert "a conda that cannot make one exits 1" in row
    stamp = _flat(_read("docs/LAUNCHERS.md"))
    assert "a network, pip or conda failure (exit 1) writes nothing" in stamp
    guide = _flat(_read("docs/INSTALL-STUDENTS.md"))
    assert ("no Python 3.12 and no Anaconda to make one, an Intel Mac below "
            "macOS 15") in guide
    assert ("When Anaconda is there but could not make a Python 3.12, that is "
            "usually the network, and the next open tries again.") in guide


def test_the_plain_install_line_is_said_to_keep_a_private_record():
    """install.sh with FLUBNF_ENGINE unset reads an existing copy's record
    and keeps the private engine; the docs say so."""
    src = _read("install.sh")
    assert '"$DEST/.flubnf.env"' in src
    row = _flat(" ".join(_launchers_row("install.sh")))
    assert ("whose `.flubnf.env` records the private engine keeps it "
            "(`setup_engine.sh --private`, said in one line)") in row
    flat = _flat(_read("docs/ENGINE.md"))
    assert ("Pasted again on a copy that records the private engine, the "
            "plain line keeps it and says so") in flat


# ------------------------------------------------- LAUNCHERS.md, by script


def test_the_unknown_value_row_names_who_refuses_and_who_goes_on():
    """install.sh, reinstall.sh and a plain setup_engine.sh stop on a
    FLUBNF_ENGINE that names no engine (exit 2); setup.sh and setup.ps1
    only say so and go on with the public engine."""
    row = _flat(" ".join(_launchers_row("FLUBNF_ENGINE")))
    assert "the installers refuse it (exit 2)" not in row
    assert ("`install.sh`, `reinstall.sh` and `setup_engine.sh` with no "
            "option refuse it (exit 2) and install nothing") in row
    assert ("`setup.sh` and `setup.ps1` say so in one line and go on with "
            "the public engine") in row
    for script in ("install.sh", "reinstall.sh", "setup_engine.sh"):
        src = _read(script)
        at = src.index("it must be private or public")
        assert "exit 2" in src[at:at + 300], script
    sh = _read("setup.sh")
    at = sh.index("which is neither private nor public")
    line = sh[at:sh.index("\n", at)]
    assert "exit" not in line, line
    ps1 = _read("setup.ps1")
    assert "$EngineRouteBad = $EngineRoute" in ps1
    engine = _flat(_read("docs/ENGINE.md"))
    assert ("The installers (`setup_engine.sh` with no option, `install.sh`, "
            "`reinstall.sh`) refuse such a value") in engine


_CALL = re.compile(r"^\s*(?:if\s+|\(\s*cd\s+\S+\s+&&\s+|\S+=\"?\$\()?"
                   r"(?:[A-Z_]+=(?:\"[^\"]*\"|\S+)\s+)*\./setup_engine\.sh\b")


def test_setup_engine_is_said_to_be_called_by_every_script_that_runs_it():
    """The "Called by" cell lists each script that runs setup_engine.sh
    (install.sh among them), and nothing that does not."""
    callers = set()
    for script in ("install.sh", "reinstall.sh", "setup.sh", "FluBNF.command",
                   "SetupEngine.command"):
        for line in _read(script).splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "echo", "warn", "say", "ok")):
                continue
            if _CALL.search(line):
                callers.add(script)
    assert callers == {"install.sh", "reinstall.sh", "FluBNF.command",
                       "SetupEngine.command"}, callers
    called_by = _launchers_row("setup_engine.sh")[3]
    named = set(re.findall(r"`([^`]+)`", called_by))
    assert callers <= named, (callers - named, called_by)


def test_setup_engine_command_is_said_to_take_the_shell_value_first():
    """SetupEngine.command reads this shell's FLUBNF_ENGINE before the
    record, as setup_engine.sh does; the row says so."""
    src = _read("SetupEngine.command")
    assert src.index('RAW="${FLUBNF_ENGINE:-}"') < src.index(". ./.flubnf.env")
    row = _flat(_launchers_row("SetupEngine.command")[2])
    assert ("on the route `FLUBNF_ENGINE` names in its shell when that is "
            "set, else the one the copy records, else public") in row
    assert "on the route the copy records:" not in row


# ------------------------------------------------- what the windows show


def test_the_student_guide_quotes_the_header_setup_engine_prints():
    m = re.search(r'say "(public PyBNF \(the Liu-West filter[^"]*)"',
                  _read("setup_engine.sh"))
    assert m, "setup_engine.sh no longer prints the public engine's header"
    assert f"== {m.group(1)} ==" in _read("docs/INSTALL-STUDENTS.md")


def test_the_windows_python_advice_matches_what_the_engine_needs():
    """3.11 runs the console; the engine needs 64-bit (x64) 3.12, as
    FluBNF.bat says when it finds no Python for the engine."""
    bat = _read("FluBNF.bat").replace("\r\n", "\n")
    said = _flat(" ".join(line[5:] for line in bat.splitlines()
                          if line.startswith("echo ")))
    assert "3.11 runs the console, but the engine needs 3.12." in said
    step = _flat(_read("docs/WINDOWS.md").split("\n2. Git from", 1)[0])
    step = step[step.index("1. A Python."):]
    assert "3.11 or newer from https://www.python.org/downloads/ works too" not in step
    assert "install 64-bit (x64) Python 3.12 from https://www.python.org/downloads/" in step
    assert ("3.11 runs the console, but the particle-filter engine needs "
            "64-bit (x64) 3.12") in step


def _bat_said() -> list[str]:
    """What FluBNF.bat echoes, one line each, its leading spaces kept."""
    bat = _read("FluBNF.bat").replace("\r\n", "\n")
    return [m.group(1) for m in re.finditer(r"^(?:if [^\n]*?)?echo (.*)$", bat,
                                            re.M)]


def test_the_windows_doc_quotes_the_switch_line_the_launcher_prints():
    """After a failed public install FluBNF.bat names the fallback and
    prints the whole command to type (setup.ps1 alone opens in an editor
    in Command Prompt and is refused in PowerShell); the doc quotes it,
    with the folder FluBNF.bat puts in it, and says which of the three
    fallback lines comes when."""
    said = _bat_said()
    full = ('    powershell -NoProfile -ExecutionPolicy Bypass -File '
            '"%~dp0setup.ps1" -Engine {}')
    assert "  To switch, type this in Command Prompt or PowerShell:" in said
    assert full.format("private") in said
    assert full.format("public") in said
    section = _section(_read("docs/WINDOWS.md"), "### If the install fails")
    assert "  To switch, type this in Command Prompt or PowerShell:" in section
    assert full.format("private").replace("%~dp0", "<FluBNF folder>\\") in section
    assert "the same line with `-Engine public`" in _flat(section)
    flat = " ".join(said)
    assert "is on this PC but not installed yet" in flat
    assert ("when the private engine's folder is on the PC but not installed "
            "yet, that the next open installs it from there") in _flat(section)


# ---------------------------------------------------- CI, as the doc says


def _ci_bullet() -> str:
    doc = _read("docs/WINDOWS.md")
    bullet = doc[doc.index("- **Windows CI is required.**"):]
    return _flat(bullet[:bullet.index("\n- **", 1)])


def test_the_ci_bullet_says_which_engine_each_setup_run_records():
    """windows-setup-script: each run's -Engine, as the workflow gives it,
    and still five runs."""
    wf = _read(".github/workflows/tests.yml")
    runs = {}
    for m in re.finditer(r'- name: "run (\d) of 5: [^"]*"\n(.*?)(?=\n      - name:)',
                         wf, re.S):
        engine = re.search(r"setup\.ps1[^\n]*?-Engine (\w+)", m.group(2))
        runs[int(m.group(1))] = engine.group(1) if engine else None
    assert sorted(runs) == [1, 2, 3, 4, 5], runs
    bullet = _ci_bullet()
    assert "runs it five times" in bullet
    for n, engine in runs.items():
        if engine:
            assert f"run {n} gives `-Engine {engine}`" in bullet, (n, engine)
            assert f"must record `FLUBNF_ENGINE={engine}`" in bullet, engine
    assert runs[1] is None
    assert "run 1 gives no `-Engine` and must write no `FLUBNF_ENGINE` line" in bullet


def test_the_ci_bullet_says_the_public_install_starts_on_the_default_route():
    """public-engine-install's first open names no engine and no option
    (test_a_fresh_install), and on macOS an open on the private route
    follows it."""
    real = _read("tests/test_public_engine_real.py")
    fresh = real[real.index("def test_a_fresh_install"):]
    fresh = fresh[:fresh.index("\ndef ")]
    assert "route=None" in fresh
    assert "def test_a_private_open_leaves_the_public_venv_alone" in real
    bullet = _ci_bullet()
    assert "(on macOS, `setup_engine.sh --public`)" not in bullet
    assert "Its first open takes the default route, with `FLUBNF_ENGINE` unset and no option" in bullet
    assert "(on macOS, `setup_engine.sh` with no option)" in bullet
    assert "on macOS only, an open on the private route (the fallback)" in bullet


# ------------------------------------------------- the Oracle doc's engine


def test_the_oracle_doc_names_both_engines_as_they_are_pinned():
    """The line-up: public PyBNF at its pinned commit, the default; the
    fork at 2fdadee0, the fallback. No opt-in route, no cutover still to
    come. The research keys the public engine refuses are the ones named."""
    pytest.importorskip("app.core.engines.lwf")
    from app.core import engine_build
    from app.core.engines import lwf
    doc = _read("docs/ORACLE-SIHRS.md")
    flat = _flat(doc)
    for gone in ("as an opt-in route", "until then every round runs on 2fdadee0",
                 "the ENGINE is the particle filter in the PyBNF fork"):
        assert gone not in flat, gone
    lineup = flat[flat.index("Engine line-up for the 2026-27 season"):]
    lineup = lineup[:lineup.index("## 6b.")]
    assert f"lanl/PyBNF at the merge commit {lwf.PUBLIC_ENGINE_COMMIT[:8]}" in lineup
    assert "(`job_type = lwf`)" in lineup
    assert f"still pinned at {engine_build.PRODUCTION_ENGINE_COMMIT}" in lineup
    for key in re.findall(r"`(pf_[a-z_]+)`", lineup[lineup.index("The four pf keys"):]):
        assert key in lwf._NO_COUNTERPART, key
    assert "the public engine has no counterpart for them" in lineup
    assert "(lanl/PyBNF, `job_type = lwf`), the default" in flat


# ------------------------------------------------------------- README


def test_readme_gives_the_fit_time_the_cost_model_gives():
    """A jurisdiction season (34 to 43 weeks of data) is about a minute on
    the public engine by pf.cell_seconds, so not "under a minute"."""
    pytest.importorskip("app.core.engines.pf")
    from app.core.engines import pf
    for weeks in (34, 43):
        seconds = pf.cell_seconds({"n_obs": weeks}, "public")
        assert 45 <= seconds <= 90, (weeks, seconds)
    readme = _flat(_read("README.md"))
    assert "a jurisdiction season fits in about a minute" in readme
    assert "fits in under a minute" not in readme


def test_the_methods_page_gives_the_same_fit_time():
    """The Methods page (published by site_build) says what README says:
    neither "seconds" nor "under a minute"."""
    page = _flat(_read("app/ui/templates/methods.html"))
    assert ('tips.stat("State-season fit", "about a minute", "", '
            'id="mt-speed")') in page
    assert "so a state-season fit takes about a minute." in page
    assert '"State-season fit", "seconds"' not in page
    assert "takes under a minute" not in page


def test_the_sites_software_card_names_the_engine_before_the_switch():
    """A site built after the switch and before the first public round
    shows only rounds and seasons fitted by the private engine: the card
    says so, as Methods does ("before it the lab's fork")."""
    card = _flat(_read("app/core/site_page.py"))
    card = card[card.index("We build our own stack"):]
    card = card[:card.index("</p>")]
    assert "fitted by the Liu-West filter in public PyBioNetFit" in card
    assert ("Rounds and sealed seasons from before the engine switch of "
            "2026-11-09 were fitted by the lab's PyBNF fork.") in card
    methods = _flat(_read("app/ui/templates/methods.html"))
    assert "from the engine switch of 2026-11-09; before it the lab's fork" in methods


@pytest.mark.parametrize("rel", ["app/core/sandbox_results.py",
                                 "scripts/engine_lock.py"])
def test_the_cutover_text_says_forecasting_sample_and_no_automatic_fallback(rel):
    """The words the project uses: a forecasting sample (never
    "posterior"), and a private engine that runs only when chosen."""
    text = _flat(_read(rel))
    assert "posterior" not in text.lower()
    assert "only the private engine installs" not in text


# ------------------------------------------------------- the team table


def test_the_team_table_names_both_engines_for_the_engine_lane():
    row = next(line for line in _read("docs/team/README.md").splitlines()
               if line.startswith("| [engine.md]"))
    for needle in ("public PyBNF", "the default", "private PyBNF fork",
                   "the fallback"):
        assert needle in row, needle


def test_the_archive_script_is_named_as_the_private_engines():
    row = next(line for line in _read("scripts/README.md").splitlines()
               if line.startswith("| `cut_engine_archive.sh`"))
    assert "the private engine's archive" in row and "the fallback" in row
    assert "student engine archive" not in row


# ------------------------------------------------------------- wording


@pytest.mark.parametrize("rel", DOCS)
def test_no_doc_says_the_filter_adapts_tracks_or_follows(rel):
    flat = _flat(_read(rel)).lower()
    hits = re.findall(r"(?:filter|engine)s? (?:adapts|tracks|follows)\b[^.]*",
                      flat)
    assert not hits, (rel, hits)
