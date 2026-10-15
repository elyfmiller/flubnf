"""The pages carry few "?" and "i" marks: what a label, a badge, a unit or
a fold already says is not repeated behind a mark (docs/UI-KIT.md).

Each page's visible marks (the kit's "?" buttons and "i" toggletips, not
inside a closed fold or a hidden subtree) are read from the served HTML
and held to the few that explain something nothing else on the page
does; marks that show only in a passing state (a missing component, no
engine, a picked file) are allowed beside them. The facts the removed
marks held live on, in a badge's words, an "i" that remains, or a fold."""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402

client = TestClient(srv.app)
ENV = srv.templates.env

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}


class _Marks(HTMLParser):
    """The ids the visible marks point at (aria-describedby of a "?",
    aria-controls of an "i"), in page order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, "hidden" | "closed" | "")
        self.ids = []

    def _hidden(self):
        # inside a hidden subtree, or inside a closed <details> but not in
        # its own summary
        for i, (_tag, hides) in enumerate(self.stack):
            if hides == "hidden":
                return True
            if hides == "closed":
                rest = self.stack[i + 1:]
                if not (rest and rest[0][0] == "summary"):
                    return True
        return False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "button" and ("tipbtn" in cls or "uk-tt-btn" in cls):
            if not self._hidden() and "hidden" not in a:
                self.ids.append(a.get("aria-describedby")
                                or a.get("aria-controls") or "")
        if tag in _VOID:
            return
        hides = ("hidden" if "hidden" in a else
                 "closed" if tag == "details" and "open" not in a else "")
        self.stack.append((tag, hides))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def marks(html: str) -> list:
    """The visible marks of the page's main content (the header's Display
    menu is a closed fold)."""
    p = _Marks()
    p.feed(html.split("<main", 1)[1] if "<main" in html else html)
    return p.ids


#: page -> (the marks it keeps, prefixes of marks a passing state adds)
KEEP = {
    "/": ({"tt-hm-map", "tt-hm-perf", "tt-hm-how"},
          ("tip-hm-miss", "tip-home-pin", "tip-eb-", "tip-hm-approx")),
    "/data": ({"tip-archive", "tip-dsup-data-about"},
              ("tip-hub-empty", "tip-hub-detail", "tip-newest-gaps",
               "tip-dsup-data-kind", "tip-ds-")),
    "/output": ({"tt-out-files"},
                ("tip-out-live-", "tip-out-lchk-", "tip-out-notice",
                 "tip-out-own")),
    "/retro": ({"tip-rt-page", "tip-rt-import-h"},
               ("tip-rt-engine-off", "tip-rt-run-why", "tip-rt-st-")),
    "/storage": (set(), ("tip-st-int-", "tip-st-cap")),
    "/models": ({"tt-md-rec"}, ()),
    "/model/analogue": ({"tt-md-rec"}, ()),
    "/model/pf2s": ({"tt-md-rec"}, ("tip-rr-start-why",)),
    "/methods": ({"tt-mt-replay"}, ()),
    "/sandbox": ({"tip-sbnew-about-t"},
                 ("tip-sb-season", "tip-sb-fdate", "tip-sb-asof",
                  "tip-sb-note-", "tip-sb-miss-")),
}


def test_each_page_keeps_only_the_marks_that_explain_something():
    for path, (keep, passing) in KEEP.items():
        seen = marks(client.get(path).text)
        rest = {m for m in seen if not m.startswith(passing)}
        assert rest == keep, (path, sorted(rest))


def test_the_display_menu_has_no_visible_question_marks():
    """Its headings stand alone; the two switches keep their descriptions
    as visually hidden text, so aria-describedby still reads them."""
    html = client.get("/data").text
    menu = html.split('id="displaymenu"', 1)[1].split("</details>", 1)[0]
    shown = menu.split('<section class="dm-sec zoomrow" hidden>', 1)[0]
    assert "tipbtn" not in shown
    for ax in ("contrast", "vision"):
        assert f'aria-describedby="tip-dm-{ax}"' in shown
        assert f'<span class="uk-sr" id="tip-dm-{ax}">' in shown


# --------------------------------------------------- Home: what moved where

def _home(**kw):
    ctx = dict(active="Home", map_svg="<svg></svg>", outlook_date="2026-01-24",
               outlook_n=1, missing=[],
               versions={"pybnf": "x", "bngsim": "0.15.1", "bionetgen": "x",
                         "perl": "x", "fastapi": "x", "plotly": "x"})
    ctx.update(kw)
    return ENV.get_template("home.html").render(**ctx)


def test_home_how_it_works_reads_the_three_equations():
    """Home has no Variables fold: the three equations' readings are How
    it works' "i", and the chips beside them carry no "?"."""
    html = _home()
    how = html.split('id="tt-hm-how"', 1)[1].split("</span></span>", 1)[0]
    for reading in ("Seasonal forcing: the curve the filter bends each",
                    "The Oracle step: each forecast path grows at the",
                    "The Groundhog: the last value scaled by past"):
        assert reading in " ".join(how.split()), reading
    for chip in ("hm-eq-forcing", "hm-eq-oracle", "hm-eq-groundhog"):
        assert f'id="tip-{chip}"' not in html, chip


def test_home_record_is_the_cards_one_i():
    """The Oracle SIHRS column's record joins the card's "i"; the column
    header is plain text."""
    html = _home()
    assert 'id="tt-home-oracle"' not in html
    assert '<th class="num">Oracle SIHRS</th>' in html
    perf = " ".join(html.split('id="tt-hm-perf"', 1)[1]
                    .split("</span></span>", 1)[0].split())
    assert "frozen-specification replication" in perf
    assert "2024-25 and 2025-26 together:" in perf
    # the figures and their cells only; the cell rule and the convention's
    # comparison with the dashboard are Methods' Scoring details
    assert "ratio of sums" in perf and 'href="/methods#policies"' in perf
    assert "third decimal" not in perf and "CDC FluSight dashboard" not in perf
    assert len(re.sub(r"<[^>]+>", " ", perf).split()) < 115


def test_home_says_the_bngsim_pin_only_when_the_build_differs():
    assert 'id="tip-home-pin"' not in _home()
    other = _home(versions={"pybnf": "x", "bngsim": "0.13.0", "bionetgen": "x",
                            "perl": "x", "fastapi": "x", "plotly": "x"})
    assert 'id="tip-home-pin"' in other
    assert "bngsim 0.15.1 (pinned by every engine installer)" in other


def test_home_says_nothing_of_the_pin_while_the_version_resolves():
    """A first launch paints the pending marker before the version poll
    fills in the pin; no "?" shows for a version not yet known."""
    from app.ui.versions import VERSION_PENDING
    html = _home(versions={"pybnf": "x", "bngsim": VERSION_PENDING,
                           "bionetgen": "x", "perl": "x", "fastapi": "x",
                           "plotly": "x"})
    assert 'id="tip-home-pin"' not in html


def test_home_coverage_has_no_mark():
    """The stat and the map's "no data" chip say what the tip did."""
    html = _home()
    assert "1 of 52" in html and 'id="tip-hm-cover"' not in html
    assert 'id="tip-hm-nofc"' not in _home(outlook_date="", outlook_n=0,
                                            map_svg="")


# ---------------------------------------------------- Data: one rule, kept

def test_data_archive_mark_keeps_the_vintage_rule():
    """The one statement that a past week's run reads that week's
    archived data sits in the Archive "?", beside the shipped
    definition."""
    html = client.get("/data").text
    tip = html.split('id="tip-archive">', 1)[1].split("</span></span>", 1)[0]
    assert ("A run on a past week reads that week's archived vintage, "
            "never later revisions.") in tip
    assert "<dt>Scored against" in html and "<dt>Comparators" not in html


# --------------------------- Output: a file's count says what was asked
# (the window badges: test_output_by_date)

def test_a_files_location_count_says_what_was_asked():
    cov = ENV.from_string('{% import "_coverage.html" as c %}{{ c.line(v) }}')
    asked = cov.render(v={"n": 1, "of": 1, "missing": [], "moved": [],
                          "not_requested": 52, "id": "cov-a"})
    assert '<span class="uk-badge-t">1 of 53 locations</span>' in asked
    whole = cov.render(v={"n": 53, "of": 53, "missing": [], "moved": [],
                          "not_requested": 0, "id": "cov-b"})
    assert '<span class="uk-badge-t">all 53 locations</span>' in whole
    gaps = cov.render(v={"n": 1, "of": 2, "missing": [("Utah", "no fit")],
                         "moved": [], "not_requested": 51, "id": "cov-c"})
    assert "1 of 2 locations" in gaps and "2 of 53 asked" in gaps
    for html in (asked, whole, gaps):
        assert "tipbtn" not in html


# ------------------------------------------ Storage: one badge, said once

def _ledger(outcome, modified=True):
    return ENV.get_template("runs.html").render(
        active="Storage", storage=None, clear_count=0, ledger=[{
            "run_id": "r1", "parts": ["as of 2098-01-03", "run 01-10 09:31"],
            "label": "as of 2098-01-03 · run 01-10 09:31", "asof": "2098-01-03",
            "status": "ok", "elapsed_s": None, "disk_h": None,
            "research": False, "modified": modified,
            "facts": ui_shared._outcome_items(json.dumps(outcome))}])


def test_a_modified_runs_badge_says_whether_it_took_the_hub_names():
    over = _ledger({"knobs": {"override": "replay-scored"},
                    "submissions": ["a.csv"]})
    row = over.split('href="/runs/r1"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="uk-badge-t">modified · hub names</span>' in row
    summary = row.split('class="st-sumcell"', 1)[1]
    assert "modified" not in summary and "tipbtn" not in row
    plain = _ledger({"knobs": {}, "submissions": ["a.csv"]})
    row = plain.split('href="/runs/r1"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="uk-badge-t">modified settings</span>' in row
    assert row.count("modified settings") == 1


def test_a_ledger_dash_says_why_in_its_title():
    html = _ledger({"submissions": ["a.csv"]}, modified=False)
    assert '<span title="recorded before timing existed">--</span>' in html
    assert '<span title="workroot deleted">--</span>' in html
    assert "<th>elapsed</th>" in html and '<th class="num">on disk</th>' in html


def test_a_plain_fact_with_a_reason_says_it_in_its_chip():
    html = _ledger({"pf_skipped": True}, modified=False)
    row = html.split('href="/runs/r1"', 1)[1].split("</tr>", 1)[0]
    assert "PF skipped (no engine)" in row and "tipbtn" not in row


# ---------------------------------- Sandbox: each start says what it is

def test_every_start_carries_its_own_note():
    """The "i" beside Start from explains the chosen start, whatever it
    is, so it never needs the "?" that explained them all."""
    html = client.get("/sandbox").text
    start = html.split('id="sbnew-start"', 1)[1].split("</select>", 1)[0]
    for opt in re.findall(r"<option [^>]*>", start):
        assert "data-note=" in opt, opt
    assert "Its lines marked EDIT are the values to set" in start
    assert 'id="tip-sb-start"' not in html and 'id="tip-sb-name"' not in html
    # the How it works steps read as a list, one line each
    how = html.split('aria-label="How the Sandbox works"', 1)[1].split("</ol>", 1)[0]
    assert how.count('class="uk-step-meta"') == 6 and "tipbtn" not in how


# ------------- the Sandbox workbench: one "i" a card, the rest in words

def test_the_workbench_keeps_one_mark_a_card_from_a_first_visit_to_a_fit(sandbox_root):
    """A student's path (the SIR example, Check, a quick fit) shows two
    "i"s, one a card: the Model heading's (what the three files hold) and
    Run settings' (what Jitter and Seed do). The file tabs, the labels,
    the fit's result and the diagram carry no "?"; their labels, badges
    and one-line reasons say it."""
    from app.core import sandbox as sb
    from test_sandbox_guide import _finish
    sb.add_example("sir_example")
    html = client.get("/sandbox?model=sir_example").text
    assert marks(html) == ["tt-sb-files", "tt-sb-run"]
    files = html.split('id="tt-sb-files"', 1)[1].split("</span></span>", 1)[0]
    for fact in ("<b>model.bngl:</b>", "A name ending <code>__FREE</code> is fitted",
                 "<b>data.exp:</b>", "a missing week is a gap in time",
                 "<b>priors.conf:</b>", "<code>uniform_var = name low high</code>",
                 "(<code>loguniform_var</code> on a log scale)"):
        assert fact in files, fact
    # what Jitter and Seed do, in the Run settings legend; the group's
    # name is the legend's words alone
    run = html.split('id="tt-sb-run"', 1)[1].split("</span></span>", 1)[0]
    for fact in ("<b>Jitter:</b> how far each fitted value is nudged between weeks",
                 "the Liu-West kernel scale", "0.15 in production, 0.2 to 0.3 for a fit that collapses",
                 "<b>Seed:</b> the same seed and files repeat a fit exactly",
                 "another seed shows how much it varies by chance"):
        assert fact in run, fact
    assert ('<fieldset class="sbrun" aria-labelledby="sb-run-name"><legend class="sb-legend">'
            '<span id="sb-run-name">Run settings</span>') in html
    # what Simulate data replaces, beside its button
    assert '<span class="sb-hint">Replaces data.exp with counts' in html
    # after a quick check: its title, its reason in sight, the full fit
    w = sb.prepare("sir_example", particles=200)
    _finish(w)
    html = client.get(f"/sandbox?model=sir_example&run={w.name}").text
    assert marks(html) == ["tt-sb-files", "tt-sb-run"]
    assert "<strong>Quick check: the model runs</strong>" in html
    assert ('<span class="sb-says">200 particles: the ranges are rough; '
            'the full fit gives the estimates.</span>') in html
    assert ">Run the full fit (10,000 particles)<" in html
    # How it works says it in the same words, and spells out ESS
    assert "with a quick check (200) the ranges are rough" in html
    assert "The effective sample size (ESS) grades the sampling" in html
    # Check's report says it in its words; only what this computer lacks
    # keeps a "?" (its remedy)
    js = (Path(srv.__file__).parent / "static" / "sandbox.js").read_text()
    assert "sb-ck-ok" not in js and "sb-ck-model" not in js
    assert "['sb-ck-machine', f.machine_tip]" in js


# ----------------------------------- Methods: the folds hold the facts

def _fold(html, fid):
    return " ".join(html.split(f'id="{fid}"', 1)[1].split("</details>", 1)[0].split())


def test_methods_keeps_the_facts_its_marks_held_in_folds():
    """What the stat tiles' marks said that their units do not lives in
    the section's fold (the facts the review listed)."""
    t = client.get("/methods").text
    what = _fold(t, "mt-oracle-what")
    assert "within two epiweeks of the forecast week, any jurisdiction" in what
    how = _fold(t, "mt-gh-how")
    for fact in ("strictly earlier seasons, any state",
                 "fewer than 30 donors means no forecast",
                 "one state gives about five donors per season",
                 # the shipped own-state weighting (since 2026-10-15)
                 "pooled across jurisdictions with the jurisdiction's own "
                 "past weeks carrying half of the weight",
                 "2021-22 is excluded from the donors",
                 "no coverage guarantee is claimed"):
        assert fact in how.replace("&#39;", "'"), fact
    # the weighting is the admissions pool's: the FluSurv-NET pool stays
    # pooled (0e60501), and both now separate it from the bare analogue
    bank = _fold(t, "mt-gh-bank")
    assert "pooled across sites with no own-state weight" in bank
    assert "since 2026-10-15 the own-state weighting" in bank
    assert "fresh run from August 1" in _fold(t, "mt-fresh")
    caveats = _fold(t, "mt-caveats")
    assert "frozen by a pre-registration before it was scored" in caveats
    scoring = _fold(t, "mt-scoring-more")
    for fact in ("log scale", "bounds included", "before 2026-09-25",
                 "withdrawn on 2026-08-24"):
        assert fact in scoring, fact
    cells = _fold(t, "mt-perf-cells").replace("&#39;", "'")
    assert "4,000 bootstrap replicates" in cells
    # the paired comparison with the bare analogue is the pooled form's,
    # under the earlier rule, and says so; the shipped row names its own
    assert ("Under it the pooled form (0.666) and the bare analogue share "
            "15,340 cells") in cells
    assert "on 17,116 cells under FluSight's cell rule" in cells


def test_methods_engine_fold_joins_the_fit_and_the_install():
    """One fold under the component table: how the filter runs (BNG2.pl
    once per state, bngsim in process), the sealed record's pin, and on
    the console the engine venv's installers and Windows' own Perl."""
    t = client.get("/methods").text
    eng = _fold(t, "mt-engine")
    assert "BNG2.pl expands the BNGL model into a reaction network" in eng
    assert "bngsim 0.15.1 (pinned by every engine installer)" in eng
    assert "<code>SetupEngine.command</code> on macOS" in eng
    assert "FluBNF.bat installs its own Perl for BNG2.pl, with no administrator" in eng
    stack = t.split('<table class="mt-stack">', 1)[1].split("</table>", 1)[0]
    assert "tipbtn" not in stack


def test_methods_lists_every_model_setting_the_panel_offers():
    """The Forecast panel carries no per-setting explanations; Methods'
    Model settings card holds each one: what it does, its range, its
    default and its note (knobs.REGISTRY, in the panel's own groups)."""
    from app.core import knobs as K
    t = client.get("/methods").text
    card = t.split('<div class="card" id="settings">', 1)[1].split(
        '<div class="card"><h2>Measured performance', 1)[0]
    text = " ".join(card.split())
    for g in K.panel("forecast")["groups"]:
        assert f'id="mt-set-{g["id"]}"' in card, g["id"]
        for r in g["rows"]:
            k = K.BY_KEY[r["key"]]
            assert f'id="set-{k.key.replace(".", "-")}"' in card, k.key
            assert " ".join(str(Markup_escape(k.help)).split()) in text, k.key
    # a choice's default reads as its option does, and the console's
    # contents row links the card; the public site has no Forecast tab
    assert "<td>2026091801</td>" in text
    # the other choices read in the panel's words, the stored value beside
    assert "expected total (early season) (season_total_early)" in text
    assert "<td>random draws (rand)</td>" in text
    assert '<a href="#settings">Model settings</a>' in t
    from app.core import site_build
    assert 'id="settings"' not in site_build.harvest_methods({})


def Markup_escape(s):
    from markupsafe import escape
    return escape(s)
