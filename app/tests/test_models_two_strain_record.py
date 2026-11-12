"""The two-strain SIHRS record on the Models tab. Both figures come from the
August 2026 ensemble gate on the seal of 2026-08-19 (docs/archive/
RELEASE-1.0.md, the seal table and the two-strain entry: equal thirds
0.7189 against the two-member 0.7039, before the donor-pool exclusion).
0.719 is the three-member ensemble with equal thirds, not the two-strain
model alone, so the record compares the ensemble with it and without it."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.routes.models import _record              # noqa: E402
from app.ui.server import app as srv                  # noqa: E402

client = TestClient(srv)

NOTE = "seal 2026-08-19, three seasons, before the donor-pool exclusion"


def _flat(html):
    return " ".join(html.split())


def test_the_bars_are_the_ensemble_with_it_and_without_it():
    rec = _record("pf2s")
    assert [(b["label"], b["text"], b["this"]) for b in rec["bars"]] == [
        ("Ensemble with it (equal thirds)", "0.719", True),
        ("Ensemble without it (50/50)", "0.704", False)]
    # 0.719 is the three-member ensemble's, so no bar is the model alone
    assert not any("Two-strain" in b["label"] for b in rec["bars"])


def test_the_record_notes_the_seal_and_the_donor_pool():
    rec = _record("pf2s")
    assert rec["facts"] == [("Seal", "2026-08-19", ""),
                            ("Seasons", "2023-24 to 2025-26", ""),
                            ("Donor pool", "before the exclusion", "")]
    text = " ".join(rec["lines"])
    assert NOTE in text
    # the blend's cell count is the seal's; the equal thirds have none
    assert "15,460 cells" in text
    assert "no cell count" in text


def test_the_badge_and_sentence_say_adding_it_scored_worse():
    rec = _record("pf2s")
    assert rec["behind"]["text"] == "0.015 worse as a third member"
    first = rec["lines"][0]
    assert first.startswith("Adding it as a third equal member scored worse")
    assert "0.719" in first and "0.704" in first
    assert "lower is better" in first
    assert "Liu-West filter" in first
    text = " ".join(rec["lines"])
    # not the model alone against the blend
    for old in ("It scored worse than the blend", "tested in",
                "behind the blend", "Two-strain SIHRS"):
        assert old not in text, old
    assert "posterior" not in text.lower()


def test_the_page_shows_the_new_record_and_not_the_old_words():
    r = client.get("/model/pf2s")
    assert r.status_code == 200
    t = _flat(r.text)
    hero = t.split('class="md-record"', 1)[1].split("</section>", 1)[0]
    for new in ("Ensemble with it (equal thirds)",
                "Ensemble without it (50/50)",
                "0.015 worse as a third member", NOTE):
        assert new in hero, new
    for old in ("Blend it was tested in", "behind the blend",
                "It scored worse than the blend"):
        assert old not in hero, old
