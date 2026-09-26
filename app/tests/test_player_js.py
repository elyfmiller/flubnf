"""The shared season player (app/ui/static/player.js): pure view-state,
availability and stats-table logic runs under JavaScriptCore, or node where
jsc is absent (skips with neither); source checks pin Safari safety, no
network calls, availability rendering and the view-state clear sites."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PLAYER = Path(__file__).resolve().parents[1] / "ui" / "static" / "player.js"
SRC = PLAYER.read_text(encoding="utf-8")
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_jsc = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")


def _js(tmp_path, expr):
    """Evaluate one expression against the player's exported internals."""
    drv = tmp_path / "driver.js"
    drv.write_text(
        "var I = FluBNFPlayer._internals;\n"
        "print(JSON.stringify((function(){ return " + expr + "; })()));\n")
    if JSC.is_file():
        cmd = [str(JSC), str(PLAYER), str(drv)]
    else:
        # node: one script, with jsc's print
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + SRC + "\n" + drv.read_text(), encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------- view-state logic (fix 1)

@needs_jsc
def test_zoom_event_becomes_active_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: null, y: null},"
              " {'xaxis.range[0]': '2098-10-01',"
              "  'xaxis.range[1]': '2098-12-01',"
              "  'yaxis.range[0]': 0, 'yaxis.range[1]': 500})")
    assert got == {"x": ["2098-10-01", "2098-12-01"], "y": [0, 500]}


@needs_jsc
def test_single_axis_pan_merges_with_stored_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: null, y: [0, 5]},"
              " {'xaxis.range[0]': 1, 'xaxis.range[1]': 2})")
    assert got == {"x": [1, 2], "y": [0, 5]}


@needs_jsc
def test_autorange_reset_clears_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: [1, 2], y: [0, 5]},"
              " {'xaxis.autorange': true})")
    assert got == {"x": None, "y": None}


@needs_jsc
def test_unrelated_relayout_leaves_view_untouched(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: [1, 2], y: null},"
              " {dragmode: 'pan'})")
    assert got == {"x": [1, 2], "y": None}


@needs_jsc
def test_array_form_range_accepted(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate(null, {'xaxis.range': [3, 4]})")
    assert got == {"x": [3, 4], "y": None}


# --------------------------------------- per-model availability (fix 2)

@needs_jsc
def test_official_availability_is_per_model(tmp_path):
    # the real case: the baseline directory healed before the ensemble
    # directory joined the sparse set, so only one official is present
    got = _js(tmp_path,
              "I.officialAvailability("
              "{official: {'FluSight-baseline': {US: {}}}}, I.OFFICIALS)")
    assert got == {"FluSight-baseline": True, "FluSight-ensemble": False}


@needs_jsc
def test_official_availability_empty_payload(tmp_path):
    got = _js(tmp_path, "I.officialAvailability(null, I.OFFICIALS)")
    assert got == {"FluSight-baseline": False, "FluSight-ensemble": False}


# ------------------------------------------ two-tier availability (fix 2)

@needs_jsc
def test_availability_tier_three_states(tmp_path):
    got = _js(tmp_path, "[I.availabilityTier(true, true),"
                        " I.availabilityTier(false, true),"
                        " I.availabilityTier(false, false)]")
    assert got == [
        # present this week: enabled, no note
        {"disabled": False, "note": ""},
        # in-season gap (outside the competition window): the toggle stays
        # live; the transient note explains the empty frame
        {"disabled": False, "note": " (no official submission this week)"},
        # absent all season: the existing disabled + Update-data state
        {"disabled": True, "note": " (fetch via Update data on the Data tab)"},
    ]


@needs_jsc
def test_availability_tier_week_presence_wins(tmp_path):
    # a week-present model is enabled regardless of the season flag (the
    # degenerate true/false combination cannot arise, but must not disable)
    got = _js(tmp_path, "I.availabilityTier(true, false)")
    assert got == {"disabled": False, "note": ""}


# ------------------------------ week-cell reading: pending vs no submission

@needs_jsc
def test_week_cell_score_always_wins(tmp_path):
    # a real number is rendered as a score no matter what the availability
    # flags say (officials included)
    got = _js(tmp_path, "[I.weekCellState(0.9, false, true, false, false),"
                        " I.weekCellState(1.2, true, true, false, true)]")
    assert got == ["score", "score"]


@needs_jsc
def test_week_cell_cataloged_official_without_a_file_reads_no_submission(
        tmp_path):
    # season-cataloged, no file for THIS week: it did not compete, which is
    # not the same as an uncomputed score
    got = _js(tmp_path, "I.weekCellState(null, true, true, false, true)")
    assert got == "nosub"


@needs_jsc
def test_week_cell_pending_cases(tmp_path):
    # every remaining blank is genuinely uncomputed: our member unscored; an
    # official present but unscored; an official absent all season; or a
    # payload that never arrived (so no no-submission claim)
    got = _js(tmp_path, "[I.weekCellState(null, false, true, false, false),"
                        " I.weekCellState(null, true, true, true, true),"
                        " I.weekCellState(null, true, true, false, false),"
                        " I.weekCellState(null, true, false, false, true)]")
    assert got == ["pending", "pending", "pending", "pending"]


# ------------------------------------ the stats table: relWIS and coverage

@needs_jsc
def test_coverage_reads_against_its_interval_level(tmp_path):
    # within 5 points of the level is ok, 2.5 at 95% (half the room above
    # it, so an interval that never misses reads too wide); further under
    # too narrow, further over too wide; judged on the printed whole
    # percentage
    got = _js(tmp_path, "[I.covState(0.45, 50), I.covState(0.444, 50),"
                        " I.covState(0.556, 50), I.covState(0.93, 95),"
                        " I.covState(0.92, 95), I.covState(0.97, 95),"
                        " I.covState(0.98, 95), I.covState(1, 95),"
                        " I.covState(null, 80), I.covPct(0.4449),"
                        " I.covTol(80), I.covTol(95)]")
    assert got == ["ok", "low", "wide", "ok", "low", "ok", "wide", "wide",
                   "", 44, 5, 2.5]


@needs_jsc
def test_stat_view_swaps_the_relwis_scale_only(tmp_path):
    st = ("{week_rel: 0.9, cum_rel: 0.8, week_log_rel: 1.1,"
          " cum_log_rel: null, week_cov: {'50': 0.5}, cum_cov: null,"
          " week_n: 12, cum_n: 40}")
    got = _js(tmp_path, f"[I.statView({st}, 'natural'),"
                        f" I.statView({st}, 'log'), I.statView(null, 'log')]")
    nat, log, empty = got
    assert nat["week"] == {"rel": 0.9, "shown": 0.9, "cov": {"50": 0.5},
                           "n": 12}
    assert nat["cum"]["shown"] == 0.8 and nat["cum"]["cov"] is None
    # the log scale shows the log figures; whether a score exists at all is
    # still the natural one's call, and coverage does not move
    assert log["week"]["shown"] == 1.1 and log["week"]["rel"] == 0.9
    assert log["cum"]["shown"] is None and log["cum"]["rel"] == 0.8
    assert log["week"]["cov"] == {"50": 0.5}
    # (JSON drops the undefined figures of an absent entry)
    assert empty["week"].get("rel") is None and empty["cum"]["cov"] is None


@needs_jsc
def test_period_cells_print_every_figure_they_color(tmp_path):
    got = _js(tmp_path,
              "[I.periodCells({rel: 0.9, shown: 0.8734, n: 4812,"
              " cov: {'50': 0.48, '80': 0.7, '95': 0.99}}, 'score', 'natural'),"
              " I.periodCells({rel: 0.9, shown: null, n: 3, cov: null},"
              " 'score', 'log'),"
              " I.periodCells({}, 'nosub', 'natural'),"
              " I.periodCells({}, 'pending', 'log')]")
    full, bare, nosub, pending = got
    assert '<td class="num g1 ok" title="relWIS over 4,812 scored cells">' \
        '0.873</td>' in full
    assert ">48%</td>" in full and 'class="num cov-ok"' in full
    assert ">70%</td>" in full and 'class="num cov-low"' in full
    assert ">99%</td>" in full
    # a figure the scores cannot give is a dash, never a colored blank
    assert bare.count(">–</td>") == 4 and "cov-" not in bare
    # no score: one cell across the group, saying which blank it is
    assert nosub == ('<td colspan="4" class="num hint gap g1">'
                     'no submission</td>')
    assert pending == ('<td colspan="4" class="num hint gap g1">'
                       'pending</td>')


@needs_jsc
def test_stats_head_groups_the_two_periods(tmp_path):
    nat, log = _js(tmp_path, "[I.statsHead('natural'), I.statsHead('log')]")
    for head in (nat, log):
        assert head.count("<tr>") == 2
        assert '<th colspan="4" scope="colgroup" class="grp g1">This week' \
            in head
        assert "Season so far" in head
        assert head.count(">95%</th>") == 2
    assert nat.count(">relWIS</th>") == 2 and "log relWIS" not in nat
    assert log.count(">log relWIS</th>") == 2


@needs_jsc
def test_a_narrow_card_stacks_the_two_periods(tmp_path):
    """A card too narrow for the periods side by side (a phone) shows them
    one above the other: one head row over the four figures, a heading row
    per period, each model's row under each; a model's debug line follows
    its season row."""
    row = ("{name: '<td class=\"mname\">A</td>', week: '<td>w</td>',"
           " cum: '<td>c</td>', debug: DBG}")
    got = _js(tmp_path,
              "[I.statsHead('natural', true), I.statsCols(true),"
              " I.statsCols(false),"
              f" I.statsBody([{row.replace('DBG', repr('x<y'))}], true),"
              f" I.statsBody([{row.replace('DBG', repr(''))}], false),"
              " I.statsBody([], true)]")
    head, n_stacked, n_wide, stacked, wide, empty = got
    assert head.count("<tr>") == 1 and "rowspan" not in head
    assert head.count(">relWIS</th>") == 1 and head.count(">95%</th>") == 1
    assert (n_stacked, n_wide) == (5, 9)
    assert stacked.index("This week") < stacked.index("Season so far")
    assert stacked.count('<tr><td class="mname">A</td><td>w</td></tr>') == 1
    assert stacked.count('<tr><td class="mname">A</td><td>c</td></tr>') == 1
    assert stacked.index("x&lt;y") > stacked.index("<td>c</td>")
    assert '<th colspan="5" scope="colgroup" class="grp">' in stacked
    assert wide == '<tr><td class="mname">A</td><td>w</td><td>c</td></tr>'
    assert empty == ('<tr><td colspan="5" class="hint">no models enabled'
                     '</td></tr>')


def test_the_table_stacks_only_when_the_wide_one_overflows():
    # drawn wide, measured against its scroll box, redrawn stacked; a
    # resize redraws, so crossing the fit either way takes effect
    body = SRC.split("function drawStatsTable(){", 1)[1].split("\n  }\n", 1)[0]
    assert "draw(false);" in body
    assert ("if(box && box.clientWidth && box.scrollWidth > box.clientWidth"
            " + 1)\n      draw(true);") in body
    assert "window.addEventListener('resize'" in SRC
    assert "P.statRows = rows;\n    drawStatsTable();" in SRC


@needs_jsc
def test_the_coverage_key_is_one_line_for_the_player_and_the_verdicts(
        tmp_path):
    from app.core import report_season
    assert _js(tmp_path, "I.covLegend()") == report_season.COV_LEGEND


@needs_jsc
def test_scale_switch_marks_the_pressed_scale(tmp_path):
    got = _js(tmp_path, "I.scaleSwitch('log')")
    assert 'data-scale="log" class="gold" aria-pressed="true"' in got
    assert 'data-scale="natural" aria-pressed="false"' in got
    assert "The CDC FluSight dashboard reports both." in got


@needs_jsc
def test_us_pf_note_only_under_the_oracle_name(tmp_path):
    got = _js(tmp_path,
              "[I.usPfNote({pf_note: 'N'}), I.usPfNote({pf_note: ''}),"
              " I.usPfNote(null),"
              " (I.MODEL_NAMES.pf = 'Particle filter alone',"
              "  I.usPfNote({pf_note: 'N'}))]")
    assert got == ["N", "", "", ""]


@needs_jsc
def test_add_days_utc(tmp_path):
    assert _js(tmp_path, "I.addDays('2098-12-02', 28)") == "2098-12-30"


# --------------------------------------------- no-forecast frames (class fix)

@needs_jsc
def test_no_forecast_note_states_the_empty_us_frame(tmp_path):
    # a US frame outside the officials' window states why it is empty
    # instead of showing bare axes
    got = _js(tmp_path, "I.noForecastNote('US', 0, 0)")
    assert "no official US submission" in got
    assert "per state" in got


@needs_jsc
def test_no_forecast_note_states_a_bare_state_frame(tmp_path):
    got = _js(tmp_path, "I.noForecastNote('Ohio', 0, 0)")
    assert got == "no forecast for Ohio this week"


@needs_jsc
def test_no_forecast_note_distinguishes_toggled_off_from_absent(tmp_path):
    # data present with every model toggled off is the viewer's own state
    got = _js(tmp_path, "[I.noForecastNote('Ohio', 2, 0),"
                        " I.noForecastNote('US', 1, 0)]")
    assert got == ["no models enabled", "no models enabled"]


@needs_jsc
def test_no_forecast_note_silent_when_fans_draw(tmp_path):
    got = _js(tmp_path, "[I.noForecastNote('Ohio', 2, 2),"
                        " I.noForecastNote('US', 1, 1)]")
    assert got == ["", ""]


# ------------------------------------------------------- source guarantees

def test_safari_safe_and_host_agnostic():
    # Safari-safe: no lookbehind regexes, nothing async at the top level
    assert "(?<=" not in SRC and "(?<!" not in SRC
    assert not re.search(r"\basync\b|\bawait\b", SRC)
    # host-agnostic: no network of its own, so it embeds in the
    # self-contained report (which bans these substrings)
    assert "fetch(" not in SRC
    assert "/static/" not in SRC
    assert "</script" not in SRC.lower()
    assert "http://" not in SRC and "https://" not in SRC
    assert "@@" not in SRC       # would collide with the report's tokens


def test_marker_and_exports():
    assert "flubnf-player-v1" in SRC
    assert "root.FluBNFPlayer = FluBNFPlayer" in SRC


def test_availability_rendering_wired():
    # each toggle has an availability note refreshed per payload: absent this
    # week but present in the season stays enabled with a note; absent all
    # season is disabled with the Update-data state
    assert "data-avail" in SRC
    assert "(fetch via Update data on the Data tab)" in SRC
    assert "(no official submission this week)" in SRC
    assert "availabilityTier(av[m], !!seasonOffs[m])" in SRC
    assert "box.disabled = tier.disabled" in SRC
    assert "officialAvailability(pl, OFFS)" in SRC
    assert "updateAvailability(pl)" in SRC
    # the user's checked state is never touched by availability updates
    assert "box.checked" not in SRC
    # season availability: host-provided (seasonOfficials, or the static
    # host's catalog union) and grown from every payload seen
    assert "cfg.seasonOfficials || (cfg.catalog && cfg.catalog.officials)" \
        in SRC
    assert "seasonOffs[m] = 1" in SRC


def test_stats_table_distinguishes_no_submission_from_pending():
    # the week group shows both readings, as ONE cell across its four
    # columns; the season group keeps an official's running figures
    # through a week it skipped
    assert "'<td colspan=\"4\" class=\"num hint gap g1\">'" in SRC
    assert "(state === 'nosub' ? 'no submission'" in SRC
    assert ": state === 'noround' ? NO_ROUND_CELL : 'pending')" in SRC
    assert "periodCells(sv.week, wk, P.scale)" in SRC
    assert "periodCells(sv.cum, cum, P.scale)" in SRC
    assert "var cum = isNum(sv.cum.rel) ? 'score' : 'pending'" in SRC
    # the verdict is driven by this week's official dict and the season
    # catalog the host supplies, never by a separate payload field
    assert "officialAvailability(pl, OFFS)" in SRC
    assert "weekCellState(sv.week.rel, OFFS.indexOf(m) >= 0" in SRC
    assert "!!seasonOffs[m]" in SRC


def test_stats_table_reads_the_contract_and_persists_the_scale():
    # every stats key is read by name (the contract tests grep st.*), the
    # scale switch persists in a guarded localStorage, natural by default
    for key in ("st.week_rel", "st.cum_rel", "st.week_log_rel",
                "st.cum_log_rel", "st.week_cov", "st.cum_cov", "st.week_n",
                "st.cum_n"):
        assert key in SRC, key
    assert "var SCALE_KEY = 'flubnf-relwis-scale'" in SRC
    assert "localStorage.getItem(SCALE_KEY) === 'log' ? 'log' : 'natural'" \
        in SRC
    assert re.search(r"try\{\s*localStorage\.setItem\(SCALE_KEY, s\);"
                     r"\s*\}catch\(e\)\{\}", SRC)
    # the head is the player's own: two rows, the groups over their columns
    assert "rowspan=\"2\"" in SRC and "scope=\"colgroup\"" in SRC
    assert "'This week'" in SRC and "'Season so far'" in SRC
    # the one-line hint beside the switch
    assert "The CDC FluSight dashboard reports '" in SRC
    assert "'both.</span>'" in SRC


def test_coverage_rule_matches_the_python_verdicts():
    # one coverage reading for the player and the verdicts
    # (report_season.cov_state): the same tolerance and the same levels
    from app.core import report_season
    m = re.search(r"var COV_TOL = (\d+);", SRC)
    assert m and int(m.group(1)) == report_season.COV_TOLERANCE
    assert "var COV_BANDS = ['50', '80', '95'];" in SRC
    assert tuple(k for k, _ in report_season.COV_LEVELS) == ("50", "80", "95")
    # judged on the printed whole percentage, halves rounding up
    assert "Math.round(100 * v)" in SRC
    # the band narrows near 100 the same way (2.5 at 95%)
    assert "return Math.min(COV_TOL, (100 - nominal) / 2);" in SRC
    assert report_season.cov_tolerance(95) == 2.5
    assert report_season.cov_tolerance(80) == 5
    cs = report_season.cov_state
    assert [cs(0.45, 50), cs(0.444, 50), cs(0.55, 50), cs(0.556, 50),
            cs(0.92, 95), cs(0.925, 95), cs(0.974, 95), cs(0.975, 95),
            cs(1.0, 95), cs(None, 95)] == \
        ["ok", "low", "ok", "wide", "low", "ok", "ok", "wide", "wide", ""]
    assert report_season.cov_text(0.4449) == "44%"
    assert report_season.cov_text(float("nan")) == "–"


def test_us_pf_label_is_the_national_note():
    # a fitted US pf fan is the plain filter: the legend entry is
    # us_national.PF_US_SHORT without its article, and the frame's note
    # the host-sent pf_note, while pf wears the Oracle SIHRS name
    from app.core import us_national as usn
    m = re.search(r"var US_PF_LABEL = '([^']+)';", SRC)
    assert m
    assert m.group(1).lower() == usn.PF_US_SHORT.lower().removeprefix("the ")
    assert "us && us.pf_note && /Oracle/.test(nameOf('pf'))" in SRC
    assert "|| (pfDrawn ? pfNote : '')" in SRC


def test_no_forecast_note_is_wired_into_the_frame_draw():
    # drawFC computes availability across ALL models each frame, so an empty
    # frame never renders as silent bare axes
    assert ("el.msg.textContent = nodata ? noteOf(w)\n"
            "        : (noForecastNote(loc, avail, drawn, cfg.us)" in SRC)
    assert "noForecastNote: noForecastNote" in SRC


# ------------------------------------------------ no-data weeks (no round)

@needs_jsc
def test_no_data_placeholder_keeps_truth_and_carries_the_season_scores(
        tmp_path):
    """A week with no published data has no payload: the player builds one
    from the nearest stored week, truth and locations kept, nothing
    forecast, the week figures cleared and the season figures carried
    over (the same keys as THE STATS CONTRACT)."""
    src = ("{asof: '2098-11-07', locations: ['Ohio'],"
           " truth: {Ohio: [['2098-10-31', 5], ['2098-11-07', 6]]},"
           " models: {pf: {Ohio: {}}}, official: {'FluSight-baseline': {}},"
           " stats: {pf: {week_rel: 0.9, cum_rel: 0.8, week_log_rel: 0.7,"
           " cum_log_rel: 0.6, week_cov: {'50': 0.5}, cum_cov: {'50': 0.4},"
           " week_n: 3, cum_n: 9, debug: 'x'}}}")
    got = _js(tmp_path, "I.noDataPayload(" + src + ", '2098-11-14')")
    assert got["asof"] == "2098-11-14"
    assert got["locations"] == ["Ohio"]
    assert got["truth"] == {"Ohio": [["2098-10-31", 5], ["2098-11-07", 6]]}
    assert got["models"] == {} and got["official"] == {}
    assert got["stats"] == {"pf": {
        "week_rel": None, "cum_rel": 0.8, "week_log_rel": None,
        "cum_log_rel": 0.6, "week_cov": None, "cum_cov": {"50": 0.4},
        "week_n": 0, "cum_n": 9}}
    assert _js(tmp_path, "I.noDataPayload(null, '2098-11-14')") is None


@needs_jsc
def test_no_round_week_cells_say_so(tmp_path):
    # the This week group reads "no FluSight round" as one cell; the season
    # group keeps its running figures
    got = _js(tmp_path, "I.periodCells({rel: null, shown: null, cov: null,"
                        " n: 0}, 'noround', 'natural')")
    assert got == ('<td colspan="4" class="num hint gap g1">'
                   'no FluSight round</td>')
    assert _js(tmp_path, "I.NO_ROUND_CELL") == "no FluSight round"


def test_no_data_weeks_are_wired_into_the_player():
    # the host's caption marks the week; stats and the frame both read the
    # placeholder; the frame titles itself with the note and draws no fan
    assert "noDataNote" in SRC
    assert "function isNoData(w)" in SRC
    assert "function payloadFor(w)" in SRC
    assert "payloadFor(w).then(function(pl){" in SRC
    assert "var wk = nodata ? 'noround'" in SRC
    assert "? ' · ' + w + '<br>' + noteOf(w)" in SRC
    assert "noDataPayload: noDataPayload" in SRC
    # both hosts hand the caption over
    from app.core.report_season import _PAGE
    assert "noDataNote: NO_DATA_NOTE" in _PAGE
    season_t = (Path(__file__).resolve().parents[1] / "ui" / "templates"
                / "retro_season.html").read_text(encoding="utf-8")
    assert "noDataNote: NO_DATA_NOTE" in season_t
    # the console's map view greys the last map under the note
    assert "host.classList.toggle('nodata', noData(w))" in season_t


def test_view_state_clear_sites():
    # stored from plotly relayout events, cleared on double click,
    # location change, and the Lock axes toggle
    assert "plotly_relayout" in SRC and "plotly_doubleclick" in SRC
    assert SRC.count("P.user = {x: null, y: null}") >= 3
    # and the stored view overrides the lock (or auto) ranges on redraw
    assert "if(P.user.x){ xa.range = P.user.x.slice()" in SRC
    assert "if(P.user.y){ ya.range = P.user.y.slice()" in SRC
