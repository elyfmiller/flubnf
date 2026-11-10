"""The Groundhog's donor weeks on a dataset, counted once per dataset
(UX review F54 and the Replay part of F53, package P4).

  * checks.donor_counts gives, for every week, what
    flubnf.analogue.donor_ratios gives on the bank the engine reads then
    (cut at the as-of; no donor season excluded), at every horizon, in
    one pass: 200 groups x 520 weeks in about a second, not minutes;
  * datasets_ui.donor_weeks keeps it in memory by dataset (never a file
    in the dataset's folder); the Forecast page's context carries it;
  * the Replay form shows how many weeks of its range have enough donors
    (informs only: Replay stays on) and how long the replay takes, by the
    same rules in Python and in static/dataset_replay.js.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import datasets as D
from app.core import estimates as ES
from app.core.datasets import checks as CK
from app.ui import datasets_ui as DU
from flubnf import analogue as AN

from test_dataset_engines import grouped_bytes         # noqa: E402
from test_datasets_ui import (TEMPLATE, client,        # noqa: E402,F401
                              isolated, stored)

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
REPLAY_JS = STATIC / "dataset_replay.js"
EST_JS = STATIC / "estimate.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")


def reference(bank, t, bandwidth=AN.DEFAULT_BANDWIDTH):
    """donor_ratios per horizon on the bank the engine reads at as-of t."""
    cut = {k: v for k, v in bank.items()
           if k[1] <= t and math.isfinite(v) and v > 0}
    return tuple(len(AN.donor_ratios(cut, AN.epiweek(t), AN.season_of(t), h,
                                     bandwidth=bandwidth, exclude_seasons=()))
                 for h in CK.GROUNDHOG_HORIZONS)


def bank_of(raw: bytes, **kw) -> dict:
    rep = D.validate(raw, **kw)
    assert rep.ok, [str(p) for p in rep.problems]
    return CK._newest(rep.records)


def zeros_bank() -> dict:
    """Three groups over five seasons with summer zeros (a donor whose
    later week reads 0 is no donor) and weeks around each August 1, where
    a donor's later week falls after the as-of."""
    out = {}
    d0 = date(2019, 7, 6)
    for i in range(5 * 52 + 10):
        d = d0 + timedelta(days=7 * i)
        for j, g in enumerate(("a", "b", "c")):
            v = 0.0 if d.month in (6, 7) and (i + j) % 3 else \
                float(3 + (i * 5 + j * 7) % 50)
            out[(g, d)] = v
    return out


@pytest.mark.parametrize("name", ["template", "short", "zeros"])
def test_the_counts_are_donor_ratios_at_every_week_and_horizon(name):
    bank = {"template": lambda: bank_of(TEMPLATE.read_bytes()),
            "short": lambda: bank_of(grouped_bytes(
                groups=("North", "South"), start=date(2023, 8, 5),
                end=date(2025, 11, 15), pop=False)),
            "zeros": zeros_bank}[name]()
    weeks = sorted({d for _, d in bank})[1:]
    got = CK.donor_counts(bank, weeks)
    assert list(got) == weeks
    for t in weeks:
        assert got[t] == reference(bank, t), t


def test_the_counts_follow_the_donor_window():
    bank = zeros_bank()
    weeks = sorted({d for _, d in bank})[1:][::7]
    got = CK.donor_counts(bank, weeks, bandwidth=4)
    for t in weeks:
        assert got[t] == reference(bank, t, bandwidth=4), t


def test_the_count_at_the_newest_week_is_the_checks_own():
    """dataset_checks' notice counts horizon 1 at the newest week: the
    same number as donor_counts there."""
    raw = grouped_bytes(groups=("North", "South"), start=date(2023, 8, 5),
                        end=date(2025, 11, 15), pop=False)
    rep = D.validate(raw)
    CK.dataset_checks(rep)
    (notice,) = [w for w in rep.warnings
                 if w.startswith(CK.TOO_LITTLE_HISTORY)]
    n = int(re.search(r"finds (\d+) weeks", notice).group(1))
    bank = CK._newest(rep.records)
    last = max(d for _, d in bank)
    assert CK.donor_counts(bank, [last])[last][0] == n == 20
    short = CK.groundhog_shortfall(rep)
    assert short == {"n": 20, "need": 30, "seasons": 1}


def test_two_hundred_groups_of_ten_seasons_count_in_seconds():
    bank = {}
    d0 = date(2014, 8, 2)
    for i in range(520):
        d = d0 + timedelta(days=7 * i)
        for g in range(200):
            bank[(g, d)] = float(5 + (i + g) % 30)
    weeks = sorted({d for _, d in bank})[1:]
    t0 = time.perf_counter()
    got = CK.donor_counts(bank, weeks)
    assert time.perf_counter() - t0 < 10        # 176 s by donor_ratios
    t = weeks[300]
    assert got[t] == reference(bank, t)


# --------------------------------------------------- one count per dataset

def test_a_datasets_counts_are_kept_in_memory_only(monkeypatch):
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    DU._DONORS.clear()
    calls = []
    real = CK.donor_counts

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(CK, "donor_counts", counting)
    before = sorted(p.relative_to(ds.path) for p in ds.path.rglob("*"))
    got = DU.donor_weeks(ds)
    assert DU.donor_weeks(D.get(ds.id)) is got and len(calls) == 1
    assert sorted(p.relative_to(ds.path) for p in ds.path.rglob("*")) \
        == before
    assert list(got) == ds.forecast_dates()
    assert sum(1 for n in got.values() if n >= 30) == 35
    assert min(k for k, n in got.items() if n >= 30) == "2024-01-13"


def test_the_forecast_page_carries_each_weeks_donors():
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    r = client.get(f"/forecast?source={ds.id}")
    view = r.context["dataset"]
    assert view["donor_need"] == AN.MIN_DONORS
    assert view["donor_weeks"] == DU.donor_weeks(ds)


# ------------------------------------------------------- the Replay form

def one_series_bytes() -> bytes:
    """One series, four seasons, no population: the Groundhog finds 15 to
    17 donor weeks at every week of its newest season."""
    d0, lines = date(2021, 8, 7), ["week_ending,cases"]
    for i in range(203):
        d = d0 + timedelta(days=7 * i)
        lines.append(f"{d.isoformat()},{20 + (i * 13) % 90}")
    return ("\n".join(lines) + "\n").encode()


def replay_form(ds) -> str:
    html = client.get(f"/retro?dataset={ds.id}").text
    form = html[html.index('id="dsr-form"'):]
    return " ".join(form[:form.index("</form>")].split())


def test_the_replay_badge_counts_its_weeks_and_replay_stays_on():
    thin = stored(one_series_bytes(), "Flu")
    form = replay_form(thin)
    assert ">Groundhog donors: enough in 0 of 38 weeks<" in form
    assert 'class="uk-badge uk-badge--warn" id="dsr-donors"' in form
    # informs only: a week without donors ends "no forecast"
    assert '<button class="gold" data-guard="console-run">Replay</button>' \
        in form
    ok = stored(TEMPLATE.read_bytes(), "Kids")
    w0, w1 = DU.replay_window(ok.forecast_dates())
    weeks = [w for w in ok.forecast_dates() if w0 <= w <= w1]
    n = sum(1 for w in weeks if DU.donor_weeks(ok)[w] >= 30)
    form = replay_form(ok)
    assert f">Groundhog donors: enough in {n} of {len(weeks)} weeks<" in form
    assert 0 < n < len(weeks)
    assert '<button class="gold" data-guard="console-run">Replay</button>' \
        in form
    # what the page's script reads: every forecast week's count
    data = re.search(r'<script type="application/json" id="dsr-donor-data">'
                     r'(.*?)</script>', form).group(1)
    assert json.loads(data) == {"need": 30, "weeks": DU.donor_weeks(ok)}


def test_the_replay_form_carries_the_estimate_and_the_time_line():
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    form = replay_form(ds)
    for k, v in {**ES.page_params(None), "data-cells": str(len(ds.truth())),
                 "data-gh-quick": str(DU.GROUNDHOG_QUICK)}.items():
        assert f'{k}="{v}"' in form
    # the form opens on the Groundhog alone: a small dataset is quick
    assert re.search(r'<div id="dsr-est"><ul class="uk-meta" aria-label='
                     r'"Replay time"><li>.*?<span>under a minute</span>',
                     form)
    assert '<script src="/static/dataset_replay.js" defer></script>' in \
        client.get(f"/retro?dataset={ds.id}").text


def test_the_time_line_by_its_rules():
    weeks = ["2024-10-05", "2024-10-12", "2024-10-19"]
    assert DU.replay_estimate([], 3, "all") == ""
    assert DU.replay_estimate(weeks, 3, "analogue", cells=400) == \
        "under a minute"
    # past the Groundhog's quick size it says nothing rather than guess
    assert DU.replay_estimate(weeks, 200, "analogue", cells=104_000) == ""
    sec = ES.run_seconds([ES.n_obs_for(w) for w in weeks], 3 * 3, 10_000)
    assert DU.replay_estimate(weeks, 3, "all") == ES.human(*ES.span(sec))
    sec = ES.run_seconds([ES.n_obs_for(w, "2024-09-07") for w in weeks],
                         2 * 5, 2_000)
    assert DU.replay_estimate(weeks, 2, "all", replicates=5, particles=2000,
                              season_start="2024-09-07") == \
        ES.human(*ES.span(sec))
    assert DU.replay_estimate(weeks, 3, "all").startswith("about ")
    assert " to " in DU.replay_estimate(weeks, 3, "all")


# ------------------------------------- the page's script, by the same rules

def _js(tmp_path, body):
    files = [EST_JS, REPLAY_JS]
    drv = ("var E = FluBNFEstimate, R = FluBNFDatasetReplay;\n"
           "print(JSON.stringify((function(){ " + body + " })()));\n")
    if JSC.is_file():
        d = tmp_path / "driver.js"
        d.write_text(drv, encoding="utf-8")
        cmd = [str(JSC), *map(str, files), str(d)]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + "\n".join(f.read_text(encoding="utf-8")
                                    for f in files) + "\n" + drv,
                        encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_js
def test_the_script_counts_the_badge_as_the_server_does(tmp_path):
    dates = ["2024-10-05", "2024-10-12", "2024-10-19", "2024-10-26"]
    counts = {"2024-10-05": 31, "2024-10-12": 29, "2024-10-19": 30}
    cases = [("", ""), ("2024-10-12", "2024-10-19"), ("2024-10-26", ""),
             ("2024-10-19", "2024-10-05"), ("2024-10-05", "2024-10-05")]
    got = _js(tmp_path, "var d = " + json.dumps(dates) + ", c = "
              + json.dumps(counts) + ", out = [], cs = " + json.dumps(cases)
              + "; for (var i = 0; i < cs.length; i++) { out.push("
              "R.donorBadge(R.weeksIn(d, cs[i][0], cs[i][1]), c, 30)); }"
              " return out;")
    want = [list(DU.donor_line([w for w in dates
                                if (not a or w >= a) and (not b or w <= b)],
                               counts, 30)) for a, b in cases]
    assert got == want
    assert want[1] == ["warn", "Groundhog donors: enough in 1 of 2 weeks"]
    assert want[4] == ["ok", "Groundhog donors: enough in 1 of 1 week"]


@needs_js
@pytest.mark.parametrize("engine", ["public", "private"])
def test_the_script_times_a_replay_as_the_server_does(tmp_path, engine,
                                                      monkeypatch):
    monkeypatch.setattr(ES.pf, "_public", lambda: engine == "public")
    attrs = {**ES.page_params(None), "data-cells": "429",
             "data-gh-quick": str(DU.GROUNDHOG_QUICK)}
    weeks = [(date(2024, 10, 5) + timedelta(days=7 * i)).isoformat()
             for i in range(38)]
    cases = [
        {"weeks": weeks, "groups": 3, "engine": "analogue", "cells": 429},
        {"weeks": weeks, "groups": 200, "engine": "analogue",
         "cells": 104_000},
        {"weeks": weeks, "groups": 3, "engine": "all", "replicates": 3,
         "particles": 10_000, "seasonStart": ""},
        {"weeks": weeks[:2], "groups": 1, "engine": "all", "replicates": 1,
         "particles": 1_000, "seasonStart": ""},
        {"weeks": weeks, "groups": 53, "engine": "all", "replicates": 3,
         "particles": 10_000, "seasonStart": "2024-08-03"},
        {"weeks": [], "groups": 3, "engine": "all", "replicates": 3,
         "particles": 10_000, "seasonStart": ""},
    ]
    got = _js(tmp_path, "var a = " + json.dumps(attrs) + ";"
              " var el = {getAttribute: function (n) {"
              " return a.hasOwnProperty(n) ? a[n] : null; }};"
              " var p = E.params(el), cs = " + json.dumps(cases)
              + ", out = []; for (var i = 0; i < cs.length; i++) {"
              " var o = cs[i]; o.quick = " + str(DU.GROUNDHOG_QUICK) + ";"
              " o.cells = o.cells || 0; o.seasonStart = o.seasonStart || '';"
              " out.push(R.estimate(E, p, o)); } return out;")
    want = [DU.replay_estimate(
        c["weeks"], c["groups"], c["engine"],
        replicates=c.get("replicates"), particles=c.get("particles"),
        season_start=c.get("seasonStart", ""), cells=c.get("cells", 0))
        for c in cases]
    assert got == want
    assert want[0] == "under a minute" and want[1] == "" and want[5] == ""
    # the span, never its low end alone
    assert re.fullmatch(r"about [\d.]+ to [\d.]+ (h|min)", want[2])
    assert re.fullmatch(r"about [\d.]+ to [\d.]+ (h|min)", want[4])
    assert want[3] == "under a minute"           # 2 small fits
