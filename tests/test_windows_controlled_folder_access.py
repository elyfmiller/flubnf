"""Windows defaults must not land inside a Controlled Folder Access folder.

Field report, Windows 11, 2026-08-25. Controlled Folder Access is Microsoft
Defender's ransomware protection. When it is on it protects Documents (among
others) for every account: a protected folder can be read by anything and
written only by programs Defender trusts, and neither git.exe nor python.exe
nor perl.exe is trusted out of the box. The Defender operational log on the
corresponding author's machine, verbatim:

    Id 1123: git.exe has been blocked from modifying
             %userprofile%\\Documents\\GitHub\\FluSight-forecast-hub
    Id 1123: python.exe has been blocked from modifying
             %userprofile%\\Documents\\GitHub\\PyBNF-pf\\pybnf\\__pycache__

`Get-MpPreference` on that machine reports EnableControlledFolderAccess = 1.
Microsoft documents the shipped state as 0, Disabled -- "CFA is turned off
by default" -- so something turned it on there: the user, the image, or IT
policy on a managed machine. An earlier draft of this work asserted it was
on by default and that assertion is retracted; what survives is that it is
on for at least one real user of this project and can be on for any student,
which is reason enough not to default a checkout into a folder it guards.

The old Windows defaults put both checkouts under Documents, so on a machine
with the protection on git cannot clone or pull the hub and Python cannot
write __pycache__ into the checkout -- and NEITHER failure mentions Defender
in the text the user sees, which is what made it cost several rounds of
wrong diagnosis.

Two things are tested here, one behavioural and one textual:

  * `flubnf.settings._checkout`, which is the resolution the app itself uses,
    runs on this machine with os.name faked, so the Windows branch is
    executed rather than described;
  * `setup.ps1` and `FluBNF.bat` are checked as TEXT, because the lab
    develops on macOS and has no PowerShell interpreter. Windows CI executes
    them for real, including a run against a machine that already holds a
    checkout at the old location.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PS1 = (REPO / "setup.ps1").read_text(encoding="utf-8")
BAT = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
DOC = (REPO / "docs" / "WINDOWS.md").read_text(encoding="utf-8")
WORKFLOW = (REPO / ".github" / "workflows" / "tests.yml").read_text(
    encoding="utf-8")

LEGACY = "Documents/GitHub"


def _checkout(monkeypatch, *, windows: bool, home: Path, localappdata: Path):
    """Call the real resolver with the platform and the profile faked.

    settings._windows() and settings._home() are the two seams. Faking
    os.name instead of the first would also work and would turn every
    pathlib.Path made afterwards into a WindowsPath, which breaks
    expanduser on this machine and would leak into the rest of the suite.

    The profile goes through settings._home() and NOT through
    monkeypatch.setenv("HOME"), which is what this helper did until run
    33200477476. $HOME steers expanduser on POSIX and nothing at all on
    Windows: pathlib.Path.expanduser calls ntpath.expanduser there, which
    reads %USERPROFILE% (then %HOMEDRIVE%%HOMEPATH%) and never consults
    $HOME. So on the Windows runner these tests resolved against the
    runner's real profile while asserting against a tmp_path, and failed
    with WindowsPath('C:/Users/runneradmin/Documents/GitHub/FluSight-...').
    The resolution under test was correct; the fake was inert.
    """
    from flubnf import settings

    monkeypatch.setattr(settings, "_windows", lambda: windows)
    monkeypatch.setattr(settings, "_home", lambda: home)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    monkeypatch.delenv("FLUBNF_HUB", raising=False)
    return settings._checkout("FLUBNF_HUB", "FluSight-forecast-hub")


def test_windows_default_is_outside_every_protected_folder(monkeypatch, tmp_path):
    """The whole point: no Documents, no Desktop, no Pictures."""
    got = _checkout(monkeypatch, windows=True, home=tmp_path / "profile",
                    localappdata=tmp_path / "profile" / "AppData" / "Local")
    assert got == (tmp_path / "profile" / "AppData" / "Local" / "FluBNF"
                   / "FluSight-forecast-hub"), got
    parts = [p.lower() for p in got.parts]
    for protected in ("documents", "desktop", "pictures"):
        assert protected not in parts, (
            f"the Windows default resolves inside {protected}, which "
            f"Controlled Folder Access protects: {got}")


def test_an_existing_checkout_under_documents_is_reused_where_it_stands(
        monkeypatch, tmp_path):
    """Nobody gets stranded, and nothing gets moved.

    The author has 143 MB of PyBNF checkout and 150 MB of hub under
    Documents. A machine configured before this change must keep working
    with no action at all, so an existing directory at the old path still
    wins over the new default.
    """
    home = tmp_path / "profile"
    legacy = home / "Documents" / "GitHub" / "FluSight-forecast-hub"
    legacy.mkdir(parents=True)
    got = _checkout(monkeypatch, windows=True, home=home,
                    localappdata=home / "AppData" / "Local")
    assert got == legacy, got
    assert not (home / "AppData" / "Local" / "FluBNF").exists(), (
        "resolution created something on disk; it must only ever look")


def test_posix_defaults_are_untouched(monkeypatch, tmp_path):
    """macOS and Linux have no Controlled Folder Access and no reason to
    move. setup.sh, setup_engine.sh and the .command launchers all still
    resolve ~/Documents/GitHub, so settings.py must agree with them."""
    home = tmp_path / "profile"
    got = _checkout(monkeypatch, windows=False, home=home,
                    localappdata=tmp_path / "unused")
    assert got == home / "Documents" / "GitHub" / "FluSight-forecast-hub", got


def test_ntpath_ignores_dollar_home_which_is_why_the_seam_exists(monkeypatch,
                                                                 tmp_path):
    """Why _checkout above patches settings._home() and not $HOME.

    ntpath is the module pathlib.Path.expanduser goes through on Windows,
    and it is importable here, so its rule can be shown on this machine:
    with %USERPROFILE%, %HOMEDRIVE% and %HOMEPATH% all absent it leaves the
    tilde alone no matter what $HOME says, and %USERPROFILE% is what it
    answers with. A test that fakes $HOME therefore fakes nothing on
    Windows, which is what made these tests resolve against the CI runner's
    real profile (run 33200477476) while asserting against a tmp_path.

    If a future CPython starts honouring $HOME on Windows this fails, and
    the right response is to update the note rather than the seam: routing
    the profile through settings._home() is correct either way.

    This is a NOTE, not a fence. It asserts a property of ntpath and would
    go on passing if _checkout above went back to the inert $HOME fake; the
    test below is the one that catches that.
    """
    import ntpath

    for var in ("USERPROFILE", "HOMEDRIVE", "HOMEPATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "profile"))
    assert ntpath.expanduser("~") == "~", (
        "Windows path semantics now expand ~ from $HOME; the note on "
        "settings._home() says they do not")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\someone")
    assert ntpath.expanduser(r"~\Documents") == r"C:\Users\someone\Documents"


def test_the_profile_fake_still_works_under_the_windows_tilde_rule(monkeypatch,
                                                                   tmp_path):
    """The fence the note above only describes.

    Putting the inert `monkeypatch.setenv("HOME", ...)` back into _checkout
    is INVISIBLE on this machine: $HOME really is the home here, so the
    whole suite stays green while the Windows job quietly goes back to
    resolving against the runner's own profile. Reviewed on 2026-08-31 by
    making exactly that edit; 32 of 32 passed. So this test installs the
    Windows tilde rule for the length of one call and asserts the fake
    still wins.

    The decoy profile below stands in for C:\\Users\\runneradmin. It holds
    a legacy checkout so that a resolver reading it lands on a path a
    reader recognises from run 33200477476, rather than on the AppData
    default, which the helper's LOCALAPPDATA fake would make look right.
    """
    import ntpath

    decoy = tmp_path / "runneradmin"
    (decoy / "Documents" / "GitHub" / "FluSight-forecast-hub").mkdir(
        parents=True)
    monkeypatch.setenv("USERPROFILE", str(decoy))
    for var in ("HOMEDRIVE", "HOMEPATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(os.path, "expanduser", ntpath.expanduser)

    home = tmp_path / "profile"
    legacy = home / "Documents" / "GitHub" / "FluSight-forecast-hub"
    legacy.mkdir(parents=True)
    got = _checkout(monkeypatch, windows=True, home=home,
                    localappdata=home / "AppData" / "Local")
    assert got == legacy, (
        f"the profile fake is inert under the Windows tilde rule: {got}. "
        f"_checkout must fake the profile through settings._home(), not "
        f"through $HOME")


def test_the_environment_variable_still_wins_everywhere(monkeypatch, tmp_path):
    from flubnf import settings

    monkeypatch.setattr(settings, "_windows", lambda: True)
    monkeypatch.setenv("FLUBNF_HUB", str(tmp_path / "elsewhere"))
    assert settings._checkout("FLUBNF_HUB", "FluSight-forecast-hub") == (
        tmp_path / "elsewhere")


def test_setup_ps1_no_longer_defaults_a_checkout_into_documents():
    for leaf in ("FluSight-forecast-hub", "PyBNF-pf"):
        assert f'Join-Path $HOME "Documents\\GitHub\\{leaf}"' not in PS1, (
            f"setup.ps1 defaults {leaf} back into Documents, which "
            f"Controlled Folder Access blocks git.exe from writing to")
    assert 'Join-Path $LocalAppData "FluBNF"' in PS1, (
        "setup.ps1 no longer builds its default under %LOCALAPPDATA%")
    for var, leaf in (("FLUBNF_HUB", "FluSight-forecast-hub"),
                      ("FLUBNF_PYBNF", "PyBNF-pf")):
        assert f'Resolve-Checkout $env:{var} "{leaf}"' in PS1, (
            f"{var} no longer goes through the resolver that reuses an "
            f"existing checkout at the old location")


def test_setup_ps1_reuses_an_old_checkout_and_never_relocates_one():
    assert "Test-Path -LiteralPath $legacy" in PS1
    assert "$script:ReusedLegacy" in PS1, (
        "setup.ps1 no longer records that it reused an old location, so the "
        "plan block cannot say so")
    assert "Reusing folders that are already on this machine" in PS1
    for forbidden in ("Move-Item", "Copy-Item", "robocopy", "xcopy"):
        assert forbidden not in PS1, (
            f"setup.ps1 contains {forbidden}: a user's 143 MB checkout is "
            f"never moved or copied for them")


def test_setup_ps1_asks_defender_and_survives_being_told_nothing():
    assert "Get-MpPreference" in PS1, (
        "setup.ps1 no longer queries Controlled Folder Access at all")
    state = PS1.index("function Get-CfaState")
    body = PS1[state:PS1.index("$Hub = Resolve-Checkout")]
    assert "Get-Command Get-MpPreference" in body, (
        "the cmdlet is called without first testing that it exists")
    assert "-ErrorAction Stop" in body and "catch" in body, (
        "Get-MpPreference is called without a catch, so a machine whose "
        "Defender module errors takes the script down with it")
    assert body.count('State = "unknown"') >= 3, (
        "not every failure mode resolves to an explicit unknown")


def test_setup_ps1_never_changes_a_defender_setting_and_never_elevates():
    for forbidden in ("Set-MpPreference", "Add-MpPreference",
                      "Remove-MpPreference", "-Verb RunAs",
                      "RunAsAdministrator"):
        assert forbidden not in PS1, (
            f"setup.ps1 contains {forbidden}. It reports on Controlled "
            f"Folder Access and never touches it, and it never elevates")
    assert "Do not switch Controlled Folder Access off." in PS1, (
        "the advice no longer tells the reader to leave the protection on")


def test_the_warning_names_the_two_failures_and_precedes_the_work():
    """A warning after the clone has already failed is worth nothing."""
    warn = PS1.index('Say "controlled folder access')
    for later in ('Say "python"', 'Say "FluSight hub data"',
                  '"--filter=blob:none"'.strip('"')):
        assert warn < PS1.index(later), (
            f"the Controlled Folder Access warning is printed after {later}")
    assert "git may fail to clone or to pull" in PS1
    assert "python may fail to write __pycache__" in PS1
    assert "never mention" in PS1, (
        "the warning no longer says that neither failure mentions Defender, "
        "which is the whole reason it is hard to recognise")


def test_the_remedies_are_offered_best_first():
    setx = PS1.index("PREFERRED: put the folder where Controlled Folder")
    allow = PS1.index("Allow the specific programs through")
    exclude = PS1.index("LAST RESORT, and it REDUCES PROTECTION")
    assert setx < allow < exclude, (
        "the remedies are out of order: relocating needs no administrator, "
        "allowing an executable does, and a folder exclusion reduces "
        "protection and must come last")
    assert "needs an ADMINISTRATOR" in PS1
    assert "git.exe and python.exe are the two Defender actually logged" in PS1


def test_the_launcher_resolves_the_hub_the_way_setup_does():
    """FluBNF.bat has its own fallback for the case where setup.ps1 has not
    run yet. If it disagreed with setup.ps1 it would offer setup forever, or
    look for data in a folder nothing ever writes to."""
    legacy = BAT.index(r"%USERPROFILE%\Documents\GitHub\FluSight-forecast-hub")
    local = BAT.index(r"%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub")
    assert legacy < local, (
        "FluBNF.bat prefers the new default over an existing checkout at the "
        "old location, so a machine that worked before would stop finding "
        "its data")
    assert 'if exist "%HUBDIR%\\." goto :hubresolved' in BAT


@pytest.mark.parametrize("needle", [
    "Id 1123",
    "git.exe has been blocked from modifying",
    "python.exe has been blocked from modifying",
    "Get-MpPreference | Select-Object EnableControlledFolderAccess",
    "Microsoft-Windows-Windows Defender/Operational",
])
def test_windows_doc_carries_the_evidence_a_student_will_search_for(needle):
    """A student who sees the Defender pop-up searches for its words. The
    log lines are in docs/WINDOWS.md verbatim so that search lands."""
    assert needle in DOC, f"docs/WINDOWS.md no longer contains {needle!r}"


def test_windows_doc_states_why_this_project_trips_it():
    for needle in ("__pycache__", "Perl", "LOCALAPPDATA"):
        assert needle in DOC, needle
    assert "keeps working" in DOC or "reused exactly where it is" in DOC, (
        "docs/WINDOWS.md no longer tells an existing install that it is safe")


def test_posix_setup_scripts_were_not_dragged_along():
    """macOS has no Controlled Folder Access and its paths are fine. These
    four are on the double-click path for the whole lab; a well-meant edit
    here would break every Mac."""
    for name in ("setup.sh", "setup_engine.sh"):
        src = (REPO / name).read_text(encoding="utf-8")
        assert f'$HOME/{LEGACY}' in src, (
            f"{name} no longer resolves ~/{LEGACY}; the POSIX defaults were "
            f"not part of the Controlled Folder Access change")
        assert "LOCALAPPDATA" not in src, f"{name} grew a Windows path"
    for name in ("FluBNF.command", "SetupEngine.command", "install.sh"):
        assert "LOCALAPPDATA" not in (REPO / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The second pass. Everything below was added after a review found eight
# problems in the first; each test names the one it pins down, so a later
# edit that undoes the fix fails here rather than on a student's machine.
# ---------------------------------------------------------------------------


def _workflow_steps():
    """(name, shell, body) for every step in .github/workflows/tests.yml.

    A short hand parse rather than PyYAML, which is not a dependency of this
    project and would be a strange one to add for a text check. The workflow
    is written in a consistent style: steps begin with "- name:" at a fixed
    indent and carry "shell:" and a "run: |" block.

    Comment lines are dropped. A block comment introducing the NEXT step
    sits between two steps and would otherwise be collected as the tail of
    the previous one, which is exactly the kind of off-by-one that makes a
    guard quietly test the wrong thing.
    """
    steps, name, shell, body, in_run = [], None, None, [], False
    for line in WORKFLOW.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if name is not None:
                steps.append((name, shell, "\n".join(body)))
            name, shell, body, in_run = stripped[len("- name:"):].strip(), \
                None, [], False
        elif stripped.startswith("shell:"):
            shell = stripped[len("shell:"):].strip()
        elif stripped.startswith("run:"):
            in_run = True
        elif in_run and name is not None and not stripped.startswith("#"):
            body.append(line)
    if name is not None:
        steps.append((name, shell, "\n".join(body)))
    return steps


def test_the_workflow_parse_finds_the_windows_steps_it_is_meant_to_check():
    """A guard on the guard. If the hand parse silently found nothing, every
    assertion built on it would pass while checking nothing at all."""
    steps = _workflow_steps()
    shells = {s for _, s, _ in steps}
    assert "powershell" in shells, shells
    assert "cmd" in shells, shells
    assert any("run 5" in n for n, _, _ in steps), (
        "the legacy-reuse run is gone from the workflow, and it is the only "
        "automated check that an existing Documents checkout is reused")


def test_no_cmd_only_construct_survives_inside_a_powershell_step():
    """`exit /b 0` left over from a cmd step is not dead code in PowerShell.

    PowerShell parses a whole script before it runs any of it, and `/b` at
    the start of a statement has no left operand for `/`. A step that fails
    at parse time runs none of its assertions, and because the Windows jobs
    carry continue-on-error the workflow still reports green -- so the check
    would be gone and nothing would say so. One such line was found in the
    run-5 assertion step; this is the fence around that hole.
    """
    offenders = []
    for name, shell, body in _workflow_steps():
        if shell != "powershell":
            continue
        for i, line in enumerate(body.splitlines(), 1):
            text = line.strip()
            if text.startswith("#"):
                continue
            for bad in ("exit /b", "goto :", "errorlevel", "set \"",
                        "rem "):
                if text.startswith(bad):
                    offenders.append(f"{name!r} line {i}: {text!r} ({bad})")
    assert not offenders, (
        "cmd syntax inside a PowerShell step:\n  " + "\n  ".join(offenders))


def test_every_cmd_step_that_ends_in_a_check_still_exits_zero():
    """The counterpart. A cmd step whose last statement is a failure test
    must say so explicitly, otherwise the step's exit code is whatever the
    last command happened to leave behind."""
    missing = []
    for name, shell, body in _workflow_steps():
        if shell != "cmd":
            continue
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        if lines and not lines[-1].startswith("exit /b"):
            missing.append(name)
    assert not missing, (
        "cmd steps that do not end with an explicit exit: " + repr(missing))


def test_setup_ps1_anchors_on_userprofile_not_on_powershells_home():
    """$HOME, %USERPROFILE% and Path('~').expanduser() are three answers.

    about_Automatic_Variables for 7.x says $HOME takes %USERPROFILE% and
    warns it "may not have the same value as $Env:HOMEDRIVE$Env:HOMEPATH";
    the 5.1 page described it as the equivalent of %homedrive%%homepath%.
    On a domain machine with an AD home directory those differ (H:\\, a UNC
    path), and FluBNF.bat and settings.py both read %USERPROFILE%. setup.ps1
    must not be the odd one out, or the three disagree about where the
    legacy checkout was and the "reuse it where it stands" promise breaks.
    """
    assert '$ProfileRoot = if ($env:USERPROFILE)' in PS1, (
        "setup.ps1 no longer resolves one profile root preferring "
        "%USERPROFILE%")
    for forbidden in ('Join-Path $HOME "Documents',
                      'Join-Path $HOME ".venvs',
                      'Join-Path $HOME "AppData'):
        assert forbidden not in PS1, (
            f"setup.ps1 builds a path from $HOME ({forbidden}), which can be "
            f"a mapped drive on a managed machine while FluBNF.bat and "
            f"flubnf/settings.py read %USERPROFILE%")


def test_setup_ps1_looks_under_every_spelling_of_the_profile_before_giving_up():
    """Preferring %USERPROFILE% must not strand a checkout an earlier
    release made under the other root. Lookups probe both; defaults do not."""
    assert "$LegacyRoots" in PS1 and "foreach ($root in $LegacyRoots)" in PS1
    assert "function Get-ProfileRoots" in PS1
    assert "function Resolve-ProfilePath" in PS1
    assert "Resolve-ProfilePath \".venvs\\flubnf-engine\"" in PS1, (
        "the engine venv default no longer probes for one an earlier release "
        "built under a different profile root, so re-running setup on such a "
        "machine would build a second one beside the working install")


def test_the_protected_set_includes_the_public_folders_and_the_machines_own():
    """Microsoft's default list carries the C:\\Users\\Public variants, and a
    managed image can protect more. Both were being thrown away: the
    Get-MpPreference result was read for one property and discarded."""
    for name in ("CommonDocuments", "CommonPictures", "CommonVideos",
                 "CommonMusic"):
        assert name in PS1, f"{name} is missing from the protected-folder set"
    assert "ControlledFolderAccessProtectedFolders" in PS1, (
        "setup.ps1 never asks Defender which folders it actually protects, "
        "so a folder IT added is invisible to the warning")
    assert "ControlledFolderAccessDefaultProtectedFolders" in PS1
    assert "Folders = $folders" in PS1 or "Folders = @()" in PS1
    assert "@($Cfa.Folders)" in PS1, (
        "the machine's own protected-folder list is fetched and then not "
        "unioned into the set the paths are tested against")


def test_the_two_disk_only_modes_are_not_reported_as_a_mystery():
    """Modes 3 and 4 guard boot sectors and leave protected folders alone.
    Reporting them as unrecognised printed a page of irrelevant alarm."""
    for token in ("BlockDiskModificationOnly", "AuditDiskModificationOnly"):
        assert token in PS1, f"{token} is not handled by Get-CfaState"
    body = PS1[PS1.index("function Get-CfaState"):
               PS1.index("$Hub = Resolve-Checkout")]
    three = body.index('$s -eq "3"')
    unknown = body.rindex('which this script does not recognise')
    assert three < unknown, (
        "mode 3 falls through to the unrecognised branch")


def test_a_failed_clone_does_not_pin_the_location_it_failed_at():
    """FLUBNF_HUB in the User environment wins over every later branch of
    Resolve-Checkout. Recording it after a clone that produced nothing sent
    every future run back to the folder it could not write to -- which is
    how the population this change exists to help got stranded."""
    assert "$HubCloneFailed" in PS1
    assert "if ($HubCloneFailed) {" in PS1, (
        "the FLUBNF_HUB write is unconditional again")
    write = PS1.index('SetEnvironmentVariable("FLUBNF_HUB", $Hub, "User")')
    guard = PS1.index("if ($HubCloneFailed) {")
    assert guard < write, "the guard no longer precedes the write"
    assert 'SetEnvironmentVariable("FLUBNF_HUB", $null' not in PS1, (
        "setup.ps1 DELETES FLUBNF_HUB on failure. A user who deliberately "
        "set it to a drive that happened to be unplugged today would lose "
        "their configuration; withholding the write is the whole fix")


def test_a_stale_recorded_pin_is_named_with_its_remedy():
    """Skipping the write helps a first run. A machine the old script
    already touched needs to be told, because nothing else will clear it."""
    assert "$Stale" in PS1
    assert "A NOTE ON WHAT IS ALREADY RECORDED ON THIS MACHINE." in PS1
    assert "FromEnv" in PS1, (
        "setup.ps1 no longer distinguishes a path that came from a recorded "
        "variable from one it resolved itself, so it cannot tell a leftover "
        "from a choice")


def test_the_fit_time_writers_are_on_the_allow_list():
    """A fit runs BNG2.pl under perl in app\\state\\workroots, inside the
    repository. Remedy 2 without perl.exe fixes setup and not the fit."""
    for token in ("$PerlExe", "$RunNetExe"):
        assert token in PS1, f"{token} is not offered to remedy 2"
    allow = PS1.index("Allow the specific programs through")
    tail = PS1[allow:allow + 3000]
    for token in ("$PerlExe", "$RunNetExe", "$GitExe", "$EnginePy", "$VenvPy"):
        assert token in tail, f"{token} is not printed under remedy 2"
    for needle in ("perl.exe", "run_network.exe", "app\\state\\workroots"):
        assert needle in DOC, f"docs/WINDOWS.md never mentions {needle}"


def test_the_doc_no_longer_claims_the_protection_is_on_by_default():
    """Microsoft: "CFA is turned off by default", mode 0 marked (default).
    The claim was asserted unhedged in five user-visible places on the
    strength of one machine reading 1."""
    # A bare substring ban would also forbid saying it is NOT on by default,
    # which is the correction itself and appears in four of these files. So
    # each hit is judged by what comes just before it: a negation, or a
    # retraction of the old claim, makes the sentence true rather than false.
    ok = ("not ", "n't", "never", "no longer", "opposite", "wrong",
          "retract", "asserted", "said it was", "instead of")
    bad = []
    for text, where in ((DOC, "docs/WINDOWS.md"),
                        ((REPO / "README.md").read_text(encoding="utf-8"),
                         "README.md"),
                        (PS1, "setup.ps1"),
                        (BAT, "FluBNF.bat"),
                        ((REPO / "flubnf" / "settings.py").read_text(
                            encoding="utf-8"), "flubnf/settings.py")):
        low = " ".join(text.lower().replace("*", "").split())
        # "stock" carried the same false claim in the draft without using
        # the words "by default": "protected ... on a stock Windows 11",
        # "which is the stock setting". Both are banned outright here.
        for claim in ("on by default", "enabled by default",
                      "on in windows 11 by default",
                      "stock windows 11", "stock setting"):
            start = 0
            while True:
                at = low.find(claim, start)
                if at < 0:
                    break
                start = at + 1
                lead = low[max(0, at - 90):at]
                if not any(marker in lead for marker in ok):
                    bad.append(f"{where}: ...{low[max(0, at - 90):at + 40]}")
    assert not bad, (
        "Controlled Folder Access is asserted to be on by default, which "
        "Microsoft's documentation contradicts:\n  " + "\n  ".join(bad))
    assert "turned off by default" in DOC, (
        "docs/WINDOWS.md no longer states the documented default at all")
    assert "policy" in DOC.lower(), (
        "docs/WINDOWS.md does not mention that a managed machine can have "
        "the setting pushed, which is the likely explanation for the one "
        "machine that has it on")


def test_the_doc_reaches_and_reassures_the_reader_who_saw_the_popup():
    """The entry condition named three triggers and a mid-fit Defender
    pop-up was none of them, so the section told that reader to leave."""
    section = DOC[DOC.index("## Controlled Folder Access"):]
    section = section[:section.index("### What it looks like")]
    # collapsed, because prose is hard-wrapped at 76 columns and a phrase
    # that happens to straddle a line break is still a phrase the reader sees
    low = " ".join(section.lower().split())
    for needle in ("pop-up", "fit stopped"):
        assert needle in low, (
            f"the section entry condition does not cover {needle!r}, which "
            f"is how a student actually arrives here")
    for needle in ("not a virus", "nothing is infected", "no data was lost"):
        assert needle in low, (
            f"the section never says {needle!r}; an alarmed reader needs "
            f"that before the mechanism, not instead of it")
    assert low.index("not a virus") < low.index("ransomware protection"), (
        "the section describes itself as ransomware protection before it "
        "reassures, which reads to an anxious student as confirmation")


def test_the_windows_doc_quotes_every_path_it_tells_a_user_to_type():
    """%LOCALAPPDATA% expands to a path under the profile directory. An
    account name with a space in it turns an unquoted clone destination into
    two arguments, and git's "Too many arguments" says nothing about why."""
    bad = []
    for i, line in enumerate(DOC.splitlines(), 1):
        text = line.strip()
        if not (text.startswith("git clone") or text.startswith("setx ")):
            continue
        for var in ("%LOCALAPPDATA%", "%USERPROFILE%"):
            if var in text and f'"{var}' not in text:
                bad.append(f"docs/WINDOWS.md:{i}: {text}")
    assert not bad, (
        "unquoted expansion used as a command argument:\n  " +
        "\n  ".join(bad))
