"""pf_sampling_interval is written into a cell's pf.conf only when the
installed engine accepts it, read off the engine's own source.

The a827e2f8 upstream tree (the expected 2026-27 engine) lists the key in
pybnf/config.py's pf key set and in pybnf/parse.py's grammar; the engine
before it lists it in neither and REFUSES an unknown key, so a conf that
carried the line unconditionally would fail every cell on a current
install. The key is what lets that tree fit a one-row .exp, the first
fitted week of a season, which it otherwise refuses (pre-registration
addendum A1 (5)). Two fake engine trees, one of each shape, drive the
tests; nothing here reads a real engine.
"""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.engines import pf                          # noqa: E402

KEY = "pf_sampling_interval"


def _tree(root: Path, *, in_parse: bool, in_config: bool,
          config_file: bool = True) -> Path:
    """An engine tree with the file the preflight looks for, a parser key
    list and a config.py pf key set, each with or without the key."""
    (root / "pybnf").mkdir(parents=True)
    (root / "pybnf" / "__init__.py").write_text("")
    (root / "pybnf" / "pf.py").write_text("# the filter\n")
    keys = list(pf.CONF_KEYS_REQUIRED) + ([KEY] if in_parse else [])
    (root / "pybnf" / "parse.py").write_text(
        "numkeys_int = [%s]\n" % ", ".join("'%s'" % k for k in keys))
    if config_file:
        pfset = ["'pf_particles'", "'pf_seed'", "'pf_jitter'",
                 "'pf_forecast_intervals'", "'pf_start_time'", "'pf_bounds'",
                 "'pf_state_file'", "'pf_cumulative_observable'"]
        if in_config:
            pfset.append("'%s'" % KEY)
        (root / "pybnf" / "config.py").write_text(
            "class Configuration:\n    def check_unused_params(self):\n"
            "        alg_params = {\n            'pf': {%s}\n        }\n"
            % ", ".join(pfset))
    return root


@pytest.fixture()
def pr_tree(tmp_path, monkeypatch):
    """The a827e2f8 shape: the key in the grammar and in the pf set."""
    root = _tree(tmp_path / "pr", in_parse=True, in_config=True)
    monkeypatch.setattr(pf, "PYBNF_PF", root)
    return root


@pytest.fixture()
def old_tree(tmp_path, monkeypatch):
    """The engine before the pull request: the key in neither file."""
    root = _tree(tmp_path / "old", in_parse=False, in_config=False)
    monkeypatch.setattr(pf, "PYBNF_PF", root)
    return root


# ---------------------------------------------------------------- detection

def test_the_key_is_read_off_both_engine_files(tmp_path, monkeypatch):
    assert pf.SAMPLING_INTERVAL_KEY == KEY
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "a", in_parse=True, in_config=True))
    assert pf.engine_accepts_pf_key(KEY) is True
    assert pf.sampling_interval_line() == f"{KEY} = 1\n"
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "b", in_parse=False, in_config=False))
    assert pf.engine_accepts_pf_key(KEY) is False
    assert pf.sampling_interval_line() == ""
    # the grammar alone is not acceptance: the pf set decides what the
    # filter reads, and the grammar decides what the parser refuses; both
    # must list it
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "c", in_parse=True, in_config=False))
    assert pf.engine_accepts_pf_key(KEY) is False
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "d", in_parse=False, in_config=True))
    assert pf.engine_accepts_pf_key(KEY) is False
    # a tree with no config.py at all is never assumed to accept it
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "e", in_parse=True, in_config=True,
                                              config_file=False))
    assert pf.engine_accepts_pf_key(KEY) is False
    # and the required keys are still judged by the grammar, as before
    assert pf.engine_current()


def test_the_key_is_never_required(pr_tree):
    """An engine that lacks it is not stale: the console adapts to it."""
    assert KEY not in pf.CONF_KEYS_REQUIRED
    assert pf.engine_missing_keys() == ()


# ------------------------------------------------------------- the conf

class _State:
    def __init__(self):
        self.times = [0, 1, 2]
        self.observed = [4.0, 5.0, 6.0]
        self.n_obs = 3
        self.last_week_offset = 2
        self.i0 = 5e-3
        self.rhomult = 0.05


def _spec():
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": ["Ohio"], "replicates": 1,
        "particles": 100, "jitter": 0.3,
        "observable_mode": "integrated", "extra": None})()


def _prep_env(monkeypatch, tmp_path):
    """Hub-free prepare(): the fakes of test_pf_hardening."""
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None, **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p

    def fake_netgen(cmd, **kw):
        (Path(kw.get("cwd", ".")) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(sf, "resolve_state", lambda loc, **kw: _State())
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp", lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", fake_netgen)


def _conf(tmp_path, monkeypatch, name):
    _prep_env(monkeypatch, tmp_path)
    w = tmp_path / name
    cells = pf.prepare(_spec(), w)
    assert [c["key"] for c in cells] == ["Ohio_r0"]
    return (Path(cells[0]["dir"]) / "pf.conf").read_text(), cells[0]


def test_prepare_writes_the_line_for_the_engine_that_accepts_it(pr_tree, tmp_path, monkeypatch):
    conf, cell = _conf(tmp_path, monkeypatch, "wr")
    assert f"\n{KEY} = 1\n" in conf
    assert conf.count(KEY) == 1
    assert cell[KEY] == 1
    assert json.loads((tmp_path / "wr" / "cells.json").read_text())[0][KEY] == 1


def test_prepare_writes_nothing_for_the_engine_that_refuses_it(old_tree, tmp_path, monkeypatch):
    conf, cell = _conf(tmp_path, monkeypatch, "wr")
    assert KEY not in conf
    assert cell[KEY] is None


def test_the_line_is_the_only_difference_between_the_two_confs(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "pr", in_parse=True, in_config=True))
    with_key, _ = _conf(tmp_path, monkeypatch, "a")
    monkeypatch.setattr(pf, "PYBNF_PF", _tree(tmp_path / "old", in_parse=False, in_config=False))
    without, _ = _conf(tmp_path, monkeypatch, "b")
    a = [l for l in with_key.splitlines() if not l.startswith(KEY)]
    b = without.splitlines()
    # the paths differ by the workroot name only
    norm = lambda lines: [l.replace(str(tmp_path / "a"), "W").replace(str(tmp_path / "b"), "W")  # noqa: E731
                          for l in lines]
    assert norm(a) == norm(b)
    # every key the record was made under is still there, unchanged
    for line in ("pf_bounds = reflect", "pf_start_time = -1",
                 "pf_cumulative_observable = Hobs", "initialization = rand"):
        assert line in without and line in with_key
