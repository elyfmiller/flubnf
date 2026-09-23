"""Backfill and reproduce: the member computed for every stored week of a
season root into a NEW root, never in place; and the relWIS tables the
reproduce command prints beside the screen's.

Offline: the source root, its vintages and its locations file are built
here; scoring against a hub is exercised only where the record is on the
machine (tests/test_oracle.py's record) and is otherwise the scorer's own
business (app/tests/test_retro_national.py and friends pin it).
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz                      # noqa: E402
from app.core import oracle as oracle_mod                # noqa: E402
from app.core import oracle_backfill as OBF              # noqa: E402
from app.core import retro                               # noqa: E402

WEEKS = ("2098-01-04", "2098-01-11")
FIPS = {"Ohio": "39", "Utah": "49", "California": "06", "Texas": "48"}


def _saturdays(first: date, last: date) -> list:
    d = first
    while d.weekday() != 5:
        d += timedelta(days=1)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out

def _synthetic_flusurv(monkeypatch, first: date, last: date) -> dict:
    """A FluSurv-NET bank over the synthetic hub's own seasons, put where
    flubnf.oracle_mix reads the committed one: the committed bank ends in
    2026 and shares no season with a hub of the 2090s, so no shrink could
    be fitted against it (the step raises then, by design)."""
    from flubnf import bank as BK
    from flubnf import oracle_mix as MX
    b = {}
    for i, d in enumerate(_saturdays(first, last)):
        for j, loc in enumerate(("ca", "co", "network_all")):
            b[(loc, d)] = round(1.9 + 0.8 * np.sin(2 * np.pi * (i + 5 * j) / 52.0)
                                + 0.05 * ((i * 7 + j) % 5), 4)
    man = {"stream": "flusurv", "digest": BK.digest(b), "cells": len(b)}
    monkeypatch.setattr(MX, "read_bank", lambda banks_dir=None: (b, man))
    return {"bank": b, "manifest": man}


@pytest.fixture
def source(tmp_path, monkeypatch):
    """A season root with two stored weeks (pf and analogue), a vintage
    per week and a locations file, the step pointed at them."""
    loc = tmp_path / "locations.csv"
    with open(loc, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["location", "abbreviation", "location_name", "population"])
        for name, f in FIPS.items():
            w.writerow([f, name[:2].upper(), name, 5_000_000])
    vint = {}
    for asof in WEEKS:
        T = date.fromisoformat(asof)
        vf = tmp_path / f"target-hospital-admissions_{asof}.csv"
        with open(vf, "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["date", "location", "location_name", "value"])
            for i, d in enumerate(_saturdays(date(2095, 8, 1), T)):
                for j, (name, f) in enumerate(FIPS.items()):
                    v = 80.0 + 50.0 * np.sin(2 * np.pi * (i + 6 * j) / 52.0) + 3 * j
                    w.writerow([d.isoformat(), f, name, round(v, 3)])
        vint[asof] = vf
    monkeypatch.setattr(oracle_mod, "LOCATIONS", loc)
    monkeypatch.setattr(oracle_mod, "vintage_path", lambda d: vint[d])
    _synthetic_flusurv(monkeypatch, date(2095, 8, 1), date.fromisoformat(max(WEEKS)))
    root = tmp_path / "src" / "2097-98"
    rng = np.random.default_rng(5)
    for asof in WEEKS:
        wd = root / "weeks" / asof
        wd.mkdir(parents=True)
        pf = {}
        for loc_name in ("Ohio", "Utah"):
            x0 = rng.gamma(30.0, 3.0, 300)
            pf[loc_name] = {hz.ORIGIN: x0.tolist(),
                            **{h: (x0 * np.exp(0.1 * (int(h) + 1))).tolist()
                               for h in hz.HORIZONS}}
        an = {"Ohio": {h: {"0.5": 100.0 + int(h), "0.025": 50.0, "0.975": 200.0}
                       for h in hz.HORIZONS}}
        retro.write_week_samples(wd, {"asof": asof, "pf": pf, "analogue": an,
                                      "pf_failures": {"Texas_r0": "FAIL: x"}})
    retro.write_meta(root, {"season": "2097-98", "status": "done",
                            "settings": {"engine": "pf", "particles": 100,
                                         "weeks_to_drop": 0, "season": "2097-98"}})
    return root


# ------------------------------------------------------------ the guard

def test_the_destination_is_never_the_source_the_seal_or_a_full_tree(source, tmp_path):
    with pytest.raises(ValueError, match="own source"):
        OBF.guard_out(source, source)
    with pytest.raises(ValueError, match="own source"):
        OBF.guard_out(source, source / "weeks" / "x")
    with pytest.raises(ValueError, match="app/state"):
        OBF.guard_out(source, OBF.REPO / "app" / "state" / "retro" / "2097-98")
    full = tmp_path / "full"
    full.mkdir()
    (full / "a").write_text("")
    with pytest.raises(ValueError, match="not empty"):
        OBF.guard_out(source, full)
    assert OBF.guard_out(source, full, force=True) == full.resolve()
    assert OBF.guard_out(source, tmp_path / "fresh") == (tmp_path / "fresh").resolve()


# ---------------------------------------------------------- the backfill

def test_backfill_writes_the_member_into_a_new_root_and_leaves_the_source(source, tmp_path):
    before = {p: p.stat().st_mtime_ns for p in source.rglob("*") if p.is_file()}
    out = tmp_path / "out" / "2097-98"
    log = []
    res = OBF.backfill_season(source, out, "2097-98",
                              progress=lambda a, m: log.append((a, m)))
    assert res["weeks"] == list(WEEKS) and res["skipped"] == []
    assert [a for a, _ in log] == list(WEEKS)
    # the source is untouched, byte for byte and file for file
    after = {p: p.stat().st_mtime_ns for p in source.rglob("*") if p.is_file()}
    assert after == before
    for asof in WEEKS:
        wd = out / "weeks" / asof
        src = retro.read_week_samples(source, asof)
        got = retro.read_week_samples(out, asof)
        assert set(got) == {"asof", "pf", "pf_filter", "analogue", "pf_failures"}
        assert got["pf_filter"] == src["pf"]                 # the source's pf, verbatim
        assert got["analogue"] == src["analogue"]
        assert got["pf_failures"] == src["pf_failures"]
        assert got["pf"]["Ohio"][hz.ORIGIN] == src["pf"]["Ohio"][hz.ORIGIN]
        assert got["pf"]["Ohio"]["0"] != src["pf"]["Ohio"]["0"]
        # the stored file keeps the stored convention: the anchor at "0"
        raw = retro.read_samples.__wrapped__ if hasattr(retro.read_samples, "__wrapped__") else None
        assert raw is None
        import gzip
        with gzip.open(wd / retro.SAMPLES_GZ, "rt") as fh:
            disk = json.load(fh)
        assert set(disk["pf"]["Ohio"]) == {"0", "1", "2", "3", "4"}
        assert disk["pf_filter"]["Ohio"]["0"] == src["pf"]["Ohio"][hz.ORIGIN]
        # the sidecar carries the shown members only
        assert set(retro.read_week_quantiles(wd)) == {"pf", "analogue"}
        # the provenance, with the backfill's own record folded in
        prov = oracle_mod.read_provenance(wd)
        assert prov["applied"] and prov["bank"]["label"].startswith("admissions-fbase@")
        assert prov["backfill"]["source_root"] == str(source.resolve())
        assert prov["backfill"]["source_samples_sha256"] == OBF._sha256(
            source / "weeks" / asof / retro.SAMPLES_GZ)
        assert (wd / oracle_mod.BANK_DIRNAME / f"paths_{asof}.csv").is_file()
    meta = retro.read_meta(out)
    assert meta["season"] == "2097-98" and meta["status"] == "done"
    assert meta["weeks_completed"] == 2 and meta["total_weeks"] == 2
    assert meta["settings"]["particles"] == 100          # the source's settings carried
    assert meta["settings"]["oracle"].startswith("applied (backfill")
    assert meta["backfill"]["source_root"] == str(source.resolve())
    assert meta["backfill"]["prereg_sha256"] == oracle_mod.OR.PREREG_SHA256
    # a second backfill into the same root is refused, and forced it reruns
    with pytest.raises(ValueError, match="not empty"):
        OBF.backfill_season(source, out, "2097-98")
    OBF.backfill_season(source, out, "2097-98", force=True)


def test_backfill_can_leave_the_filter_out_and_skips_a_week_without_pf(source, tmp_path):
    wd = source / "weeks" / "2098-01-18"
    wd.mkdir()
    retro.write_week_samples(wd, {"asof": "2098-01-18",
                                  "analogue": {"Ohio": {"0": {"0.5": 1.0}}}})
    out = tmp_path / "out"
    res = OBF.backfill_season(source, out, "2097-98", keep_filter=False)
    assert res["skipped"] == ["2098-01-18"] and res["weeks"] == list(WEEKS)
    got = retro.read_week_samples(out, WEEKS[0])
    assert "pf_filter" not in got and "pf" in got
    assert not (out / "weeks" / "2098-01-18").exists()
    assert retro.read_meta(out)["backfill"]["weeks_skipped"] == ["2098-01-18"]


# --------------------------------------------------------- the tables

def _frame():
    rows = []
    for season, asofs in (("2024-25", ["a", "b"]), ("2025-26", ["c"])):
        for asof in asofs:
            for h in (0, 1):
                rows.append({"model": "pf", "location": "Ohio", "fips": "39", "asof": asof,
                             "horizon": h, "wis": 2.0, "base_wis": 4.0, "season": season})
                rows.append({"model": "analogue", "location": "Ohio", "fips": "39", "asof": asof,
                             "horizon": h, "wis": 1.0, "base_wis": 4.0, "season": season})
            # a cell the Groundhog scored and the filter did not
            rows.append({"model": "analogue", "location": "Utah", "fips": "49", "asof": asof,
                         "horizon": 0, "wis": 8.0, "base_wis": 4.0, "season": season})
    return pd.DataFrame(rows)


def test_relwis_tables_state_both_cell_sets_with_their_counts():
    t = OBF.relwis_tables(_frame())
    assert set(t) == {"2024-25", "2025-26", "all"}
    a = t["all"]
    assert a["record"]["pf"] == {"relwis": 0.5, "cells": 6}
    assert a["record"]["analogue"]["cells"] == 9
    assert a["record"]["analogue"]["relwis"] == pytest.approx((6 * 1.0 + 3 * 8.0) / 36.0)
    assert a["common"]["pf"] == {"relwis": 0.5, "cells": 6}
    assert a["common"]["analogue"] == {"relwis": 0.25, "cells": 6}
    assert t["2025-26"]["record"]["pf"]["cells"] == 2
    assert OBF.relwis_tables(pd.DataFrame()) == {}


def test_report_lines_put_the_screen_beside_each_scope(tmp_path):
    screen = {"seeds": [2026091801, 2026091802],
              "frozen_document_sha256": "abc",
              "relwis_tables": {
                  "LB": {"common": {"2024-25": 0.71, "2025-26": 0.77, "active2": 0.74},
                         "native": {"active2": 0.7409, "pooled3": 0.761}, "native_cells": 15300,
                         "per_seed_common": {"active2": [0.7408, 0.7409]}},
                  "NULL": {"common": {"active2": 0.8135}, "native": {"active2": 0.8135}},
                  "LB25": {}}}
    sp = tmp_path / "screen.json"
    sp.write_text(json.dumps(screen))
    res = {"member": OBF.relwis_tables(_frame()), "null": OBF.relwis_tables(_frame()),
           "screen": OBF.screen_tables(sp)}
    lines = OBF.report_lines(res)
    text = "\n".join(lines)
    assert "all:" in text and "2024-25:" in text
    assert "screen LB common (seed mean) 0.7400, seed 2026091801 0.7408" in text
    assert "screen LB native (seed mean) 0.7409" in text and "native cells 15300" in text
    assert "screen NULL common 0.8135" in text
    assert "on 6 cells" in text and "on 9 cells" in text
    assert res["screen"]["LB"]["native_cells"] == 15300


def test_score_root_read_only_refuses_a_stale_sidecar(source, monkeypatch):
    assert OBF.sidecars_current(source)
    wd = source / "weeks" / WEEKS[0]
    (wd / retro.QUANTILES_NAME).unlink()
    assert not OBF.sidecars_current(source)
    with pytest.raises(ValueError, match="refused"):
        OBF.score_root(source, "2097-98", read_only=True)
    assert not (wd / retro.QUANTILES_NAME).exists()          # nothing written


# -------------------------------------------------------------- the CLI

def test_the_cli_backfills_and_refuses_the_wrong_destination(source, tmp_path):
    from typer.testing import CliRunner
    from flubnf.cli import app as cli_app
    runner = CliRunner()
    out = tmp_path / "cli_out" / "2097-98"
    r = runner.invoke(cli_app, ["oracle", "backfill", "2097-98", "--source", str(source),
                               "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "2 weeks backfilled" in r.output
    assert retro.read_meta(out)["backfill"]["source_root"] == str(source.resolve())
    r = runner.invoke(cli_app, ["oracle", "backfill", "2097-98", "--source", str(source),
                               "--out", str(source)])
    assert r.exit_code == 2 and "own source" in r.output
    r = runner.invoke(cli_app, ["oracle", "backfill", "2097-98", "--source", str(source),
                               "--out", str(out)])
    assert r.exit_code == 2 and "not empty" in r.output


def test_the_cli_reproduce_refuses_a_source_with_a_stale_sidecar(source, tmp_path):
    from typer.testing import CliRunner
    from flubnf.cli import app as cli_app
    runner = CliRunner()
    out = tmp_path / "cli_out" / "2097-98"
    OBF.backfill_season(source, out, "2097-98")
    (source / "weeks" / WEEKS[0] / retro.QUANTILES_NAME).unlink()
    r = runner.invoke(cli_app, ["oracle", "reproduce", str(out), "--source", str(source)])
    assert r.exit_code == 2 and "refused" in r.output
    assert not (source / "weeks" / WEEKS[0] / retro.QUANTILES_NAME).exists()
