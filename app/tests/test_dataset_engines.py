"""The engines on a custom dataset (app/core/datasets.py), and the hub path
held byte-identical.

  * Groundhog (app/core/engines/analogue.py): runs for real on small
    fixtures. The hub branch is pinned to a golden file generated from the
    engine BEFORE the dataset seam existed (golden/analogue_hub_fixture.json,
    built by `_hub_archive` below; regenerate only on a deliberate change).
  * Particle filter (app/core/engines/pf.py): no engine in CI, so prepare()
    is driven with resolve_state replaced by a sentinel that raises with
    the arguments it was given (the test_pf_hardening pattern).

No hub, no network: runs with FLUBNF_HUB=/nonexistent.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import datasets as D
from app.core.engines import analogue as EA
from app.core.engines import pf as PF
from app.core.runs import RunSpec
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL

GOLDEN = Path(__file__).resolve().parent / "golden" / "analogue_hub_fixture.json"

#: the fixture's hub locations: three states and the national row
HUB_LOCS = (("01", "AL", "Alabama", 5_000_000), ("02", "AK", "Alaska", 700_000),
            ("04", "AZ", "Arizona", 7_000_000), ("US", "US", "US", 330_000_000))
#: forecast dates the golden file pins (in season, and late season)
GOLDEN_DATES = ("2023-12-02", "2024-02-24")


def _saturdays(a: date, b: date):
    d = a + timedelta(days=(5 - a.weekday()) % 7)
    while d <= b:
        yield d
        d += timedelta(days=7)


def _curve(i: int, j: int, scale: float) -> float:
    """A deterministic seasonal wave: a winter peak, a group phase, a floor."""
    phase = ((i + 3 * j) % 52) / 52.0
    w = math.exp(-((phase - 0.4) ** 2) / 0.008)
    return float(round(scale * (0.6 + 9.0 * w) * (1 + 0.05 * ((i * 7 + j) % 5)), 0))


def _hub_archive(root: Path) -> dict:
    """A FluSight-shaped archive: {date: vintage csv path}, plus the
    locations table at root/locations.csv. One vintage per GOLDEN_DATE,
    each holding every week through its date."""
    root.mkdir(parents=True, exist_ok=True)
    loc_csv = root / "locations.csv"
    loc_csv.write_text("abbreviation,location,location_name,population\n" + "".join(
        f"{a},{f},{n},{p}\n" for f, a, n, p in HUB_LOCS))
    weeks = list(_saturdays(date(2019, 8, 3), date(2024, 2, 24)))
    rows = [(d.isoformat(), f, n, _curve(i, j, p / 1e6))
            for i, d in enumerate(weeks) for j, (f, _a, n, p) in enumerate(HUB_LOCS)]
    out = {}
    for fd in GOLDEN_DATES:
        v = root / f"target-hospital-admissions_{fd}.csv"
        v.write_text("date,location,location_name,value,weekly_rate\n" + "".join(
            f"{d},{f},{n},{val:g},\n" for d, f, n, val in rows if d <= fd))
        out[fd] = v
    return {"vintages": out, "locations": loc_csv}


def _golden_specs():
    """(label, RunSpec) pairs the golden file pins: the bare analogue, the
    shipped Groundhog (FluSurv-NET donors), a weeks-to-drop trim and the
    bandwidth knob."""
    shipped = EA.aux_preset(EA.SHIPPED_AUX)(None, 0, None)
    names = [n for _f, _a, n, _p in HUB_LOCS]
    out = []
    for fd in GOLDEN_DATES:
        out += [
            (f"{fd}/bare", RunSpec(engine="analogue", forecast_date=fd,
                                   locations=names, extra={})),
            (f"{fd}/groundhog", RunSpec(engine="analogue", forecast_date=fd,
                                        locations=names, extra=dict(shipped))),
            (f"{fd}/drop1", RunSpec(engine="analogue", forecast_date=fd,
                                    locations=names, weeks_to_drop=1,
                                    extra={})),
            (f"{fd}/bw3", RunSpec(engine="analogue", forecast_date=fd,
                                  locations=names,
                                  extra={"knobs": {"groundhog.bandwidth": 3}})),
        ]
    return out


def _run_golden(engine_module, arch: dict, monkeypatch) -> dict:
    monkeypatch.setattr(engine_module, "vintage_path",
                        lambda d: arch["vintages"][str(d)])
    monkeypatch.setattr(engine_module, "LOCATIONS", arch["locations"])
    out = {}
    for label, spec in _golden_specs():
        q = engine_module.run(spec)
        out[label] = {loc: {h: [round(float(lv[float(L)]), 9) for L in QL]
                            for h, lv in sorted(hq.items())}
                      for loc, hq in sorted(q.items())}
    return out


# ------------------------------------------------------------ the hub path

def test_hub_path_quantiles_unchanged(tmp_path, monkeypatch):
    """The Groundhog's hub path, byte for byte against the pre-seam engine."""
    arch = _hub_archive(tmp_path / "hub")
    got = _run_golden(EA, arch, monkeypatch)
    want = json.loads(GOLDEN.read_text())
    assert sorted(got) == sorted(want)
    for label in want:
        assert got[label] == want[label], label
    # the fixture is not vacuous: every configuration forecasts every row
    assert all(len(v) >= 3 for v in want.values())


def test_hub_path_never_reads_the_dataset_store(tmp_path, monkeypatch):
    """No extra['dataset'] -> from_spec returns before any filesystem
    access: a store that raises on every read is never reached."""
    arch = _hub_archive(tmp_path / "hub")
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("store read"))
    monkeypatch.setattr(D, "get", boom)
    monkeypatch.setattr(D, "resolve", boom)
    monkeypatch.setattr(D, "list_datasets", boom)
    monkeypatch.setattr(EA, "vintage_path", lambda d: arch["vintages"][str(d)])
    monkeypatch.setattr(EA, "LOCATIONS", arch["locations"])
    q = EA.run(RunSpec(engine="analogue", forecast_date=GOLDEN_DATES[0],
                       locations=["Alabama"], extra={}))
    assert set(q) == {"Alabama"}


def test_hub_path_passes_no_exclusion_keyword(tmp_path, monkeypatch):
    """The shipped call to the library is unchanged: no exclude_seasons."""
    arch = _hub_archive(tmp_path / "hub")
    monkeypatch.setattr(EA, "vintage_path", lambda d: arch["vintages"][str(d)])
    monkeypatch.setattr(EA, "LOCATIONS", arch["locations"])
    seen = []
    real = EA.AN.forecast

    def spy(*a, **k):
        seen.append(set(k))
        return real(*a, **k)
    monkeypatch.setattr(EA.AN, "forecast", spy)
    EA.run(RunSpec(engine="analogue", forecast_date=GOLDEN_DATES[0],
                   locations=["Alabama"], extra={}))
    assert seen and all("exclude_seasons" not in k for k in seen)


# ------------------------------------------------------- custom datasets

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    return tmp_path / "datasets"


def mh_bytes(groups=("Pediatric", "Adult", "Overall"), start=date(2019, 8, 3),
             end=date(2024, 2, 24), pop=True, rate=False) -> bytes:
    """A MicroHub file: groups x weeks of the seasonal wave, Overall the sum."""
    head = "date,target_group,value" + (",population" if pop else "")
    lines = [head]
    for i, d in enumerate(_saturdays(start, end)):
        vals = {}
        for j, g in enumerate(groups):
            if g == "Overall":
                continue
            vals[g] = _curve(i, j, 3.0 + j)
        if "Overall" in groups:
            vals["Overall"] = sum(vals.values())
        for j, g in enumerate(groups):
            v = vals[g] / 10.0 + 0.25 if rate else vals[g]
            lines.append(f"{d.month}/{d.day}/{d:%y},{g},{v:g}"
                         + (f",{100000 * (j + 1)}" if pop else ""))
    return ("\n".join(lines) + "\n").encode()


def _no_hub(monkeypatch):
    """The hub archive and locations table raise if touched."""
    def boom(*a, **k):
        raise AssertionError("the hub archive was read")
    monkeypatch.setattr(EA, "vintage_path", boom)
    monkeypatch.setattr(EA, "LOCATIONS", Path("/nonexistent/locations.csv"))


def ds_spec(ds, fd, **kw):
    extra = {"dataset": ds.ref(), **kw.pop("extra", {})}
    return RunSpec(engine="analogue", forecast_date=fd,
                   locations=kw.pop("locations", ds.groups), extra=extra, **kw)


def test_groundhog_forecasts_a_custom_dataset_without_the_hub(store, monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    _no_hub(monkeypatch)
    q = EA.run(ds_spec(ds, "2023-12-02"))
    assert set(q) == {"Pediatric", "Adult", "Overall"}
    for hq in q.values():
        assert sorted(hq) == ["0", "1", "2", "3"]
        for lv in hq.values():
            assert sorted(lv) == sorted(float(L) for L in QL)
            vs = [lv[float(L)] for L in QL]
            assert vs == sorted(vs) and vs[0] > 0


def test_groundhog_on_unversioned_data_never_sees_later_weeks(store, monkeypatch):
    """Final data read at an early as-of equals the same data cut there."""
    full = D.ingest(mh_bytes(), "full", kind="count")
    cut = D.ingest(mh_bytes(end=date(2023, 12, 2)), "cut", kind="count")
    _no_hub(monkeypatch)
    a = EA.run(ds_spec(full, "2023-12-02"))
    b = EA.run(ds_spec(cut, "2023-12-02"))
    assert a == b


def test_groundhog_refuses_a_week_the_dataset_lacks(store, monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    _no_hub(monkeypatch)
    with pytest.raises(FileNotFoundError, match="No week 2023-12-03"):
        EA.run(ds_spec(ds, "2023-12-03"))


def test_custom_default_uses_no_flu_donor_exclusions(store, monkeypatch):
    """Donors from season 2021 (registered as excluded for US flu) serve a
    custom dataset by default; asking for the exclusion removes them."""
    raw = mh_bytes(start=date(2020, 8, 1), end=date(2022, 12, 3))
    ds = D.ingest(raw, "short", kind="count")
    _no_hub(monkeypatch)
    fd = "2022-11-26"                          # season 2022: donors 2020, 2021
    free = EA.run(ds_spec(ds, fd))
    assert free, "the unrestricted pool forecasts"
    both = EA.run(ds_spec(ds, fd, extra={"donor_exclusions": [2020, 2021]}))
    assert both == {}                          # no prior season left


def test_hub_only_research_keys_are_refused_on_a_dataset(store, monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    _no_hub(monkeypatch)
    for key, val in (("reporting", {"mode": "both"}),
                     ("analogue_completeness", {"c01": 0.9})):
        with pytest.raises(ValueError, match="completeness"):
            EA.run(ds_spec(ds, "2023-12-02", extra={key: val}))


def test_a_changed_or_deleted_dataset_is_refused_loudly(store, monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    spec = ds_spec(ds, "2023-12-02")
    spec.extra["dataset"] = {**ds.ref(), "digest": "0" * 16}
    with pytest.raises(D.DatasetError, match="no longer matches"):
        EA.run(spec)
    D.delete(ds.id)
    with pytest.raises(D.DatasetError, match="No dataset"):
        EA.run(ds_spec(ds, "2023-12-02"))


def test_dataset_adapters(store):
    ds = D.ingest(mh_bytes(end=date(2020, 9, 26)), "small", kind="count")
    assert ds.weeks()[0] == "2019-08-03" and ds.weeks()[-1] == "2020-09-26"
    assert ds.forecast_dates() == ds.weeks()[1:]
    assert not ds.vintage_true
    assert ds.truth_path("2020-01-04") == ds.final_path
    s = ds.series("Adult", "2019-08-24")
    assert s["dates"] == ["2019-08-03", "2019-08-10", "2019-08-17", "2019-08-24"]
    assert len(ds.series("Adult")["dates"]) == len(ds.weeks())
    t = ds.truth()
    assert t[("Overall", "2019-08-03")] == (t[("Pediatric", "2019-08-03")]
                                            + t[("Adult", "2019-08-03")])
    assert D.from_spec(RunSpec(engine="analogue", forecast_date="2020-01-04")) is None
    assert D.from_spec({"extra": {"dataset": ds.ref()}}).id == ds.id


# --------------------------------------------------------- particle filter

class _Sentinel(Exception):
    pass


def _pf_ready(monkeypatch, seen):
    import flubnf.sihrs_fit as sf
    monkeypatch.setattr(PF, "perl_available", lambda: True)
    monkeypatch.setattr(PF, "engine_current", lambda: True)

    def sentinel(loc, **kw):
        seen.append((loc, kw))
        raise _Sentinel(f"resolve_state({loc}, {kw})")
    monkeypatch.setattr(sf, "resolve_state", sentinel)


def test_pf_prepare_reads_the_dataset_truth_and_locations(store, tmp_path,
                                                          monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    seen = []
    _pf_ready(monkeypatch, seen)
    import app.core.data as data

    def boom(*a, **k):
        raise AssertionError("the hub archive was read")
    monkeypatch.setattr(data, "vintage_path", boom)
    with pytest.raises(_Sentinel):
        PF.prepare(ds_spec(ds, "2023-12-02", locations=["Adult"]),
                   tmp_path / "w")
    loc, kw = seen[0]
    assert loc == "Adult"
    assert Path(kw["truth_csv"]) == ds.final_path
    assert Path(kw["locations_csv"]) == ds.locations_csv
    assert kw["as_of"] == "2023-12-02"


def test_pf_prepare_default_uses_the_hub_paths(tmp_path, monkeypatch):
    import app.core.data as data
    seen = []
    _pf_ready(monkeypatch, seen)
    monkeypatch.setattr(data, "vintage_path", lambda d: Path(f"/hub/v_{d}.csv"))
    with pytest.raises(_Sentinel):
        PF.prepare(RunSpec(engine="pf", forecast_date="2023-12-02",
                           locations=["Ohio"]), tmp_path / "w")
    _loc, kw = seen[0]
    assert kw["truth_csv"] == Path("/hub/v_2023-12-02.csv")
    assert kw["locations_csv"] == data.LOCATIONS


def test_pf_refuses_hub_only_variants_on_a_dataset(store, tmp_path,
                                                   monkeypatch):
    ds = D.ingest(mh_bytes(), "wave", kind="count")
    _pf_ready(monkeypatch, [])
    for key, val in (("variant", "natg"), ("variant", "2strain"),
                     ("anchor_asof", "2023-11-25"),
                     ("reporting", {"mode": "anchor"})):
        with pytest.raises(ValueError, match="plain SIHRS filter can"):
            PF.prepare(ds_spec(ds, "2023-12-02", extra={key: val}),
                       tmp_path / f"w-{key}-{len(str(val))}")


def test_pf_cell_stems_are_safe_for_a_national_spelling():
    assert PF.dataset_tag("US (national)") == "US__national_"
    assert PF.dataset_tag("Age 0") == "Age_0"
    assert PF._hub_tag("New York") == "New_York"
