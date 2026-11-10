"""The Storage page's words, counts and marks (bug hunt 2026-10-25, G29).

  * The ledger's heading counts every run recorded, not the rows shown.
  * The sections carry no "?" of their own; an entry in use has its
    Delete off with no "?", and why is said once above the sections; a
    report archive is in use only for the running run's own date.
  * Archived runs read in this computer's time, as the workroot rows do.
  * The bulk controls say "not running" and count one plainly; the
    ledger's clear lists no statuses it could miss.
  * The empty states follow what the page lists.
  * A workroot's delete leads with the run's name and says what goes.
  * A dataset's delete notice names only what it had.
  * The ledger's "failed" filter takes every run that did not end ok, and
    Find matches a run's full date.
"""
from pathlib import Path

from app.ui import datasets_ui as DU
from app.ui.routes import storage as ui_storage
from test_storage import client, state                       # noqa: F401

PAGE = (Path(__file__).resolve().parents[1] / "ui" / "templates"
        / "runs.html").read_text(encoding="utf-8")


def test_the_ledger_heading_counts_every_run_recorded():
    assert "{% set n_led = ledger_total | default(ledger | length, true) %}" \
        in PAGE
    assert "{{ n_led }} run{{" in PAGE


def test_sections_carry_no_marks_and_busy_rows_say_why_once(state):
    html = client.get("/runs").text
    for hid in ("st-wr", "st-rs", "st-ra", "st-rp", "st-datasets",
                "st-protected", "st-reclaim-none"):
        assert f'id="tip-{hid}"' not in html, hid
    busy = html.split('id="st-busy"', 1)[1].split("</div>", 1)[0]
    assert busy.count("is active; its workroot cannot be deleted") == 1
    # the running run archives its own date only
    assert 'run_fd in ("", d)' in (Path(ui_storage.__file__)
                                   .read_text(encoding="utf-8"))


def test_archived_runs_read_in_this_computers_time(monkeypatch):
    import re
    import time
    assert ui_storage._local_when("odd") == "odd"
    # the workroot rows' form, in this computer's own zone
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                        ui_storage._local_when("20261025T191800Z"))
    if not hasattr(time, "tzset"):
        return                      # Windows: no zone can be set from here
    monkeypatch.setenv("TZ", "America/Phoenix")
    time.tzset()
    try:
        assert ui_storage._local_when("20261025T191800Z") == "2026-10-25 12:18"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_bulk_controls_say_not_running_and_list_no_statuses():
    assert "not running ({{ clear_workroots.size_h }})" in PAGE
    assert '{{ "the" if clear_workroots.count == 1 else "all" }}' in PAGE
    assert "statuses ok" not in PAGE


def test_empty_states_follow_the_listings():
    assert "{% elif not st_listed %}" in PAGE
    assert '{% if not st_listed %}' in PAGE
    assert '"No runs in the ledger"' in PAGE


def test_a_workroot_delete_leads_with_the_runs_name(state):
    html = client.get("/runs").text
    rid = state["rids"]["ok"]
    row = html.split(f'data-wid="{rid}"', 1)[1].split("</div>", 1)[0]
    assert 'data-what="the run ' in row
    assert (f"Its folder {rid} goes, with the run&#39;s report and "
            "submission files in it.") in row


def test_a_dataset_delete_names_only_what_it_had():
    class D:
        name = "My counts"
    msg, kind, detail = DU.deleted_message(D, 12_500, 1, 0, replays=0)
    assert detail == ("Its 1 run workroot went with it; the runs' ledger rows "
                      "are kept.")
    assert DU.deleted_message(D, 12_500, 0, 0)[2] == ""
    assert DU.deleted_message(D, 1, 0, 0, replays=2)[2] == \
        "Its 2 replays went with it."


def test_a_dataset_delete_that_kept_its_only_workroot_says_so():
    """Review of #88 (S3): the dataset's one run workroot could not be
    deleted and it had no replays: the detail was " The rest stay under
    Run workroots.", a leading space and the rest of nothing."""
    class D:
        name = "My counts"
    msg, kind, detail = DU.deleted_message(D, 2_000, 0, 1, replays=0)
    assert kind == "warn"
    assert msg == "Deleted My counts, but 1 run workroot could not be deleted."
    assert detail == "The run workroot stays under Run workroots."
    assert DU.deleted_message(D, 2_000, 0, 2)[2] == \
        "The 2 run workroots stay under Run workroots."
    # replays went, no workroot did: "the rest" would be of the replays
    assert DU.deleted_message(D, 2_000, 0, 1, replays=2)[2] == (
        "Its 2 replays went with it. The run workroot stays under Run "
        "workroots.")
    # some went: the rest stay, as before
    assert DU.deleted_message(D, 2_000, 2, 1, replays=1)[2] == (
        "Its 1 replay and 2 run workroots went with it; the runs' ledger "
        "rows are kept. The rest stay under Run workroots.")
    for gone, kept, replays in ((0, 1, 0), (0, 3, 0), (0, 1, 1), (1, 1, 0),
                                (0, 0, 0), (2, 0, 3)):
        detail = DU.deleted_message(D, 1, gone, kept, replays=replays)[2]
        assert detail == detail.strip() and "  " not in detail


def test_the_failed_filter_and_find_cover_every_unfinished_run():
    assert ("['failed','error','partial','stopped','interrupted']"
            ".indexOf(st)<0") in PAGE
    assert ("{{ r.run_id[:4] }}-{{ r.run_id[4:6] }}-{{ r.run_id[6:8] }}"
            in PAGE)


def test_a_report_archive_is_held_only_for_the_running_runs_date(state):
    from app.ui import state as ui_state
    ui_state._status["running"] = "running"
    inv = ui_storage._storage_inventory()
    held = {a["id"]: a["busy"] for a in inv["report_archives"]}
    live = [w for w in inv["workroots"] if w.get("busy")]
    assert live and held                          # a live run, an archive
    # the archive here is another date than the live run's: deletable
    assert not any(held.values())


def test_a_groundhog_only_run_holds_no_report_archive(state):
    from pathlib import Path as _P
    from app.core.runs import Ledger, RunSpec
    from app.ui import state as ui_state
    rid = Ledger().open_run(RunSpec(engine="analogue",
                                    forecast_date="2098-01-03"),
                            _P("pending"), {})
    ui_state._status["running"] = f"analogue:{rid}"
    ui_state._status["workroot"] = str(state["root"] / "workroots" / rid)
    # the pipeline archives a run of both models only (its own date)
    assert ui_storage._archiving_date() is None
    inv = ui_storage._storage_inventory()
    assert not any(a["busy"] for a in inv["report_archives"])
