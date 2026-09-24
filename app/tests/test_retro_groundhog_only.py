"""The Groundhog-only retrospective: engine="analogue" replays the analogue
member alone (no cells, no engine venv) and stores a week every reader takes
as one member; it reproduces the Groundhog's published numbers in minutes.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import retro                               # noqa: E402
from app.core.engines import analogue as an              # noqa: E402

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL  # noqa: E402

SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"
#: a full 23-level fan per horizon (the scorer needs every FluSight level),
#: with the median at 5 + h so a reader can tell the horizons apart
AN_Q = {"Ohio": {h: {float(L): 5.0 + int(h) + 10.0 * (float(L) - 0.5)
                     for L in QL}
                 for h in ("0", "1", "2", "3")}}


def _no_pf(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the particle filter must not be touched")
    monkeypatch.setattr(retro.pf_engine, "prepare", boom)
    monkeypatch.setattr(retro.pf_engine, "collect", boom)
    monkeypatch.setattr(retro, "_launch_runners", boom)


def test_an_analogue_only_week_stores_the_one_member_and_no_cells(
        tmp_path, monkeypatch):
    _no_pf(monkeypatch)
    seen = []

    def fake_an(spec):
        seen.append(dict(spec.extra or {}))
        return {loc: {h: dict(q) for h, q in qs.items()}
                for loc, qs in AN_Q.items()}
    monkeypatch.setattr(retro.an_engine, "run", fake_an)
    root = tmp_path / SEASON
    out = retro.run_week(root, SEASON, W1, ["Ohio"], width=1,
                         engine="analogue",
                         extra={"aux_pools": an.shipped_aux_pools()})
    assert set(out) == {"asof", "analogue"}            # no pf block at all
    assert seen == [{"aux_pools": an.shipped_aux_pools()}]
    wd = root / "weeks" / W1
    assert retro.week_done(root, W1)
    assert not (wd / "cells_done").exists()
    assert json.loads((wd / "manifest.json").read_text())["engine"] == "analogue"
    # every reader sees one member
    mq = retro.week_member_quantiles(root, W1)
    assert set(mq) == {"analogue"}
    assert mq["analogue"]["Ohio"]["1"][0.5] == pytest.approx(6.0)
    rec = retro.read_week_samples(root, W1)
    assert "pf" not in rec and set(rec["analogue"]) == {"Ohio"}


def test_an_analogue_only_season_records_its_engine_and_donors(
        tmp_path, monkeypatch):
    _no_pf(monkeypatch)
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {loc: {h: dict(q) for h, q in qs.items()}
                                      for loc, qs in AN_Q.items()})
    root = tmp_path / SEASON
    done = retro.run_season(root, SEASON, ["Ohio"], width=1,
                            engine="analogue")
    assert done == [W1, W2]
    rec = retro.read_meta(root)["settings"]
    assert rec["engine"] == "analogue"
    assert rec["week_extra"] == "aux_preset:" + an.shipped_aux_label()
    # scoring sees the one member, and no blend row appears
    import pandas as pd
    monkeypatch.setattr("app.core.scoring.load_truth",
                        lambda: ({("39", pd.Timestamp(W1) + pd.Timedelta(days=7 * k)): 6.0
                                  for k in range(1, 6)}, {"Ohio": "39"}))
    monkeypatch.setattr("app.core.scoring._baseline_cells",
                        lambda asof, fips, truth: {(f, asof, h): 1.0
                                                   for f in fips
                                                   for h in range(4)})
    df = retro.score_season(root, SEASON)
    assert set(df.model.unique()) == {"analogue"}
    assert len(df) == 8                               # 2 weeks x 4 horizons


def test_the_engine_name_is_checked(tmp_path):
    with pytest.raises(ValueError, match="engine must be one of"):
        retro.run_week(tmp_path / SEASON, SEASON, W1, ["Ohio"], engine="pf2s")
    with pytest.raises(ValueError, match="engine must be one of"):
        retro.run_season(tmp_path / SEASON, SEASON, ["Ohio"], engine="nope")
