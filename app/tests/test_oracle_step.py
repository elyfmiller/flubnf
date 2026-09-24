"""The Oracle step at the storage boundary: the member under pf, the
filter's own samples under the research key, provenance beside the week,
the plain-filter research run, and the two call sites. Hub-free: every test
builds its own tiny vintage and locations file.
"""
import csv
import gzip
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz                      # noqa: E402
from app.core import oracle as oracle_mod                # noqa: E402
from app.core import reclaim, retro                      # noqa: E402
from app.core.runs import RunSpec, is_research, spec_settings   # noqa: E402
from flubnf import oracle as OR                          # noqa: E402
from flubnf import oracle_bank as OB                     # noqa: E402
from flubnf import oracle_mix as MX                      # noqa: E402

ASOF = "2098-01-04"                                       # a Saturday
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
    """A synthetic FluSurv-NET bank over the synthetic hub's seasons, patched
    where oracle_mix reads the committed one (which shares no season with a
    2090s hub, so no shrink could be fitted)."""
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
def hubfiles(tmp_path, monkeypatch):
    """A locations.csv and a vintage for ASOF with two donor seasons, and
    the step pointed at them."""
    loc = tmp_path / "locations.csv"
    with open(loc, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["location", "abbreviation", "location_name", "population"])
        for name, f in FIPS.items():
            w.writerow([f, name[:2].upper(), name, 5_000_000])
        w.writerow(["US", "US", "US", 330_000_000])
    T = date.fromisoformat(ASOF)
    assert T.weekday() == 5
    vf = tmp_path / f"target-hospital-admissions_{ASOF}.csv"
    with open(vf, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "location", "location_name", "value"])
        for i, d in enumerate(_saturdays(date(2095, 8, 1), T)):
            for j, (name, f) in enumerate(list(FIPS.items()) + [("US", "US")]):
                v = 80.0 + 50.0 * np.sin(2 * np.pi * (i + 6 * j) / 52.0) + 3 * j
                w.writerow([d.isoformat(), f, name, round(v, 3)])
    monkeypatch.setattr(oracle_mod, "LOCATIONS", loc)
    monkeypatch.setattr(oracle_mod, "vintage_path", lambda d: vf)
    aux = _synthetic_flusurv(monkeypatch, date(2095, 8, 1), T)
    return {"locations": loc, "vintage": vf, "aux": aux}


def _samples(locs=("Ohio", "Utah", "US"), n=400, seed=1) -> dict:
    """collect()'s shape: canonical horizons, the anchor under ORIGIN."""
    rng = np.random.default_rng(seed)
    out = {}
    for loc in locs:
        x0 = rng.gamma(30.0, 3.0, n)
        out[loc] = {hz.ORIGIN: x0.tolist(),
                    **{h: (x0 * np.exp(0.08 * (int(h) + 1))
                           * rng.lognormal(0, 0.05, n)).tolist() for h in hz.HORIZONS}}
    return out


# ---------------------------------------------------------------- the step

def test_apply_week_stores_the_member_and_writes_the_provenance(hubfiles, tmp_path):
    raw = _samples()
    wd = tmp_path / "week"
    member, prov = oracle_mod.apply_week(raw, ASOF, wd)
    # the member: every location, the anchor untouched, the forecasts moved
    assert set(member) == {"Ohio", "Utah", "US"}
    for loc in ("Ohio", "Utah"):
        assert member[loc][hz.ORIGIN] == raw[loc][hz.ORIGIN]
        for h in hz.HORIZONS:
            assert len(member[loc][h]) == len(raw[loc][h])
            assert member[loc][h] != raw[loc][h]
    # the US row is outside the registered member: untouched, and said so
    assert member["US"] == raw["US"]
    assert prov["locations"]["US"]["reason"].startswith("outside the registered member")
    assert prov["cells"]["outside_member"] == ["US"]
    # the library's own answer, bit for bit: the mixture of the two written
    # halves (bank change B2)
    pool, man = OB.read_pool(wd / oracle_mod.BANK_DIRNAME, ASOF)
    araw, aman = MX.read_pool(wd / oracle_mod.BANK_DIRNAME, ASOF)
    auxp = MX.shrunk_pool(araw, aman["shrink"])
    r = OR.member_for_cell(raw["Ohio"][hz.ORIGIN], [raw["Ohio"][h] for h in hz.HORIZONS],
                           pool, date.fromisoformat(ASOF), "39", aux_pool=auxp)
    assert r.active and r.w_aux == 0.5 and 0 < r.n_aux_drawn < len(raw["Ohio"]["0"])
    for hi, h in enumerate(hz.HORIZONS):
        assert member["Ohio"][h] == r.samples[hi].tolist()
    lb = OR.member_for_cell(raw["Ohio"][hz.ORIGIN], [raw["Ohio"][h] for h in hz.HORIZONS],
                            pool, date.fromisoformat(ASOF), "39")
    # the provenance
    fp = wd / oracle_mod.PROVENANCE_NAME
    assert fp.is_file() and json.loads(fp.read_text()) == prov
    assert prov["applied"] is True and prov["member"] == "Oracle SIHRS"
    assert prov["prereg_sha256"] == OR.PREREG_SHA256
    assert prov["b2_sha256"] == OR.B2_SHA256
    assert prov["addendum_a2_sha256"] == OR.ADDENDUM_A2_SHA256
    aux_digest = hubfiles["aux"]["manifest"]["digest"]
    assert prov["bank"]["label"] == f"admissions-fbase@{man['digest'][:8]}+flusurv@{aux_digest[:8]}"
    assert prov["bank"]["stream"] == MX.STREAM == "admissions-fbase+flusurv"
    ba, bx, bm = prov["bank"]["admissions"], prov["bank"]["flusurv"], prov["bank"]["mixture"]
    assert ba["digest"] == man["digest"] and ba["n_paths"] == pool["n"] and ba["admissible"]
    assert bx["bank_digest"] == aux_digest and bx["pool_digest"] == aman["digest"]
    assert bx["n_paths"] == araw["n"] >= 30 and bx["admissible"]
    assert bx["shrink"] == aman["shrink"] and 0 < bx["shrink"] and bx["shrink_prior_seasons"]
    assert bm == {"identity_rule": "R_EITHER", "state": "both", "w_aux": 0.5, "w_aux_nominal": 0.5}
    assert prov["vintage"]["sha256"] == OB.sha256_file(hubfiles["vintage"])
    assert prov["rule_flusurv"]["count_floor"] is None and prov["rule_flusurv"]["w_aux"] == 0.5
    assert prov["rule"]["name"] == "FBASE" and prov["rule"]["bandwidth"] == 2
    assert prov["rule"]["min_donors"] == 30 and prov["rule"]["min_donor_seasons"] == 2
    assert prov["rule"]["floor_weeks"] == [-1, 0, 1, 2] and prov["rule"]["path_weeks"] == list(range(-1, 7))
    assert prov["w"] == 0.5 and prov["w_secondary"] == 0.25
    assert prov["seeds"] == list(OR.SEEDS) and prov["submitted_seed"] == 2026091801
    assert prov["reading"] == "F" and prov["transform"] == "REPLACE"
    assert prov["trimmed_weeks"]["k_by_location"] == {"Ohio": 0, "Utah": 0, "US": 0}
    assert "the spec" in prov["trimmed_weeks"]["source"]
    o = prov["locations"]["Ohio"]
    assert o["fips"] == "39" and o["eligible"] and o["active"] == 1
    assert o["state"] == "both" and o["w_aux"] == 0.5 and o["n_flusurv_drawn"] == r.n_aux_drawn
    assert o["m_0"] == float(np.median(raw["Ohio"][hz.ORIGIN]))
    assert o["y_T"] is not None and o["m0_over_yT"] == o["m_0"] / o["y_T"]
    assert o["abstentions"] == 0 and o["guard_hits"] == 0
    assert prov["cells"] == {"locations": 3, "eligible": 2, "active": 2,
                             "identity_pool": [], "not_eligible": [], "outside_member": ["US"]}
    q = prov["quantiles"]
    assert q["levels"] == OR.QL and set(q["null"]) == {"Ohio", "Utah"}
    assert set(q["primary"]["per_seed"]) == {str(s) for s in OR.SEEDS}
    assert set(q["secondary"]["per_seed"]) == {str(s) for s in OR.SEEDS}
    for s in OR.SEEDS:
        blk = q["primary"]["per_seed"][str(s)]["Ohio"]
        assert set(blk) == {"0", "1", "2", "3"}
        assert blk["0"]["internal_h"] == 1 and len(blk["0"]["unrounded"]) == 23
        assert blk["0"]["unrounded"] == [float(z) for z in r.q_seed[s][0]]
    assert q["null"]["Ohio"]["3"]["unrounded"] == [float(z) for z in r.q_null[3]]
    # the admissions-only member (LB), logged beside the primary
    assert q["primary"]["bank"] == "admissions-fbase+flusurv"
    assert q["admissions_only"]["bank"] == "admissions-fbase"
    for s in OR.SEEDS:
        assert q["admissions_only"]["per_seed"][str(s)]["Ohio"]["2"]["unrounded"] == \
            [float(z) for z in lb.q_seed[s][2]]
    assert q["horizons"]["table"][0]["flusight_horizon"] == -1
    assert [t["flusight_horizon"] for t in q["horizons"]["table"][1:]] == [0, 1, 2, 3]
    assert q["horizons"]["reference_date"] == "2098-01-11"


def test_k_comes_from_cells_json_when_the_week_has_one(hubfiles, tmp_path):
    wd = tmp_path / "week"
    wd.mkdir()
    (wd / "cells.json").write_text(json.dumps([
        {"key": "Ohio_r0", "location": "Ohio", "weeks_dropped": 1},
        {"key": "Ohio_r1", "location": "Ohio", "weeks_dropped": 2},
        {"key": "Utah_r0", "location": "Utah", "weeks_dropped": 0}]))
    _, prov = oracle_mod.apply_week(_samples(), ASOF, wd, weeks_to_drop=3)
    assert prov["trimmed_weeks"]["k_by_location"] == {"Ohio": 2, "Utah": 0, "US": 3}
    assert prov["trimmed_weeks"]["source"].startswith("cells.json")


def test_an_ineligible_cell_is_the_identity_and_named(hubfiles, tmp_path):
    raw = _samples()
    raw["Utah"] = {h: [0.0] * 50 for h in (hz.ORIGIN, *hz.HORIZONS)}
    member, prov = oracle_mod.apply_week(raw, ASOF, tmp_path / "w")
    assert member["Utah"] == raw["Utah"]
    assert prov["cells"]["not_eligible"] == ["Utah"] and prov["cells"]["active"] == 1
    assert prov["locations"]["Utah"]["active"] == 0


def test_a_missing_vintage_raises_rather_than_shipping_the_identity(hubfiles, tmp_path, monkeypatch):
    def gone(d):
        raise FileNotFoundError("No vintage for " + d)
    monkeypatch.setattr(oracle_mod, "vintage_path", gone)
    with pytest.raises(FileNotFoundError):
        oracle_mod.apply_week(_samples(), ASOF, tmp_path / "w")
    assert not (tmp_path / "w" / oracle_mod.PROVENANCE_NAME).exists()


def test_a_missing_or_unfittable_flusurv_half_raises(hubfiles, tmp_path, monkeypatch):
    """No silent fallback to the admissions-only member: an unreadable bank
    or unfittable shrink stops the week."""
    def gone(banks_dir=None):
        raise FileNotFoundError("no committed 'flusurv' donor bank")
    monkeypatch.setattr(MX, "read_bank", gone)
    with pytest.raises(FileNotFoundError):
        oracle_mod.apply_week(_samples(), ASOF, tmp_path / "w")
    assert not (tmp_path / "w" / oracle_mod.PROVENANCE_NAME).exists()
    # the committed bank ends in 2026: against a hub of the 2090s it shares
    # no season, so the shrink cannot be fitted
    monkeypatch.undo()
    monkeypatch.setattr(oracle_mod, "LOCATIONS", hubfiles["locations"])
    monkeypatch.setattr(oracle_mod, "vintage_path", lambda d: hubfiles["vintage"])
    with pytest.raises(ValueError, match="cannot be fitted"):
        oracle_mod.apply_week(_samples(), ASOF, tmp_path / "w2")
    assert not (tmp_path / "w2" / oracle_mod.PROVENANCE_NAME).exists()


def test_the_option_and_the_research_tag():
    assert oracle_mod.wanted({}) and oracle_mod.wanted(None) and oracle_mod.wanted({"oracle": ""})
    assert not oracle_mod.wanted({"oracle": "none"})
    spec = RunSpec(engine="all", forecast_date=ASOF, extra={"oracle": "none"})
    assert is_research(spec) and is_research(spec.to_json())
    assert not is_research(RunSpec(engine="all", forecast_date=ASOF, extra={}))
    pairs = dict(spec_settings(spec))
    assert pairs["Oracle step"] == "none (the plain filter, a research run)"
    pairs = dict(spec_settings(RunSpec(engine="all", forecast_date=ASOF)))
    assert pairs["Oracle step"] == "on (console default)"


def test_the_storage_boundary_converts_the_research_key():
    stored = {"asof": ASOF, "pf": {"Ohio": {"0": [1.0], "1": [2.0]}},
              "pf_filter": {"Ohio": {"0": [1.0], "1": [3.0]}}}
    canon = hz.record_to_canonical(stored)
    assert canon["pf_filter"]["Ohio"] == {hz.ORIGIN: [1.0], "0": [3.0]}
    assert hz.record_to_stored(canon) == stored
    assert "pf_filter" in hz.MEMBERS and oracle_mod.FILTER_KEY == "pf_filter"


def test_the_pruner_keeps_the_provenance(hubfiles, tmp_path):
    wd = tmp_path / "2097-98" / "weeks" / ASOF
    wd.mkdir(parents=True)
    member, _ = oracle_mod.apply_week(_samples(), ASOF, wd)
    (wd / "Ohio_r0").mkdir()
    (wd / "runner_0.py").write_text("")
    retro.write_week_samples(wd, {"asof": ASOF, "pf": member})
    reclaim.prune_week(wd)
    left = {p.name for p in wd.iterdir()}
    assert left == {retro.SAMPLES_GZ, retro.QUANTILES_NAME,
                    oracle_mod.PROVENANCE_NAME, oracle_mod.BANK_DIRNAME}
    OB.read_pool(wd / oracle_mod.BANK_DIRNAME, ASOF)      # still verifiable


# ------------------------------------------------------------ run_week

def _stub_retro(monkeypatch, raw):
    def fake_prepare(spec, wd):
        cells = [{"key": "Ohio_r0", "dir": str(Path(wd) / "Ohio_r0"),
                  "location": "Ohio", "weeks_dropped": 0}]
        (Path(wd) / "cells.json").write_text(json.dumps(cells))
        return cells

    class Runner:
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], "ok")
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect", lambda wd: raw)
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"0": {0.5: 2.0}}})
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s) for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)


def test_run_week_stores_the_member_under_pf_and_not_the_filter(hubfiles, tmp_path, monkeypatch):
    raw = _samples(("Ohio", "Utah"))
    _stub_retro(monkeypatch, raw)
    root = tmp_path / "2097-98"
    out = retro.run_week(root, "2097-98", ASOF, ["Ohio", "Utah"], width=1)
    wd = root / "weeks" / ASOF
    # the stored week holds the member and the analogue, as on main: the
    # filter's own samples are not stored
    assert set(out) == {"asof", "pf", "analogue"}
    assert out["pf"]["Ohio"]["0"] != raw["Ohio"]["0"]
    back = retro.read_week_samples(root, ASOF)
    assert oracle_mod.FILTER_KEY not in back
    assert set(back) >= {"pf", "analogue"}
    assert back["pf"]["Ohio"]["3"] == out["pf"]["Ohio"]["3"]
    side = retro.read_week_quantiles(wd)
    assert set(side) == {"pf", "analogue"}
    # the provenance beside the week, and it survived the prune
    prov = oracle_mod.read_provenance(wd)
    assert prov["applied"] and prov["bank"]["label"].startswith("admissions-fbase@")
    # the filter's own 23 quantiles per location and horizon are there
    # instead, which is all scoring and the comparison read
    null = prov["quantiles"]["null"]
    assert set(null) == {"Ohio", "Utah"}
    for loc in null:
        assert set(null[loc]) == {"0", "1", "2", "3"}
        assert all(len(null[loc][h]["unrounded"]) == 23 for h in null[loc])
    assert "+flusurv@" in prov["bank"]["label"]
    assert prov["trimmed_weeks"]["source"].startswith("cells.json")
    assert (wd / oracle_mod.BANK_DIRNAME / f"paths_{ASOF}.csv").is_file()
    assert not (wd / "cells.json").exists()               # pruned, as before


def test_run_week_with_oracle_none_stores_the_plain_filter(hubfiles, tmp_path, monkeypatch):
    raw = _samples(("Ohio",))
    _stub_retro(monkeypatch, raw)
    root = tmp_path / "2097-98"
    out = retro.run_week(root, "2097-98", ASOF, ["Ohio"], width=1,
                         extra={"oracle": "none"})
    assert set(out) == {"asof", "pf", "analogue"} and out["pf"] == raw
    prov = oracle_mod.read_provenance(root / "weeks" / ASOF)
    assert prov["applied"] is False and "oracle = none" in prov["reason"]
    assert not (root / "weeks" / ASOF / oracle_mod.BANK_DIRNAME).exists()


def test_run_season_records_the_oracle_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(retro, "season_vintages", lambda s: [ASOF])
    monkeypatch.setattr(retro, "run_week", lambda *a, **k: {"asof": ASOF})
    from app.core.engines import analogue as an
    monkeypatch.setattr(an, "aux_preset", lambda name: an.bare_analogue)
    root = tmp_path / "s"
    retro.run_season(root, "2097-98", ["Ohio"], width=1)
    assert retro.read_meta(root)["settings"]["oracle"] == "applied"
    root2 = tmp_path / "s2"

    def none_extra(asof, i, vintages):
        return {"oracle": "none"}
    retro.run_season(root2, "2097-98", ["Ohio"], width=1, week_extra=none_extra)
    assert retro.read_meta(root2)["settings"]["oracle"].startswith("none")
    root3 = tmp_path / "s3"
    retro.run_season(root3, "2097-98", ["Ohio"], width=1, engine="analogue")
    assert "oracle" not in retro.read_meta(root3)["settings"]


def test_a_console_replay_is_the_oracle_sihrs_from_the_season_start(hubfiles, tmp_path, monkeypatch):
    """The Retrospective run form -> _retro_bg -> run_season -> run_week path:
    fits from the season start, applies the step with that week's vintage and
    donor pool, records settings.oracle = "applied", writes oracle.json,
    stores no filter samples, and names the tree the Oracle SIHRS."""
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    season = "2097-98"
    raw = _samples(("Ohio", "Utah"))
    _stub_retro(monkeypatch, raw)
    stub_prepare, specs = retro.pf_engine.prepare, []

    def spy(spec, wd):
        specs.append(spec)
        return stub_prepare(spec, wd)
    monkeypatch.setattr(retro.pf_engine, "prepare", spy)
    monkeypatch.setattr(retro, "available_seasons", lambda: [season])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [ASOF])
    live = tmp_path / "retro"
    live.mkdir()
    monkeypatch.setattr(srv, "RETRO_ROOT", live)
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)

    class _Done:
        def is_set(self):
            return True

        def wait(self, *a):
            return True
    monkeypatch.setattr(srv, "_ensure_results_job",
                        lambda root, s, **k: {"done": _Done(), "error": ""})
    real_bg, calls = srv._retro_bg, []
    monkeypatch.setattr(srv, "_retro_bg", lambda *a: calls.append(a))
    status_before = dict(srv._retro_status)
    try:
        r = TestClient(srv.app).post("/retro/run", data={
            "season": season, "locations": "custom",
            "custom_locations": ["Ohio", "Utah"], "national": "0",
            "particles": "1000", "replicates": "1", "width": "1",
            "engine": "pf", "mode": "resume"}, follow_redirects=False)
        assert r.status_code == 303 and len(calls) == 1
        # the form's arguments, run by the real season worker
        assert calls[0][-1] == "pf" and calls[0][1] == ["Ohio", "Utah"]
        real_bg(*calls[0])
        assert srv._retro_status[season] == "done", srv._retro_status[season]
    finally:
        srv._retro_status.clear()
        srv._retro_status.update(status_before)
        srv._invalidate_scans()
    root = live / season
    # the fit runs from the season start through the as-of week
    assert [(sp.forecast_date, sp.season_start) for sp in specs] == \
        [(ASOF, retro.season_bounds(season)[0])]
    # the run record says the step ran, and the week says with what
    meta = retro.read_meta(root)
    assert meta["settings"]["engine"] == "pf"
    assert meta["settings"]["oracle"] == "applied"
    wd = root / "weeks" / ASOF
    prov = oracle_mod.read_provenance(wd)
    assert prov["applied"] is True and prov["member"] == oracle_mod.MEMBER_NAME
    assert prov["asof"] == ASOF
    assert Path(prov["vintage"]["file"]) == hubfiles["vintage"]
    assert prov["bank"]["label"].startswith("admissions-fbase@")
    assert "+flusurv@" in prov["bank"]["label"]
    # the stored week is the member and the Groundhog, nothing else
    back = retro.read_week_samples(root, ASOF)
    assert oracle_mod.FILTER_KEY not in back and "pf" in back
    assert back["pf"]["Ohio"]["3"] != raw["Ohio"]["3"]
    # and the tree is titled the Oracle SIHRS wherever pf is named
    # 1,000 particles and 1 replicate are off the shipped values: the tree
    # records them as model knobs and never wears the bare shipped name
    assert srv._names_for_root(root)["pf"] == "Oracle SIHRS (modified settings)"


# ------------------------------------------------------------ the console

@pytest.fixture
def console(hubfiles, tmp_path, monkeypatch):
    """srv._run_all with fake engines and the real step."""
    import app.core.engines.analogue as an_engine
    import app.core.engines.pf as pf_engine
    import app.core.floor as floor_mod
    import app.core.runs as runs_mod
    import app.core.scoring as scoring_mod
    import flubnf.settings as fs
    from app.ui import server as srv
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    exe = tmp_path / "exe"
    exe.write_text("")
    monkeypatch.setattr(fs, "PY_ENGINE", exe)
    monkeypatch.setattr(fs, "PYBNF", exe)
    raw = _samples(("Ohio", "Utah"))
    monkeypatch.setattr(pf_engine, "prepare", lambda spec, w: [])
    monkeypatch.setattr(pf_engine, "execute", lambda w: {"Ohio_r0": "ok", "Utah_r0": "ok"})
    monkeypatch.setattr(pf_engine, "collect", lambda w: {loc: {h: list(v) for h, v in s.items()}
                                                         for loc, s in raw.items()})
    an_q = {h: {float(L): 10.0 + 3 * i + int(h) for i, L in enumerate(srv.QUANTILES)}
            for h in hz.HORIZONS} if hasattr(srv, "QUANTILES") else None
    from app.core.submit import QUANTILES
    an_q = {h: {float(L): 10.0 + 3 * i + int(h) for i, L in enumerate(QUANTILES)}
            for h in hz.HORIZONS}
    monkeypatch.setattr(an_engine, "run",
                        lambda spec: {loc: {h: dict(q) for h, q in an_q.items()}
                                      for loc in spec.locations})
    monkeypatch.setattr(floor_mod, "floor_samples", lambda s, loc, d, recent=None: s)
    monkeypatch.setattr(floor_mod, "floor_quantiles", lambda q: q)

    def _no_truth():
        raise RuntimeError("no truth in this test")
    monkeypatch.setattr(scoring_mod, "load_truth", _no_truth)
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    monkeypatch.setattr(srv, "_engine_versions_for_ledger", lambda e: {})
    monkeypatch.setattr(srv, "_harvest_params", lambda w: {})
    monkeypatch.setattr(srv, "_write_weekly_report", lambda *a, **k: None)
    monkeypatch.setattr(srv, "_archive_run", lambda w, d: "archived")
    status_before = dict(srv._status)
    yield srv, raw
    srv._status.clear()
    srv._status.update(status_before)
    srv._invalidate_scans()


def _run(srv, oracle=None):
    from app.core.runs import Ledger
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                   replicates=1, extra=srv._run_extra(2, "vintage", None, oracle))
    srv._run_all(spec)
    row = next(iter(Ledger().rows(5)))
    outcome = json.loads(row.get("outcome") or "{}")
    from app.core.runs import APP_STATE
    return spec, row, outcome, APP_STATE / "workroots" / row["run_id"]


def test_a_console_run_applies_the_step_by_default(console):
    srv, raw = console
    spec, row, outcome, w = _run(srv)
    assert outcome["oracle"].startswith("admissions-fbase@")
    assert row["status"] == "ok" and "submission_withheld" not in outcome
    assert "NAU_PyBNF-OracleSIHRS" in outcome["submissions"]
    assert outcome["archived"] == "archived"
    prov = oracle_mod.read_provenance(w)
    assert prov["applied"] and prov["bank"]["label"] == outcome["oracle"]
    assert json.loads((w / "results.json").read_text())["oracle"] == outcome["oracle"]
    # the filter's own samples kept beside the provenance, stored form
    with gzip.open(w / oracle_mod.FILTER_RECORD_NAME, "rt") as fh:
        kept = json.load(fh)
    assert set(kept) == {"asof", "pf_filter"}
    assert kept["pf_filter"]["Ohio"]["0"] == raw["Ohio"][hz.ORIGIN]
    assert kept["pf_filter"]["Ohio"]["4"] == raw["Ohio"]["3"]
    # the submitted file is the member's quantiles, not the filter's
    sub = Path(outcome["submissions"]["NAU_PyBNF-OracleSIHRS"]).read_text()
    assert "2098-01-11" in sub
    # and the workroot's prune keeps the record
    reclaim.prune_workroot(w)
    assert (w / oracle_mod.PROVENANCE_NAME).is_file()
    assert (w / oracle_mod.FILTER_RECORD_NAME).is_file()
    assert (w / oracle_mod.BANK_DIRNAME).is_dir()


def test_oracle_none_is_a_research_run_with_its_file_withheld(console):
    srv, raw = console
    spec, row, outcome, w = _run(srv, oracle="none")
    assert outcome["oracle"] == "none"
    assert "Oracle SIHRS" in outcome["submission_withheld"]
    assert "oracle = none" in outcome["submission_withheld"]
    assert "NAU_PyBNF-OracleSIHRS" not in outcome["submissions"]
    assert "NAU_PyBNF-GroundHogCGR" in outcome["submissions"]
    assert outcome["archived"] == "skipped: research run"
    assert is_research(row["spec"])
    assert json.loads((w / "results.json").read_text())["research"] is True
    prov = oracle_mod.read_provenance(w)
    assert prov["applied"] is False
    assert not (w / oracle_mod.FILTER_RECORD_NAME).exists()
    assert "submission withheld" in srv._outcome_chips(json.dumps(outcome))


def test_run_extra_carries_the_switch_and_refuses_anything_else():
    from app.ui import server as srv
    assert "oracle" not in srv._run_extra(2, "realtime", "")
    assert srv._run_extra(2, "realtime", "", "none")["oracle"] == "none"
    assert "oracle" not in srv._run_extra(2, "realtime", "", "")
    with pytest.raises(ValueError, match="oracle must be"):
        srv._run_extra(2, "realtime", "", "half")


def test_the_run_route_accepts_the_field_and_the_rerun_passes_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    import app.core.runs as runs_mod
    from app.core import data as core_data
    from app.core.runs import Ledger
    client = TestClient(srv.app)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(core_data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(core_data, "vintages", lambda: [ASOF])
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda spec: started.append(spec))
    status_before = dict(srv._status)
    try:
        srv._status["running"] = None
        r = client.post("/run", data={"forecast_date": ASOF, "locations": "custom",
                                      "custom_locations": ["Ohio"], "engine": "all",
                                      "replicates": "1", "oracle": "none"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert started and started[-1].extra.get("oracle") == "none"
        assert is_research(started[-1])
        # a re-run of that row carries the switch through
        led = Ledger()
        rid = led.open_run(started[-1], Path("pending"), {})
        led.close_run(rid, "ok", {})
        srv._status["running"] = None
        r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
        assert r.status_code == 303
        assert started[-1].extra.get("oracle") == "none"
        # and a row without it re-runs the member
        srv._status["running"] = None
        client.post("/run", data={"forecast_date": ASOF, "locations": "custom",
                                  "custom_locations": ["Ohio"], "engine": "all",
                                  "replicates": "1"}, follow_redirects=False)
        assert "oracle" not in started[-1].extra
    finally:
        srv._status.clear()
        srv._status.update(status_before)
        srv._invalidate_scans()
