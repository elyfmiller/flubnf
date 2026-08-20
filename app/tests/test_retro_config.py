"""Retro tab configuration, fitted-parameter harvest, season derivation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------- params harvest

def _write_params_cell(root, loc, rep, names, rows):
    d = root / f"{loc}_r{rep}"
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    body = "\n".join(" ".join(f"{v:.6e}" for v in r) for r in rows)
    (runs / f"params_{rep}.txt").write_text("\t".join(names) + "\n" + body + "\n")
    return {"key": f"{loc}_r{rep}", "dir": str(d), "location": loc,
            "replicate": rep}


def test_params_harvest_pools_reps_and_strips_suffix(tmp_path):
    from app.ui.server import _harvest_params
    names = ["Reff__FREE", "mult__FREE"]
    cells = [
        _write_params_cell(tmp_path, "Ohio", 0, names,
                           [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0)]),
        _write_params_cell(tmp_path, "Ohio", 1, names,
                           [(5.0, 50.0), (6.0, 60.0), (7.0, 70.0)]),
        # a cell whose params file is missing must not break the harvest
        {"key": "Utah_r0", "dir": str(tmp_path / "nope"),
         "location": "Utah", "replicate": 0},
    ]
    (tmp_path / "cells.json").write_text(json.dumps(cells))
    out = _harvest_params(tmp_path)
    assert set(out) == {"Ohio"}                 # Utah absent, not fatal
    assert out["Ohio"]["Reff"] == 4.0           # median over BOTH replicates
    assert out["Ohio"]["mult"] == 40.0
    assert "Reff__FREE" not in out["Ohio"]      # suffix stripped


def test_params_harvest_without_cells_is_empty(tmp_path):
    from app.ui.server import _harvest_params
    assert _harvest_params(tmp_path) == {}


# ------------------------------------------------------------- season derivation

def test_available_seasons_derives_from_archive(tmp_path, monkeypatch):
    from app.core import retro
    for v in ("2027-10-04", "2028-01-10", "2028-11-02", "2027-07-03"):
        (tmp_path / f"target-hospital-admissions_{v}.csv").write_text("x")
    monkeypatch.setattr(retro, "ARCHIVE", tmp_path)
    # 2027-07-03 sits outside every season window: no phantom season
    assert retro.available_seasons() == ["2027-28", "2028-29"]


def test_available_seasons_falls_back_when_archive_empty(tmp_path, monkeypatch):
    from app.core import retro
    monkeypatch.setattr(retro, "ARCHIVE", tmp_path)
    assert retro.available_seasons() == sorted(retro.SEASON_BOUNDS)


def test_season_bounds_formulaic_beyond_hardcoded_list():
    from app.core.retro import SEASON_BOUNDS, season_bounds
    assert season_bounds("2023-24") == SEASON_BOUNDS["2023-24"]
    assert season_bounds("2030-31") == ("2030-08-01", "2031-06-15")


# ------------------------------------------------------------------- form render

def test_retro_form_offers_full_config():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/retro")
    assert r.status_code == 200
    for needle in ('name="season"', 'name="locations"', 'name="particles"',
                   'name="replicates"', 'name="width"', 'name="engine"',
                   'name="custom_locations"'):
        assert needle in r.text, needle
    assert 'value="10000"' in r.text            # particles default
    assert "Wyoming" in r.text                  # custom checklist populated
    assert 'value="custom"' in r.text           # custom scope offered
