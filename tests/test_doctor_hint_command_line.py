"""`flubnf doctor` prints the hub hint's git command whole, on its own line,
in a narrow terminal too (review 3 of #93, re-check R2).

doctor._check_hub ends the hint with the command alone on its last line,
so a pasted line carries no comma. The CLI printed hints through rich,
which breaks a line at the terminal's width: at 80 columns the command
(about 100 characters with a home folder's hub path) came out as two
lines, and a paste of either ran a different command. The command line is
now printed with soft wrapping: the terminal folds it on screen, and the
text holds it as one line.
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from flubnf import doctor, settings
from flubnf.cli import app


@pytest.fixture
def hub_clone_lacking_data(tmp_path, monkeypatch):
    """A hub folder with its own .git and no data folders: doctor's git
    step (no git is run here)."""
    hub = tmp_path / "a folder with a long name" / "FluSight-forecast-hub"
    (hub / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "HUB", hub)
    return hub


@pytest.mark.parametrize("columns", ["60", "80", "200"])
def test_the_git_command_is_one_line_at_any_width(hub_clone_lacking_data,
                                                  monkeypatch, columns):
    hub = hub_clone_lacking_data
    res = doctor._check_hub("darwin")
    cmd = (f'git -C "{hub}" sparse-checkout add auxiliary-data '
           "target-data")
    assert res.hint.endswith("\n    " + cmd)
    assert len(cmd) > 80                     # longer than the narrow widths
    rep = doctor.DoctorReport()
    rep.add(res)
    monkeypatch.setattr(doctor, "run_doctor", lambda *, online=False: rep)
    out = CliRunner().invoke(app, ["doctor"], env={"COLUMNS": columns})
    assert out.exit_code == 1, out.output
    lines = out.stdout.splitlines()
    assert "    " + cmd in lines, out.stdout
    # the sentence before it is still there, and still wrapped as before
    text = " ".join(ln.strip() for ln in lines)
    assert "Or widen this clone with git:" in text
    assert "Run ./setup.sh: it makes or widens the sparse clone" in text


def test_a_one_line_hint_prints_as_before(monkeypatch):
    rep = doctor.DoctorReport()
    rep.add(doctor.CheckResult("check", doctor.Status.WARN, "detail",
                               "a hint on one line"))
    monkeypatch.setattr(doctor, "run_doctor", lambda *, online=False: rep)
    out = CliRunner().invoke(app, ["doctor"], env={"COLUMNS": "200"})
    assert out.exit_code == 0, out.output
    assert "  • check: a hint on one line" in out.stdout.splitlines()
