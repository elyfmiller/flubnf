"""Tests for flubnf.backfill_priors."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.backfill_priors import (BackfillOutcome, backfill_all,
                                    backfill_state, discover_states,
                                    observed_for_state, season_window)
from flubnf.constants import StateInfo
from flubnf.historical_priors import load_history


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _write_sorted_params(dirpath: Path, n_rows: int = 30,
                         param_cols: tuple[str, ...] = (
                             "b0__FREE", "gamma__FREE", "mult__FREE",
                             "r__FREE", "t0__FREE")) -> Path:
    """Write a PyBNF-format sorted_params_final.txt under dirpath."""
    rng = np.random.default_rng(0)
    results = dirpath / "Results"
    results.mkdir(parents=True, exist_ok=True)
    out = results / "sorted_params_final.txt"
    rows = []
    rows.append("\t".join(["#", "Simulation", "Obj", *param_cols]))
    obj = sorted(rng.uniform(100, 200, n_rows))
    for i in range(n_rows):
        params = [str(float(rng.uniform(0.1, 1.0))) for _ in param_cols]
        rows.append("\t".join(
            ["", f"gen0ind{i}", f"{obj[i]:.6f}", *params]
        ))
    out.write_text("\n".join(rows) + "\n")
    return out


def _make_target_csv(path: Path, *, onset: date, weeks: int = 30,
                     locations: list[tuple[str, str, list[float]]]) -> Path:
    """Build a minimal FluSight target-hospital-admissions.csv.

    `onset` is the MMWR-week Sunday (as pymmwr returns); we emit dates on
    the Saturday week-ending date to match the real FluSight schema.
    locations: [(fips, name, [value_per_week...])] — one row per (date, fips).
    """
    records = []
    for fips, name, values in locations:
        for i, v in enumerate(values[:weeks]):
            d = onset + timedelta(days=7 * i + 6)
            records.append(
                {"date": d.isoformat(), "location": fips,
                 "location_name": name, "value": v, "weekly_rate": 0.0}
            )
    df = pd.DataFrame.from_records(records)
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def fake_locations() -> dict[str, StateInfo]:
    return {
        "Alabama": StateInfo("Alabama", "AL", "01", 5_000_000),
        "Alaska": StateInfo("Alaska", "AK", "02", 700_000),
        "Arizona": StateInfo("Arizona", "AZ", "04", 7_000_000),
    }


# ---------------------------------------------------------------------------
# Pure-logic tests
# ---------------------------------------------------------------------------
class TestDiscoverStates:
    def test_finds_states_with_final_params(self, tmp_path: Path):
        _write_sorted_params(tmp_path / "Alabama")
        _write_sorted_params(tmp_path / "Alaska")
        (tmp_path / "Wyoming").mkdir()   # no Results
        assert discover_states(tmp_path) == ["Alabama", "Alaska"]

    def test_missing_root_returns_empty(self, tmp_path: Path):
        assert discover_states(tmp_path / "nope") == []

    def test_ignores_non_directories(self, tmp_path: Path):
        _write_sorted_params(tmp_path / "Alabama")
        (tmp_path / "stray.txt").write_text("nope")
        assert discover_states(tmp_path) == ["Alabama"]


class TestSeasonWindow:
    def test_onset_and_end_align_to_mmwr_week_start(self):
        onset, end = season_window(2024)
        # MMWR week 26 of 2024 → late June Sunday; MMWR week 47 of 2025 →
        # mid-Nov Sunday. pymmwr returns the Sunday week-start.
        assert end > onset
        assert onset.weekday() == 6
        assert end.weekday() == 6


class TestObservedForState:
    def test_extracts_in_season_values(self, tmp_path, fake_locations):
        onset, end = season_window(2024)
        values = [float(i + 1) for i in range(20)]   # 1..20
        target = _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=20,
            locations=[("01", "Alabama", values)],
        )
        df = pd.read_csv(target, dtype={"location": str})
        obs = observed_for_state(df, fake_locations["Alabama"], onset, end)
        # 20 weeks of consecutive data => 20 finite entries (no NaN gap).
        assert len(obs) == 20
        assert obs[0] == 1.0
        assert obs[-1] == 20.0

    def test_truncates_at_first_gap(self, tmp_path, fake_locations):
        onset, end = season_window(2024)
        # Skip week 5 → gap, should truncate.
        all_vals = [float(i + 1) for i in range(20)]
        target = _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=20,
            locations=[("01", "Alabama",
                       all_vals[:5] + [np.nan] + all_vals[6:])],
        )
        df = pd.read_csv(target, dtype={"location": str})
        # Drop the NaN row so CSV→pd doesn't carry it through directly.
        df = df.dropna(subset=["value"])
        obs = observed_for_state(df, fake_locations["Alabama"], onset, end)
        assert len(obs) == 5

    def test_no_rows_for_state_returns_empty(self, tmp_path, fake_locations):
        onset, end = season_window(2024)
        target = _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=10,
            locations=[("02", "Alaska", [1.0] * 10)],
        )
        df = pd.read_csv(target, dtype={"location": str})
        obs = observed_for_state(df, fake_locations["Alabama"], onset, end)
        assert obs.size == 0


# ---------------------------------------------------------------------------
# backfill_state
# ---------------------------------------------------------------------------
class TestBackfillState:
    def _setup(self, tmp_path, fake_locations):
        onset, end = season_window(2024)
        _write_sorted_params(tmp_path / "results" / "Alabama")
        _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=20,
            locations=[("01", "Alabama", list(range(1, 21)))],
        )
        target_df = pd.read_csv(tmp_path / "target.csv",
                                dtype={"location": str})
        return onset, end, target_df

    def test_records_history_entry(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        outcome = backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end,
        )
        assert outcome.status == "ok"
        assert outcome.peak == 20.0
        assert outcome.n_params == 5
        hist = load_history(tmp_path / "data", "Alabama")
        assert hist is not None
        assert len(hist.seasons) == 1
        assert hist.seasons[0].season_year == 2024

    def test_dry_run_writes_nothing(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        outcome = backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end, dry_run=True,
        )
        assert outcome.status == "ok"
        assert "dry-run" in outcome.message
        assert load_history(tmp_path / "data", "Alabama") is None

    def test_skip_when_year_already_present(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end,
        )
        # Second call without --force should skip.
        outcome = backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end,
        )
        assert outcome.status == "skipped-exists"

    def test_force_overwrites(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end,
        )
        outcome = backfill_state(
            tmp_path / "data", "Alabama", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end, force=True,
        )
        assert outcome.status == "ok"
        hist = load_history(tmp_path / "data", "Alabama")
        # Still only one entry for 2024 (record_season replaces, doesn't append).
        assert len([s for s in hist.seasons if s.season_year == 2024]) == 1

    def test_no_fit_status(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        # Point at an empty directory.
        empty = tmp_path / "results" / "Alaska"
        empty.mkdir(parents=True)
        outcome = backfill_state(
            tmp_path / "data", "Alaska", 2024,
            empty, target_df, fake_locations, onset, end,
        )
        assert outcome.status == "no-fit"

    def test_no_observed_status(self, tmp_path, fake_locations):
        # Build a fit but no target rows for this state.
        _write_sorted_params(tmp_path / "results" / "Alaska")
        onset, end = season_window(2024)
        # Target only has Alabama.
        _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=10,
            locations=[("01", "Alabama", [1.0] * 10)],
        )
        target_df = pd.read_csv(tmp_path / "target.csv",
                                dtype={"location": str})
        outcome = backfill_state(
            tmp_path / "data", "Alaska", 2024,
            tmp_path / "results" / "Alaska", target_df, fake_locations,
            onset, end,
        )
        assert outcome.status == "no-observed"

    def test_unknown_state_returns_error(self, tmp_path, fake_locations):
        onset, end, target_df = self._setup(tmp_path, fake_locations)
        outcome = backfill_state(
            tmp_path / "data", "Atlantis", 2024,
            tmp_path / "results" / "Alabama", target_df, fake_locations,
            onset, end,
        )
        assert outcome.status == "error"


# ---------------------------------------------------------------------------
# backfill_all
# ---------------------------------------------------------------------------
class TestBackfillAll:
    def test_walks_all_discovered_states(self, tmp_path, fake_locations):
        for s in ("Alabama", "Alaska", "Arizona"):
            _write_sorted_params(tmp_path / "results" / s)
        onset, end = season_window(2024)
        _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=10,
            locations=[
                ("01", "Alabama", [10.0] * 10),
                ("02", "Alaska", [3.0] * 10),
                ("04", "Arizona", [12.0] * 10),
            ],
        )
        outcomes = backfill_all(
            tmp_path / "data",
            season_year=2024,
            results_root=tmp_path / "results",
            target_csv=tmp_path / "target.csv",
            locations=fake_locations,
        )
        assert {o.state for o in outcomes} == {"Alabama", "Alaska", "Arizona"}
        assert all(o.status == "ok" for o in outcomes)

    def test_states_filter_restricts(self, tmp_path, fake_locations):
        for s in ("Alabama", "Alaska", "Arizona"):
            _write_sorted_params(tmp_path / "results" / s)
        onset, end = season_window(2024)
        _make_target_csv(
            tmp_path / "target.csv", onset=onset, weeks=10,
            locations=[
                ("01", "Alabama", [10.0] * 10),
                ("02", "Alaska", [3.0] * 10),
                ("04", "Arizona", [12.0] * 10),
            ],
        )
        outcomes = backfill_all(
            tmp_path / "data",
            season_year=2024,
            results_root=tmp_path / "results",
            target_csv=tmp_path / "target.csv",
            locations=fake_locations,
            states=["Alabama"],
        )
        assert [o.state for o in outcomes] == ["Alabama"]

    def test_missing_target_raises(self, tmp_path, fake_locations):
        with pytest.raises(FileNotFoundError):
            backfill_all(
                tmp_path / "data",
                season_year=2024,
                results_root=tmp_path / "results",
                target_csv=tmp_path / "nonexistent.csv",
                locations=fake_locations,
            )

    def test_empty_root_returns_empty(self, tmp_path, fake_locations):
        (tmp_path / "results").mkdir()
        (tmp_path / "target.csv").write_text(
            "date,location,location_name,value,weekly_rate\n"
        )
        outcomes = backfill_all(
            tmp_path / "data",
            season_year=2024,
            results_root=tmp_path / "results",
            target_csv=tmp_path / "target.csv",
            locations=fake_locations,
        )
        assert outcomes == []


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------
import re as _re

_ANSI_RE = _re.compile(r"\x1b\[[0-9;]*m")


def _plain(s: str) -> str:
    """Strip ANSI escapes — Rich emits per-char styles in CI."""
    return _ANSI_RE.sub("", s or "")


class TestBackfillCLI:
    def test_help_lists_options(self):
        from typer.testing import CliRunner
        from flubnf.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["backfill-priors", "--help"],
                                env={"NO_COLOR": "1"})
        assert result.exit_code == 0
        plain = _plain(result.stdout)
        assert "--source" in plain
        assert "--year" in plain
        assert "--dry-run" in plain
        assert "--force" in plain

    def test_missing_target_errors_cleanly(self, tmp_path):
        from typer.testing import CliRunner
        from flubnf.cli import app
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["backfill-priors",
             "--source", str(tmp_path / "results"),
             "--year", "2024",
             "--target", str(tmp_path / "nope.csv")],
            env={"NO_COLOR": "1"},
        )
        assert result.exit_code != 0
        combined = _plain((result.stdout or "") + (result.output or ""))
        assert "target CSV not found" in combined
