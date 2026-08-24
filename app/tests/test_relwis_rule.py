"""The single relWIS rule.

Everywhere a relWIS prints outside a scores table it must wear the same
encoding the app teaches elsewhere: tabular numerals, the ok/bad
below-1-beats-baseline classes, and a label naming the member and the cell
coverage the score rests on. Error chips speak plain language; the raw
error string lives on the run page and nowhere else. The Methods
performance table colors every printed score, member failures included.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

NAU = Path(__file__).resolve().parents[1] / "ui" / "static" / "nau.css"


def test_relwis_chip_formats_member_coverage_and_classes():
    assert srv.relwis_chip(4.067, cells=2) == \
        'PF relWIS <span class="relwis bad">4.067</span> (2 cells)'
    assert srv.relwis_chip(0.987, cells=1) == \
        'PF relWIS <span class="relwis ok">0.987</span> (1 cell)'
    # coverage unknown: the parenthetical is omitted, never invented
    assert srv.relwis_chip(0.5) == \
        'PF relWIS <span class="relwis ok">0.500</span>'
    # an unreadable value yields nothing rather than a broken chip
    assert srv.relwis_chip("nonsense") == ""
    assert srv.relwis_chip(None) == ""


def test_outcome_chips_apply_the_rule():
    chips = srv._outcome_chips(json.dumps(
        {"pf_cells": 2, "pf_failures": {"a": "boom"},
         "submissions": {"PF-SIHRS": "p", "Ensemble": "q"},
         "report": "r.html", "pf_relwis": 4.067}))
    assert "PF 2 fits" in chips
    assert '<span class="bad">1 failure</span>' in chips
    assert "2 submissions" in chips
    assert 'PF relWIS <span class="relwis bad">4.067</span> (2 cells)' \
        in chips
    good = srv._outcome_chips(json.dumps({"pf_cells": 1,
                                          "pf_relwis": 0.702}))
    assert 'PF relWIS <span class="relwis ok">0.702</span> (1 cell)' in good


def test_error_chips_speak_plain_language_never_tracebacks():
    raw = "module 'pandas.io.json' has no attribute 'dumps'"
    chips = srv._outcome_chips(json.dumps({"error": raw}))
    assert "pandas" not in chips                  # the raw string never leaks
    assert '<span class="bad">failed</span>' in chips
    assert "run page" in chips                    # and says where the raw is


def test_runs_page_renders_chips_as_markup():
    html = srv.templates.env.get_template("runs.html").render(
        active="Runs", ledger=[
            {"run_id": "r1", "label": "2098-01-03 · Jan 03 09:31",
             "status": "ok", "elapsed_s": 60.0,
             "chips": srv._outcome_chips(json.dumps(
                 {"pf_cells": 2, "pf_relwis": 4.067}))}])
    # the span survives unescaped, so the color classes actually apply
    assert '<span class="relwis bad">4.067</span>' in html
    assert "&lt;span" not in html


def test_run_page_keeps_the_raw_error_string():
    raw = "module 'pandas.io.json' has no attribute 'dumps'"
    html = srv.templates.env.get_template("run.html").render(
        active="Runs", run_id="r1", status="error", error=raw,
        label="2098-01-03", models={}, settings=[], versions=[],
        subs=[], report=None)
    assert "pandas.io.json" in html               # the raw record of what broke


def test_methods_table_colors_every_score_members_included():
    r = client.get("/methods")
    assert r.status_code == 200
    # member seasons that lost to the baseline are marked, not neutral
    assert '<td class="bad">1.023</td>' in r.text
    assert '<td class="bad">1.045</td>' in r.text
    # and member seasons that beat it wear the same ok the ensemble does
    for v in ("0.636", "0.825", "0.756", "0.621"):
        assert f'<td class="ok">{v}</td>' in r.text, v
    assert '<td class="ok">0.813</td>' in r.text


def test_relwis_class_is_tabular():
    css = NAU.read_text()
    assert ".relwis{font-variant-numeric:tabular-nums" in css
