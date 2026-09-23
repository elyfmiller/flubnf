"""The Oracle SIHRS in words: one marked place, sourced figures, the
pipeline figure, and the member's name on every page.

  * the donor-bank sentences live in app/core/oracle_text and nowhere else:
    its stream must be the library's (a bank change fails here until the
    words follow), and no template types the bank's stream itself;
  * every figure the pages print for the Oracle SIHRS appears, to four
    places, in docs/ORACLE-SIHRS.md, where its provenance is written;
  * the pipeline figure keeps the diagrams' house rules and reaches the
    model tab and Methods;
  * the model tab and Methods say what the member is: the fit, the blend,
    one donor per sample path, why, the record with its caveat, and how it
    differs from the Groundhog;
  * no rendered page names the model, member, forecast or submission as
    bare SIHRS: what remains is the compartment model, the two-strain
    research variant, file names and the BNGL listing (the record's bytes);
  * the public site names its mechanistic column for what the published
    trees store.
"""
import json
import re
from html import unescape
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                              # noqa: E402
from fastapi.testclient import TestClient                  # noqa: E402
from markupsafe import escape                              # noqa: E402

from app.core import oracle_text as ot                     # noqa: E402
from app.ui import server as srv                           # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "ORACLE-SIHRS.md"
TEMPLATES = REPO / "app" / "ui" / "templates"
client = TestClient(srv.app)


# ------------------------------------------------------- the one marked place

def test_the_bank_words_follow_the_library_stream():
    from flubnf import oracle_mix
    assert ot.BANK_STREAM == oracle_mix.STREAM, (
        "the Oracle step's shipped donor bank changed: rewrite "
        "app/core/oracle_text.BANK_TEXT, then BANK_STREAM, together")
    # both streams are named wherever the bank is described
    for key in ("phrase", "diagram", "pool", "card"):
        assert "NHSN" in ot.BANK_TEXT[key] and "FluSurv-NET" in ot.BANK_TEXT[key], key
    assert "Groundhog's own" in ot.BANK_TEXT["pool"] and "half and half" in ot.BANK_TEXT["pool"]


def test_the_document_hashes_are_the_librarys():
    from flubnf import oracle
    assert ot.PREREG_SHA256 == oracle.PREREG_SHA256
    assert ot.B2_SHA256 == oracle.B2_SHA256
    assert ot.ADDENDUM_A2_SHA256 == oracle.ADDENDUM_A2_SHA256


def test_no_template_types_the_bank_itself():
    """The pages name the donor pool's stream only through the global."""
    for name in ("diagrams.html", "methods.html", "model.html", "home.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        assert ot.BANK_TEXT["diagram"] not in src, name
        assert ot.BANK_TEXT["pool"][:60] not in src, name


# --------------------------------------------------------- sourced figures

def test_every_record_figure_is_in_the_oracle_doc():
    doc = DOC.read_text(encoding="utf-8")
    for key, r in ot.RECORD.items():
        for field in ("oracle", "filter"):
            assert ot.fmt(r[field], 4) in doc, (key, field)
        assert ot.cells(r["cells"]) in doc, key
    assert ot.fmt(ot.RECORD_ADMISSIONS_ONLY["both"], 4) in doc
    lo, hi = ot.RECORD_B2_1["reading95"]
    assert f"{lo:+.4f} to {hi:+.4f}" in doc and ot.RECORD_B2_1["outcome"] in doc
    # the three-place figures the pages print are those, rounded
    assert ot.fmt(ot.RECORD["both"]["oracle"]) == "0.731"
    assert ot.fmt(ot.RECORD["both"]["filter"]) == "0.813"
    assert ot.fmt(ot.RECORD_ADMISSIONS_ONLY["both"]) == "0.741"


_B2_SCORES = (Path("~/Documents/FluBNF-local/research/groundhog-beta/oracle_member/b2/"
                   "results/screen_b2_scores.json").expanduser())


@pytest.mark.skipif(not _B2_SCORES.is_file(), reason="the B2 screen's scores are not on this machine")
def test_the_record_is_the_b2_screens_own_numbers():
    """RECORD is read from the B2 screen, never typed: the shipped member
    (LBGH) and the plain filter (NULL) on the common set, seed mean, and
    the screen's cell counts; the admissions-only member (LB) and claim
    B2-1's reading beside them."""
    d = json.loads(_B2_SCORES.read_text())
    assert d["b2_frozen_sha256"] == ot.B2_SHA256
    rt, ps = d["relwis_tables"], d["per_season"]
    scope = {"2023-24": "2023-24", "2024-25": "2024-25", "2025-26": "2025-26",
             "both": "active2", "three": "pooled3"}
    for key, sc in scope.items():
        assert ot.RECORD[key]["oracle"] == rt["LBGH"]["common"][sc], key
        assert ot.RECORD[key]["filter"] == rt["NULL"]["common"][sc], key
        assert ot.RECORD[key]["cells"] == ps[sc]["cells_common"], key
    assert ot.RECORD_ADMISSIONS_ONLY["both"] == rt["LB"]["common"]["active2"]
    r = d["readings"]["claim_B2_1_BEATS_THE_FROZEN_MEMBER"]
    assert ot.RECORD_B2_1["point"] == r["point"] and ot.RECORD_B2_1["outcome"] == r["outcome"]
    assert list(ot.RECORD_B2_1["reading95"]) == r["reading95"]


# ----------------------------------------------------------- the pipeline

def _pipeline():
    return srv.templates.env.get_template("diagrams.html").module \
        .oracle_pipeline(uid="t")


def test_pipeline_figure_keeps_the_house_rules():
    html = str(_pipeline())
    assert 'role="img"' in html and 'aria-label="Oracle SIHRS pipeline' in html
    assert "<desc>" in html and "<title>" not in html
    assert 'stroke="currentColor"' in html          # ink follows the theme
    for token in ("var(--slate)", "var(--gold)", "var(--warn)"):
        assert token in html, token
    assert "var(--bad)" not in html                 # red stays semantic
    assert "svgt-sm" in html and 'font-size="' not in html
    # the stages, in order, and the donor pool's stream from the global
    stages = ["Weekly fit", "Filter forecast", "Growth blend",
              "Oracle SIHRS", "Donor pool"]
    drawing = html[html.index("</defs>"):]
    at = [drawing.index(s) for s in stages]
    assert at[:4] == sorted(at[:4])
    assert ot.BANK_TEXT["diagram"] in html
    # every label fits its 210-unit box at the A+ step (22 characters)
    for line in re.findall(r'class="svgt-sm"[^>]*>([^<]+)<', html):
        assert len(unescape(line)) <= 22, line


def test_pipeline_and_blend_equation_reach_the_model_tab_and_methods():
    for page in ("/models", "/methods"):
        t = client.get(page).text
        assert t.count('aria-label="Oracle SIHRS pipeline') == 1, page
        assert "the growth blend" in t, page
        assert str(escape(ot.BANK_TEXT["pool"])) in t, page


# ------------------------------------------------ what the pages now say

def test_model_tab_describes_the_member_as_it_is():
    t = " ".join(client.get("/models").text.split())
    for needle in ("SIHRS compartment model", "particle filter",
                   "August 1", "geometric mean", "same calendar week",
                   "one donor growth path", "own current state",
                   "calendar-donor principle the Groundhog uses",
                   "donor growth ratios to the last observed count",
                   "separate models", "frozen-specification replication",
                   "2026-27 season is its prospective test",
                   "relWIS 0.731 against the plain filter's 0.813",
                   "0.767 against 0.840 in 2023-24", "0.738 against 0.819",
                   "0.731 against 0.741", "includes zero",
                   "9,279 cells", "How the forecast is made",
                   "The compartment model the filter fits"):
        assert needle in t, needle


def test_methods_carries_the_oracle_step_card():
    t = " ".join(client.get("/methods").text.split())
    assert 'id="oracle"' in t
    for needle in ("The Oracle step", "One donor per sample",
                   "How it relates to the Groundhog", "Why.",
                   "frozen by a pre-registration", ot.PREREG_SHA256[:16],
                   ot.B2_SHA256[:16],
                   "0.697", "0.794", "0.781", "0.843", "0.731", "0.813",
                   "0.767", "0.840", "0.738", "0.819", "0.741",
                   "only one earlier NHSN season (2022-23) is admissible",
                   "includes zero",
                   "flubnf retro --oracle none"):
        assert needle in t, needle
    # the three-season table names the filter it scores
    assert "Particle filter alone (the Oracle SIHRS before its step)" in t


# --------------------------------------- the member's name on every page

#: what may still say SIHRS without "Oracle " on a page a person reads: the
#: compartment model the member is built on, the research two-strain
#: variant of it, and file names
_ALLOWED = re.compile(
    r"SIHRS compartment|[Tt]wo-strain SIHRS|SIHRS circuits|SIHRS_pop\w*"
    r"|ORACLE-SIHRS\.md|OracleSIHRS")


def test_no_page_names_the_model_as_bare_sihrs():
    pages = ("/", "/methods", "/models", "/model/analogue", "/model/pf2s",
             "/forecast", "/retro", "/runs", "/output", "/data", "/sandbox")
    for page in pages:
        html = client.get(page).text
        # the BNGL listing is the template file shown as stored: its bytes
        # are the record's and are not renamed
        html = re.sub(r"<pre>.*?</pre>", "", html, flags=re.S)
        text = " ".join(html.split())
        for m in re.finditer(r"(?<!Oracle )SIHRS", text):
            window = text[max(0, m.start() - 12):m.end() + 14]
            assert _ALLOWED.search(window), (page, window)


# ------------------------------------------ the public site's column name

def test_site_names_the_mechanistic_column_for_what_the_trees_store(tmp_path):
    from app.core import retro
    from app.core import site_build as sb
    plain = tmp_path / "2024-25"
    (plain / "weeks" / "2024-11-16").mkdir(parents=True)
    retro.write_meta(plain, {"settings": {"engine": "pf"}})
    member = tmp_path / "2025-26"
    (member / "weeks" / "2025-11-15").mkdir(parents=True)
    (member / "weeks" / "2025-11-15" / "oracle.json").write_text(
        json.dumps({"applied": True}))
    by_meta = tmp_path / "2026-27"
    (by_meta / "weeks").mkdir(parents=True)
    retro.write_meta(by_meta, {"settings": {"oracle": "applied"}})
    research = tmp_path / "2023-24"
    (research / "weeks" / "2023-11-04").mkdir(parents=True)
    (research / "weeks" / "2023-11-04" / "oracle.json").write_text("{}")
    retro.write_meta(research, {"settings": {
        "oracle": "none (the plain filter, a research run)"}})

    assert not sb.tree_carries_oracle(plain)
    assert sb.tree_carries_oracle(member)
    assert sb.tree_carries_oracle(by_meta)
    assert not sb.tree_carries_oracle(research)
    # no run record to say so: the week's own oracle.json decides, and a
    # plain-filter research week writes one with "applied": false
    unrecorded = tmp_path / "2022-23"
    (unrecorded / "weeks" / "2022-11-05").mkdir(parents=True)
    (unrecorded / "weeks" / "2022-11-05" / "oracle.json").write_text(
        json.dumps({"applied": False, "reason": "oracle = none"}))
    assert not sb.tree_carries_oracle(unrecorded)
    # the public site's per-week fan name reads the same flag (build_outlook)
    assert sb._week_applied(member / "weeks" / "2025-11-15")
    assert not sb._week_applied(unrecorded / "weeks" / "2022-11-05")
    assert not sb._week_applied(plain / "weeks" / "2024-11-16")
    assert sb.pf_label({"a": {"root": member}, "b": {"root": by_meta}}) \
        == sb.PF_LABEL_ORACLE
    assert sb.pf_label({"a": {"root": member}, "b": {"root": plain}}) \
        == sb.PF_LABEL_FILTER
    assert sb.pf_label({}) == sb.PF_LABEL_FILTER
    checks = sb.cross_check(
        [{"season": "2024-25", "models": {"pf": {"rel": 0.797}}}],
        {"2024-25": {"app_rel": 0.797}}, sb.PF_LABEL_FILTER)
    assert checks[0]["what"] == "2024-25 Particle filter alone relWIS"
