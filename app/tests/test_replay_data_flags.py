"""A replay records the weeks its missing-data rules flagged
(app/core/missing.py; data.trailing_zero, data.partial_week), as a console
run does in its outcome's data_flags.

  * the FluSight replay (app/core/retro.py): run_meta.json "data_flags",
    {as-of: {member: [{location, week, value, rule}]}}, one entry per
    replayed week, and a "flagged weeks" count in the replay's settings;
  * the own-data replay (app/core/custom_retro.py): the same key in its
    run_meta.json, and the same count on its page.

With no rule on nothing is recorded and the settings are as before.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from app.core import custom_retro as CX
from app.core import datasets as D
from app.core import knobs as K
from app.core import missing as MS
from app.core import retro
from app.core.engines import analogue as EA

from test_datasets_ui import client, isolated, stored    # noqa: F401
from test_dataset_engines import grouped_bytes            # noqa: E402
from test_retro_fit_level import SEASON, W1, _stub_engines  # noqa: E402

ON = {"knobs": {"data.trailing_zero": "missing"}}
ROW = {"week": W1, "rule": "trailing zero", "value": 0.0}


# --- the helpers -------------------------------------------------------------------

def test_cell_flags_reads_replicate_zero_only():
    cells = [{"location": "Ohio", "replicate": 0, "data_flags": [ROW]},
             {"location": "Ohio", "replicate": 1, "data_flags": [ROW]},
             {"location": "Utah", "replicate": 0}]
    assert MS.cell_flags(cells) == [{"location": "Ohio", **ROW}]
    assert MS.cell_flags([]) == [] and MS.cell_flags(None) == []


def test_replay_count():
    assert MS.replay_count(None) == "" and MS.replay_count({}) == ""
    assert MS.replay_count({"2098-11-07": {"analogue": [], "pf": []}}) == \
        "on; no week flagged"
    both = [{"location": "Ohio", **ROW}]
    got = MS.replay_count({"2098-11-07": {"analogue": both, "pf": both},
                           "2098-11-14": {"analogue": []}})
    # the members' rows for one location and week count once
    assert got == ("1 newest week treated as unreported, in 1 of 2 "
                   "forecast weeks")


# --- the FluSight replay -----------------------------------------------------------

def _flagging_engines(monkeypatch):
    """_stub_engines' filter and Groundhog, with a flagged week each."""
    _stub_engines(monkeypatch, [])

    def fake_prepare(spec, wd):
        cells = [{"key": "Ohio_r0", "dir": str(Path(wd) / "Ohio_r0"),
                  "location": "Ohio", "replicate": 0,
                  **({"data_flags": [ROW]} if MS.rules_of(spec.extra)
                     else {})}]
        (Path(wd) / "cells.json").write_text(json.dumps(cells))
        return cells
    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)

    def fake_an(spec, flags=None):
        if flags is not None:
            flags.append({"location": "Ohio", **ROW})
        return {"Ohio": {"1": {0.5: 2.0}}}
    monkeypatch.setattr(retro.an_engine, "run", fake_an)


def test_a_replayed_week_records_its_flagged_weeks(tmp_path, monkeypatch):
    _flagging_engines(monkeypatch)
    root = tmp_path / SEASON
    retro.run_week(root, SEASON, W1, ["Ohio"], width=1, extra=dict(ON))
    want = [{"location": "Ohio", **ROW}]
    assert retro.read_meta(root)["data_flags"] == {
        W1: {"analogue": want, "pf": want}}
    assert ("flagged weeks", "1 newest week treated as unreported, in 1 of "
            "1 forecast week") in retro.settings_summary(
        {**retro.read_meta(root), "settings": {"season": SEASON}})


def test_a_shipped_replay_records_nothing(tmp_path, monkeypatch):
    _flagging_engines(monkeypatch)
    root = tmp_path / SEASON
    retro.run_week(root, SEASON, W1, ["Ohio"], width=1)
    assert "data_flags" not in retro.read_meta(root)
    assert all(k != "flagged weeks" for k, _ in retro.settings_summary(
        {**retro.read_meta(root), "settings": {"season": SEASON}}))


def test_a_groundhog_season_records_every_week(tmp_path, monkeypatch):
    """engine "analogue", through run_season and the knob channel."""
    W2 = "2098-11-14"
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def fake_an(spec, flags=None):
        if flags is not None and spec.forecast_date == W2:
            flags.append({"location": "Ohio", **dict(ROW, week=W2)})
        return {"Ohio": {"1": {0.5: 2.0}}}
    monkeypatch.setattr(retro.an_engine, "run", fake_an)
    nd = {"data.trailing_zero": "missing"}
    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue",
                     week_extra=K.retro_week_extra(
                         EA.aux_preset(EA.SHIPPED_AUX), nd),
                     settings={"knobs": nd})
    meta = retro.read_meta(root)
    assert meta["data_flags"] == {
        W1: {"analogue": []},
        W2: {"analogue": [{"location": "Ohio", **dict(ROW, week=W2)}]}}
    assert ("flagged weeks", "1 newest week treated as unreported, in 1 of "
            "2 forecast weeks") in retro.settings_summary(meta)


# --- the own-data replay -----------------------------------------------------------

def _zero_tail_dataset(name="zero"):
    """Pediatric and Adult through 2023-12-02; Adult's newest week reads 0
    (the trailing-zero rule's case)."""
    lines = grouped_bytes(groups=("Pediatric", "Adult"),
                          end=date(2023, 12, 2)).decode().strip().split("\n")
    i = max(j for j, ln in enumerate(lines) if ",Adult," in ln)
    lines[i] = re.sub(r",Adult,[^,]*", ",Adult,0", lines[i])
    return ("\n".join(lines) + "\n").encode()


def test_an_own_data_replay_records_and_shows_its_flagged_weeks():
    ds = stored(_zero_tail_dataset(), "Zero")
    weeks = ["2023-11-25", "2023-12-02"]
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    meta = CX.run(ds, weeks, ds.groups, out_dir=out,
                  extra=K.write_extra({"data.trailing_zero": "missing"}, {}))
    assert meta["status"] == "done"
    assert meta["data_flags"] == {
        "2023-11-25": {"analogue": []},
        "2023-12-02": {"analogue": [{"location": "Adult", "rule":
                                     "trailing zero", "week": "2023-12-02",
                                     "value": 0.0}]}}
    assert json.loads((out / CX.META).read_text())["data_flags"] == \
        meta["data_flags"]
    page = " ".join(client.get(f"/retro/dataset/{ds.id}/{out.name}")
                    .text.split())
    assert ("<dt>flagged weeks</dt><dd>1 newest week treated as unreported, "
            "in 1 of 2 forecast weeks</dd>") in page


def test_a_shipped_own_data_replay_records_nothing():
    ds = stored(_zero_tail_dataset(), "Zero")
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    meta = CX.run(ds, ["2023-12-02"], ds.groups, out_dir=out)
    assert "data_flags" not in meta
    page = client.get(f"/retro/dataset/{ds.id}/{out.name}").text
    assert "flagged weeks" not in page
