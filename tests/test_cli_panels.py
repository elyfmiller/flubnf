"""`flubnf --help` panels: every top-level command sits in exactly one
HELP_PANELS panel, an unlisted command stops the group from building, and
the removed legacy DE/AMCMC workspace commands are gone (usage error, 2)."""
from __future__ import annotations

import re

import pytest
import typer
from typer.testing import CliRunner

from flubnf.cli import HELP_PANELS, _PanelledGroup, app

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

REMOVED = ("init", "fetch", "update-exp", "update-files", "analyze",
           "backtest", "weekly-job", "score-team", "validate-submission",
           "clean-cache", "record-season", "backfill-priors", "tune-slope",
           "baseline-score", "compare", "run", "status")


def _help() -> str:
    r = runner.invoke(app, ["--help"], env={"NO_COLOR": "1"},
                      terminal_width=200)
    assert r.exit_code == 0, r.output
    return _ANSI.sub("", r.output)


def test_every_command_is_in_exactly_one_panel():
    group = typer.main.get_command(app)
    listed = [n for names in HELP_PANELS.values() for n in names]
    assert len(listed) == len(set(listed)), "a command is in two panels"
    assert sorted(group.commands) == sorted(listed)
    for name, cmd in group.commands.items():
        assert name in HELP_PANELS[cmd.rich_help_panel]


def test_help_shows_the_three_panels_in_order_and_no_legacy_panel():
    out = _help()
    assert list(HELP_PANELS) == ["Console", "Replay & verification",
                                 "Donor banks"]
    at = [out.index(f"─ {p} ") for p in HELP_PANELS]
    assert at == sorted(at)
    assert "Legacy" not in out
    assert "DE/AMCMC" not in out


def test_an_unlisted_command_refuses_to_build():
    stray = typer.Typer(cls=_PanelledGroup, add_completion=False)

    @stray.command("app")
    def _listed():
        pass

    @stray.command("stray")
    def _unlisted():
        pass

    with pytest.raises(RuntimeError, match="'stray' is not listed"):
        typer.main.get_command(stray)


@pytest.mark.parametrize("name", REMOVED)
def test_removed_legacy_commands_are_usage_errors(name):
    r = runner.invoke(app, [name])
    assert r.exit_code == 2, r.output
