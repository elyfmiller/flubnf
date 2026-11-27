"""The Data tab's small aids: the data's age beside "Data through", Update
data as the primary only once a check finds new flu data, the pull's
notice saying what changed, the hub badge and the check's words in the
clone fold, and the newest weeks' change column."""
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


def test_new_data_reads_the_check():
    F = data_mod.Freshness
    assert D._new_data(None) is False
    assert D._new_data(F(None, None, 0, True, "ok")) is False
    assert D._new_data(F(None, None, 0, False, "x", local_live="2026-09-26",
                         remote_live="2026-10-03")) is True
    assert D._new_data(F("2026-09-19", "2026-09-26", 0, False, "x")) is True
    # commits that bring no new week are not new data (the hub's file was
    # read and holds the same newest week)
    assert D._new_data(F(None, None, 3, False, "x", local_live="2026-10-03",
                         remote_live="2026-10-03")) is False
    # commits whose file could not be read: Update data stays the next step
    assert D._new_data(F(None, None, 3, False, "x")) is True
    # a file on disk that is not the hub's
    assert D._new_data(F(None, None, 0, False, "x", local_live="2026-10-03",
                         remote_live="2026-10-03", tree_stale=True)) is True


def test_pull_changes_counts_weeks_and_revisions():
    b = {("2026-09-26", "01"): 10.0, ("2026-09-19", "01"): 8.0}
    a = {("2026-10-03", "01"): 12.0, ("2026-09-26", "01"): 11.0,
         ("2026-09-19", "01"): 8.0}
    assert D._pull_changes("2026-09-26", "2026-10-03", b, a) == \
        ["+1 week", "1 revised value"]
    assert D._pull_changes("2026-09-26", "2026-09-26", b, b) == []
    assert D._pull_changes(None, "2026-10-03", None, a) == []


def test_hub_badge_and_the_checks_words_sit_in_the_clone_fold():
    src = (TEMPLATES / "data.html").read_text(encoding="utf-8")
    fold = src.split('{% call tips.fold("Hub clone details"', 1)[1] \
        .split("{% endcall %}\n  {% endcall %}", 1)[0]
    assert 'id="hub-pill"' in fold and 'id="hub-detail"' in fold


def test_newest_weeks_table_has_a_change_column():
    src = (TEMPLATES / "data.html").read_text(encoding="utf-8")
    assert '<th class="num">change</th>' in src and "dt-wow" in src
