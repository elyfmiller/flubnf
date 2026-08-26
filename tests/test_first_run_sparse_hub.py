"""A hub clone that exists but holds no data must never read as ready.

Field report, 2026-08-25 (Windows 11, git 2.45.2.windows.1): the corresponding
author cloned the FluSight hub by hand with

    git clone --filter=blob:none --sparse --depth 1 <hub> <path>

which succeeded. `--sparse` is documented to check out only the files in the
repository ROOT, so that clone contains no `auxiliary-data/`, no
`target-data/` and no `model-output/`. Every gate in the project then tested
for the clone rather than for its contents:

  * `flubnf.settings.check()` tested `HUB.exists()` and printed
    "all externals present -- you are ready" over the empty clone,
  * `FluBNF.bat` tested `%HUBDIR%\\.git` and stopped offering setup,
  * `setup.ps1` / `setup.sh` said "hub present" and ran `sparse-checkout
    reapply`, which re-applies the recorded cone and so re-applies nothing.

Measured on git 2.39.5 against a local fixture shaped like the hub: after a
`--sparse` clone the working tree holds the root file only; `reapply` adds
nothing; `sparse-checkout add` brings the directories in and is idempotent;
`sparse-checkout set` against a FULL clone deletes every directory not named,
which is why the repair uses `add`.

The two setup scripts cannot be executed here (the lab develops on macOS and
`setup.ps1` needs a PowerShell interpreter this machine does not have), so
they are checked as text. Windows CI executes `setup.ps1` for real.
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
    """Run flubnf.settings.check() in a fresh interpreter against `hub`.

    A subprocess, not monkeypatch: settings resolves its paths at import, and
    reloading it mid-session would leave every module that already imported
    HUB pointing at the old object.
    """
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
    """The .bat bounds its own question (choice /t 20 /d N); the script it
    hands off to must not then ask one with no timeout. setup.ps1 offers a
    winget install of Strawberry Perl via Read-Host whenever it decides the
    session is interactive, which a double-clicked .bat is."""
    bat = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
    launch = [l for l in bat.splitlines()
              if "setup.ps1" in l and l.lstrip().lower().startswith("powershell")]
    assert launch, "FluBNF.bat no longer runs setup.ps1 at all"
    for line in launch:
        assert "-NoPrompt" in line, (
            f"FluBNF.bat runs setup.ps1 without -NoPrompt: {line.strip()!r}. "
            "A double-click would then stop at Read-Host with no timeout.")


def test_setup_scripts_widen_an_existing_cone_with_add_not_set():
    """`add` extends a cone and fails harmlessly on a full clone; `set`
    silently prunes every directory it is not given. Both scripts must repair
    an existing clone, and must do it with `add`."""
    for name, needle in (("setup.ps1", '"sparse-checkout", "add"'),
                         ("setup.sh", "git sparse-checkout add")):
        src = (REPO / name).read_text(encoding="utf-8")
        assert needle in src, (
            f"{name} never runs sparse-checkout add, so a clone made with "
            f"--sparse is left holding only the repository root")
        for d in HUB_DIRS:
            assert d in src, f"{name} no longer names {d}"


def test_setup_ps1_only_narrows_the_cone_on_a_clone_it_just_made():
    """`sparse-checkout set` is safe exactly once: on the clone created one
    statement earlier, whose cone is empty and whose contents are nobody's.
    Anywhere else it would delete a deliberate full checkout."""
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
    """Ordering is the whole point: reapply re-applies the recorded cone, so
    it can never add a directory the cone never held."""
    src = (REPO / "setup.ps1").read_text(encoding="utf-8")
    repair = src.index("Repair-HubCone $Hub $HubDirs")
    reapply = src.index('"sparse-checkout", "reapply"')
    assert repair < reapply, (
        "setup.ps1 reapplies the sparse cone before widening it, so a "
        "root-only clone stays root-only")
