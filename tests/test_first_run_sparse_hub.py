"""A hub clone that exists but holds no data must never read as ready.

`git clone --sparse` checks out only the root, so every gate tests for hub
DATA (auxiliary-data/locations.csv), not for the clone or .git. Repair uses
`sparse-checkout add` (idempotent); `reapply` adds nothing, and `set` on a
full clone deletes every unnamed directory. setup.ps1/setup.sh are checked
as text; Windows CI executes setup.ps1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# every directory the sparse cone has to contain, in git's own path form
HUB_DIRS = ("auxiliary-data", "target-data",
            "model-output/FluSight-baseline", "model-output/FluSight-ensemble")


def _check_with_hub(hub: Path) -> list:
    """Run flubnf.settings.check() in a fresh interpreter against `hub`
    (settings resolves paths at import; reloading would leave stale HUBs)."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import json, os, sys;"
         "from flubnf.settings import check;"
         "json.dump([m[0] for m in check(verbose=False)], sys.stdout)"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={**os.environ, "FLUBNF_HUB": str(hub)})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_doctor_reports_a_clone_with_no_data_directories_as_missing(tmp_path):
    """The exact reported state: the directory is there, the data is not."""
    hub = tmp_path / "FluSight-forecast-hub"
    (hub / ".git").mkdir(parents=True)          # a real clone, root only
    (hub / "README.md").write_text("root file\n")
    assert "FLUBNF_HUB" in _check_with_hub(hub), (
        "check() certified a sparse clone that holds none of the app's data; "
        "that is the green tick over the broken state from the field report")


def test_doctor_accepts_a_hub_once_the_data_directories_are_there(tmp_path):
    hub = tmp_path / "FluSight-forecast-hub"
    for d in HUB_DIRS:
        (hub / d).mkdir(parents=True)
    (hub / "auxiliary-data" / "locations.csv").write_text("location\nUS\n")
    assert "FLUBNF_HUB" not in _check_with_hub(hub)


def test_launcher_gates_the_setup_offer_on_data_not_on_dot_git():
    """FluBNF.bat must re-offer setup for a clone that exists but is empty."""
    bat = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
    assert 'if exist "%HUBDIR%\\auxiliary-data\\locations.csv" goto :launch' in bat, (
        "FluBNF.bat no longer gates on the hub's DATA. Gating on "
        r'"%HUBDIR%\.git" declares a root-only sparse clone finished and '
        "never offers setup.ps1 again.")
    assert 'if exist "%HUBDIR%\\.git" goto :launch' not in bat


def test_launcher_never_leaves_a_double_click_at_an_unbounded_prompt():
    """The .bat bounds its own question; the setup.ps1 it hands off to must
    run with -NoPrompt (its Read-Host has no timeout)."""
    bat = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
    launch = [l for l in bat.splitlines()
              if "setup.ps1" in l and l.lstrip().lower().startswith("powershell")]
    assert launch, "FluBNF.bat no longer runs setup.ps1 at all"
    for line in launch:
        assert "-NoPrompt" in line, (
            f"FluBNF.bat runs setup.ps1 without -NoPrompt: {line.strip()!r}. "
            "A double-click would then stop at Read-Host with no timeout.")


def test_setup_scripts_widen_an_existing_cone_with_add_not_set():
    """Both scripts repair an existing clone with `add` (`set` would prune
    every directory it is not given)."""
    for name, needle in (("setup.ps1", '"sparse-checkout", "add"'),
                         ("setup.sh", "git sparse-checkout add")):
        src = (REPO / name).read_text(encoding="utf-8")
        assert needle in src, (
            f"{name} never runs sparse-checkout add, so a clone made with "
            f"--sparse is left holding only the repository root")
        for d in HUB_DIRS:
            assert d in src, f"{name} no longer names {d}"


def test_setup_ps1_only_narrows_the_cone_on_a_clone_it_just_made():
    """`sparse-checkout set` appears once: on the fresh clone, whose cone is
    empty; anywhere else it would delete a full checkout."""
    src = (REPO / "setup.ps1").read_text(encoding="utf-8")
    sets = [l for l in src.splitlines()
            if '"sparse-checkout", "set"' in l or "sparse-checkout set" in l]
    assert len(sets) == 1, (
        f"expected exactly one `sparse-checkout set` in setup.ps1 (the fresh "
        f"clone); found {len(sets)}: {sets}")
    # and it has to sit inside the clone branch, after the clone succeeded
    clone_at = src.index("--filter=blob:none")
    assert src.index(sets[0]) > clone_at


def test_setup_ps1_repairs_the_cone_before_it_reapplies_it():
    """Repair before reapply (reapply only re-applies the recorded cone)."""
    src = (REPO / "setup.ps1").read_text(encoding="utf-8")
    repair = src.index("Repair-HubCone $Hub $HubDirs")
    reapply = src.index('"sparse-checkout", "reapply"')
    assert repair < reapply, (
        "setup.ps1 reapplies the sparse cone before widening it, so a "
        "root-only clone stays root-only")
