"""The swarm-carry machinery: the seed anchor, the pinned initialization
line, and a particle cloud that is saved at the end of a week and continued
from at the start of the next (research/swarm-carry pre-registration).

Hub-free: resolve_state, the materializer, the exp writer, the vintage
path and netgen are faked as test_pf_hardening fakes them, so every test
here reads the pf.conf and cells.json prepare() actually writes.
"""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import reclaim, retro                      # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.runs import derive_seed                    # noqa: E402


class _State:
    def __init__(self):
        self.times = [0, 1, 2]
        self.observed = [4.0, 5.0, 6.0]
        self.n_obs = 3
        self.last_week_offset = 2
        self.i0 = 5e-3          # prepare() records the anchor it used
        self.rhomult = 0.05


def _spec(locations, replicates=2, extra=None):
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": list(locations), "replicates": replicates,
        "particles": 100, "jitter": 0.3,
        "observable_mode": "integrated", "extra": extra})()


def _prep_env(monkeypatch, tmp_path):
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None,
                         **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p

    def fake_netgen(cmd, **kw):
        (Path(kw.get("cwd", ".")) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(sf, "resolve_state", lambda loc, **kw: _State())
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp",
                        lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", fake_netgen)


def _conf(cell):
    return (Path(cell["dir"]) / "pf.conf").read_text()


# ------------------------------------------------------------ the seed anchor

def test_prepare_pins_independent_draws_and_keys_the_seed_on_the_as_of_date(
        monkeypatch, tmp_path):
    """Two pins on the ordinary forecast's conf. initialization = rand:
    PyBNF's default for the key is lh and the engine honours it since
    PyBNF-pf f09eeb9b, so without the line an engine update would have
    turned every initial cloud into a Latin hypercube in silence. And the
    seed keyed on the forecast date, the sealed convention; no state-file
    keys at all, so the conf is what it was."""
    _prep_env(monkeypatch, tmp_path)
    cells = pf.prepare(_spec(["Ohio"]), tmp_path / "wr")
    for c in cells:
        conf = _conf(c)
        assert "initialization = rand\n" in conf
        assert "pf_state_file" not in conf and "pf_continue" not in conf
        want = derive_seed("Ohio", "2098-11-07", c["replicate"])
        assert f"seed = {want}\n" in conf and c["seed"] == want
        assert c["seed_date"] == "2098-11-07"
        assert c["state_file"] is None and c["continued_from"] is None
        assert c["save_state_to"] is None


def test_prepare_keys_the_seed_on_the_season_start_when_asked(monkeypatch,
                                                              tmp_path):
    _prep_env(monkeypatch, tmp_path)
    cells = pf.prepare(_spec(["Ohio"], extra={"seed_anchor": "season_start"}),
                       tmp_path / "wr")
    for c in cells:
        want = derive_seed("Ohio", "2098-08-01", c["replicate"])
        assert f"seed = {want}\n" in _conf(c) and c["seed"] == want
        assert c["seed_date"] == "2098-08-01"
    # the same location seeds differently under the two anchors
    assert cells[0]["seed"] != derive_seed("Ohio", "2098-11-07", 0)


def test_prepare_refuses_an_unknown_seed_anchor(monkeypatch, tmp_path):
    _prep_env(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="seed_anchor"):
        pf.prepare(_spec(["Ohio"], extra={"seed_anchor": "tuesday"}),
                   tmp_path / "wr")


# ----------------------------------------------------- continuing and saving

def test_prepare_continues_from_a_saved_cloud_and_records_a_missing_one(
        monkeypatch, tmp_path):
    """A cloud in the continue_states directory is copied into the cell
    (outside out/, which the runners clear) and the conf continues from
    the copy; the source is never the engine's write target. A cell whose
    cloud is absent starts fresh and SAYS so in cells.json."""
    _prep_env(monkeypatch, tmp_path)
    src_dir = tmp_path / "states" / "2098-10-31"
    src_dir.mkdir(parents=True)
    (src_dir / "Ohio_r0.npz").write_bytes(b"cloud-bytes-r0")
    save_dir = tmp_path / "states" / "2098-11-07"
    cells = pf.prepare(_spec(["Ohio"], extra={"continue_states": str(src_dir),
                                              "save_states": str(save_dir)}),
                       tmp_path / "wr")
    r0, r1 = cells
    assert r0["continued_from"] == str(src_dir / "Ohio_r0.npz")
    assert r0["state_file"] == str(Path(r0["dir"]) / pf.CLOUD_NAME)
    assert Path(r0["state_file"]).read_bytes() == b"cloud-bytes-r0"
    assert "pf_continue = 1\n" in _conf(r0)
    assert f"pf_state_file = {r0['state_file']}\n" in _conf(r0)
    assert r0["save_state_to"] == str(save_dir / "Ohio_r0.npz")

    assert r1["continued_from"] is None            # recorded, not silent
    assert not Path(r1["state_file"]).exists()
    assert "pf_continue = 0\n" in _conf(r1)
    assert f"pf_state_file = {r1['state_file']}\n" in _conf(r1)
    assert r1["save_state_to"] == str(save_dir / "Ohio_r1.npz")
    assert (src_dir / "Ohio_r0.npz").read_bytes() == b"cloud-bytes-r0"


def test_prepare_pins_the_initial_state_to_the_anchor_week(monkeypatch,
                                                           tmp_path):
    """resolve_state derives i0 from the season-to-date count, so the
    model changes every week with no revision at all (measured: Alaska i0
    9.14e-3 then 6.86e-3 on identical rows). anchor_asof takes i0 from one
    week's vintage; the observations stay this week's."""
    import flubnf.sihrs_fit as sf
    import app.core.data as data
    _prep_env(monkeypatch, tmp_path)
    seen = {}

    class S(_State):
        def __init__(self, as_of):
            super().__init__()
            self.i0 = {"2098-09-05": 9e-3, "2098-11-07": 6e-3}[as_of]
            self.rhomult = self.i0 * 10
            if as_of == "2098-11-07":
                self.observed = [4.0, 5.0, 6.0, 7.0]
                self.times, self.n_obs, self.last_week_offset = [0, 1, 2, 3], 4, 3

    monkeypatch.setattr(sf, "resolve_state",
                        lambda loc, **kw: S(kw["as_of"]))
    monkeypatch.setattr(data, "vintage_path",
                        lambda d: seen.setdefault("vintages", []).append(d)
                        or str(tmp_path / f"v{d}.csv"))
    def fake_materialize(s, template, out, suffix, **kw):
        seen.setdefault("i0", []).append(s.i0)
        Path(out).write_text("begin parameters\nend parameters\n")
        return Path(out)

    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    cells = pf.prepare(_spec(["Ohio"], replicates=1,
                             extra={"anchor_asof": "2098-09-05"}),
                       tmp_path / "wr")
    assert seen["i0"] == [9e-3]                    # the anchor week's i0
    assert cells[0]["i0"] == 9e-3
    assert cells[0]["anchor_asof"] == "2098-09-05"
    assert "2098-09-05" in seen["vintages"]        # the anchor's vintage read
    assert cells[0]["n_obs"] == 4                  # this week's observations
    # and without the key the week anchors itself, as it always did
    seen.clear()
    cells = pf.prepare(_spec(["Ohio"], replicates=1), tmp_path / "wr2")
    assert seen["i0"] == [6e-3] and cells[0]["anchor_asof"] == "2098-11-07"


def test_prepare_can_fit_the_initial_infected_fraction(monkeypatch, tmp_path):
    """fit_i0 = [lo, hi] makes i0 the sixth fitted parameter: the model's
    i0 line names i0__FREE, whose default is this week's data-derived
    anchor, and the conf carries a loguniform prior for it."""
    import flubnf.sihrs_fit as sf
    _prep_env(monkeypatch, tmp_path)

    def fake_materialize(s, template, out, suffix, **kw):
        Path(out).write_text("begin parameters\nmult    mult__FREE\n"
                             "i0      %.8e     # initial infected fraction\n"
                             "end parameters\n" % s.i0)
        return Path(out)

    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    cells = pf.prepare(_spec(["Ohio"], replicates=1,
                             extra={"fit_i0": [1e-6, 1e-3]}), tmp_path / "wr")
    c = cells[0]
    model = (Path(c["dir"]) / "m.bngl").read_text()
    assert "i0      i0__FREE" in model
    assert "i0__FREE 5.00000000e-03" in model           # the anchor as default
    assert model.count("i0__FREE") == 2
    assert "loguniform_var = i0__FREE 1e-06 0.001\n" in _conf(c)
    assert c["fit_i0"] == [1e-6, 1e-3] and c["i0"] == 5e-3
    # without the key nothing changes
    cells = pf.prepare(_spec(["Ohio"], replicates=1), tmp_path / "wr2")
    assert "i0__FREE" not in (Path(cells[0]["dir"]) / "m.bngl").read_text()
    assert "i0__FREE" not in _conf(cells[0]) and cells[0]["fit_i0"] is None
    with pytest.raises(ValueError, match="fit_i0"):
        pf.prepare(_spec(["Ohio"], replicates=1, extra={"fit_i0": [0.5, 0.1]}),
                   tmp_path / "wr3")


def _traj_cell(w, key, loc, content, **more):
    d = w / key
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    (runs / "sim_traj_noise.txt").write_text(content)
    return {"key": key, "dir": str(d), "location": loc, "n_obs": 3,
            "particles": 100, "last_observed": 10.0, **more}


_TRAJ = "0 1 2 3 4 5 6\n0 1 2 3 4 5 6\n"


def test_collect_copies_the_ending_cloud_and_records_a_missing_one(tmp_path):
    """collect() runs before the week's tree is pruned, so it is where the
    cloud is carried out. A fitted cell with no cloud file is still pooled
    (its forecast is good) and is recorded in pf_state_missing.json: the
    carry is lost for that cell, never the week."""
    w = tmp_path / "wr"
    w.mkdir()
    dest = tmp_path / "states" / "2098-11-07"
    c0 = _traj_cell(w, "Ohio_r0", "Ohio", _TRAJ,
                    state_file=str(w / "Ohio_r0" / pf.CLOUD_NAME),
                    save_state_to=str(dest / "Ohio_r0.npz"))
    Path(c0["state_file"]).write_bytes(b"ending-cloud")
    c1 = _traj_cell(w, "Ohio_r1", "Ohio", _TRAJ,
                    state_file=str(w / "Ohio_r1" / pf.CLOUD_NAME),
                    save_state_to=str(dest / "Ohio_r1.npz"))
    c2 = _traj_cell(w, "Utah_r0", "Utah", _TRAJ)      # no carry asked
    (w / "cells.json").write_text(json.dumps([c0, c1, c2]))

    out = pf.collect(w)
    assert sorted(out) == ["Ohio", "Utah"]
    assert out["Ohio"]["0"] == [10.0, 10.0, 10.0, 10.0]   # both replicates
    assert (dest / "Ohio_r0.npz").read_bytes() == b"ending-cloud"
    assert not (dest / "Ohio_r1.npz").exists()
    missing = json.loads((w / pf.STATE_MISSING_NAME).read_text())
    assert list(missing) == ["Ohio_r1"] and "no cloud file" in missing["Ohio_r1"]


# ------------------------------------------------- the retro path threads it

SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"


def test_run_week_hands_extra_to_prepare_and_records_it_in_the_manifest(
        tmp_path, monkeypatch):
    seen = {}

    def fake_prepare(spec, wd):
        seen["extra"] = dict(spec.extra)
        wd = Path(wd)
        cells = [{"key": "c0", "dir": str(wd / "c0")}]
        (wd / "cells.json").write_text(json.dumps(cells))
        return cells

    class Runner:
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], "ok")
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {"Ohio": {"0": [1.0]}})
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"1": {0.5: 2.0}}})
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s)
                                                  for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)
    monkeypatch.setattr(reclaim, "prune_week", lambda wd: 0)
    root = tmp_path / SEASON
    extra = {"seed_anchor": "season_start", "save_states": "/x"}
    retro.run_week(root, SEASON, W1, ["Ohio"], width=1, extra=extra)
    assert seen["extra"] == extra
    manifest = json.loads((root / "weeks" / W1 / retro.PREP_NAME).read_text())
    assert manifest["extra"] == extra
    # a week without extra keeps the manifest it always had
    seen.clear()
    retro.run_week(root, SEASON, W2, ["Ohio"], width=1)
    assert seen["extra"] == {}
    assert "extra" not in json.loads(
        (root / "weeks" / W2 / retro.PREP_NAME).read_text())


def test_run_week_takes_the_season_start_from_extra(tmp_path, monkeypatch):
    """The solstice arm: extra["season_start"] moves the model's first
    observed week; without it the archive's August 1 boundary stands."""
    seen = []

    def fake_prepare(spec, wd):
        seen.append(spec.season_start)
        wd = Path(wd)
        cells = [{"key": "c0", "dir": str(wd / "c0")}]
        (wd / "cells.json").write_text(json.dumps(cells))
        return cells

    class Runner:
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], "ok")
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {"Ohio": {"0": [1.0]}})
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"1": {0.5: 2.0}}})
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s)
                                                  for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)
    monkeypatch.setattr(reclaim, "prune_week", lambda wd: 0)
    root = tmp_path / SEASON
    retro.run_week(root, SEASON, W1, ["Ohio"], width=1,
                   extra={"season_start": "2098-06-21"})
    retro.run_week(root, SEASON, W2, ["Ohio"], width=1)
    assert seen == ["2098-06-21", retro.season_bounds(SEASON)[0]]


def test_run_season_asks_week_extra_for_every_week_in_order(tmp_path,
                                                            monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(retro, "_now", lambda: clock["t"])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    got = []

    def fake_week(r, season, asof, locations, replicates, particles, width,
                  **kw):
        clock["t"] += 60.0
        got.append((asof, kw.get("extra")))
        wd = Path(r) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "samples.json").write_text(json.dumps({"asof": asof}))
        return {"asof": asof}

    monkeypatch.setattr(retro, "run_week", fake_week)
    calls = []

    def carry(asof, i, vintages):
        calls.append((asof, i, list(vintages)))
        return {"continue_states": vintages[i - 1] if i else None}

    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio"], width=1, week_extra=carry)
    assert calls == [(W1, 0, [W1, W2]), (W2, 1, [W1, W2])]
    assert got == [(W1, {"continue_states": None}),
                   (W2, {"continue_states": W1})]
    assert retro.read_meta(root)["settings"]["week_extra"] == "carry"
    # without the callable nothing is asked and nothing is recorded
    got.clear()
    root2 = tmp_path / "plain"
    retro.run_season(root2, SEASON, ["Ohio"], width=1)
    assert got == [(W1, None), (W2, None)]
    assert "week_extra" not in retro.read_meta(root2)["settings"]
