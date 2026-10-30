"""The Oracle SIHRS's words on Methods and the Models tab: the submitted
weight beside the registered one, the donor floor, the narrowing screen's
member, what a step change costs, each record's cell rule, and the
two-strain card."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                       # noqa: E402
from app.ui.routes.models import _record              # noqa: E402
from app.ui.server import app as srv                  # noqa: E402

client = TestClient(srv)


def _flat(html):
    return " ".join(html.split())


def test_methods_says_the_submitted_weight_beside_the_registered_one():
    # the hub card (1.4): one quarter on the filter's growth from the
    # 2026-10-17 round, one half before
    t = _flat(client.get("/methods").text)
    what = t.split('id="mt-oracle-what"', 1)[1].split("</details>", 1)[0]
    assert ("the weighted geometric mean of the filter's and the donor's, "
            "propagated in closed form from the filter's own state: half and "
            "half by default, and one quarter on the filter's growth in the "
            "rounds submitted since 2026-10-17, each run recording the weight "
            "it used") in what.replace("&#39;", "'")
    rel = t.split('id="mt-oracle-gh"', 1)[1].split("</details>", 1)[0]
    assert "at half weight" not in rel and "at the blend weight" in rel
    assert "the registered blend weight, set a priori" in t


def test_the_donor_floor_is_neither_stream_not_each():
    # where only one stream has 30 paths, it supplies every donor
    for path in ("/methods", "/models"):
        t = _flat(client.get(path).text)
        assert ("A week where neither stream supplies 30 donor paths leaves "
                "the filter unchanged; where only one does, that stream "
                "supplies every donor.") in t, path
        assert "30 paths per stream" not in t, path


def test_the_narrowing_note_names_the_member_its_screen_used():
    note = K.BY_KEY["oracle.narrow"].note
    assert ("on the stage-rule member at weight 0.25 (9,152 cells): k = 0.7 "
            "took pooled relWIS from 0.720 to 0.671") in note


def test_the_oracle_steps_cost_line_promises_no_refit_on_the_forecast_tab():
    # a Forecast-tab run fits every state; a replay keeps its fitted weeks
    tip = dict((g, tip) for g, _title, tip in K.PANEL_GROUPS)["step"]
    assert "costs no refit" not in tip
    assert tip.endswith("a replay reuses its fitted weeks, a console run "
                        "fits again.")


def test_each_record_names_its_cell_rule_and_its_comparison():
    assert "under the earlier cell rule" in _record("pf")["lines"][0]
    pf2s = _record("pf2s")
    assert [b["label"] for b in pf2s["bars"]] == [
        "Two-strain SIHRS", "Blend it was tested in"]
    assert "full grid" not in pf2s["lines"][0]


def test_the_two_strain_card_does_not_call_its_linked_page_hidden():
    t = _flat(client.get("/methods").text)
    assert "reachable by URL" not in t
    assert "it stays a research run.</p>" in t
