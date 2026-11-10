"""Which report archive a live console run holds on Storage (bug hunt
2026-10-25, ST-08, and the review of its fix in #88).

A live run holds its own date's archive exactly when the pipeline's
archive step (app/ui/pipeline.py, step 7) would write it: a run of both
models that is not research and whose files go out under the hub names.
A vintage run and a modified run exported under the hub names reach
_archive_run, so they hold it; a modified run under the non-hub name, a
research run and a one-model run do not. Another date's archive is never
held (ST-08: before #88 every archive was held during any run).
"""
from pathlib import Path

import pytest

from app.core.runs import Ledger, RunSpec
from app.ui import shared as ui_shared
from app.ui import state as ui_state
from app.ui.routes import storage as ui_storage
# _isolated_status (autouse): the live run each case claims is put back, so
# no later test starts with a run in progress
from test_storage import _isolated_status, client, state     # noqa: F401

# the live run's date; OTHER is the fixture's own report archive
DATE, OTHER = "2098-02-07", "2098-01-03"
MOD = {"knobs": {"oracle.w": 0.25}}
OVERRIDE = {**MOD, "knobs_override": "the registered weight"}

# kind: (engine, spec extra, whether the pipeline would archive it)
KINDS = {
    "shipped": ("all", {}, True),
    "vintage": ("all", {"mode": "vintage"}, True),
    "modified, hub names by override": ("all", OVERRIDE, True),
    "vintage, modified, hub names by override":
        ("all", {**OVERRIDE, "mode": "vintage"}, True),
    "modified, non-hub names": ("all", MOD, False),
    "research (plain filter)": ("all", {"oracle": "none"}, False),
    "Oracle SIHRS only": ("pf", {}, False),
}


def _go_live(state, engine, extra):
    rid = Ledger().open_run(RunSpec(engine=engine, forecast_date=DATE,
                                    extra=dict(extra)),
                            Path("pending"), {})
    wr = state["root"] / "workroots" / rid
    wr.mkdir(parents=True)
    # every console run claims as "all:<id>"; the ledger spec tells kinds
    ui_state._status["running"] = f"all:{rid}"
    ui_state._status["workroot"] = str(wr)


def _delete(day):
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": day, "confirm": day},
                follow_redirects=False)


@pytest.mark.parametrize("kind", list(KINDS))
def test_a_live_run_holds_the_archive_the_pipeline_would_write(state, kind):
    engine, extra, writes = KINDS[kind]
    arch = state["root"] / "archive"
    (arch / DATE / "submission").mkdir(parents=True)
    (arch / DATE / "report.html").write_text("<p>r</p>")
    ui_shared._invalidate_scans()
    _go_live(state, engine, extra)
    assert ui_storage._may_archive() is writes
    assert ui_storage._archiving_date() == (DATE if writes else None)
    busy = {a["id"]: a["busy"]
            for a in ui_storage._storage_inventory()["report_archives"]}
    assert busy == {DATE: writes, OTHER: False}
    # its own date's: refused while it runs, exactly when it may write it
    _delete(DATE)
    assert (arch / DATE).is_dir() is writes
    # another date's is not its to write: deletable (ST-08)
    _delete(OTHER)
    assert not (arch / OTHER).exists()
