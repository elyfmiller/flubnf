"""The two pages the owner opens after every replay and every run carry
the marks that explain something and no more (docs/UI-KIT.md).

  * The Retrospective season page, and the season report that renders it:
    one "i", beside the title, holds how to read the scores, the coverage
    colors, what the pooled and US figures are and the player's keys;
    badges, tags and labelled values say the rest, the run settings every
    value in plain sight.
  * A run's page: no mark at all; the medians' weeks are under their
    heading, a refused file says why beside its badge.

Marks are counted as test_fewer_marks counts them: the visible "?" and
"i" buttons, not inside a closed fold or a hidden subtree."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                                  # noqa: E402
from app.core import relwis, report_season                       # noqa: E402
from app.core import us_national as usn                          # noqa: E402
from app.tests.test_fewer_marks import marks                      # noqa: E402
from app.tests.test_output_run_pages import (                     # noqa: E402,F401
    GH, OR, _run, client, root)
from app.tests.test_report_parity import (                       # noqa: E402,F401
    _app_page, _mk_root, _report, _warm, built)
from app.tests.test_retro_player import CONTEXT, _figs           # noqa: E402
from app.ui.routes.retro import MAP_HORIZON                      # noqa: E402
from app.ui.server import templates                              # noqa: E402

W1 = "2098-11-07"

#: a finished replay's settings as retro_settings.settings_summary words
#: them, with every parenthetical a value can carry
SETTINGS = [
    ("season", "2098-99"),
    ("locations", "1 state plus US national: Ohio"),
    ("particles", "10,000"),
    ("engine", "Oracle SIHRS and the Groundhog"),
    ("PyBNF build", "2fdadee0 (main), not the production build"),
    ("model settings", "Oracle blend weight 0.25 (default 0.5), Seed "
                       "denominator expected total (early season)"),
    ("settings digest", "a1b2c3d4"),
    ("zero-anchor rule", "abstain (replayed before the rule existed)"),
    ("zero-anchor weeks", "3 location-weeks (2 level, 1 abstain)"),
    ("output floor", "not applied (stored before replays applied it)"),
    ("flagged weeks", "on; no week flagged"),
]


def _prog(**kw):
    p = {"status": "done", "active": False, "done": 30, "total": 30,
         "elapsed_s": 3725.0, "mean_s": 124.0, "weeks_measured": 30,
         "eta_s": None, "slowest_week": W1, "slowest_s": 300.0,
         "added": [], "added_n": 0, "sealed": False, "settings": SETTINGS}
    p.update(kw)
    return p


def _us(provenance=usn.FITTED, step=usn.FILTER):
    return usn.UsNational(provenance, scores={"pf": 0.9, "analogue": 0.58},
                          cells={"pf": 96, "analogue": 96}, n_states=52,
                          pf_step=step).as_dict()


def _page(**kw):
    """A scored, modified season with a fitted US row of the filter era,
    a sealed record's earlier cell rule and a finished replay's record."""
    us = _us()
    ctx = dict(CONTEXT, heads={"pf": 0.783, "analogue": 0.651},
               season_models=["pf", "analogue"], figs=_figs(), us=us,
               us_row=us, prog=_prog(), knobs_modified=True,
               map_legend=[("#888", "no data")], map_horizon=MAP_HORIZON,
               rule_note="Scored under the earlier cell rule: the pooled "
                         "tiles.")
    ctx.update(kw)
    ctx["states"] = list(ctx["figs"].states) if ctx["figs"] else []
    return templates.env.get_template("retro_season.html").render(**ctx)


def _page_i(html):
    """The page's "i": its panel's lines, up to the title's badges."""
    return html.split('id="tt-rs-page">', 1)[1].split("</div>", 1)[0] \
        .split('<span class="uk-badge', 1)[0]


def _words(markup):
    return len(re.sub(r"<[^>]+>", " ", markup).split())


# ------------------------------------------------------------ season page

def test_the_season_page_has_one_mark_its_i():
    html = _page()
    assert marks(html) == ["tt-rs-page"]
    # the modified badge says it alone; the settings row names the changes
    assert ('<span class="uk-badge uk-badge--warn" id="rs-knobs" '
            'data-state="warn">') in html
    assert 'id="tip-rs-knobs"' not in html
    # the earlier cell rule's badge, likewise; its note is in the "i". A
    # neutral dot, never the info badge's circled "i" that would read as a
    # second "i" beside the page's
    assert ('<span class="uk-badge uk-badge--neutral" id="rs-rule" '
            'data-state="neutral">') in html
    assert 'id="tip-rs-rule"' not in html
    pw = _page(conv=relwis.PAIRWISE, heads={"pf": 0.7}, figs=_pairwise(),
               us=None, us_row=None)
    badge = pw.split('<span class="uk-badge-t">pairwise relWIS</span>', 1)[0] \
        .rsplit('<span class="uk-badge', 1)[1]
    assert badge.startswith(' uk-badge--neutral"')


def _pairwise(available=True):
    figs = _figs()
    if not available:
        return relwis.Figures(convention=relwis.PAIRWISE, values={},
                              detail={}, reason="no hub field data cached")
    return relwis.Figures(convention=relwis.PAIRWISE, values={"pf": 0.7},
                          detail={"pf": {"n_cells": 100}},
                          states=tuple(figs.states), n_field=47)


@pytest.mark.parametrize("kw", [
    dict(prog=_prog(status="stopped", done=12)),
    dict(prog=_prog(status="interrupted", done=12)),
    dict(prog=_prog(added=["2098-12-05", "2098-12-12", "2098-12-19"],
                    added_n=3)),
    dict(prog=_prog(status="running", active=True, done=3)),
    dict(prog=_prog(status="paused", active=True, done=3)),
    dict(archive="20981201T090000", archive_when="2098-12-01 09:00"),
    dict(archive="20981201T090000",
         imported={"from": "lab-mac", "imported_at": "2098-12-02T10:00:00",
                   "exported_at": "2098-12-01T10:00:00", "source": "live"}),
    dict(heads={}, figs=None, us=None, us_row=None, unsettled=True),
    dict(heads={}, figs=None, us=None, us_row=None, score_error="boom"),
    dict(conv=relwis.PAIRWISE, heads={"pf": 0.7}, figs=_pairwise(),
         us=None, us_row=None),
    dict(conv=relwis.PAIRWISE, heads={}, figs=_pairwise(False), us=None,
         us_row=None),
    dict(us=_us(usn.AGGREGATED, None), us_row=_us(usn.AGGREGATED, None)),
], ids=["stopped", "interrupted", "weeks-added", "running", "paused",
        "archived", "imported", "unsettled", "score-error", "pairwise",
        "pairwise-unavailable", "us-aggregated"])
def test_every_state_of_the_season_page_keeps_the_one_i(kw):
    assert marks(_page(**kw)) == ["tt-rs-page"]


def test_preparing_has_no_mark():
    html = _page(preparing={"phase": "scoring", "elapsed_s": 1.0})
    assert marks(html) == []


def test_the_badges_and_lines_say_what_their_tips_did():
    stopped = _page(prog=_prog(status="stopped", done=12))
    assert '<span class="uk-badge-t">stopped before the last week</span>' in stopped
    gone = _page(prog=_prog(status="interrupted", done=12))
    assert '<span class="uk-badge-t">interrupted: the app closed</span>' in gone
    two = _page(prog=_prog(added=["2098-12-05", "2098-12-12"], added_n=2))
    assert ('<span class="uk-badge-t">2 weeks added: 2098-12-05, '
            '2098-12-12</span>') in two
    many = _page(prog=_prog(added=["2098-12-05", "2098-12-12", "2098-12-19"],
                            added_n=3))
    assert ('<span class="uk-badge-t">3 weeks added: 2098-12-05 to '
            '2098-12-19</span>') in many
    # a sealed record cannot take them: the badge says so
    sealed = _page(prog=_prog(added=["2098-12-05"], added_n=1, sealed=True))
    assert ('<span class="uk-badge-t">1 week added: 2098-12-05 (sealed, '
            'needs a fresh replay)</span>') in sealed
    # each says the way on, a link to the Retrospective tab whose card
    # resumes the replay or, for a sealed record, starts a fresh one
    for html in (stopped, gone, two, many):
        assert ('<a class="btn quiet" id="rs-onward" href="/retro">Resume on '
                'Retrospective</a>') in html
    assert ('<a class="btn quiet" id="rs-onward" href="/retro">Replay on '
            'Retrospective</a>') in sealed
    # a finished replay, an archived run and the report have nowhere to go
    assert 'id="rs-onward"' not in _page()
    assert 'id="rs-onward"' not in _page(
        archive="20981201T090000", archive_when="2098-12-01 09:00",
        prog=dict(_prog(), status="archived"))
    assert 'id="rs-onward"' not in _page(
        export=True, prog=_prog(status="stopped", done=12))
    # a live replay's readout says the time left or "paused" in plain
    # sight; what the estimate rests on is for a screen reader only
    live = _page(prog=_prog(status="running", active=True, done=3,
                            weeks_measured=3))
    assert ('<span class="rbasis uk-sr">estimate from 3 completed weeks'
            '</span>') in live
    # the banners say it in their line
    arch = _page(archive="20981201T090000", archive_when="2098-12-01 09:00")
    assert "Set aside when a fresh replay started; read only." in arch
    imp = _page(archive="20981201T090000",
                imported={"from": "lab-mac", "exported_at":
                          "2098-12-01T10:00:00", "source": "live"})
    assert "Exported there on 2098-12-01 from the live season; read only." in imp
    # a scoring failure points at the Data tab in place of a "?", its raw
    # message in a fold
    err = _page(heads={}, figs=None, us=None, us_row=None, score_error="boom")
    fail = err.split('id="rs-scorefail"', 1)[1].split("</span></div>", 1)[0]
    assert "<code>boom</code>" in fail and 'href="/data"' in fail
    assert '<span class="uk-fold-sum">Details</span>' in fail
    # the map's tag says which week it shows
    assert ('<span class="uk-tag">horizon 0, the week after the newest '
            'data</span>') in _page()


def test_the_settings_row_shows_every_setting_in_plain_sight():
    html = _page()
    row = html.split('<div class="rs-settings rt-settings">', 1)[1] \
        .split("</div>", 1)[0]
    # the model settings, the build and the zero-anchor count in full
    for fact in ("model settings Oracle blend weight 0.25 (default 0.5), Seed "
                 "denominator expected total (early season)",
                 "settings digest a1b2c3d4",
                 "PyBNF build 2fdadee0 (main), not the production build",
                 "zero-anchor weeks 3 location-weeks (2 level, 1 abstain)"):
        assert fact in row, fact
    # a season replayed before the zero-anchor rule says so, never as if
    # abstain had been chosen
    assert ("<li>zero-anchor abstain (replayed before the rule existed)"
            "</li>") in row
    # the parentheticals that only explain a value stay out
    assert "<li>floor not applied</li>" in row
    assert "stored before replays applied it" not in row
    assert "tipbtn" not in row


def test_the_i_holds_what_the_marks_held_and_reads_short():
    html = _page()
    i = _page_i(html)
    flat = " ".join(i.split())
    assert report_season.LIVE_SCORES_NOTE in flat
    assert f'<span class="pblegend">{report_season.COV_LEGEND}</span>' in i
    assert usn.POOLED_SCOPE_NOTE in flat
    assert usn.PF_US_NOTES[usn.FILTER] in flat
    assert "Scored under the earlier cell rule: the pooled tiles." in flat
    for key in ("&larr;", "<kbd>Home</kbd>", "<kbd>Space</kbd>",
                "<kbd>[</kbd>", "<kbd>M</kbd>", "<kbd>F</kbd>",
                "<kbd>L</kbd>"):
        assert key in i, key
    # the owner's usual page, a fresh season with nothing scored yet, and
    # a scored one with a fitted US row of the current era
    early = _page_i(_page(heads={}, figs=None, us=None, us_row=None,
                          unsettled=True, rule_note=""))
    assert _words(early) < 115
    stepped = _us(step=usn.STEPPED)
    scored = _page_i(_page(us=stepped, us_row=stepped, rule_note=""))
    assert _words(scored) < 170
    # the US row's provenance in one line: fitted as its own location, its
    # Oracle SIHRS figure with the step since addendum A3
    assert (f'<span class="uk-tt-line">{usn.NOTES[usn.FITTED]} '
            f'{usn.PF_US_NOTES[usn.STEPPED]}</span>') in scored


def test_the_tiles_carry_their_cells_and_the_us_era_in_plain_sight():
    html = _page()
    us = html.split('<h3 id="rs-g-us">US national</h3>', 1)[1] \
        .split("</section>", 1)[0]
    pf = us.split("<h2>Oracle SIHRS</h2>", 1)[1].split("</dl></div></div>", 1)[0]
    assert f'<p class="rt-tilenote">{usn.PF_US_SHORT}</p>' in pf
    assert "<dt>cells</dt><dd>96</dd>" in pf


# ------------------------------------------------- the real route and export

def test_the_season_page_and_its_report_keep_one_mark(built):
    app_html, report_html = built
    assert marks(app_html) == ["tt-rs-page"]
    assert marks(report_html) == ["tt-rs-page"]
    # the report's "i" is the page's: the reader of the file keeps the facts
    assert _page_i(app_html) == _page_i(report_html)


def test_a_modified_replay_names_its_settings_and_digest(tmp_path,
                                                         monkeypatch):
    from app.core import retro
    root = _mk_root(tmp_path, monkeypatch)
    meta = retro.read_meta(root)
    nd = {"groundhog.bandwidth": 3}
    meta["settings"]["knobs"] = nd
    retro.write_meta(root, meta)
    _warm(root)
    html = _app_page(tmp_path, monkeypatch)
    assert marks(html) == ["tt-rs-page"]
    assert 'id="rs-knobs"' in html and 'id="tip-rs-knobs"' not in html
    row = html.split('<div class="rs-settings rt-settings">', 1)[1] \
        .split("</div>", 1)[0]
    assert f"model settings {K.words(nd)}" in row
    assert f"settings digest {K.digest(nd)}" in row


# --------------------------------------------------------------- run page

#: marks a run page shows only in a passing state: a file failing the hub
#: checks lists its problems in an "i" (Output's row), and the Results
#: table's own chips (app/core/runs.results_html) explain an error
RUN_PASSING = ("tt-run-chk-", "tip-sub-", "tip-pf-broken")


def _run_marks(html):
    return [m for m in marks(html) if not m.startswith(RUN_PASSING)]


def test_a_run_page_has_no_mark(root):
    rid = _run(root, "2098-01-03", [OR, GH])
    html = client.get(f"/runs/{rid}").text
    assert 'id="run-supersession"' in html
    assert _run_marks(html) == []
    # the medians' weeks under their heading: h0 the reference date
    med = html.split('id="run-medians"', 1)[1]
    assert "weeks ending 2098-01-10 to 2098-01-31" in med
    assert 'id="tip-run-med"' not in html


def test_a_superseded_run_says_so_without_a_mark(root):
    failed = _run(root, "2098-01-03", [], status="failed",
                  outcome={"error": "boom"})
    _run(root, "2098-01-03", [OR, GH])
    html = client.get(f"/runs/{failed}").text
    assert "Superseded." in html and "Run failed." in html
    assert _run_marks(html) == []


def test_a_refused_file_says_why_beside_its_badge(root):
    rid = _run(root, "2098-01-03", [GH],
               outcome={"submission_errors": {OR: "a quantile out of order"}})
    html = client.get(f"/runs/{rid}").text
    assert _run_marks(html) == []
    assert ('<span class="uk-badge-t">no file written</span></span> '
            '<span class="hint">a quantile out of order</span>') in html


def test_the_median_weeks_follow_the_run_kind():
    from app.ui.routes.forecast import _median_weeks
    # a hub run: h0 ends on the reference date, h3 three weeks on
    assert _median_weeks("2098-01-03") == ("2098-01-10", "2098-01-31")
    # a dataset run: one to four weeks after its forecast date
    assert _median_weeks("2098-01-03", dataset=True) == ("2098-01-10",
                                                         "2098-01-31")
    assert _median_weeks("") == () and _median_weeks("not a date") == ()
