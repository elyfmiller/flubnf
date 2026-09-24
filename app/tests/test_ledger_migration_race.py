"""The ledger's column migration survives two concurrent constructions.

Two Ledgers on the default path (a route and the season worker) can both
pass the PRAGMA check; the loser's ALTER then hits the winner's column, and
that OperationalError must not kill its construction. The interleaving is
reproduced deterministically.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                         # noqa: E402
from app.core.runs import Ledger, RunSpec                # noqa: E402

MIGRATED = ("finished_utc", "elapsed_s")


class _RacingConn:
    """A real connection, except that right after the migration's PRAGMA
    check answers, a second connection applies the whole migration."""

    def __init__(self, real, path):
        self._real = real
        self._path = path
        self._raced = False

    def execute(self, sql, *a):
        cur = self._real.execute(sql, *a)
        if sql.startswith("PRAGMA table_info") and not self._raced:
            self._raced = True
            stale = cur.fetchall()
            winner = sqlite3.connect(self._path)
            for col in MIGRATED:
                winner.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
            winner.commit()
            winner.close()
            return stale
        return cur

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_the_losing_constructor_survives_the_migration_race(tmp_path,
                                                            monkeypatch):
    real_connect = sqlite3.connect
    monkeypatch.setattr(
        runs_mod.sqlite3, "connect",
        lambda path, *a, **k: _RacingConn(real_connect(path, *a, **k), path))

    led = Ledger(tmp_path / "ledger.sqlite")     # must not raise

    cols = [r[1] for r in led._db.execute("PRAGMA table_info(runs)")]
    for col in MIGRATED:
        assert cols.count(col) == 1, cols
    # and the raced ledger is a working ledger: the migrated columns take
    # a full open/close round trip
    rid = led.open_run(RunSpec(engine="analogue", forecast_date="2098-01-03"),
                       tmp_path, {})
    led.close_run(rid, "ok", {})
    row = led._db.execute(
        "SELECT finished_utc, elapsed_s FROM runs WHERE run_id=?",
        (rid,)).fetchone()
    assert row[0] is not None and row[1] >= 0


def test_sequential_reconstruction_stays_idempotent(tmp_path):
    """The ordinary path: a second Ledger over an already-migrated file
    changes nothing and loses nothing."""
    p = tmp_path / "ledger.sqlite"
    Ledger(p)
    led = Ledger(p)
    cols = [r[1] for r in led._db.execute("PRAGMA table_info(runs)")]
    for col in MIGRATED:
        assert cols.count(col) == 1, cols
