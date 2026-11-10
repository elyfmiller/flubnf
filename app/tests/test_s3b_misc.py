"""Small defects left from the bug hunt's fix review (second S3 pass).

  * Two stored datasets of one name over the same weeks are told apart, in
    the Source list and in the New model list (SB-06): by the day each was
    uploaded, else by the end of its id.
  * BNG2.pl's ABORT line keeps the "at line N" that follows it, as its
    ERROR line does (SB-04).
  * The season report on paper draws the Groundhog in the light themes'
    dark gold, whichever theme is on screen (UI-03).

Hub-free and engine-free (conftest.sandbox_root)."""
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

import css_cascade                                       # noqa: E402
from app.core import datasets                            # noqa: E402
from app.core import sandbox_data as sbd                 # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)
TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"

WEEKS = ("2024-01-06", "2024-06-29")


def _ds(ident, created, weeks=WEEKS, name="cases"):
    """A stored dataset as dataset_choices reads it."""
    meta = {"groups": [{"name": "Springfield", "first": weeks[0],
                        "last": weeks[1], "population": 100000}]}
    if created:
        meta["created"] = created
    return types.SimpleNamespace(id=ident, name=name, kind="count",
                                 pf_eligible=True, meta=meta)


# ---------------------------------- SB-06: two datasets of one name and weeks

def test_same_named_datasets_over_the_same_weeks_get_distinct_labels(
        monkeypatch):
    monkeypatch.setattr(datasets, "list_datasets", lambda: [
        _ds("cases-a1b2c3d4e5f6", "2026-11-02T11:00:00Z"),
        _ds("cases-0f9e8d7c6b5a", "2026-11-02T10:00:00Z"),
        _ds("cases-77aa88bb99cc", "2026-10-30T09:00:00Z"),
        _ds("cases-1234567890ab", "2026-10-29T09:00:00Z",
            ("2025-01-04", "2025-03-29")),
        _ds("flu-5555aaaa6666", "2026-10-28T09:00:00Z", name="flu")])
    labels = [d["label"] for d in sbd.dataset_choices()]
    assert labels == [
        # uploaded the same day: the end of the id
        "cases (2024-01-06 to 2024-06-29, id ending d4e5f6)",
        "cases (2024-01-06 to 2024-06-29, id ending 7c6b5a)",
        # the only one uploaded that day: the day
        "cases (2024-01-06 to 2024-06-29, uploaded 2026-10-30)",
        # other weeks: the weeks are enough, as before
        "cases (2025-01-04 to 2025-03-29)",
        "flu"]
    assert len(set(labels)) == len(labels)


def test_ids_that_end_alike_and_datasets_without_weeks_or_a_day():
    out = [{"id": i, "name": "cases", "groups": []}
           for i in ("cases-aaaaaa123456", "cases-bbbbbb123456")]
    sbd._label_choices(out, ["", ""])
    assert [d["label"] for d in out] == ["cases (id ending a123456)",
                                         "cases (id ending b123456)"]
    one = [{"id": "cases-aaaaaa123456", "name": "cases", "groups": []}]
    sbd._label_choices(one, [""])
    assert one[0]["label"] == "cases"


def test_the_new_model_list_tells_same_named_datasets_apart(sandbox_root,
                                                            monkeypatch):
    monkeypatch.setattr(datasets, "list_datasets", lambda: [
        _ds("cases-a1b2c3d4e5f6", "2026-11-02T11:00:00Z"),
        _ds("cases-77aa88bb99cc", "2026-10-30T09:00:00Z")])
    html = client.get("/sandbox").text
    opts = re.findall(r'<option value="shipped:dataset:([^"]+)" '
                      r'data-note="([^"]*)"[^>]*>([^<]*)</option>', html)
    assert [(i, t) for i, _, t in opts] == [
        ("cases-a1b2c3d4e5f6", "Oracle SIHRS filter, dataset cases "
                               "(2024-01-06 to 2024-06-29, uploaded 2026-11-02)"),
        ("cases-77aa88bb99cc", "Oracle SIHRS filter, dataset cases "
                               "(2024-01-06 to 2024-06-29, uploaded 2026-10-30)")]
    notes = [n for _, n, _ in opts]
    assert len(set(notes)) == 2
    assert notes[1].endswith(", for one group of cases (2024-01-06 to "
                             "2024-06-29, uploaded 2026-10-30) and week.")


# ------------------------------------------- SB-04: the line BNG2.pl names

def test_the_abort_line_keeps_its_line_number():
    assert pf.bng_said_why(
        "ABORT: Parameter 'nosuchparam' is referenced but not defined\n"
        "at line 49") == ("Parameter 'nosuchparam' is referenced but not "
                          "defined (line 49)")
    # indented, after BioNetGen's banner, as BNG2.pl prints it
    assert pf.bng_said_why(
        "BioNetGen version 2.9.3\nABORT: Molecule Q not defined\n"
        "  at line 12\n") == "Molecule Q not defined (line 12)"
    # an ABORT with no line stays as it was
    assert pf.bng_said_why("BioNetGen version 2.9.3\nABORT: Molecule Q not "
                           "defined\n") == "Molecule Q not defined"
    assert pf.bng_said_why("ABORT: bad rule\nsomething else") == "bad rule"
    # the ERROR line still comes first, with its own line
    assert pf.bng_said_why(
        "ERROR: Molecule Z() does not match\n  at line 48\n"
        "ABORT: Reaction rule list could not be read\n  at line 3\n") == \
        "Molecule Z() does not match (line 48)"


# ------------------------------------ UI-03: the season report on paper

def _season_print_cascade():
    """base.html's sheets, then the season page's own <style> block (the
    export's print rule), as the export orders them."""
    tpl = (TEMPLATES / "retro_season.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<style>(.*?)</style>", tpl, re.S)
    assert blocks, "the season page lost its print style"
    cas = css_cascade.Cascade.page()
    for b in blocks:
        cas.rules += css_cascade.parse(b, "retro_season.html")
    for i, r in enumerate(cas.rules):
        r.order = i
    return cas


@pytest.mark.parametrize("theme", css_cascade.themes())
def test_the_groundhog_prints_dark_enough_on_white_in_every_theme(theme):
    cas = _season_print_cascade()
    root = css_cascade.path(f'html[data-theme="{theme}"]')
    printed = cas.token(root, "--model-analogue", on={"print"})
    assert css_cascade.contrast(printed, "#FFFFFF") >= 3, (theme, printed)


def test_the_print_rule_leaves_the_screen_colour_alone():
    cas = _season_print_cascade()
    dark = css_cascade.path('html[data-theme="dark"]')
    assert cas.token(dark, "--model-analogue").upper() == "#FFC72C"
    assert cas.token(dark, "--model-analogue", on={"print"}).upper() == \
        "#806000"
