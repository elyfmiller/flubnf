"""The weekly report's red tail figures follow the run's own cap
(2026-11-27): a run whose knobs.json records an upper-tail cap reads each
member's h3 97.5% (before the cap) over the level that member's cap
multiplies (flubnf.tailcap: the mean, the last week or the larger) and
marks it red above the cap's n; the submitted file's figure is over the
same level, so a clipped location's arrow reads the cap. A run with no
cap (no knobs.json, a cap of 0, a file that does not read) reads as
before: over the last three weeks' average, red above TAIL_X."""
import html
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                               # noqa: E402
from app.core import report_grid as G                         # noqa: E402
from app.core import report_v2                                 # noqa: E402
from app.core.runs import RunSpec                              # noqa: E402
from app.tests.test_report_design_pass import _bundle          # noqa: E402
from app.tests.test_report_grid import ASOF, COLORS, _filed    # noqa: E402
from flubnf import tailcap                                     # noqa: E402

TIMES = ["2098-01-10", "2098-01-17", "2098-01-24", "2098-01-31"]
PF, GH = G._SHORT["pf"], G._SHORT["analogue"]


def _record(folder: Path, **values) -> Path:
    """knobs.json as a modified run writes it (knobs.write_record)."""
    folder.mkdir(parents=True, exist_ok=True)
    spec = RunSpec("all", ASOF, extra={"knobs": values})
    assert K.write_record(folder / "knobs.json", spec)
    return folder


def _cap(tmp_path: Path, n=10.0, level=None, mode=None) -> dict:
    """The run's cap as the report reads it from its knobs.json."""
    vals = {"output.tail_cap": n}
    if level:
        vals["output.tail_level"] = level
    if mode:
        vals["output.tail_mode"] = mode
    sub = tmp_path / f"cap-{n}-{level}-{mode}"
    cap = G.cap_settings(_record(sub, **vals))
    assert cap is not None
    return cap


def _panel(obs, **q975):
    """A panel whose last three observed weeks are `obs` and each named
    member's h3 97.5% the given value."""
    return {"key": "XX", "name": "X",
            "observed": [["2097-12-20", obs[0]], ["2097-12-27", obs[1]],
                         [ASOF, obs[2]]],
            "models": {m: {"times": TIMES, "q": [[1, 2, 3, 4, v]] * 4}
                       for m, v in q975.items()}}


def _words(line: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", line))


# ------------------------------------------------------- the run's cap

def test_cap_settings_reads_the_runs_own_knobs(tmp_path):
    """n, the level choice with each member's level, and the form, from
    the knobs.json beside the report; an unrecorded level or form is the
    registered one."""
    d = _record(tmp_path / "a", **{"output.tail_cap": 10.0,
                                    "output.tail_level": "larger",
                                    "output.tail_mode": "shrink",
                                    "oracle.narrow": 0.7})
    assert K.read_record(d)["output.tail_cap"] == 10.0
    assert G.cap_settings(d) == {
        "n": 10.0, "level": "larger",
        "levels": tailcap.member_levels("larger"), "mode": "shrink"}
    d = _record(tmp_path / "b", **{"output.tail_cap": 12.5})
    cap = G.cap_settings(d)
    assert cap["n"] == 12.5 and cap["level"] == tailcap.LEVEL_PRODUCTION
    assert cap["levels"] == tailcap.member_levels(tailcap.LEVEL_PRODUCTION)
    assert cap["mode"] == tailcap.MODE_PRODUCTION
    d = _record(tmp_path / "c", **{"output.tail_cap": 10.0,
                                    "output.tail_level": "larger_groundhog"})
    assert G.cap_settings(d)["levels"] == tailcap.member_levels(
        "larger_groundhog")


def test_a_run_with_no_cap_reads_none_and_nothing_raises(tmp_path):
    """No file (a shipped run: its registered cap is CAP_PRODUCTION, none),
    a modified run without a cap, a cap of 0, and every file or value that
    does not read: None, never an error."""
    assert tailcap.CAP_PRODUCTION == 0
    assert G.cap_settings(tmp_path / "shipped") is None
    assert G.cap_settings(tmp_path / "nowhere" / "at-all") is None
    assert K.read_record(tmp_path / "shipped") == {}
    assert G.cap_settings(_record(tmp_path / "narrow",
                                  **{"oracle.narrow": 0.7})) is None
    bad = {
        "zero": '{"values": {"output.tail_cap": 0.0}}',
        "negative": '{"values": {"output.tail_cap": -5}}',
        "nan": '{"values": {"output.tail_cap": NaN}}',
        "word": '{"values": {"output.tail_cap": "ten"}}',
        "level": ('{"values": {"output.tail_cap": 10, '
                  '"output.tail_level": "highest"}}'),
        "corrupt": '{"values": {"output.tail_cap": 10',
        "list": "[1, 2]",
        "values-list": '{"values": [1]}',
        "empty": "",
    }
    for name, text in bad.items():
        d = tmp_path / name
        d.mkdir()
        (d / "knobs.json").write_text(text, encoding="utf-8")
        assert G.cap_settings(d) is None, name
    d = tmp_path / "a-folder"
    (d / "knobs.json").mkdir(parents=True)          # not a file at all
    assert G.cap_settings(d) is None and K.read_record(d) == {}


# ----------------------------------------- red at the run's own n

# the last three observed weeks: A's last week above its mean, B's below
OBS_A = (10.0, 20.0, 60.0)        # mean 30, last 60, larger 60
OBS_B = (60.0, 30.0, 15.0)        # mean 35, last 15, larger 35


@pytest.mark.parametrize("obs,q,level,base,red", [
    (OBS_A, 330.0, "mean", 30.0, True),       # 11x
    (OBS_A, 330.0, "last", 60.0, False),      # 5.5x
    (OBS_A, 330.0, "larger", 60.0, False),
    (OBS_A, 660.0, "last", 60.0, True),       # 11x
    (OBS_A, 660.0, "larger", 60.0, True),
    (OBS_B, 165.0, "mean", 35.0, False),      # 4.7x
    (OBS_B, 165.0, "last", 15.0, True),       # 11x
    (OBS_B, 165.0, "larger", 35.0, False),
    (OBS_B, 385.0, "larger", 35.0, True),     # 11x
    (OBS_B, 385.0, "mean", 35.0, True),
])
def test_red_at_the_runs_own_n_on_each_level(tmp_path, obs, q, level, base,
                                             red):
    """Each figure is the h3 97.5% over the level the run's cap multiplies,
    red above the cap's 10: 11x is red, as it never was against 15."""
    cap = _cap(tmp_path, 10.0, level)
    p = _panel(obs, analogue=q)
    x, over, filed = G.tail_ratios(p, cap)["analogue"]
    assert abs(x - q / base) < 1e-9 and over is red and filed is None
    tail = G._tail(p, COLORS, cap)
    cls = "g-tail-over" if red else "g-tail-own"
    assert (f'<span class="{cls}" aria-hidden="true">'
            f'{G._tail_times(x, red, 10.0)}</span>') in tail
    assert ("above 10×" in tail) is red and "15×" not in tail
    # the same panel with no cap: the mean, against 15, as before
    x0, over0, _ = G.tail_ratios(p)["analogue"]
    assert abs(x0 - q / (sum(obs) / 3)) < 1e-9 and over0 is (x0 > 15)


def test_larger_groundhog_reads_each_member_against_its_own_level(tmp_path):
    """The per-member choice: the Oracle SIHRS's figure over the mean, the
    Groundhog's over the larger level, each red above the run's n, each
    figure's words naming its own level."""
    cap = _cap(tmp_path, 10.0, "larger_groundhog")
    p = _panel(OBS_A, pf=330.0, analogue=330.0)
    rs = G.tail_ratios(p, cap)
    assert abs(rs["pf"][0] - 11.0) < 1e-9 and rs["pf"][1]
    assert abs(rs["analogue"][0] - 5.5) < 1e-9 and not rs["analogue"][1]
    tail = G._tail(p, COLORS, cap)
    assert '<span class="g-tail-over" aria-hidden="true">11×</span>' in tail
    assert '<span class="g-tail-own" aria-hidden="true">5.5×</span>' in tail
    assert G.tail_words("pf", *rs["pf"], cap) == (
        f"97.5% at h3 = 11× the last three weeks' average ({PF}), "
        "above 10×")
    assert G.tail_words("analogue", *rs["analogue"], cap) == (
        "97.5% at h3 = 5.5× the larger of the last week and the "
        f"three-week average ({GH})")
    # the last week's words
    last = _cap(tmp_path, 10.0, "last")
    r = G.tail_ratios(_panel(OBS_B, analogue=165.0), last)["analogue"]
    assert G.tail_words("analogue", *r, last) == (
        f"97.5% at h3 = 11× the last week's count ({GH}), above 10×")
    # spoken: times the cap's level, above the cap
    label = G.panel_label(p, cap)
    assert (f"{PF} 4-week-ahead 97.5% quantile 11.0 times the cap's level, "
            "above 10") in label
    assert (f"{GH} 4-week-ahead 97.5% quantile 5.5 times the cap's "
            "level") in label
    assert "recent level" not in label and "above 15" not in label
    # without a cap: the recent level, above 15
    p15 = _panel(OBS_A, pf=480.0)                   # 16x the mean
    assert ("16.0 times the recent level, above 15"
            in G.panel_label(p15))


def test_a_figure_on_the_cap_is_not_red(tmp_path):
    """The two-decimal rule holds at the run's n: on the line, float noise
    included, or still reading 10.00, a figure is muted with no "above";
    10.01 is above and reads so. A fractional cap is its own line."""
    cap = _cap(tmp_path, 10.0)
    p = _panel((10.0, 10.0, 10.0), analogue=100.0)
    x, over, _ = G.tail_ratios(p, cap)["analogue"]
    assert x == 10.0 and not over
    tail = G._tail(p, COLORS, cap)
    assert '<span class="g-tail-own" aria-hidden="true">10.0×</span>' in tail
    assert "g-tail-over" not in tail and "above" not in tail
    assert "above" not in G.panel_label(p, cap)
    # level 50: 500.15 is 10.003x (reads 10.0), 500.3 is 10.006x (10.01)
    x, over, _ = G.tail_ratios(_panel((50.0,) * 3, analogue=500.15),
                               cap)["analogue"]
    assert x > 10.0 and not over and G._tail_times(x, over, 10.0) == "10.0×"
    x, over, _ = G.tail_ratios(_panel((50.0,) * 3, analogue=500.3),
                               cap)["analogue"]
    assert over and G._tail_times(x, over, 10.0) == "10.01×"
    # a cap of 15: 245 over 16, 16, 17 is 15.000000000000002, on the line
    cap15 = _cap(tmp_path, 15.0)
    p = _panel((16.0, 16.0, 17.0), analogue=245.0)
    x, over, _ = G.tail_ratios(p, cap15)["analogue"]
    assert x != 15.0 and not over
    # a fractional cap: 12.5 is its line, in the figures and the words
    cap = _cap(tmp_path, 12.5)
    on = G.tail_ratios(_panel((10.0,) * 3, analogue=125.0), cap)["analogue"]
    assert not on[1]
    up = G.tail_ratios(_panel((10.0,) * 3, analogue=126.0), cap)["analogue"]
    assert up[1] and G._tail_times(up[0], True, 12.5) == "13×"
    assert G.tail_words("analogue", *up, cap).endswith(", above 12.5×")
    assert ", above 12.5" in G.panel_label(
        _panel((10.0,) * 3, analogue=126.0), cap)
    assert "red</span> above 12.5×, the run's cap." in G.tail_key(
        "Jan 31", cap=cap)


# ------------------------------------------------------- the legend line

def test_the_legend_says_which_line_in_three_forms(tmp_path):
    """No cap: the last three weeks' average, red above 15x (unchanged).
    A cap with one level: before the cap, that level in words, red above
    the run's cap, then the arrow sentence where the cap changed a file.
    Per-member levels: each drawn member's level, by name."""
    head = ("h3 97.5% is the top of each model's 95% range for the last "
            "forecast week (h3, ending Dec 19)")
    arrow = " → marks the same figure in the submitted file, after the cap."
    assert _words(G.tail_key("Dec 19")) == (
        f"{head}, as a multiple of the average of the last three weeks of "
        "data; red above 15×.")
    larger = _cap(tmp_path, 10.0, "larger")
    assert _words(G.tail_key("Dec 19", True, larger)) == (
        f"{head}, before the cap, as a multiple of the larger of the last "
        "week and the average of the last three weeks, the level the run's "
        f"cap multiplies; red above 10×, the run's cap.{arrow}")
    assert _words(G.tail_key("Dec 19", False, larger)).endswith(
        "red above 10×, the run's cap.")
    for level, words in (("mean", "the average of the last three weeks of "
                                  "data"),
                         ("last", "the last week of data")):
        assert (f"as a multiple of {words}, the level the run's cap "
                "multiplies; red above 10×") in _words(
            G.tail_key("Dec 19", True, _cap(tmp_path, 10.0, level)))
    per = _cap(tmp_path, 10.0, "larger_groundhog")
    assert _words(G.tail_key("Dec 19", True, per)) == (
        f"{head}, before the cap, as a multiple of the level the run's cap "
        f"multiplies ({PF}: the average of the last three weeks of data; "
        f"{GH}: the larger of the last week and the average of the last "
        f"three weeks); red above 10×, the run's cap.{arrow}")
    # one member drawn: its level alone
    assert ("as a multiple of the larger of the last week and the average "
            "of the last three weeks, the level the run's cap multiplies"
            in _words(G.tail_key("Dec 19", True, per, ("analogue",))))
    # one line, red in the figures' red
    for cap in (None, larger, per):
        k = G.tail_key("Dec 19", True, cap)
        assert k.count("<p ") == 1 and "\n" not in k
        assert '<span class="g-tail-over">red</span> above ' in k


# --------------------------------------------- a capped run, rendered

def _report(folder: Path, cap_values=None, raw=None, bundle_cap=...) -> str:
    """The shared bundle rendered into `folder` with Ohio's, Alabama's and
    the United States' Oracle SIHRS files lowered by a cap and, beside the
    report, a
    knobs.json (`cap_values` through knobs.write_record, or `raw` text).
    Ohio's last three weeks are 10, 20, 60 (mean 30, larger 60) and its
    own h3 97.5% 900; Alabama's 21, 22, 23 (mean 22, larger 23) and 276;
    the United States' 21, 22, 23 and 276."""
    b = _bundle()
    if bundle_cap is not ...:
        b["tail_cap"] = bundle_cap
    b["details"]["US"] = dict(b["details"]["OH"], name="United States")
    panels = {p["key"]: p for p in b["grid"]["panels"]}
    panels["OH"]["observed"][-3:] = [[d, v] for (d, _), v in zip(
        panels["OH"]["observed"][-3:], (10.0, 20.0, 60.0))]
    for key, top in (("OH", 900.0), ("AL", 276.0), ("US", 276.0)):
        panels[key]["models"]["pf"]["q"][3][4] = top
    folder.mkdir(parents=True, exist_ok=True)
    _filed(folder, panels["OH"], top=600.0)
    _filed(folder, panels["AL"], fips="01", top=230.0)
    _filed(folder, panels["US"], fips="US", top=230.0)
    if cap_values is not None:
        _record(folder, **cap_values)
    if raw is not None:
        (folder / "knobs.json").write_text(raw, encoding="utf-8")
    return report_v2.render_bundle(b, folder / "r.html").read_text(
        encoding="utf-8")


def _cut(text, start, end):
    s = text[text.index(start):]
    return s[:s.index(end)]


def _fig(text, key):
    return _cut(text, f'<figure class="gpanel" id="g-{key}"', "</figure>")


def _capline(where, uid):
    m = re.search(rf'<p class="g-capline" id="gcap-{uid}" '
                  r'data-cap-line="[^"]+" hidden>([^<]+)</p>', where)
    return html.unescape(m.group(1)) if m else None


def test_a_capped_report_reads_red_and_arrows_at_its_own_cap(tmp_path):
    """A run capped at 10 on the larger level: Ohio's 900 is 15x its
    larger level (60) and its file's 600 is 10x; Alabama's 276 is 12x its
    larger level (23), red, which against 15 it never was. Every arrow
    reads at most the cap; the panel, the national feature, the detail
    sections and the legend line all read it."""
    page = _report(tmp_path, {"output.tail_cap": 10.0,
                              "output.tail_level": "larger",
                              "output.tail_mode": "shrink"})
    oh, al = _fig(page, "OH"), _fig(page, "AL")
    assert '<span class="g-tail-over" aria-hidden="true">15×</span>' in oh
    assert '<span class="g-tail-f" aria-hidden="true">→10×</span>' in oh
    assert '<span class="g-tail-over" aria-hidden="true">12×</span>' in al
    assert '<span class="g-tail-f" aria-hidden="true">→10×</span>' in al
    want = ("Shown before the cap. h3 97.5%, before → submitted: "
            f"{PF} 900 → 600 (15× → 10×).")
    detail = _cut(page, '<section class="state" id="st-OH"', "</section>")
    assert _capline(oh, "OH") == want and _capline(detail, "st-OH") == want
    label = html.unescape(re.search(r'<svg class="g-svg"[^>]*aria-label="'
                                    r'([^"]*)"', oh).group(1))
    assert (f"{PF} 4-week-ahead 97.5% quantile 15.0 times the cap's level, "
            "above 10, 10.0 as submitted") in label
    # the United States: its panel, the feature under the map, its detail
    feat = _cut(page, 'id="us-feature"', "</aside>")
    nat = _cut(page, '<section class="state" id="st-US"', "</section>")
    for where in (_fig(page, "US"), feat):
        assert ('<span class="g-tail-over" aria-hidden="true">12×</span>'
                in where)
        assert '<span class="g-tail-f" aria-hidden="true">→10×</span>' in where
    us_want = ("Shown before the cap. h3 97.5%, before → submitted: "
               f"{PF} 276 → 230 (12× → 10×).")
    assert _capline(feat, "US-feature") == us_want
    assert _capline(nat, "st-US") == us_want
    # no arrow reads above the run's cap
    arrows = [float(v) for v in re.findall(
        r'<span class="g-tail-f" aria-hidden="true">→([0-9.]+)×</span>', page)]
    assert arrows and max(arrows) <= 10.0
    # the legend line: the larger level, red above the run's cap, the arrow
    key = _words(_cut(page, '<p class="g-tailkey">', "</p>"))
    assert key == (
        "h3 97.5% is the top of each model's 95% range for the last forecast "
        "week (h3, ending Jan 31), before the cap, as a multiple of the "
        "larger of the last week and the average of the last three weeks, "
        "the level the run's cap multiplies; red above 10×, the run's cap. "
        "→ marks the same figure in the submitted file, after the cap.")
    assert page.count('class="g-tailkey"') == 1


def test_an_uncapped_run_reads_as_before(tmp_path):
    """The same files with no cap on record (a shipped run's missing
    knobs.json, a modified run without a cap, a cap of 0, a corrupt
    file): the mean of the last three weeks, red above 15, Alabama's 12.5x
    muted and Ohio's arrow at its file's 20x; the All locations section is
    the same in all four."""
    pages = {"none": _report(tmp_path / "none"),
             "narrow": _report(tmp_path / "narrow", {"oracle.narrow": 0.7}),
             "zero": _report(tmp_path / "zero",
                             raw='{"values": {"output.tail_cap": 0}}'),
             "corrupt": _report(tmp_path / "corrupt", raw="{")}
    grids = {k: _cut(v, 'id="all-locations"', "</section>")
             for k, v in pages.items()}
    assert len(set(grids.values())) == 1
    page = pages["none"]
    oh, al = _fig(page, "OH"), _fig(page, "AL")
    assert '<span class="g-tail-own" aria-hidden="true">13×</span>' in al
    assert '<span class="g-tail-over" aria-hidden="true">30×</span>' in oh
    assert '<span class="g-tail-f" aria-hidden="true">→20×</span>' in oh
    assert _capline(oh, "OH") == (
        "Shown before the cap. h3 97.5%, before → submitted: "
        f"{PF} 900 → 600 (30× → 20×).")
    assert "times the recent level, above 15" in html.unescape(oh)
    key = _words(_cut(page, '<p class="g-tailkey">', "</p>"))
    assert key == (
        "h3 97.5% is the top of each model's 95% range for the last forecast "
        "week (h3, ending Jan 31), as a multiple of the average of the last "
        "three weeks of data, before the cap; red above 15×. → marks the "
        "same figure in the submitted file, after the cap.")


# ------------------------------------------- the cap as the run recorded it

def _raw_record(folder: Path, values: dict, effective: dict) -> Path:
    """knobs.json with `values` and an "effective" table of `effective`
    ({key: value}), as a run whose knobs were fewer than today's wrote it."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"key": k, "value": v, "default": v} for k, v in effective.items()]
    (folder / "knobs.json").write_text(json.dumps(
        {"values": values, "effective": rows}), encoding="utf-8")
    return folder


def test_a_cap_reads_as_the_run_recorded_it_never_by_todays_defaults(
        tmp_path, monkeypatch):
    """A knob the run did not record is never filled from today's default:
    the runs of 2026-10-24 to 11-04 recorded a cap of 10 and shrink before
    the level knob existed, and capped on the mean; a run that recorded no
    cap had none. Changing today's defaults changes neither."""
    monkeypatch.setattr(tailcap, "LEVEL_PRODUCTION", "larger")
    monkeypatch.setattr(tailcap, "CAP_PRODUCTION", 10.0)
    monkeypatch.setattr(tailcap, "MODE_PRODUCTION", "shrink")
    old = _raw_record(tmp_path / "old", {"output.tail_cap": 10.0,
                                         "output.tail_mode": "shrink"},
                      {"output.tail_cap": 10.0, "output.tail_mode": "shrink"})
    cap = G.cap_settings(old)
    assert cap["n"] == 10.0 and cap["level"] == "mean"
    assert cap["levels"] == tailcap.member_levels("mean")
    older = _raw_record(tmp_path / "older", {"output.tail_cap": 15.0}, {})
    assert G.cap_settings(older)["mode"] == "clip"
    # no cap recorded: none, whatever today's registered cap
    none = _raw_record(tmp_path / "none", {"pf.particles": 5000},
                       {"pf.particles": 5000})
    assert G.cap_settings(none) is None
    # a value the run used at its default sits in the effective table only
    deflt = _raw_record(tmp_path / "default", {"output.tail_cap": 10.0},
                        {"output.tail_cap": 10.0,
                         "output.tail_level": "last"})
    assert G.cap_settings(deflt)["level"] == "last"
    assert K.read_record(deflt)["output.tail_level"] == "last"


def test_a_bundle_that_records_its_cap_is_read_before_the_knobs(tmp_path):
    """A report bundle written since the cap was recorded in it says the
    cap itself: its own n, level and form, read before the knobs.json
    beside it; null there is no cap, whatever the file says."""
    page = _report(tmp_path / "rec", {"output.tail_cap": 15.0},
                   bundle_cap={"n": 10.0, "level": "larger",
                               "mode": "shrink"})
    assert "red</span> above 10×, the run's cap" in page
    page = _report(tmp_path / "null", {"output.tail_cap": 10.0},
                   bundle_cap=None)
    assert "red</span> above 15×." in page
    assert "the run's cap" not in page


def test_the_run_writes_its_cap_into_the_report_bundle(tmp_path, monkeypatch):
    """The pipeline records the cap it applied (outcome["tail_cap"]: n,
    level, mode) in the report bundle, so the report's red line stays the
    run's own whatever later defaults or files say."""
    from app.tests.test_outlook_toggle import _synth_run_all_models
    from app.ui import pipeline as ui_pipeline
    real = ui_pipeline._write_weekly_report

    def capped(*a, **k):
        outcome = a[8]
        outcome["tail_cap"] = {"n": 10.0, "mode": "shrink",
                               "level": "larger",
                               "levels": tailcap.member_levels("larger"),
                               "recent_weeks": 3, "cells": {}}
        return real(*a, **k)
    monkeypatch.setattr(ui_pipeline, "_write_weekly_report", capped)
    wr = tmp_path / "wr"
    _synth_run_all_models(wr)
    bundle = json.loads((wr / report_v2.BUNDLE_NAME).read_text(
        encoding="utf-8"))
    assert bundle["tail_cap"] == {"n": 10.0, "level": "larger",
                                  "mode": "shrink"}
    assert "red</span> above 10×, the run's cap" in (
        wr / "report.html").read_text(encoding="utf-8")
    # a run with no cap records null
    monkeypatch.setattr(ui_pipeline, "_write_weekly_report", real)
    wr2 = tmp_path / "wr2"
    _synth_run_all_models(wr2)
    assert json.loads((wr2 / report_v2.BUNDLE_NAME).read_text(
        encoding="utf-8"))["tail_cap"] is None
