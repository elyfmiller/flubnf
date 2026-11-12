"""prepare() runs BNG2.pl once per location (app/core/engines/pf.py).

Replicate 0 of each location runs BNG2.pl's network check. A later
replicate holds the same model and data, byte for byte, so it gets copies
of the files BNG2.pl added to replicate 0's folder: the bytes BNG2.pl
would write again, since its output depends on the model alone. A
replicate whose files differ, a BNG2.pl that changes an input or writes a
folder, runs BNG2.pl as before.

The hub and the cases are test_prepare_golden.py's (which pins today's
cells and passes unchanged). BNG2.pl is a stub that writes four files from
the model's bytes, as the real one writes m.net, m_<suffix>.net, .cdat and
.gdat, and counts its calls. The reference is prepare with the copy turned
off: BNG2.pl in every cell, as before.
"""
import hashlib
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402
from app.core.runs import RunSpec                        # noqa: E402
from app.tests.test_prepare_golden import (              # noqa: E402
    ASOF, CASES, LOCATIONS, SEASON_START, _env, _extra, _paths, normalize,
    prepare_case)


def _bng(mp, calls: list, fail_for=(), changes_input=False,
         makes_folder=False):
    """BNG2.pl, stubbed after the golden's _env: each call is counted by
    its cell folder's name; it writes m.net, m_<suffix>.net, .cdat and
    .gdat from the model's sha256, except in `fail_for`, where it writes
    nothing and says why on stderr. Optionally it also rewrites the .exp
    or makes a folder, as no BNG2.pl does today."""
    real = pf.subprocess.run

    def run(cmd, *a, **kw):
        if not (cmd and cmd[0] == "perl"):
            return real(cmd, *a, **kw)
        cwd = Path(kw["cwd"])
        calls.append(cwd.name)
        if cwd.name in fail_for:
            return types.SimpleNamespace(
                stdout="BioNetGen version 2.9.3\n",
                stderr="ABORT: the stub refuses this model\n", returncode=1)
        h = hashlib.sha256((cwd / "m.bngl").read_bytes()).hexdigest()
        sfx = next(cwd.glob("*.exp")).stem
        (cwd / "m.net").write_text(f"# network of {h}\n", encoding="utf-8")
        (cwd / f"m_{sfx}.net").write_text(f"# {sfx} network of {h}\n",
                                         encoding="utf-8")
        (cwd / f"m_{sfx}.cdat").write_text(f"0 {h[:8]}\n", encoding="utf-8")
        (cwd / f"m_{sfx}.gdat").write_text(f"0 {h[8:16]}\n", encoding="utf-8")
        if changes_input:
            exp = next(cwd.glob("*.exp"))
            exp.write_text(exp.read_text(encoding="utf-8") + "# touched\n",
                           encoding="utf-8")
        if makes_folder:
            (cwd / "scratch").mkdir()
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    mp.setattr(pf.subprocess, "run", run)


def _tree(root: Path, env: dict) -> dict:
    """Every file under root as {relative path: normalized text}."""
    paths = _paths(root, env)
    return {p.relative_to(root).as_posix():
            normalize(p.read_bytes().decode("utf-8"), paths)
            for p in sorted(root.rglob("*")) if p.is_file()}


def _spec3(env: dict, extra=None) -> RunSpec:
    """The golden's base run with three replicates."""
    return RunSpec(engine="retro", forecast_date=ASOF,
                   locations=list(LOCATIONS), season_start=SEASON_START,
                   replicates=3, particles=100,
                   extra=_extra("base", env) if extra is None else extra)


def test_each_location_runs_bng2pl_once_and_every_replicate_holds_its_files(
        monkeypatch, tmp_path):
    """2 locations x 3 replicates: 2 BNG2.pl runs; replicates 1 and 2
    hold replicate 0's names and bytes, and nothing else differs but
    pf.conf (paths and seed) and cells.json."""
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    root = (tmp_path / "wr").resolve()
    cells = pf.prepare(_spec3(env), root)
    assert len(cells) == 6
    assert calls == ["Vermont_r0", "New_York_r0"]
    for loc in ("Vermont", "New_York"):
        r0 = root / f"{loc}_r0"
        want = {p.name: p.read_bytes() for p in r0.iterdir()
                if p.name != "pf.conf"}
        assert {"m.net", f"m_{loc}_flu.net", f"m_{loc}_flu.cdat",
                f"m_{loc}_flu.gdat", "m.bngl", f"{loc}_flu.exp"} == set(want)
        for rep in (1, 2):
            d = root / f"{loc}_r{rep}"
            got = {p.name: p.read_bytes() for p in d.iterdir()
                   if p.name != "pf.conf"}
            assert got == want, (loc, rep)


@pytest.mark.parametrize("case", list(CASES))
def test_every_cell_holds_what_bng2pl_in_every_cell_wrote(case, monkeypatch,
                                                          tmp_path):
    """Every golden case, against prepare with the copy turned off (BNG2.pl
    in every cell, as before): the same files, byte for byte, in every
    cell, and the same cells.json, failures and notes."""
    env = _env(monkeypatch, tmp_path)
    calls_new, calls_old = [], []
    _bng(monkeypatch, calls_new)
    new = (tmp_path / "new").resolve()
    new.mkdir()
    cells_new = prepare_case(case, env, monkeypatch, new)

    _bng(monkeypatch, calls_old)
    monkeypatch.setattr(pf, "_netgen_added", lambda d, before: None)
    old = (tmp_path / "old").resolve()
    old.mkdir()
    cells_old = prepare_case(case, env, monkeypatch, old)

    assert len(calls_old) == len(cells_old) == 4
    assert len(calls_new) == 2                  # one per location
    assert _tree(new, env) == _tree(old, env)
    assert (normalize(json.dumps(cells_new), _paths(new, env))
            == normalize(json.dumps(cells_old), _paths(old, env)))


def test_a_location_whose_replicate_0_fails_is_recorded_alone(monkeypatch,
                                                              tmp_path):
    """BNG2.pl refuses New York's model: New York is recorded with the
    netgen failure and no cell, Vermont keeps all three, and BNG2.pl is
    not asked again for New York's other replicates."""
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls, fail_for=("New_York_r0",))
    root = (tmp_path / "wr").resolve()
    cells = pf.prepare(_spec3(env), root)
    assert [c["key"] for c in cells] == ["Vermont_r0", "Vermont_r1",
                                         "Vermont_r2"]
    assert calls == ["Vermont_r0", "New_York_r0"]
    failures = pf.read_prepare_failures(root)
    assert set(failures) == {"New_York"}
    assert failures["New_York"].startswith(
        "FAIL: prepare: netgen failed for New York: ")
    assert "ABORT: the stub refuses this model" in failures["New_York"]


def test_a_replicate_whose_model_differs_runs_bng2pl(monkeypatch, tmp_path):
    """Replicate 1's model is not replicate 0's: BNG2.pl runs for it, and
    for replicate 2 (which matches replicate 0) it does not."""
    import flubnf.sihrs_fit as sf
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    same = sf.materialize_model

    def materialize(s, template, out_path, suffix, extra_tokens=None, **kw):
        p = same(s, template, out_path, suffix, extra_tokens=extra_tokens,
                 **kw)
        if Path(out_path).parent.name == "Vermont_r1":
            p.write_text(p.read_text(encoding="utf-8") + "# differs\n",
                         encoding="utf-8", newline="\n")
        return p
    monkeypatch.setattr(sf, "materialize_model", materialize)
    root = (tmp_path / "wr").resolve()
    pf.prepare(_spec3(env), root)
    assert calls == ["Vermont_r0", "Vermont_r1", "New_York_r0"]
    r0, r1, r2 = (root / f"Vermont_r{i}" for i in range(3))
    assert (r1 / "m.net").read_bytes() != (r0 / "m.net").read_bytes()
    assert (r2 / "m.net").read_bytes() == (r0 / "m.net").read_bytes()


@pytest.mark.parametrize("how", ["changes_input", "makes_folder"])
def test_a_bng2pl_that_changes_an_input_or_writes_a_folder_runs_in_every_cell(
        how, monkeypatch, tmp_path):
    """What BNG2.pl added cannot be copied safely when it also changed a
    file it was given, or wrote a folder: every replicate runs it."""
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls, **{how: True})
    cells = pf.prepare(_spec3(env), (tmp_path / "wr").resolve())
    assert len(cells) == 6
    assert sorted(calls) == sorted(c["key"] for c in cells)
