"""A stored retrospective season plays back without a hub clone: scoring
reads the bundled locations list, and a week that has no observed data at
all answers with a plain message instead of a server error."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import playback, scoring


def test_truth_uses_the_bundled_locations_without_a_hub(tmp_path, monkeypatch):
    target = tmp_path / "target-data" / "target-hospital-admissions.csv"
    target.parent.mkdir(parents=True)
    target.write_text('date,location,location_name,value,weekly_rate\n'
                      '2026-01-03,"04","Arizona",120,1.6\n')
    monkeypatch.setattr(scoring, "HUB", tmp_path)   # no auxiliary-data/
    assert scoring.BUNDLED_LOCATIONS.is_file()
    truth, n2f = scoring.load_truth()
    assert n2f["Arizona"] == "04"
    assert list(truth.values()) == [120.0]


def test_playback_without_any_observed_data_is_not_a_server_error(monkeypatch):
    from app.ui import server
    from app.ui.routes import retro

    def no_truth(*a, **k):
        raise FileNotFoundError("no settled truth")
    monkeypatch.setattr(playback, "build_week", no_truth)
    r = TestClient(server.app).get("/api/retro/2025-26/playback/2026-01-03")
    assert r.status_code == 503
    assert r.text == retro.NO_TRUTH
