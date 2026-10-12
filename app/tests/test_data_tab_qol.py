"""The Data tab's small aids: the data's age beside "Data through", Update
data as the primary only once a check finds the clone behind, the pull's
notice saying what changed, the hub badge held with its "?", and the
newest weeks' change column."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as data_mod                # noqa: E402
from app.ui.routes import data as D                  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"


def test_data_age_in_days_and_overdue_past_eleven():
    assert D._data_age("2026-09-26", today=date(2026, 10, 5)) == \
        {"text": "9 days", "state": "neutral"}
    assert D._data_age("2026-10-04", today=date(2026, 10, 5))["text"] == "1 day"
    assert D._data_age("2026-10-05", today=date(2026, 10, 5))["text"] == "today"
    assert D._data_age("2026-09-19", today=date(2026, 10, 5))["state"] == "warn"
    assert D._data_age(None) is None and D._data_age("soon") is None


def test_clone_behind_reads_the_check():
    F = data_mod.Freshness
    assert D._clone_behind(None) is False
    assert D._clone_behind(F(None, None, 0, True, "ok")) is False
    assert D._clone_behind(F(None, None, 0, False, "x", local_live="2026-09-26",
                             remote_live="2026-10-03")) is True
    assert D._clone_behind(F("2026-09-19", "2026-09-26", 0, False, "x")) is True
    assert D._clone_behind(F(None, None, 3, False, "x")) is True


def test_pull_changes_counts_weeks_and_revisions():
    b = {("2026-09-26", "01"): 10.0, ("2026-09-19", "01"): 8.0}
    a = {("2026-10-03", "01"): 12.0, ("2026-09-26", "01"): 11.0,
         ("2026-09-19", "01"): 8.0}
    assert D._pull_changes("2026-09-26", "2026-10-03", b, a) == \
        ["+1 week", "1 revised value"]
    assert D._pull_changes("2026-09-26", "2026-09-26", b, b) == []
    assert D._pull_changes(None, "2026-10-03", None, a) == []


def test_hub_badge_and_its_tip_never_separate():
    src = (TEMPLATES / "data.html").read_text(encoding="utf-8")
    pair = src.split('{% set clone %}')[1].split('{% endset %}')[0]
    assert pair.startswith('<span class="uk-badge-pair">')
    assert 'id="hub-detail"' in pair and 'id="hub-pill"' in pair


def test_newest_weeks_table_has_a_change_column():
    src = (TEMPLATES / "data.html").read_text(encoding="utf-8")
    assert '<th class="num">change</th>' in src and "dt-wow" in src
