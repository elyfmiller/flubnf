"""The public engine, the default (app/core/engines/lwf.py): the switch
and the install's record of it, the translation of a prepared cell into lanl/PyBNF's job_type = lwf,
the runners, reading Results/LWF back, and the build record.

The fixture (fixtures/lwf_alaska) is one production cell, Alaska as of
2025-01-11: the private engine's pf.conf, model and data as pf.prepare
wrote them (lab paths replaced by {CELL} and {BNG}), the public files the
lwf-production equivalence study ran (FluBNF-local, 2026-10-03), and the
first 100 particles of the public engine's own-stream outputs for it. A real
public venv is needed only by the last test, which is skipped without one.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.core.engines import lwf
from app.core.engines import pf as pf_engine

FIX = Path(__file__).resolve().parent / "fixtures" / "lwf_alaska"
BNG = "/opt/bng/BNG2.pl"


@pytest.fixture
def public(monkeypatch, tmp_path):
    """FLUBNF_ENGINE=public with a venv Python that does not exist."""
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(tmp_path / "nopy" / "python"))
    lwf._CHECK.clear()
    lwf._BUILD.clear()
    yield
    lwf._CHECK.clear()
    lwf._BUILD.clear()


def _cell(tmp_path: Path, name: str = "Alaska_r0") -> Path:
    """The fixture's private cell, as pf.prepare leaves it."""
    d = tmp_path / name
    d.mkdir(parents=True)
    for f in ("m.bngl", "Alaska_flu.exp"):
        shutil.copy(FIX / "private" / f, d / f)
    conf = (FIX / "private" / "pf.conf").read_text(encoding="utf-8")
    (d / "pf.conf").write_text(conf.replace("{CELL}", str(d)).replace("{BNG}", BNG),
                               encoding="utf-8")
    return d


def _record(d: Path, **kw) -> dict:
    rows = [ln.split() for ln in (d / "Alaska_flu.exp").read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    rec = {"key": d.name, "dir": str(d), "location": "Alaska", "replicate": 0,
           "n_obs": len(rows), "last_week_offset": int(rows[-1][0]),
           "weeks_dropped": 0, "last_observed": float(rows[-1][1]),
           "particles": 10000}
    rec.update(kw)
    return rec


def _with_results(d: Path) -> Path:
    r = d.joinpath(*lwf.RESULTS)
    r.mkdir(parents=True)
    for f in (FIX / "results").iterdir():
        shutil.copy(f, r / f.name)
    return r


# --- the switch -------------------------------------------------------------

@pytest.fixture
def default_engine(monkeypatch, tmp_path):
    """FLUBNF_ENGINE unset, and an install folder with no record yet:
    settings reads the folder's .flubnf.env afresh. Yields the folder."""
    from flubnf import settings
    root = tmp_path / "install"
    root.mkdir()
    monkeypatch.delenv("FLUBNF_ENGINE", raising=False)
    monkeypatch.setattr(settings, "INSTALL_ROOT", root)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    settings.forget_record()
    yield root
    settings.forget_record()


@pytest.mark.parametrize("value,want", [
    (None, "public"), ("", "public"), ("private", "private"),
    ("public", "public"), (" Public ", "public"), ("lwf", "public"),
    ("PRIVATE", "private"), ('"private"', "private")])
def test_engine_choice(default_engine, monkeypatch, value, want):
    from flubnf import settings
    if value is not None:
        monkeypatch.setenv("FLUBNF_ENGINE", value)
    assert settings.engine_choice() == want
    assert settings.engine_public() is (want == "public")
    assert settings.engine_value_unknown(value) is (value == "lwf")


def test_a_private_record_is_read_when_the_variable_is_unset(default_engine):
    from flubnf import settings
    (default_engine / ".flubnf.env").write_text(
        'export FLUBNF_PY_ENGINE="/x/bin/python"\n'
        "export FLUBNF_ENGINE=private\n", encoding="utf-8")
    assert settings.engine_choice() == "private"
    assert settings.engine_source() == (".flubnf.env", "private")


def test_the_environment_beats_the_record(default_engine, monkeypatch):
    from flubnf import settings
    (default_engine / ".flubnf.env").write_text(
        "export FLUBNF_ENGINE=private\n", encoding="utf-8")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert settings.engine_choice() == "public"
    assert settings.engine_source() == ("environment", "public")
    monkeypatch.setenv("FLUBNF_ENGINE", " ")        # blank: the record
    assert settings.engine_choice() == "private"


def test_no_record_and_an_unknown_record_mean_public(default_engine):
    from flubnf import settings
    assert settings.engine_choice() == "public"
    assert settings.engine_source() == ("default", None)
    settings.forget_record()
    (default_engine / ".flubnf.env").write_text(
        "export FLUBNF_ENGINE=lwf\n", encoding="utf-8")
    assert settings.engine_choice() == "public"
    assert settings.engine_source() == (".flubnf.env", "lwf")
    assert settings.engine_value_unknown("lwf")


def test_the_record_is_read_once_per_process(default_engine):
    """A running console never changes engine because someone edited the
    record; recorded_engine itself reads the file every time."""
    from flubnf import settings
    envf = default_engine / ".flubnf.env"
    envf.write_text("export FLUBNF_ENGINE=private\n", encoding="utf-8")
    assert settings.engine_choice() == "private"
    envf.write_text("export FLUBNF_ENGINE=public\n", encoding="utf-8")
    assert settings.engine_choice() == "private"
    assert settings.recorded_engine(default_engine) == "public"
    settings.forget_record()
    assert settings.engine_choice() == "public"


def test_the_windows_record(default_engine, monkeypatch):
    from flubnf import settings
    monkeypatch.setattr(settings, "_windows", lambda: True)
    (default_engine / ".flubnf.env").write_text(
        "export FLUBNF_ENGINE=public\n", encoding="utf-8")   # not cmd's
    (default_engine / ".flubnf.env.cmd").write_bytes(
        b'@echo off\r\nset "FLUBNF_HUB=C:\\hub"\r\n'
        b'set "FLUBNF_ENGINE=private"\r\n')
    assert settings.engine_choice() == "private"
    assert settings.engine_source() == (".flubnf.env.cmd", "private")


def test_the_private_engine_installed_is_two_files(monkeypatch, tmp_path):
    from flubnf import settings
    py, fork = tmp_path / "py", tmp_path / "fork"
    monkeypatch.setattr(settings, "PY_ENGINE", py)
    monkeypatch.setattr(settings, "PYBNF", fork)
    assert settings.private_engine_installed() is False
    py.write_text("")
    assert settings.private_engine_installed() is False
    (fork / "pybnf").mkdir(parents=True)
    (fork / "pybnf" / "pf.py").write_text("")
    assert settings.private_engine_installed() is True


def test_public_python_paths(monkeypatch, tmp_path):
    from flubnf import settings
    monkeypatch.delenv("FLUBNF_PY_ENGINE_PUBLIC", raising=False)
    posix = settings._public_python_candidates(windows=False)
    assert posix == ("~/.venvs/flubnf-public/bin/python",)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    win = settings._public_python_candidates(windows=True)
    assert win == (str(tmp_path / "Local" / "FluBNF" / "venv-public"
                       / "Scripts" / "python.exe"),)
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(tmp_path / "py"))
    assert settings.py_engine_public() == tmp_path / "py"


def test_settings_check_names_the_public_venv(public):
    from flubnf import settings
    names = [m[0] for m in settings.check(verbose=False)]
    assert "FLUBNF_PY_ENGINE_PUBLIC" in names
    assert "FLUBNF_PYBNF" not in names and "FLUBNF_PY_ENGINE" not in names


def test_engine_checks_hand_over(public, monkeypatch, tmp_path):
    from flubnf import settings
    assert pf_engine.engine_available() is False
    # the private engine installed here: the message names the fallback
    fork = tmp_path / "fork"
    (fork / "pybnf").mkdir(parents=True)
    (fork / "pybnf" / "pf.py").write_text("")
    private_py = tmp_path / "private" / "python"
    private_py.parent.mkdir()
    private_py.write_text("")
    monkeypatch.setattr(settings, "PY_ENGINE", private_py)
    monkeypatch.setattr(settings, "PYBNF", fork)
    msg = pf_engine.engine_missing_message("darwin")
    assert "public engine (the default) is not installed" in msg
    assert "setup_engine.sh --public" in msg
    assert "setup_engine.sh --private" in msg
    assert "FLUBNF_ENGINE=private" in msg
    assert "or leave it unset" not in msg
    win = pf_engine.engine_missing_message("win32")
    assert "FluBNF.bat" in win and "setup.ps1 -Engine private" in win
    # not installed: no step that would fail, the doc instead
    monkeypatch.setattr(settings, "PYBNF", tmp_path / "no-fork")
    msg = pf_engine.engine_missing_message("darwin")
    assert "public engine (the default) is not installed" in msg
    assert "setup_engine.sh --public" in msg
    assert msg.endswith("The private engine, the fallback, is not installed "
                        "here (docs/ENGINE.md).")
    assert "--private" not in msg
    assert pf_engine.engine_current() is False
    assert "does not match engine-requirements.txt" in pf_engine.engine_stale_message()
    cmd = pf_engine.runner_cmd("r.py")
    assert cmd[0] == str(lwf.python()) and "-I" in cmd and cmd[-1] == "r.py"


def test_private_is_untouched(monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    cmd = pf_engine.runner_cmd("r.py")
    assert cmd[0] == str(pf_engine.PY310) and "-I" not in cmd


# --- translation --------------------------------------------------------------

def test_translation_matches_the_equivalence_study(tmp_path):
    d = _cell(tmp_path)
    conf = lwf.translate_cell(_record(d))
    w = d / lwf.LWF_DIR
    assert conf == w / lwf.CONF_NAME
    # byte for byte the files the study ran (144 of 144 cells reproduced
    # the private engine's draws when fed its random inputs)
    assert (w / "m.bngl").read_bytes() == (FIX / "public" / "m.bngl").read_bytes()
    assert (w / "Alaska_flu.exp").read_bytes() == (FIX / "public" / "Alaska_flu.exp").read_bytes()
    want = (FIX / "public" / "lwf.conf").read_text().replace("{BNG}", BNG)
    assert conf.read_text() == want
    rec = json.loads((w / "translate.json").read_text())
    assert rec["random_seed"] == 1736257424 and rec["gaps"] == []


def test_conf_names_no_folder(tmp_path):
    d = _cell(tmp_path / "José m.contreras")
    text = lwf.translate_cell(_record(d)).read_text()
    assert str(d) not in text
    assert "model: m.bngl" in text and "output_dir = out" in text
    assert "data: Alaska_flu.exp" in text


def test_rows_gaps_and_leading_weeks():
    vals, rec = lwf.lwf_rows("# time H_weekly\n2 3\n3 4.5\n5 0\n")
    assert vals == ["nan", "nan", "3.000000", "4.500000", "nan", "0.000000"]
    assert rec == {"gaps": [0, 1, 4], "missing": [], "first_row": 2,
                   "n_rows": 3, "last_week": 5}


def test_a_negative_count_is_a_missing_week():
    """The Sandbox's mark for a missing week; the private engine leaves the
    row unscored and lwf refuses a count below 0."""
    vals, rec = lwf.lwf_rows("0 1\n1 -1\n2 3\n")
    assert vals == ["1.000000", "nan", "3.000000"] and rec["missing"] == [1]


@pytest.mark.parametrize("text", ["0 1\n7 2\n14 3\n", "0 1\n2 2\n4 3\n"])
def test_data_in_other_time_units_is_refused(text):
    with pytest.raises(lwf.Untranslatable, match="time units apart"):
        lwf.lwf_rows(text)


def test_windows_model_line_splits_at_the_spaced_colon():
    m, d = lwf._model_and_data([("model", "C:/Users/ELY~1/w/A_r0/m.bngl : "
                                          "C:/Users/ELY~1/w/A_r0/A_flu.exp")])
    # as_posix: on Windows str() gives the path back with backslashes
    assert m.as_posix().endswith("A_r0/m.bngl") and str(m).startswith("C:")
    assert d.as_posix().endswith("A_r0/A_flu.exp") and str(d).startswith("C:")
    with pytest.raises(lwf.Untranslatable, match="does not pair"):
        lwf._model_and_data([("model", "m.bngl")])


@pytest.mark.parametrize("model", [
    "begin parameters\nk 1\nend parameters\ngenerate_network({overwrite=>1})\n"
    "simulate({suffix=>\"x\",\n  t_end=>10})\n# kept\n",
    "begin model\nbegin parameters\nk 1\nend parameters\nend model\n"
    "Begin Actions # run\nsimulate({})\nEND ACTIONS\nsimulate_ode({t_end=>4})\n"])
def test_every_action_is_removed(model):
    out = lwf.strip_actions(model)
    assert "simulate" not in out and "generate_network" not in out
    assert "begin parameters\nk 1\nend parameters\n" in out


@pytest.mark.parametrize("text,why", [
    ("0 1 2\n", "columns"), ("0 1\n0 2\n", "twice"), ("0.5 1\n", "whole"),
    ("1 1\n0 2\n", "order"), ("# only a header\n", "no rows")])
def test_rows_refused(text, why):
    with pytest.raises(lwf.Untranslatable, match=why):
        lwf.lwf_rows(text)


@pytest.mark.parametrize("platform", ["darwin", "win32"])
@pytest.mark.parametrize("key", sorted(lwf._NO_COUNTERPART))
def test_every_refusal_fits_its_line_and_names_the_switch(tmp_path, monkeypatch,
                                                        platform, key):
    """What the cell's failure line carries (FAIL: public engine: ...,
    cut at 200 characters) is the whole refusal, its step included."""
    from app.core.engine_build import switch_step
    from flubnf import settings
    monkeypatch.setattr(settings, "_windows", lambda: platform == "win32")
    d = _cell(tmp_path)
    with open(d / "pf.conf", "a", encoding="utf-8") as f:
        f.write(f"{key} = 1\n")
    with pytest.raises(lwf.Untranslatable) as e:
        lwf.translate_cell(_record(d))
    line = f"FAIL: public engine: {e.value}"
    assert len(line) <= 200, (len(line), line)
    step = switch_step("private", platform, short=True)
    assert str(e.value).endswith(f"the private engine runs it ({step})")


@pytest.mark.parametrize("line,why", [
    ("pf_shrink = 1", "no counterpart"),
    ("pf_forecast_jitter = 0.1", "no counterpart"),
    ("pf_binom_neff_cap = 300", "two-strain"),
    ("pf_mean_scale_column = completeness", "reporting model"),
    ("pf_state_file = /x/cloud.npz", "carried particle cloud"),
    ("some_new_key = 1", "has no counterpart")])
def test_research_keys_refused(tmp_path, line, why):
    d = _cell(tmp_path)
    (d / "pf.conf").write_text((d / "pf.conf").read_text() + line + "\n")
    with pytest.raises(lwf.Untranslatable, match=why):
        lwf.translate_cell(_record(d))


@pytest.mark.parametrize("old,new,why", [
    ("objfunc = neg_bin_dynamic", "objfunc = chi_sq", "objfunc"),
    ("pf_start_time = -1", "pf_start_time = 0", "pf_start_time"),
    ("pf_cumulative_observable = Hobs\n", "", "cumulative observable"),
    ("loguniform_var = r__FREE 0.1 40.0\n", "", "r__FREE")])
def test_settings_refused(tmp_path, old, new, why):
    d = _cell(tmp_path)
    text = (d / "pf.conf").read_text()
    assert old in text
    (d / "pf.conf").write_text(text.replace(old, new))
    with pytest.raises(lwf.Untranslatable, match=why):
        lwf.translate_cell(_record(d))


def test_sandbox_conf_relative_and_no_bng_line(tmp_path):
    """The Sandbox writes bare names and no bng_command (BNGPATH)."""
    d = _cell(tmp_path)
    text = (d / "pf.conf").read_text().replace(str(d) + "/", "")
    text = "\n".join(ln for ln in text.splitlines() if not ln.startswith("bng_command"))
    (d / "pf.conf").write_text(text + "\npf_sampling_interval = 1\n")
    conf = lwf.translate_cell(_record(d)).read_text()
    assert "bng_command" not in conf and "pf_sampling_interval" not in conf
    assert (d / "lwf" / "Alaska_flu.exp").is_file()


def test_sampling_interval_other_than_one_is_refused(tmp_path):
    d = _cell(tmp_path)
    (d / "pf.conf").write_text((d / "pf.conf").read_text() + "pf_sampling_interval = 7\n")
    with pytest.raises(lwf.Untranslatable, match="pf_sampling_interval"):
        lwf.translate_cell(_record(d))


@pytest.mark.parametrize("brk", ["\x0c", "\x0b", "\x1d", "\x85", " ", "\r"])
def test_a_line_break_bng2_does_not_see_is_refused(tmp_path, brk):
    # a comment that ends here for PyBNF would leave setOption a statement
    d = _cell(tmp_path)
    m = d / "m.bngl"
    text = m.read_text(encoding="utf-8").replace(
        "begin model", f"begin model\n# note{brk}setOption(\"x\",1)", 1)
    m.write_bytes(text.encode("utf-8"))
    with pytest.raises(lwf.Untranslatable, match=r"m\.bngl line \d+: .*line break"):
        lwf.translate_cell(_record(d))
    assert not (d / "lwf" / "m.bngl").exists()


def test_a_model_reading_bngl_time_is_refused(tmp_path):
    """time() reads the simulator's clock, which lwf starts a week after the
    private engine does (data week t at lwf time t + 1): refused, not run a
    week out of phase. The templates' counter species is unaffected."""
    d = _cell(tmp_path)
    m = d / "m.bngl"
    m.write_text(m.read_text(encoding="utf-8").replace(
        "cos(2*pi*(t-phi1)/52)", "cos(2*pi*(time()-phi1)/52)", 1),
        encoding="utf-8")
    with pytest.raises(lwf.Untranslatable,
                       match=r"m\.bngl line \d+: time\(\) would run a week "
                             r"out of phase.*counter species"):
        lwf.translate_cell(_record(d))
    assert not (d / "lwf" / "m.bngl").exists()


def test_time_in_a_comment_or_another_name_is_not_refused(tmp_path):
    d = _cell(tmp_path)
    m = d / "m.bngl"
    m.write_text(m.read_text(encoding="utf-8").replace(
        "begin functions",
        "begin functions\n# the clock is t, not time()\nmytime() = t", 1),
        encoding="utf-8")
    lwf.translate_cell(_record(d))
    assert "mytime() = t" in (d / "lwf" / "m.bngl").read_text()


def test_the_model_checks_are_one_function_others_can_call(tmp_path):
    """model_refusal is what translate_cell raises, for the Sandbox's Check
    to say before a run; a model the public engine runs gives None."""
    d = _cell(tmp_path)
    text = (d / "m.bngl").read_text(encoding="utf-8")
    assert lwf.model_refusal(text, "m.bngl") is None
    clock = text.replace("(t-phi1)", "(time()-phi1)", 1)
    line = clock[:clock.index("time()")].count("\n") + 1
    assert lwf.model_refusal(clock, "m.bngl").startswith(
        f"m.bngl line {line}: time() would run a week out of phase")
    assert "line break" in lwf.model_refusal(text.replace("\n", "\f", 1))


def test_crlf_is_not_a_lone_break(tmp_path):
    d = _cell(tmp_path)
    m = d / "m.bngl"
    lf = m.read_bytes()
    m.write_bytes(lf.replace(b"\n", b"\r\n"))
    lwf.translate_cell(_record(d))
    assert b"\r" not in (d / "lwf" / "m.bngl").read_bytes()


def test_normal_priors_pass_through(tmp_path):
    d = _cell(tmp_path)
    text = (d / "pf.conf").read_text().replace(
        "uniform_var = eps1__FREE 0.0 1.0", "lognormal_var = eps1__FREE -1.6 0.5")
    (d / "pf.conf").write_text(text)
    conf = lwf.translate_cell(_record(d)).read_text()
    assert "lognormal_var = eps1__FREE -1.6 0.5" in conf


def test_resample_threshold_maps(tmp_path):
    d = _cell(tmp_path)
    (d / "pf.conf").write_text((d / "pf.conf").read_text() + "pf_resample_threshold = 0.3\n")
    conf = lwf.translate_cell(_record(d)).read_text()
    assert "lwf_resample_threshold = 0.3" in conf
    assert conf.count("lwf_resample_threshold") == 1


def test_translate_cells_fails_cells_in_words(tmp_path):
    good, bad = _cell(tmp_path, "A_r0"), _cell(tmp_path, "B_r0")
    (bad / "pf.conf").write_text((bad / "pf.conf").read_text() + "pf_shrink = 1\n")
    failed = lwf.translate_cells([_record(good), _record(bad)])
    assert list(failed) == ["B_r0"]
    assert failed["B_r0"].startswith("FAIL: public engine: pf_shrink")


# --- reading Results/LWF ---------------------------------------------------

def _independent(rec: dict, k: int = 0) -> dict:
    """The anchoring, computed here from the raw tables (the study's
    score.py arithmetic), not through lwf or pf."""
    def table(p):
        rows = [ln for ln in Path(p).read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
        return np.array([[float(x) for x in r.split()] for r in rows[1:]])
    pc = table(FIX / "results" / "predicted_counts.txt")
    fc = table(FIX / "results" / "forecasts.txt")
    origin = pc[:, -1]
    med = float(np.median(origin))
    last = rec["last_observed"]
    scale = last / med
    return {"origin": (origin * scale).tolist(),
            **{str(h - 1): (fc[:, k + h - 1] * scale).tolist() for h in (1, 2, 3, 4)}}


def test_collect_reads_and_anchors_a_public_cell(tmp_path):
    d = _cell(tmp_path)
    _with_results(d)
    rec = _record(d)
    (tmp_path / "cells.json").write_text(json.dumps([rec]))
    by = pf_engine.collect(tmp_path)
    want = _independent(rec)
    assert set(by["Alaska"]) == set(want)
    for key, vals in want.items():
        assert np.allclose(by["Alaska"][key], vals, rtol=0, atol=1e-9), key
        assert len(by["Alaska"][key]) == 100


def test_collect_records_a_misaligned_cell(tmp_path):
    d = _cell(tmp_path)
    _with_results(d)
    rec = _record(d, last_week_offset=30)       # the tables end at week 23
    (tmp_path / "cells.json").write_text(json.dumps([rec]))
    assert pf_engine.collect(tmp_path) == {}
    st = json.loads((tmp_path / "pf_status.json").read_text())
    assert st[rec["key"]].startswith("FAIL: predicted_counts.txt ends at t = 24")


def test_collect_records_a_torn_table(tmp_path):
    d = _cell(tmp_path)
    r = _with_results(d)
    (r / "forecasts.txt").write_text("# note\n25\t26\t27\t28\n")
    (tmp_path / "cells.json").write_text(json.dumps([_record(d)]))
    assert pf_engine.collect(tmp_path) == {}
    st = json.loads((tmp_path / "pf_status.json").read_text())
    assert "forecasts.txt is torn" in st["Alaska_r0"]


def test_trimmed_weeks_shift_the_horizons(tmp_path):
    """weeks_dropped = 1: the conf asked for 5 intervals; the as-of week is
    the first forecast column and the horizons the next four."""
    d = tmp_path / "X_r0"
    r = d.joinpath(*lwf.RESULTS)
    r.mkdir(parents=True)
    (r / "parameters.txt").write_text("k__FREE\n1\n2\n")
    (r / "predicted_counts.txt").write_text("1\t2\t3\n1\t2\t4\n1\t2\t2\n")
    (r / "forecasts.txt").write_text("4\t5\t6\t7\t8\n10\t20\t30\t40\t50\n"
                                     "11\t21\t31\t41\t51\n")
    rec = {"key": "X_r0", "dir": str(d), "location": "X", "n_obs": 3,
           "last_week_offset": 2, "weeks_dropped": 1, "last_observed": 6.0}
    origin, as_of, hs = lwf.cell_blocks(rec)
    assert origin.tolist() == [4, 2] and as_of.tolist() == [10, 11]
    assert [h.tolist() for h in hs] == [[20, 21], [30, 31], [40, 41], [50, 51]]
    (tmp_path / "cells.json").write_text(json.dumps([rec]))
    by = pf_engine.collect(tmp_path)
    scale = 6.0 / 3.0                           # last observed / median origin
    assert by["X"]["origin"] == [20.0, 22.0]
    assert by["X"]["3"] == [50 * scale, 51 * scale]


def test_collect_reads_each_cell_by_what_it_holds(tmp_path):
    """A week resumed under the other engine: both cells are pooled."""
    d = _cell(tmp_path)
    _with_results(d)
    p = tmp_path / "P_r0" / "out" / "Results" / "PF" / "Runs"
    p.mkdir(parents=True)
    np.savetxt(p / "x_traj_noise_0.txt", np.array([[1, 2, 3, 4, 5, 6, 7],
                                                    [1, 2, 3, 4, 5, 6, 7]]))
    priv = {"key": "P_r0", "dir": str(tmp_path / "P_r0"), "location": "Alaska",
            "n_obs": 3, "last_week_offset": 2, "weeks_dropped": 0,
            "last_observed": 3.0}
    (tmp_path / "cells.json").write_text(json.dumps([_record(d), priv]))
    by = pf_engine.collect(tmp_path)
    assert len(by["Alaska"]["0"]) == 102
    assert by["Alaska"]["0"][-1] == 4.0


# --- runners --------------------------------------------------------------------

def test_runner_texts_compile():
    a = lwf.runner_text(lwf.RUNNER, pf_engine.RUNNER_COMMON, cells_json="c",
                        out_json="o", halt_path="h")
    b = lwf.runner_text(lwf.RETRO_RUNNER, pf_engine.RUNNER_COMMON,
                        cells_json="c", halt_path="h", done_dir="d")
    for src in (a, b):
        compile(src, "runner", "exec")
        assert "sys.path.insert" not in src       # nothing shadows the venv
        assert "_dies_with_runner(proc)" in src   # Windows: no orphan PyBNF
        assert "_run_lwf(c)" in src


def test_execute_on_public_runs_and_reports_in_words(public, monkeypatch, tmp_path):
    """The real runner, in a Python without pybnf: every cell fails with
    the engine's own last line, and a cell that cannot be translated is
    failed before anything runs."""
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    good, bad = _cell(tmp_path, "A_r0"), _cell(tmp_path, "B_r0")
    (bad / "pf.conf").write_text((bad / "pf.conf").read_text() + "pf_continue = 0\n")
    (tmp_path / "cells.json").write_text(json.dumps([_record(good), _record(bad)]))
    st = pf_engine.execute(tmp_path, width=1)
    assert st["B_r0"].startswith("FAIL: public engine: pf_continue")
    assert st["A_r0"].startswith("FAIL: the public engine stopped (exit code 1)")
    assert "pybnf" in st["A_r0"]
    assert (good / "lwf" / "run.log").is_file()
    assert "_run_lwf" in (tmp_path / "pf_runner_0.py").read_text()


def test_retro_launch_on_public(public, monkeypatch, tmp_path):
    from app.core import retro
    seen = []

    class _P:
        pid = 0

        def poll(self):
            return 0

    def fake_popen(cmd, **kw):
        seen.append(cmd)
        return _P()

    monkeypatch.setattr(retro.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(pf_engine, "record_runner_pids", lambda procs, path=None: None)
    good, bad = _cell(tmp_path, "A_r0"), _cell(tmp_path, "B_r0")
    (bad / "pf.conf").write_text((bad / "pf.conf").read_text() + "pf_shrink = 1\n")
    procs = retro._launch_runners(tmp_path, [[_record(good)], [_record(bad)]],
                                  tmp_path / "HALT")
    assert len(procs) == 1
    assert retro.cells_failed(tmp_path)["B_r0"].startswith("FAIL: public engine: pf_shrink")
    assert "_run_lwf" in (tmp_path / "runner_0.py").read_text()
    assert "-I" in seen[0]
    assert (good / "lwf" / "lwf.conf").is_file()


# --- the build -------------------------------------------------------------------

def _build(**kw):
    b = {"branch": "lanl/PyBNF", "commit": lwf.PUBLIC_ENGINE_COMMIT[:8],
         "dirty": False, "source": "wheel", "path": "/v/bin/python",
         "engine": "public", "full_commit": lwf.PUBLIC_ENGINE_COMMIT,
         "wheel_sha256": "ab" * 32, "lock_wheel": True, "bngsim": "0.15.1",
         "bngsim_build": "458bf7d72354"}
    b.update(kw)
    return b


def test_public_build_label_and_record():
    from app.core import engine_build as eb
    b = _build()
    assert eb.is_production(b)
    assert eb.label(b) == "8410f794 (lanl/PyBNF, bngsim 0.15.1)"
    assert eb.warning(b) == ""
    rec = eb.record(b)
    assert rec["full_commit"] == lwf.PUBLIC_ENGINE_COMMIT
    assert rec["bngsim_build"] == "458bf7d72354" and "path" not in rec
    prior = {"branch": "feature/particle-filter", "commit": "2fdadee0",
             "dirty": False, "source": "git"}
    assert "this machine's engine is 8410f794" in eb.change(prior, b)
    assert eb.change(rec, b) is None


def test_public_build_not_the_lock():
    from app.core import engine_build as eb
    b = _build(lock_wheel=False)
    assert not eb.is_production(b)
    assert "not the lock's wheel" in eb.warning(b)
    assert "setup_engine.sh --public" in eb.fix(b, "darwin")
    g = _build(source="git", lock_wheel=None)
    assert eb.is_production(g)          # a git install of the pinned commit
    assert not eb.is_production(_build(source="git", full_commit="0" * 40, commit="00000000"))


def test_engine_build_dispatches(public, monkeypatch):
    from app.core import engine_build as eb
    monkeypatch.setattr(lwf, "public_build", lambda: _build())
    assert eb.engine_build()["engine"] == "public"


def test_public_build_without_pybnf(public, monkeypatch):
    """A Python with no pybnf: the build is unknown and says why."""
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    from app.core import engine_build as eb
    b = lwf.public_build()
    assert b["source"] == "unknown" and "pybnf" in b["error"]
    assert "could not be read" in eb.warning(b)


def _probe_returns(monkeypatch, rc: int, out: str = ""):
    """The venv probes' subprocess.run answers rc; the kwargs are kept."""
    seen = []

    def run(cmd, **kw):
        seen.append(kw)
        return subprocess.CompletedProcess(cmd, rc, out, "")
    monkeypatch.setattr(lwf.subprocess, "run", run)
    return seen


def test_a_lock_check_stopped_by_a_signal_is_said_and_never_cached(
        public, monkeypatch):
    """A probe killed by a signal (a terminal's Ctrl-C reaching it) is no
    answer about the venv: it is said as such and asked again next time,
    not kept for CHECK_TTL_S as a stale engine."""
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    seen = _probe_returns(monkeypatch, -2, "Traceback (most recent call last):")
    assert lwf.lock_check() == (
        False, "the check was stopped by signal 2; run it again")
    assert not lwf._CHECK
    _probe_returns(monkeypatch, 0, "pybnf matches the lock")
    assert lwf.lock_check() == (True, "pybnf matches the lock")
    assert lwf._CHECK                           # an answer is kept
    if sys.platform != "win32":                 # its own session: no Ctrl-C
        assert seen[0].get("start_new_session") is True


def test_a_build_probe_stopped_by_a_signal_is_never_cached(public, monkeypatch):
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    seen = _probe_returns(monkeypatch, -2)
    b = lwf.public_build()
    assert b["source"] == "unknown" and "signal 2" in b["error"]
    assert not lwf._BUILD
    if sys.platform != "win32":
        assert seen[0].get("start_new_session") is True


# --- the Sandbox and the run page -------------------------------------------------

def test_sandbox_results_read_a_public_run(tmp_path):
    from app.core.sandbox_results import results
    wr = tmp_path / "20261030-000000_m"
    d = _cell(wr, "m_r0")
    _with_results(d)
    times = list(range(24))
    observed = [float(ln.split()[1]) for ln in (d / "Alaska_flu.exp").read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
    (wr / "meta.json").write_text(json.dumps({
        "model": "m", "status": "ok", "particles": 100, "time": times,
        "observed": observed, "n_obs": 24}))
    res = results(wr)
    assert [p["name"] for p in res["params"]][0] == "Reff__FREE"
    assert res["sample"] == 100
    assert res["ess"][0]["t"] == 0.0 and len(res["ess"]) == 24
    assert res["traj"]["columns"] == 28 and res["traj"]["n_obs"] == 24
    assert res["health"] is not None


def test_sandbox_run_without_forecast_weeks(tmp_path):
    """lwf_forecast_intervals = 0 writes no forecasts.txt: still a public
    run, read with no forecast columns."""
    d = _cell(tmp_path)
    r = _with_results(d)
    (r / "forecasts.txt").unlink()
    assert lwf.has_outputs({"dir": str(d)})
    tr = lwf.trajectory({"dir": str(d)}, list(range(24)))
    assert tr.shape == (100, 24)


def test_readiness_gate_on_the_public_engine(public, monkeypatch, tmp_path):
    """A machine with only the public engine is ready (the private venv
    and fork are not looked for)."""
    from app.ui.pipeline import _pf_engine_state
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    assert _pf_engine_state() == "ready"
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(tmp_path / "none"))
    assert _pf_engine_state() == "absent"


def test_cost_model_follows_the_engine(public, monkeypatch):
    cell = {"n_obs": 20, "particles": 10000}
    pub = pf_engine.cell_seconds(cell)
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    assert pub == pytest.approx(pf_engine.cell_seconds(cell) * pf_engine.PUBLIC_COST_RATIO)


def test_a_week_is_never_finished_on_the_other_engine(public, monkeypatch, tmp_path):
    from app.core import retro
    from app.core.retro_settings import EngineBuildMismatch
    retro._week_engine(tmp_path, "private")
    retro.mark_cell_done(tmp_path, "A_r0", "ok")
    assert "engine" not in retro.cells_done(tmp_path)
    with pytest.raises(EngineBuildMismatch, match="began on the private engine"):
        retro._week_engine(tmp_path, "public")
    retro._week_engine(tmp_path, "private")          # the same engine goes on


def test_a_season_from_before_build_records_stays_private(public, monkeypatch):
    from app.core.retro_settings import engine_build_change
    legacy = {"locations": ["Alaska"]}               # no engine_build key
    assert "before engine builds were recorded" in engine_build_change(
        legacy, "pf", _build())
    assert engine_build_change(legacy, "pf", {"commit": "2fdadee0",
                                               "branch": "feature/particle-filter"}) is None


def test_load_failure_names_the_public_venv(public):
    from app.core import sandbox
    said = sandbox._with_load_remedy("FAIL: ModuleNotFoundError: No module named 'pybnf'")
    # the remedy is the platform's own: FluBNF.bat on Windows
    step = "FluBNF.bat" if sys.platform == "win32" else "setup_engine.sh --public"
    assert str(lwf.python()) in said and step in said


def test_harvest_params_reads_a_public_cell(tmp_path):
    from app.ui.pipeline import _harvest_params
    d = _cell(tmp_path)
    _with_results(d)
    (tmp_path / "cells.json").write_text(json.dumps([_record(d)]))
    got = _harvest_params(tmp_path)["Alaska"]
    assert set(got) == {"Reff", "eps1", "phi1", "mult", "r"}


# --- a real run, when this machine has the public engine ---------------------------

def _real_python():
    p = os.environ.get("FLUBNF_TEST_PUBLIC_PYTHON", "")
    return p if p and Path(p).is_file() else None


@pytest.mark.skipif(_real_python() is None or shutil.which("perl") is None,
                    reason="set FLUBNF_TEST_PUBLIC_PYTHON to a public engine "
                           "venv's Python (and have Perl and BNG2.pl)")
def test_real_public_run_reproduces_the_fixture(public, monkeypatch, tmp_path):
    from flubnf.settings import BNG
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", _real_python())
    d = _cell(tmp_path)
    (d / "pf.conf").write_text((d / "pf.conf").read_text().replace(BNG_PLACEHOLDER, str(BNG)))
    (tmp_path / "cells.json").write_text(json.dumps([_record(d)]))
    st = pf_engine.execute(tmp_path, width=1)
    assert st == {"Alaska_r0": "ok"}, st
    got = d.joinpath(*lwf.RESULTS, "forecasts.txt").read_text().splitlines()
    want = (FIX / "results" / "forecasts.txt").read_text().splitlines()
    assert got[:len(want)] == want


BNG_PLACEHOLDER = BNG
