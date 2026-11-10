"""Season results without re-reading the forecasting samples (P2, F10, F12).

  * Every week's national quantile sets are cached in
    playback_cache/us_quantiles/<week>.json, so the national aggregate a
    rescore asks for (new truth, a new scores.json) reads no samples. The
    result equals the aggregate as it was built before (frozen below), less
    its wall time; the construction is pinned to NATIONAL_CACHE_V.
  * scores.json is parsed once per content and shared by the season page
    and the season player (retro_store.scores_frame, under a lock); the
    shared frame is never changed by a serve or a season report.
  * The season player's payloads are byte-identical to those built by the
    readers as they stood (the unmemoised truth reader, a fresh
    pd.read_json per serve).
"""
import hashlib
import json
import os
import shutil
import sys
import threading
import zlib
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as core_data                     # noqa: E402
from app.core import horizons as hz                        # noqa: E402
from app.core import playback, retro, retro_store, scoring  # noqa: E402
from app.core import us_national as usn                    # noqa: E402
from app.ui import retro_prep as ui_retro_prep             # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

SEASON = "2097-98"
WEEKS = ("2097-11-01", "2097-11-08", "2097-11-15", "2097-11-22")
STATES = {"Ohio": "39", "Utah": "49", "Texas": "48", "Puerto Rico": "72"}
LEVELS = [float(L) for L in QL]


# ------------------------------------- the aggregate as built before P2

def _old_week_quantiles(d: dict, levels: list) -> tuple:
    """The per-week body of national_aggregate before P2, verbatim. FROZEN
    for NATIONAL_CACHE_V 4: a change to retro.national_week_quantiles must
    bump NATIONAL_CACHE_V (every week's cached sets then rebuild) and
    replace this copy and the version pinned below together."""
    asof = d["asof"]
    pf_locs = [l for l in d.get("pf", {}) if not usn.is_us(l)]
    an_locs = [l for l in d.get("analogue", {}) if not usn.is_us(l)]
    pf_nat, an_nat = {}, {}
    for h in hz.HORIZONS:
        arrs = []
        for loc in pf_locs:
            a = np.asarray(d["pf"][loc].get(h, []), float)
            if a.size:
                arrs.append(a)
        if arrs:
            n = min(a.size for a in arrs)
            tot = np.zeros(n)
            for a in arrs:
                tot += a[:n]
            tot = tot[np.isfinite(tot)]
            if tot.size:
                pf_nat[h] = {L: float(np.quantile(tot, L))
                             for L in levels}
        draws = None
        for loc in an_locs:
            q = d["analogue"][loc].get(h)
            if not q:
                continue
            ks = sorted(q, key=float)
            lv = np.asarray([float(k) for k in ks])
            vv = np.maximum.accumulate(
                np.asarray([float(q[k]) for k in ks]))
            rng = np.random.default_rng(
                zlib.crc32(f"{asof}|{loc}|{h}".encode()))
            v = np.interp(rng.random(30_000), lv, vv)
            draws = v if draws is None else draws + v
        if draws is not None:
            draws = draws[np.isfinite(draws)]
            if draws.size:
                an_nat[h] = {L: float(np.quantile(draws, L))
                             for L in levels}
    return pf_nat, an_nat


#: the construction version _old_week_quantiles is frozen for
FROZEN_NATIONAL_CACHE_V = 4


def old_national_aggregate(root: Path, read=retro_store.read_samples):
    """national_aggregate before P2, verbatim but for its us_aggregate.json
    read and write (a computation, never a cache): the reference."""
    import time
    root = Path(root)
    wks = retro_store.season_sample_files(root)
    if not wks:
        return None
    t0 = time.monotonic()
    truth, _n2f = scoring.load_truth()
    levels = [float(L) for L in QL]
    rows = []
    for wp in wks:
        d = read(wp)
        asof = d["asof"]
        T = pd.Timestamp(asof)
        pf_nat, an_nat = _old_week_quantiles(d, levels)
        for model, qs in (("pf", pf_nat), ("analogue", an_nat)):
            for h in hz.HORIZONS:
                q = qs.get(h)
                actual = truth.get(
                    ("US", T + timedelta(days=7 * (int(h) + 1))))
                if not (scoring.truth_settled(actual)
                        and scoring.forecast_scoreable(q)):
                    continue
                m = scoring.cell_metrics(q, actual)
                if m is None:
                    continue
                rows.append((model, asof, int(h), m))
    bases, lbases = {}, {}
    for asof in {r[1] for r in rows}:
        bases.update(scoring._baseline_cells(asof, {"US"}, truth))
        lbases.update(scoring._baseline_log_cells(asof, {"US"}, truth))
    result = {"cells": {}, "weeks": len(wks), "log_rel": {}, "cov": {}}
    for model in ("pf", "analogue"):
        cells = [{**m, "base_wis": bases.get(("US", asof, h)),
                  "base_log_wis": lbases.get(("US", asof, h), np.nan)}
                 for mm, asof, h, m in rows if mm == model]
        cells = [c for c in cells if c["base_wis"] is not None]
        if cells:
            pm = scoring.pooled_metrics(pd.DataFrame(cells))
            if pm["rel"] is not None:
                result[model] = pm["rel"]
            result["cells"][model] = pm["n"]
            result["log_rel"][model] = pm["log_rel"]
            result["cov"][model] = pm["cov"]
    result["seconds"] = round(time.monotonic() - t0, 1)
    return result


def _old_season_scores(root: Path):
    """playback._season_scores before P2: a fresh read per call."""
    sf = root / "scores.json"
    if not sf.is_file():
        return None
    try:
        df = pd.read_json(sf)
    except Exception:
        return None
    if df.empty or "model" not in df.columns:
        return None
    return df


def _old_load_truth():
    """scoring.load_truth before P2 (settled branch): a parse per call."""
    target = scoring.HUB / "target-data/target-hospital-admissions.csv"
    t = pd.read_csv(target, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    locs_csv = scoring.HUB / "auxiliary-data/locations.csv"
    locs = pd.read_csv(locs_csv, dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    return truth, n2f


def same(a: dict, b: dict) -> bool:
    """Equal results, wall time aside (JSON text, so NaN equals NaN)."""
    a, b = dict(a), dict(b)
    a.pop("seconds", None), b.pop("seconds", None)
    return (json.dumps(a, sort_keys=True, default=str)
            == json.dumps(b, sort_keys=True, default=str))


# ------------------------------------------------------------------ fixtures

def _truth_csv(us_shift=0.0) -> str:
    rows = ["date,location,location_name,value"]
    for k in range(-10, 12):
        d = (pd.Timestamp(WEEKS[0]) + pd.Timedelta(days=7 * k)).date()
        tot = 0.0
        for i, (name, fips) in enumerate(STATES.items()):
            v = 40.0 + 15 * i + 3 * k
            tot += v
            rows.append(f"{d},{fips},{name},{v}")
        rows.append(f"{d},US,US,{tot + us_shift}")
    return "\n".join(rows) + "\n"


def _hub(tmp_path: Path, monkeypatch) -> Path:
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / "auxiliary-data").mkdir()
    (hub / "target-data" / "target-hospital-admissions.csv").write_text(
        _truth_csv())
    (hub / "auxiliary-data" / "locations.csv").write_text(
        "location,location_name,abbreviation,population\n"
        + "".join(f"{f},{n},X{f},{1_000_000 + int(f) * 1000}\n"
                  for n, f in STATES.items())
        + "US,US,US,340000000\n")
    for mod in (scoring, playback, core_data):
        monkeypatch.setattr(mod, "HUB", hub)
    return hub


def _stub_baselines(monkeypatch):
    """The FluSight baseline's cells (no model-output folder here): a
    deterministic WIS per cell, the same for every module's rebind."""
    def cells(asof, fips_set, truth, log=False):
        return {(f, asof, h): (0.3 if log else 3.0) + 0.5 * h + len(f) * 0.1
                for f in fips_set for h in range(4)}
    for mod in (scoring, playback):
        monkeypatch.setattr(mod, "_baseline_cells",
                            lambda a, fs, tr: cells(a, fs, tr))
        monkeypatch.setattr(mod, "_baseline_log_cells",
                            lambda a, fs, tr: cells(a, fs, tr, log=True))


def _write_week(root: Path, asof: str, i: int):
    rng = np.random.default_rng(100 + i)
    T = pd.Timestamp(asof)
    pf, an = {}, {}
    for j, (name, fips) in enumerate(STATES.items()):
        base = 40.0 + 15 * j
        k0 = (T - pd.Timestamp(WEEKS[0])).days // 7
        # stored convention: "0" the anchor, "1".."4" the forecast weeks
        pf[name] = {str(h): [float(v) for v in
                             base + 3 * (k0 + h) + rng.normal(0, 4, 400)]
                    for h in range(5)}
        an[name] = {str(h): {str(L): base + 3 * (k0 + h) + (L - 0.5) * 18
                             for L in QL} for h in range(1, 5)}
    if i == 1:
        pf["Ohio"]["2"][7] = float("nan")          # one poisoned draw index
        an["Utah"]["3"][str(QL[12])] -= 0.25       # a small inversion
        # a fitted national block: never summed into the aggregate
        pf["US"] = {str(h): [500.0] * 400 for h in range(5)}
        an["US"] = {str(h): {str(L): 500.0 for L in QL} for h in range(1, 5)}
    if i == 2:
        pf["Texas"]["3"] = pf["Texas"]["3"][:250]  # a shorter draw set
    wd = root / "weeks" / asof
    wd.mkdir(parents=True)
    (wd / "samples.json").write_text(
        json.dumps({"asof": asof, "pf": pf, "analogue": an}))


@pytest.fixture
def season(tmp_path, monkeypatch):
    """Four stored weeks (the third gzipped) of four states, against a
    fixture hub's truth read by the real load_truth."""
    _hub(tmp_path, monkeypatch)
    _stub_baselines(monkeypatch)
    monkeypatch.setattr(ui_retro_prep, "_WARM_MAP_CARDS", False)
    scoring._TRUTH_MEMO.clear()
    root = tmp_path / SEASON
    for i, asof in enumerate(WEEKS):
        _write_week(root, asof, i)
    retro_store.compress_samples_file(root / "weeks" / WEEKS[2]
                                      / "samples.json")
    yield root
    scoring._TRUTH_MEMO.clear()


@pytest.fixture
def sample_reads(monkeypatch):
    """The samples files retro.read_samples was asked for under this
    test's tree (another module's thread could read its own)."""
    seen = []
    real = retro.read_samples

    def spy(fp):
        seen.append(Path(fp))
        return real(fp)
    monkeypatch.setattr(retro, "read_samples", spy)
    return seen


def _ours(seen, root):
    return [p for p in seen if Path(root) in p.parents]


def _forbid_samples(monkeypatch):
    def boom(fp):
        raise AssertionError(f"samples read: {fp}")
    monkeypatch.setattr(retro, "read_samples", boom)


def _touch(p: Path, dt=60):
    st = p.stat()
    os.utime(p, (st.st_atime + dt, st.st_mtime + dt))


# ------------------------------------------- the national aggregate (F10)

def test_the_aggregate_equals_the_one_built_before(season):
    old = old_national_aggregate(season)
    new = retro.national_aggregate(season)
    assert same(new, old)
    assert new["cells"]["pf"] > 0 and new["cells"]["analogue"] > 0
    # one cache per week, in the subfolder, carrying its as-of
    qd = season / "playback_cache" / retro.US_QUANTILES_DIRNAME
    assert sorted(p.stem for p in qd.glob("*.json")) == list(WEEKS)
    for w in WEEKS:
        c = json.loads((qd / f"{w}.json").read_text())
        assert c["asof"] == w and c["key"]["v"] == retro.NATIONAL_CACHE_V
    assert not list(qd.glob("*.tmp"))
    # and the aggregate's own cache answers the next call
    assert retro.national_aggregate(season) == new


def test_a_rescore_reads_no_samples_and_scores_the_new_truth(
        season, monkeypatch):
    first = retro.national_aggregate(season)
    # a rescore: scores.json rewritten (the aggregate's key moves) and new
    # truth from Update data
    (season / "scores.json").write_text("{}")
    _touch(season / "scores.json")
    hub = scoring.HUB
    (hub / "target-data" / "target-hospital-admissions.csv").write_text(
        _truth_csv(us_shift=25.0))
    want = old_national_aggregate(season)
    assert not same(want, first)                  # the truth matters
    _forbid_samples(monkeypatch)
    got = retro.national_aggregate(season)
    assert same(got, want)


def test_the_construction_is_pinned_to_its_cache_version(season):
    """A change to the construction must bump NATIONAL_CACHE_V: cached
    weeks are no longer rebuilt by a rescore."""
    assert retro.NATIONAL_CACHE_V == FROZEN_NATIONAL_CACHE_V
    assert retro._NATIONAL_DRAWS == 30_000
    for sp in retro_store.season_sample_files(season):
        d = retro_store.read_samples(sp)
        want = json.dumps(_old_week_quantiles(d, LEVELS))
        for _ in range(2):
            got = retro.national_week_quantiles(d, LEVELS)
            assert json.dumps(got) == want
        # what the cache gives back is what was computed: levels as floats
        asof, pf_nat, an_nat = retro._national_week(season, sp, LEVELS)
        assert asof == sp.parent.name
        assert json.dumps((pf_nat, an_nat)) == want
        assert all(isinstance(L, float) for q in pf_nat.values() for L in q)
        asof2, pf2, an2 = retro._national_week(season, sp, LEVELS)
        assert (pf2, an2) == (pf_nat, an_nat)
        assert list(pf2) == list(pf_nat) and all(
            list(pf2[h]) == list(pf_nat[h]) for h in pf2)


def test_one_changed_week_alone_is_read_again(season, sample_reads):
    retro.national_aggregate(season)
    assert len(_ours(sample_reads, season)) == len(WEEKS)
    sample_reads.clear()
    sp = retro_store.week_samples_path(season, WEEKS[1])
    _touch(sp)
    got = retro.national_aggregate(season)
    assert _ours(sample_reads, season) == [sp]
    assert same(got, old_national_aggregate(season))


def test_a_cache_that_does_not_parse_or_match_is_a_miss(season,
                                                         sample_reads):
    retro.national_aggregate(season)
    qd = season / "playback_cache" / retro.US_QUANTILES_DIRNAME
    (qd / f"{WEEKS[0]}.json").write_text("not json")
    c = json.loads((qd / f"{WEEKS[1]}.json").read_text())
    c["key"]["draws"] = 10
    (qd / f"{WEEKS[1]}.json").write_text(json.dumps(c))
    c = json.loads((qd / f"{WEEKS[3]}.json").read_text())
    del c["analogue"]
    (qd / f"{WEEKS[3]}.json").write_text(json.dumps(c))
    (season / "playback_cache" / "us_aggregate.json").unlink()
    sample_reads.clear()
    got = retro.national_aggregate(season)
    assert sorted(p.parent.name for p in _ours(sample_reads, season)) == \
        [WEEKS[0], WEEKS[1], WEEKS[3]]
    assert same(got, old_national_aggregate(season))


def test_a_version_bump_reads_every_week_again(season, sample_reads,
                                               monkeypatch):
    retro.national_aggregate(season)
    sample_reads.clear()
    monkeypatch.setattr(retro, "NATIONAL_CACHE_V", 99)
    retro.national_aggregate(season)
    assert len(_ours(sample_reads, season)) == len(WEEKS)


def test_compressing_a_week_keeps_its_cache(season, monkeypatch):
    first = retro.national_aggregate(season)
    retro_store.compress_samples_file(
        season / "weeks" / WEEKS[0] / "samples.json")
    (season / "playback_cache" / "us_aggregate.json").unlink()
    _forbid_samples(monkeypatch)
    assert same(retro.national_aggregate(season), first)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="POSIX permissions, not root")
def test_an_unwritable_tree_still_aggregates(season):
    pc = season / "playback_cache"
    pc.mkdir()
    pc.chmod(0o555)
    try:
        got = retro.national_aggregate(season)
        assert same(got, old_national_aggregate(season))
        assert not (pc / retro.US_QUANTILES_DIRNAME).exists()
    finally:
        pc.chmod(0o755)


def test_a_tree_deleted_meanwhile_is_not_recreated(season, monkeypatch):
    real = retro.national_week_quantiles

    def gone(d, levels):
        out = real(d, levels)
        shutil.rmtree(season)
        return out
    monkeypatch.setattr(retro, "national_week_quantiles", gone)
    sp = retro_store.week_samples_path(season, WEEKS[0])
    asof, pf_nat, an_nat = retro._national_week(season, sp, LEVELS)
    assert asof == WEEKS[0] and pf_nat and an_nat
    assert not season.exists()


def test_the_week_caches_stay_out_of_the_report_glob(season):
    from app.core import report_season
    retro.national_aggregate(season)
    pc = season / "playback_cache"
    assert [p.name for p in pc.glob("*.json")] == ["us_aggregate.json"]
    newest = report_season._newest_input(season)
    # a week's cache rewritten later moves nothing the export watches
    qf = pc / retro.US_QUANTILES_DIRNAME / f"{WEEKS[0]}.json"
    _touch(qf, dt=3600)
    assert report_season._newest_input(season) == newest


def test_finalize_after_new_truth_reads_no_samples(season, monkeypatch):
    """The weekly path: Update data brings new truth, the season page's
    finalize rescores, and the national phase reads no samples."""
    retro.finalize_season(season, SEASON)
    # the aggregate's own key holds scores.json's mtime in whole seconds; a
    # rescore inside the same second (only here) would not move it
    (season / "playback_cache" / "us_aggregate.json").unlink()
    hub = scoring.HUB
    tf = hub / "target-data" / "target-hospital-admissions.csv"
    tf.write_text(_truth_csv(us_shift=10.0))
    _touch(tf, dt=120)
    assert not retro.national_aggregate_fresh(season) or \
        not retro.scores_current(season)
    want = old_national_aggregate(season)
    _forbid_samples(monkeypatch)
    sec = retro.finalize_season(season, SEASON)
    assert "national" in sec
    assert retro.national_aggregate_fresh(season)
    got = json.loads((season / "playback_cache" / "us_aggregate.json")
                     .read_text())["result"]
    assert same(got, want)


# ------------------------------------------------ the season player (F12)

def _payload_hashes(root: Path) -> dict:
    """{week: (sha of a fresh build, sha of the cache-served one)}."""
    out = {}
    for w in WEEKS:
        for f in (root / "playback_cache").glob("*.json"):
            if f.name != "us_aggregate.json":
                f.unlink()
        fresh = playback.build_week(root, SEASON, w)
        served = playback.build_week(root, SEASON, w)
        out[w] = tuple(hashlib.sha256(json.dumps(p, sort_keys=True)
                                      .encode()).hexdigest()
                       for p in (fresh, served))
    return out


def test_playback_payloads_are_byte_identical(season, monkeypatch):
    retro.finalize_season(season, SEASON)
    new = _payload_hashes(season)
    with monkeypatch.context() as m:
        m.setattr(playback, "_season_scores", _old_season_scores)
        m.setattr(scoring, "load_truth", _old_load_truth)
        m.setattr(playback, "load_truth", _old_load_truth)
        old = _payload_hashes(season)
    assert new == old and len(new) == len(WEEKS)


def test_a_cached_serve_parses_neither_truth_nor_scores(season, monkeypatch):
    retro.finalize_season(season, SEASON)
    served = {w: playback.build_week(season, SEASON, w) for w in WEEKS}

    def boom(*a, **k):
        raise AssertionError("parsed again")
    monkeypatch.setattr(pd, "read_csv", boom)
    monkeypatch.setattr(pd, "read_json", boom)
    for w in WEEKS:
        assert playback.build_week(season, SEASON, w) == served[w]


def _frame_hash(df) -> str:
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    h.update(repr(list(df.columns)).encode())
    h.update(repr([str(t) for t in df.dtypes]).encode())
    return h.hexdigest()


def test_the_shared_frame_is_never_changed(season):
    from app.core import report_season
    retro.finalize_season(season, SEASON)
    frame = retro_store.scores_frame(season)
    assert frame is not None and len(frame)
    # one frame for the page and the player
    assert ui_retro_prep._scores_df(season) is frame
    assert playback._season_scores(season) is frame
    before = _frame_hash(frame)
    assert before == _frame_hash(pd.read_json(season / "scores.json"))
    for w in WEEKS:
        playback.build_week(season, SEASON, w)
        playback.build_week(season, SEASON, w)
    report_season.build_season_report(season, SEASON)
    from app.ui.routes import retro as ui_retro
    ui_retro.season_page_context(season, SEASON)
    usn.resolve(season)
    assert retro_store.scores_frame(season) is frame
    assert _frame_hash(frame) == before


def test_the_scores_lru_holds_under_threads(tmp_path, monkeypatch):
    """Request threads and a finalize thread hammer the LRU across more
    roots than it holds: no KeyError, every frame its own root's."""
    monkeypatch.setattr(retro_store, "SCORES_FRAMES_MAX", 3)
    retro_store.SCORES_FRAMES.clear()
    roots = []
    for i in range(6):
        r = tmp_path / f"r{i}"
        r.mkdir()
        pd.DataFrame([{"model": "pf", "location": "Ohio", "asof": WEEKS[0],
                       "horizon": h, "wis": 1.0 + i, "rel": 0.5}
                      for h in range(i + 1)]).to_json(r / "scores.json")
        roots.append(r)
    errors = []
    go = threading.Barrier(5)

    def hammer(k):
        try:
            go.wait(5)
            for n in range(150):
                i = (n * (k + 1) + k) % len(roots)
                getter = (ui_retro_prep._scores_df if k % 2
                          else playback._season_scores)
                df = getter(roots[i])
                assert df is not None and len(df) == i + 1
        except Exception as e:                   # pragma: no cover
            errors.append(repr(e))
    threads = [threading.Thread(target=hammer, args=(k,)) for k in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors
    assert len(retro_store.SCORES_FRAMES) <= 3
    retro_store.SCORES_FRAMES.clear()


def test_a_scores_file_replaced_mid_read_is_served_not_kept(tmp_path,
                                                            monkeypatch):
    retro_store.SCORES_FRAMES.clear()
    r = tmp_path / "r"
    r.mkdir()
    sf = r / "scores.json"
    pd.DataFrame([{"model": "pf", "wis": 1.0}]).to_json(sf)
    real = pd.read_json

    def racing(path, *a, **k):
        df = real(path, *a, **k)
        pd.DataFrame([{"model": "pf", "wis": 2.0},
                      {"model": "pf", "wis": 3.0}]).to_json(sf)
        return df
    monkeypatch.setattr(pd, "read_json", racing)
    assert len(retro_store.scores_frame(r)) == 1
    assert not retro_store.SCORES_FRAMES
    monkeypatch.setattr(pd, "read_json", real)
    assert len(retro_store.scores_frame(r)) == 2
    retro_store.SCORES_FRAMES.clear()
