"""The sandbox's Oracle SIHRS start (app/core/sandbox.py from_shipped,
shipped_state, set_population; the gallery's New model form): the
production cell composed from the production pieces, byte for byte what
pf.prepare materializes for the same location and date (suffix, model,
data, conf keys and seed), with calendar-true week offsets, creation
digests that an edit or a copy cannot carry, and a stored dataset with a
population as the other source. Hub-free and engine-free: a tiny vintage
and locations table in tmp, BNG2.pl faked (conftest.sandbox_root).
"""
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import data as data_mod                    # noqa: E402
from app.core import datasets as D                       # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.runs import RunSpec, derive_seed           # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402

client = TestClient(srv.app)

FD = "2024-11-09"                                         # a Saturday
POPS = {"Alabama": ("01", 5_157_699), "New York": ("36", 19_571_216),
        "US": ("US", 340_110_988)}
#: Alabama did not report this week: a gap in t, never a renumbered row
MISSING = "2024-10-19"


def _saturdays(a: date, b: date):
    d = a + timedelta(days=(5 - a.weekday()) % 7)
    while d <= b:
        yield d
        d += timedelta(days=7)


@pytest.fixture
def hub(sandbox_root, tmp_path, monkeypatch):
    """A locations table and one vintage (FD) the sandbox and pf.prepare
    both read through app.core.data."""
    loc = tmp_path / "locations.csv"
    with open(loc, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["abbreviation", "location", "location_name", "population"])
        for name, (f, p) in POPS.items():
            w.writerow([name[:2].upper(), f, name, p])
    vf = tmp_path / f"target-hospital-admissions_{FD}.csv"
    with open(vf, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "location", "location_name", "value"])
        for i, d in enumerate(_saturdays(date(2024, 8, 1), date.fromisoformat(FD))):
            for j, (name, (f, _p)) in enumerate(POPS.items()):
                if name == "Alabama" and d.isoformat() == MISSING:
                    continue
                w.writerow([d.isoformat(), f, name, 10 + 3 * i + j])

    def vintage_path(d):
        if str(d) != FD:
            raise FileNotFoundError(f"No vintage for {d}. Nearby: [{FD!r}]")
        return vf
    monkeypatch.setattr(data_mod, "LOCATIONS", loc)
    monkeypatch.setattr(data_mod, "vintage_path", vintage_path)
    monkeypatch.setattr(data_mod, "vintages", lambda: [FD])
    return {"locations": loc, "vintage": vf}


def _conf_keys(text: str) -> dict:
    """key -> value of a pf.conf, the prior lines as one sorted list, the
    three path keys left out (they name each tree's own folder)."""
    out, priors = {}, []
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s or "=" not in s:
            continue
        k, v = (x.strip() for x in s.split("=", 1))
        if k in ("bng_command", "model", "output_dir"):
            continue
        if k.endswith("_var"):
            priors.append(" ".join(s.split()))
        else:
            assert k not in out, f"{k} written twice"
            out[k] = v
    out["priors"] = sorted(priors)
    return out


# --------------------------------------------------- the production cell

def test_shipped_start_is_the_production_cell(hub, tmp_path):
    """model.bngl (after its header comment), data.exp, the suffix, the
    seed and the conf keys equal what pf.prepare writes for the same
    location and date; a space in the name becomes '_' as in production."""
    sb.from_shipped("ny", "New York", FD)
    files = sb.read_model("ny")
    cells = pf.prepare(RunSpec(engine="pf", forecast_date=FD,
                               locations=["New York"], replicates=1),
                       tmp_path / "prod")
    cell = Path(cells[0]["dir"])
    assert cell.name == "New_York_r0"
    header, _, body = files["model.bngl"].partition("begin model\n")
    assert "begin model\n" + body == (cell / "m.bngl").read_text()
    assert all(l.startswith("#") for l in header.splitlines())
    assert sb.simulate_suffix(files["model.bngl"]) == "New_York_flu"
    assert files["data.exp"] == (cell / "New_York_flu.exp").read_text()
    info = sb.read_info("ny")
    assert info["origin"] == sb.SHIPPED and info["location"] == "New York"
    assert info["forecast_date"] == FD and info["season_start"] == "2024-08-01"
    assert info["seed"] == cells[0]["seed"] == derive_seed("New York", FD, 0)
    assert info["population"] == POPS["New York"][1]
    assert info["digests"] == sb.digests(files)
    # the conf: the sandbox's run of the shipped model at production's
    # settings writes production's keys and priors
    w = sb.prepare("ny", particles=10_000, jitter=0.15, forecast_weeks=4,
                   seed=info["seed"])
    mine = _conf_keys((w / "ny_r0" / "pf.conf").read_text())
    prod = _conf_keys((cell / "pf.conf").read_text())
    assert mine == prod
    # the cell names its jurisdiction, as production's does
    c = json.loads((w / "cells.json").read_text())[0]
    assert c["location"] == "New York" and c["n_obs"] == cells[0]["n_obs"]
    assert c["last_week_offset"] == cells[0]["last_week_offset"]
    meta = json.loads((w / "meta.json").read_text())
    assert meta["origin"] == sb.SHIPPED and meta["shipped"]["intact"] is True
    assert meta["digests"] == info["digests"]


def test_shipped_data_keeps_calendar_week_offsets(hub):
    sb.from_shipped("al", "Alabama", FD)
    rows = sb.read_exp(sb.read_model("al")["data.exp"])["rows"]
    t = [int(r[0]) for r in rows]
    gap = [b - a for a, b in zip(t, t[1:])]
    assert gap.count(2) == 1 and set(gap) == {1, 2}       # the missing week
    src = sb.read_data_source("al")
    assert src["asof"] == FD and src["origin"] == "2024-08-01"
    assert src["dropped"] == 1 and MISSING not in src["dates"]
    assert src["dates"][0] == "2024-08-03" and src["dates"][-1] == FD
    assert all(date.fromisoformat(d).weekday() == 5 for d in src["dates"])
    # a refill anchors t at the model's season start, not the range's
    assert sb.week_origin("al", "2024-09-07") == "2024-08-01"


def test_a_season_start_is_kept(hub):
    sb.from_shipped("al2", "Alabama", FD, season_start="2024-09-01")
    info = sb.read_info("al2")
    assert info["season_start"] == "2024-09-01"
    src = sb.read_data_source("al2")
    assert src["dates"][0] == "2024-09-07"
    assert sb.read_exp(sb.read_model("al2")["data.exp"])["rows"][0][0] == 0


def test_shipped_start_refusals_leave_nothing_behind(hub, monkeypatch):
    with pytest.raises(sb.SandboxError, match="no hub vintage for 2024-11-02"):
        sb.from_shipped("x1", "Alabama", "2024-11-02")
    with pytest.raises(sb.SandboxError, match="unknown location 'Atlantis'"):
        sb.from_shipped("x2", "Atlantis", FD)
    with pytest.raises(sb.SandboxError, match="not before the forecast date"):
        sb.from_shipped("x3", "Alabama", FD, season_start="2024-12-01")
    with pytest.raises(sb.SandboxError, match="not a model name"):
        sb.from_shipped("bad name", "Alabama", FD)
    sb.from_shipped("al", "Alabama", FD)
    with pytest.raises(sb.SandboxError, match="already exists"):
        sb.from_shipped("al", "Alabama", FD)
    assert sorted(p.name for p in sb.MODELS.iterdir()) == ["al"]


def test_an_edit_or_a_copy_is_not_the_shipped_model(hub):
    sb.from_shipped("al", "Alabama", FD)
    st = sb.shipped_state("al")
    assert st["shipped"] and st["intact"] and st["changed"] == []
    origins = {m["name"]: m["origin"] for m in sb.list_models()}
    assert origins["al"] == f"the Oracle SIHRS start (Alabama, {FD})"
    sb.copy_model("al", "al_copy")
    assert sb.read_info("al_copy")["origin"] == "copy:al"
    assert not sb.shipped_state("al_copy")["shipped"]
    assert sb.read_info("al_copy")["season_start"] == "2024-08-01"
    pri = sb.read_model("al")["priors.conf"].replace("0.6 2.5", "0.8 2.5")
    sb.save_model("al", {"priors.conf": pri})
    st = sb.shipped_state("al")
    assert st["shipped"] and not st["intact"] and st["changed"] == ["priors.conf"]
    origins = {m["name"]: m["origin"] for m in sb.list_models()}
    assert origins["al"] == f"the Oracle SIHRS start (Alabama, {FD}), modified"
    # a hand-written model.json naming the origin, without digests, is not it
    (sb.MODELS / "al_copy" / sb.MODEL_FILE).write_text(
        json.dumps({"origin": sb.SHIPPED, "location": "Alabama"}))
    assert not sb.shipped_state("al_copy")["intact"]


# ---------------------------------------------------- a stored dataset

def _mh(pop=True, kind_rate=False) -> bytes:
    lines = ["date,target_group,value" + (",population" if pop else "")]
    for i, d in enumerate(_saturdays(date(2023, 8, 5), date(2024, 2, 24))):
        for j, g in enumerate(("Adult", "Child")):
            v = 20 + 2 * i + j
            lines.append(f"{d.month}/{d.day}/{d:%y},{g},{v}"
                         + (f",{250000 * (j + 1)}" if pop else ""))
    return ("\n".join(lines) + "\n").encode()


def test_a_dataset_group_with_a_population_starts_the_filter(sandbox_root,
                                                            tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")

    def no_hub(*a, **k):
        raise AssertionError("the hub archive was read")
    monkeypatch.setattr(data_mod, "vintage_path", no_hub)
    ds = D.ingest(_mh(), "wave", kind="count")
    sb.from_shipped("adult", "Adult", "2024-01-06", dataset=ds.id)
    info = sb.read_info("adult")
    assert info["origin"] == sb.SHIPPED_DATASET and info["dataset"] == ds.ref()
    assert info["population"] == 250000 and info["season_start"] == "2023-08-01"
    files = sb.read_model("adult")
    assert sb.simulate_suffix(files["model.bngl"]) == "Adult_flu"
    assert re.search(r"(?m)^N\s+250000\b", files["model.bngl"])
    assert sb.read_data_source("adult")["dataset"]["id"] == ds.id
    assert {m["name"]: m["origin"] for m in sb.list_models()}["adult"] == \
        "the Oracle SIHRS start (Adult, 2024-01-06)"
    # the gallery offers it; a dataset without a population is not offered
    bare = D.ingest(_mh(pop=False), "nopop", kind="count")
    html = client.get("/sandbox").text
    assert f'value="shipped:dataset:{ds.id}"' in html
    assert f'value="shipped:dataset:{bare.id}"' not in html
    with pytest.raises(sb.SandboxError, match="no population"):
        sb.from_shipped("x", "Adult", "2024-01-06", dataset=bare.id)
    with pytest.raises(sb.SandboxError, match="No week 2024-01-07"):
        sb.from_shipped("x", "Adult", "2024-01-07", dataset=ds.id)
    with pytest.raises(sb.SandboxError, match="no group"):
        sb.from_shipped("x", "Elder", "2024-01-06", dataset=ds.id)
    r = client.post("/sandbox/new", data={
        "name": "child", "start": f"shipped:dataset:{ds.id}", "group": "Child",
        "as_of": "2024-01-06"}, follow_redirects=False)
    assert r.headers["location"] == "/sandbox?model=child"
    assert sb.read_info("child")["location"] == "Child"


# ------------------------------------------------------ set_population

def test_set_population_rewrites_n_and_refuses_an_sihrs_shaped_model(sandbox_root):
    sb.add_example("sir_example")
    sb.set_population("sir_example", 123456)
    assert re.search(r"(?m)^N\s+123456\s+# population",
                     sb.read_model("sir_example")["model.bngl"])
    sb.add_example("sihrs_example")
    before = sb.read_model("sihrs_example")["model.bngl"]
    with pytest.raises(sb.SandboxError, match="derives i0 from N"):
        sb.set_population("sihrs_example", 5)
    assert sb.read_model("sihrs_example")["model.bngl"] == before
    sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError, match="no line named N"):
        sb.set_population("kinetics_example", 5)


def test_fill_with_set_population_uses_the_hub_population(hub, monkeypatch):
    monkeypatch.setattr(data_mod, "vintage_series", lambda d, loc: {
        "dates": ["2024-09-07", "2024-09-14"], "values": [5.0, 7.0]})
    sb.add_example("sir_example")
    info = sb.fill_data("sir_example", "Alabama", "2024-09-07", FD, asof=FD,
                        set_pop=True)
    assert info["population_set"] == POPS["Alabama"][1]
    assert re.search(rf"(?m)^N\s+{POPS['Alabama'][1]}\b",
                     sb.read_model("sir_example")["model.bngl"])
    sb.from_shipped("al", "Alabama", FD)
    exp = sb.read_model("al")["data.exp"]
    with pytest.raises(sb.SandboxError, match="derives i0 from N"):
        sb.fill_data("al", "Alabama", "2024-09-07", FD, asof=FD, set_pop=True)
    assert sb.read_model("al")["data.exp"] == exp            # nothing loaded


# ------------------------------------------------------------ the pages

def test_the_gallery_offers_the_start_and_the_route_creates_it(hub):
    html = client.get("/sandbox").text
    assert '<option value="shipped:sihrs">' in html
    assert f'<option value="{FD}">{FD}</option>' in html
    assert 'name="season_start"' in html
    r = client.post("/sandbox/new", data={
        "name": "oracle_alabama", "start": "shipped:sihrs",
        "location": "Alabama", "forecast_date": FD}, follow_redirects=False)
    assert r.headers["location"] == "/sandbox?model=oracle_alabama"
    info = sb.read_info("oracle_alabama")
    assert info["origin"] == sb.SHIPPED and info["seed"] == derive_seed("Alabama", FD, 0)
    # the run settings: the full fit (production's 10,000), a quick check
    # one click away, the production seed and 4 forecast weeks
    html = client.get("/sandbox?model=oracle_alabama").text
    assert re.search(r'<option value="full" selected>Full fit \(10,000\)', html)
    assert "Quick check (200)" in html
    assert f'name="seed" type="number" value="{info["seed"]}"' in html
    assert 'name="forecast_weeks" type="number" value="4"' in html
    assert "the Oracle SIHRS start (Alabama" in html
    # a refusal flashes and creates nothing
    ui_state._status.pop("flash", None)
    client.post("/sandbox/new", data={"name": "nope", "start": "shipped:sihrs",
                                      "location": "Alabama",
                                      "forecast_date": "2020-01-04"},
                follow_redirects=False)
    assert "no hub vintage" in (ui_state._status.get("flash") or "")
    assert not (sb.MODELS / "nope").exists()


def test_without_a_hub_the_start_is_disabled(sandbox_root, monkeypatch):
    monkeypatch.setattr(sb, "vintages", lambda: [])
    html = client.get("/sandbox").text
    assert re.search(r'<option value="shipped:sihrs" disabled>[^<]*no hub archive', html)


def test_no_bare_model_name_in_the_sandbox_pages(hub):
    sb.from_shipped("al", "Alabama", FD)
    for page in ("/sandbox", "/sandbox?model=al"):
        html = client.get(page).text
        html = re.sub(r"<textarea.*?</textarea>", "", html, flags=re.S)
        html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
        text = " ".join(html.split())
        # the compartment model the member is built on keeps its own name,
        # as on every other page (test_oracle_text._ALLOWED): an example's
        # note says "the SIHRS compartment model"
        bare = [text[max(0, m.start() - 20):m.end() + 10]
                for m in re.finditer(r"(?<!Oracle )SIHRS(?! compartment)", text)]
        assert not bare, (page, bare)
