"""Suite-wide isolation: no test may touch or depend on the real install.

  * pf.RUNNER_PIDS_FILE -> tmp: a real relaunch sweeps the pids recorded in
    app/state/pf_runners.json, so test pids must never land there.
  * pf.PYBNF_PF -> a stub fork: prepare() refuses fit_type = pf without
    pybnf/pf.py (CI has no fork); preflight tests override PYBNF_PF.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402


@pytest.fixture(autouse=True)
def _runner_registry_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "RUNNER_PIDS_FILE", tmp_path / "pf_runners.json")


@pytest.fixture(scope="session")
def _engine_root(tmp_path_factory):
    """A fork-shaped directory: the one file the engine preflight looks
    for, built once for the session."""
    root = tmp_path_factory.mktemp("fork")
    (root / "pybnf").mkdir()
    (root / "pybnf" / "pf.py").write_text("# stub: presence is the test\n")
    # the key lists the contract check reads: every key the console writes
    (root / "pybnf" / "parse.py").write_text(
        "numkeys_int = [%s]\n" % ", ".join("'%s'" % k for k in pf.CONF_KEYS_REQUIRED))
    return root


@pytest.fixture(autouse=True)
def _engine_in_tmp(_engine_root, monkeypatch):
    monkeypatch.setattr(pf, "PYBNF_PF", _engine_root)


@pytest.fixture(autouse=True)
def _sealed_records_in_tmp(tmp_path, monkeypatch):
    """The production record (app/state/retro_reseal) must never be served by
    accident; RETRO_SEAL tests already point at their own trees."""
    from app.ui import server as srv
    monkeypatch.setattr(srv, "RETRO_RESEAL", tmp_path / "retro_reseal")
