"""setup.ps1 checks a hub clone for what doctor FAILs without.

doctor FAILs a clone without auxiliary-data/target-data-archive
(flubnf.doctor.HUB_DIRS). setup.ps1 used to check $HubDirs only, so a
Windows cone holding auxiliary-data but not its archive passed the check
and was never widened, and doctor then failed it.

The archive is in the CHECK only. git is given $HubDirs, unchanged: in cone
mode `sparse-checkout add auxiliary-data` brings in the whole folder, and
$HubDirs itself is pinned by tests/test_first_run_sparse_hub.py (as
setup.sh's HUB_DIRS, the same four folders).

There is no PowerShell on the Macs this runs on, so setup.ps1 is read as
text; Windows CI executes it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = "auxiliary-data/target-data-archive"


def _ps1() -> str:
    return (REPO / "setup.ps1").read_text(encoding="utf-8")


def _quoted(text: str) -> tuple:
    return tuple(re.findall(r'"([^"]+)"', text))


def _hub_dirs(src: str) -> tuple:
    block = re.search(r"^\$HubDirs = @\((.*?)\)", src, re.M | re.S)
    assert block, "setup.ps1 no longer sets $HubDirs"
    return _quoted(block.group(1))


def _top_level_lists(src: str) -> dict:
    """$HubDirs and every script-level list built from it, by name."""
    lists = {"$HubDirs": _hub_dirs(src)}
    for name, expr in re.findall(r"^(\$\w+)\s*=\s*(@\(\$HubDirs\).*)$",
                                 src, re.M):
        lists[name] = lists["$HubDirs"] + _quoted(expr)
    return lists


def _function(src: str, name: str) -> tuple:
    """(parameter names, body) of a setup.ps1 function."""
    m = re.search(r"^function " + re.escape(name) + r" \{\n(.*?)^\}$",
                  src, re.M | re.S)
    assert m, f"setup.ps1 no longer defines {name}"
    body = m.group(1)
    params = re.search(r"param\(([^)]*)\)", body)
    assert params, f"{name} no longer has a param() block"
    return tuple(re.findall(r"\$(\w+)", params.group(1))), body


def _outside(src: str, name: str) -> str:
    """setup.ps1 without the body of function `name`."""
    return re.sub(r"^function " + re.escape(name) + r" \{\n.*?^\}$", "",
                  src, flags=re.M | re.S)


def _checked_lists(src: str) -> list:
    """Every list Get-MissingHubDirs is handed, resolved to its folders, as
    (where, folders). Inside Repair-HubCone the argument is one of its
    parameters, resolved through each Repair-HubCone call."""
    lists = _top_level_lists(src)
    script = _outside(_outside(src, "Get-MissingHubDirs"), "Repair-HubCone")
    out = []
    for var in re.findall(r"Get-MissingHubDirs \$Hub (\$\w+)", script):
        assert var in lists, f"setup.ps1 checks the hub against {var}, " \
                             f"which this test cannot resolve"
        out.append((f"Get-MissingHubDirs $Hub {var}", lists[var]))
    params, body = _function(src, "Repair-HubCone")
    inner = re.findall(r"Get-MissingHubDirs \$Hub \$(\w+)", body)
    assert inner, "Repair-HubCone no longer checks what is missing"
    calls = re.findall(r"^\s*Repair-HubCone ((?:\$\w+ ?)+)$", script, re.M)
    assert calls, "setup.ps1 no longer calls Repair-HubCone"
    for call in calls:
        args = call.split()
        for p in inner:
            i = params.index(p)
            assert i < len(args), (
                f"Repair-HubCone checks ${p}, but the call "
                f"`Repair-HubCone {call}` does not pass it")
            assert args[i] in lists, args[i]
            out.append((f"Repair-HubCone {call} (its ${p})", lists[args[i]]))
    return out


def test_every_hub_check_in_setup_ps1_requires_what_doctor_fails_without():
    """A cone with auxiliary-data but not its archive must not pass: doctor
    FAILs it, so setup.ps1 has to widen it."""
    from flubnf.doctor import HUB_DIRS as HUB_DATA_DIRS
    assert ARCHIVE in HUB_DATA_DIRS
    checks = _checked_lists(_ps1())
    # the no-git branch, the repair (before and after `add`), the full clone
    assert len(checks) >= 4, checks
    for where, folders in checks:
        missing = [d for d in HUB_DATA_DIRS if d not in folders]
        assert not missing, (
            f"setup.ps1's `{where}` does not check {missing}, so a sparse "
            f"clone without them passes it while doctor FAILs the same clone "
            f"and tells the user to run setup.ps1")


def test_setup_ps1_checks_what_setup_sh_clones_and_doctor_needs():
    """One list of folders a finished clone holds: the four setup.sh gives
    git (its HUB_DIRS, setup.ps1's $HubDirs) and what doctor FAILs
    without."""
    from flubnf.doctor import HUB_DIRS as HUB_DATA_DIRS
    sh = (REPO / "setup.sh").read_text(encoding="utf-8")
    dirs = re.findall(r'^HUB_DIRS="([^"]*)"$', sh, re.M)
    assert len(dirs) == 1, dirs
    needs = sorted(set(dirs[0].split()) | set(HUB_DATA_DIRS))
    assert ARCHIVE in needs
    for where, folders in _checked_lists(_ps1()):
        assert sorted(folders) == needs, (
            f"setup.ps1's `{where}` checks {sorted(folders)}; a finished "
            f"clone holds {needs}")


def test_git_is_only_ever_given_hub_dirs():
    """The archive is in the check, never in the cone git is told about:
    every sparse-checkout list setup.ps1 builds resolves to $HubDirs."""
    src = _ps1()
    hub_dirs = _hub_dirs(src)
    assert ARCHIVE not in hub_dirs
    sparse = re.findall(r'"sparse-checkout", "(add|set)"\)\s*\+\s*(\$\w+)',
                        src)
    assert {verb for verb, _ in sparse} == {"add", "set"}, sparse
    params, body = _function(src, "Repair-HubCone")
    script = _outside(src, "Repair-HubCone")
    calls = re.findall(r"^\s*Repair-HubCone ((?:\$\w+ ?)+)$", script, re.M)
    for verb, var in sparse:
        if f'"sparse-checkout", "{verb}") + {var}' in body:
            # a Repair-HubCone parameter: every call must pass $HubDirs
            i = params.index(var[1:])
            for call in calls:
                assert call.split()[i] == "$HubDirs", (
                    f"Repair-HubCone runs sparse-checkout {verb} with {var}, "
                    f"and `Repair-HubCone {call}` passes {call.split()[i]}")
        else:
            assert var == "$HubDirs", (
                f"setup.ps1 runs sparse-checkout {verb} with {var}, "
                f"not $HubDirs")
