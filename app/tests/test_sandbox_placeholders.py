"""A Sandbox model that keeps the replay placeholders ({{POP}},
{{I0FRAC}}, ...): filled in memory for every reader of model.bngl
(app/core/sandbox_data.py filled_bngl; Check, Save and run, Simulate
data, the diagrams), from the location its data was loaded for, as a
replay fills them for each location and week; its files never rewritten.
A model without placeholders is left exactly as it was. Hub-free and
engine-free: test_sandbox_shipped's tiny hub, and one fake BNG2.pl that
refuses a placeholder as the real one does (strict_bng).
"""
import json
import sys
import types
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

import app.core                                          # noqa: E402
from app.core import data as data_mod                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core import sandbox_check                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from flubnf.sihrs_fit import (materialize_model, pin_from,  # noqa: E402
                              resolve_state)
from flubnf.sihrs_priors import (ATTACK_RATE_RANGE,      # noqa: E402
                                 SEED_DENOMINATOR, gamma_per_week)
from test_contactmap import BIND                         # noqa: E402
from test_problem_codes import _mirrors                  # noqa: E402
from test_sandbox_check import NET                       # noqa: E402
from test_sandbox_shipped import FD, POPS, hub           # noqa: E402,F401

client = TestClient(srv.app)

#: what BNG2.pl says of a placeholder in a model (it cannot read one)
REFUSED = "BioNetGen version 2.9.3\nABORT: Expecting operator argument\n"
#: Check's facts of a model without placeholders, as they were before
FACTS = {"suffix", "free", "priors", "rows", "columns", "cumulative",
         "species", "reactions", "network", "at_start", "machine",
         "machine_tip"}


@pytest.fixture
def strict_bng(sandbox_root, monkeypatch, tmp_path):
    """BNG2.pl present (a stub file) and faked for every reader at once:
    conftest's fake (a run's m.bngl) and the boxes' (Check's and the
    diagrams' cm.bngl) patch the same subprocess.run, so this one answers
    both. It reads cwd / cmd[-1] and records the text in .seen; a text
    holding a placeholder or the word 'broken' is refused as BNG2.pl
    refuses it, writing nothing. Otherwise it writes m.net for m.bngl, or
    the network and the contact map for cm.bngl. It writes no trajectory:
    a test that needs counts patches sandbox_check.expected_counts."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))
    seen = []

    def fake(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = cwd / str(cmd[-1])
        if src.suffix != ".bngl" or not src.is_file():
            return types.SimpleNamespace(stdout="", stderr="", returncode=0)
        text = src.read_text(encoding="utf-8")
        seen.append(text)
        if "{{" in text or "broken" in text:
            return types.SimpleNamespace(stdout=REFUSED, stderr="",
                                         returncode=0)
        if src.name == "m.bngl":
            (cwd / "m.net").write_text("# net\n")
        else:
            (cwd / "cm.net").write_text(NET)
            (cwd / "cm_contactmap.graphml").write_text(BIND)
        return types.SimpleNamespace(stdout="BioNetGen version 2.9.3\n",
                                     stderr="", returncode=0)
    monkeypatch.setattr(sb.subprocess, "run", fake)
    return types.SimpleNamespace(seen=seen, root=sandbox_root)


def _template(name: str = "tpl", loc: str = "Alabama") -> dict:
    sb.from_shipped(name, loc, FD, template=True)
    return sb.read_model(name)


def _snapshot(name: str) -> dict:
    """Every file of a model's folder: its bytes and its mtime."""
    d = sb.MODELS / name
    return {p.relative_to(d).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(d.rglob("*")) if p.is_file()}


def _pin(obs: list, pop: int) -> float:
    """resolve_state's i0 for these counts."""
    return pin_from(obs, pop, float(np.mean(ATTACK_RATE_RANGE)), None,
                    gamma_per_week(), SEED_DENOMINATOR)[1]


def _flash() -> str:
    return ui_state._status.get("flash") or ""


# ------------------------------------------------ models without placeholders

def test_a_model_without_placeholders_is_left_alone(strict_bng, hub):
    """The skeleton, every example and an Oracle start: the text as
    given, the library never imported, Check's report exactly as it was
    (no "replays", no facts["placeholders"]), and a run of the text as
    saved."""
    sb.new_model("skel")
    names = ["skel", "al"] + sb.list_examples()
    for e in sb.list_examples():
        sb.add_example(e)
    sb.from_shipped("al", "Alabama", FD)

    def counts(f, times=None, work=None):
        times = [r[0] for r in sb.read_exp(f["data.exp"])["rows"]]
        return {"times": times, "expected": [9.0] * len(times),
                "column": "Tobs"}
    with pytest.MonkeyPatch.context() as mp:
        # any import of the library raises
        mp.setitem(sys.modules, "app.core.library", None)
        mp.delattr(app.core, "library", raising=False)
        mp.setattr(sandbox_check, "expected_counts", counts)
        for n in names:
            files = sb.read_model(n)
            assert sb.filled_bngl(n, files) == (files["model.bngl"], {}), n
            r = sb.check(files, name=n)
            assert r == sb.check(files), n
            assert set(r) == {"ok", "problems", "warnings", "facts",
                              "codes"}, n
            assert set(r["facts"]) == FACTS, n
        sb.simulate_data("skel")
        for n in names:
            files = sb.read_model(n)
            w = sb.prepare(n)
            assert (w / f"{n}_r0" / "m.bngl").read_text(
                encoding="utf-8") == files["model.bngl"], n
            assert "placeholders" not in json.loads(
                (w / "meta.json").read_text())


# --------------------------------------------------------------- the fill

def test_the_data_fill_is_what_materialize_model_writes(strict_bng, hub,
                                                        tmp_path):
    files = _template()
    text, fill = sb.filled_bngl("tpl", files)
    s = resolve_state("Alabama", truth_csv=hub["vintage"],
                      locations_csv=hub["locations"],
                      season_start="2024-08-01", as_of=FD)
    full = tmp_path / "full.bngl"
    full.write_text(files["model.bngl"], encoding="utf-8", newline="\n")
    want = materialize_model(s, full, tmp_path / "m.bngl", "SIHRS_flu")
    assert text == want.read_text(encoding="utf-8")
    assert fill == {"from": "data", "location": "Alabama",
                    "population": POPS["Alabama"][1], "i0": s.i0}
    assert sb.simulate_suffix(text) == "SIHRS_flu"


def test_the_location_holds_after_an_edit_and_follows_a_load(strict_bng, hub,
                                                             monkeypatch):
    files = _template()
    pop = POPS["Alabama"][1]
    rows = files["data.exp"].splitlines()
    # a row removed by hand: still Alabama, pinned on the rows left
    edited = "\n".join(rows[:3] + rows[4:]) + "\n"
    sb.save_model("tpl", {"data.exp": edited})
    assert sb.read_data_source("tpl") is None          # edited since loaded
    _, fill = sb.filled_bngl("tpl", sb.read_model("tpl"))
    obs = [r[1] for r in sb.read_exp(edited)["rows"]]
    assert fill["location"] == "Alabama" and fill["population"] == pop
    assert fill["i0"] == _pin(obs, pop)
    # a missing week written -1 is left out of the pin
    gap = edited.splitlines()
    gap[1] = gap[1].split()[0] + " -1"
    sb.save_model("tpl", {"data.exp": "\n".join(gap) + "\n"})
    _, fill = sb.filled_bngl("tpl", sb.read_model("tpl"))
    assert fill["i0"] == _pin(obs[1:], pop)
    # another location loaded: its population, from the hub's table
    monkeypatch.setattr(data_mod, "vintage_series", lambda d, loc: {
        "dates": ["2024-09-07", "2024-09-14"], "values": [5.0, 7.0]})
    sb.fill_data("tpl", "New York", "2024-09-07", FD, asof=FD)
    assert "population" not in json.loads(
        (sb.MODELS / "tpl" / sb.SOURCE_FILE).read_text())
    text, fill = sb.filled_bngl("tpl", sb.read_model("tpl"))
    assert fill["location"] == "New York"
    assert fill["population"] == POPS["New York"][1] == 19_571_216
    assert "N       19571216" in text
    assert fill["i0"] == _pin([5.0, 7.0], 19_571_216)


def _no_sidecar(d: Path) -> None:
    (d / sb.SOURCE_FILE).unlink()


def _sidecar(**src):
    def edit(d: Path) -> None:
        (d / sb.SOURCE_FILE).write_text(json.dumps(src))
    return edit


def _nested(d: Path) -> None:
    (d / sb.SOURCE_FILE).write_text("[" * 200000)    # too deep to read


def _exp(text: str):
    def edit(d: Path) -> None:
        (d / "data.exp").write_text(text)
    return edit


def _a0share(d: Path) -> None:
    p = d / "model.bngl"
    p.write_text(p.read_text().replace("{{RHO}}", "{{A0SHARE}}"))


@pytest.mark.parametrize("edit, words", [
    (_a0share, "model.bngl uses {{A0SHARE}}, which the Sandbox does not "
     "fill: it fills {{POP}}, {{I0FRAC}}, {{S0FRAC}}, {{GAMMA}}, {{RHO}}, "
     "{{GAMMAH}} and {{OMEGA}}"),
    (_no_sidecar, "the placeholders in model.bngl are filled for the "
     "location data.exp was loaded for, and none is known: load a "
     "location's counts under Load data"),
    (_nested, "the placeholders in model.bngl are filled for the location"),
    # a dataset's group is not the hub's location of that name
    (_sidecar(location="Alabama", kind="count",
              dataset={"id": "x", "name": "wave"}),
     "no population is known for Alabama, which the placeholders need"),
    (_sidecar(location="Alabama", kind="count", population=True,
              dataset={"id": "x", "name": "wave"}),
     "no population is known for Alabama, which the placeholders need"),
    (_sidecar(location="Adult", kind="rate", population=250000,
              dataset={"id": "x", "name": "wave"}),
     "{{I0FRAC}} is pinned from counts, and data.exp holds rates (wave): "
     "load counts under Load data"),
    (_exp("1 5\n2 7\n"), "data.exp cannot be read, so {{I0FRAC}} cannot be "
     "pinned from it: data.exp must start with a header line"),
    (_exp("# time H_weekly\n0 0\n1 0\n2 -1\n"), "data.exp holds no "
     "admissions yet, so {{I0FRAC}} cannot be pinned from it"),
])
def test_each_refusal_is_in_words_with_its_code(strict_bng, hub, edit, words):
    _template()
    edit(sb.MODELS / "tpl")
    before = _snapshot("tpl")
    for fn in (lambda: sb.filled_bngl("tpl", sb.read_model("tpl")),
               lambda: sb.simulate_data("tpl")):
        with pytest.raises(sb.SandboxError) as e:
            fn()
        assert e.value.code == "PLACEHOLDERS_UNFILLED"
        assert str(e.value).startswith(words), str(e.value)
    assert _snapshot("tpl") == before


def test_the_sample_fill_reads_nothing_and_never_refuses(strict_bng):
    from app.core import library as L
    text = L.shipped_files("sihrs")["model.bngl"] + "# {{FOO}} {{A0SHARE}}\n"
    filled, fill = sb.filled_bngl("nobody", {"model.bngl": text}, sample=True)
    assert fill == {"from": "sample"}
    assert "N       1000000" in filled and "i0      1e-05" in filled
    assert "{{FOO}}" in filled and "{{A0SHARE}}" not in filled
    assert L.tokens(filled) == {"{{FOO}}"}
    assert not sb.MODELS.exists()


# ------------------------------------------------------------------ Check

def test_check_fills_and_never_sends_a_placeholder_to_bng2(strict_bng, hub):
    _template()
    r = client.post("/api/sandbox/models/tpl/check").json()
    assert r["facts"]["placeholders"] == {
        "from": "data", "location": "Alabama",
        "population": POPS["Alabama"][1],
        "i0": sb.filled_bngl("tpl", sb.read_model("tpl"))[1]["i0"]}
    assert r["ok"] and r["facts"]["network"] == "generates"
    assert r["replays"] == {"ready": True, "findings": [], "registered": None}
    assert strict_bng.seen and not [t for t in strict_bng.seen if "{{" in t]
    assert _mirrors(r) == []


def test_check_without_a_location_says_so_and_still_checks_the_network(
        strict_bng, hub, monkeypatch):
    _template()
    (sb.MODELS / "tpl" / sb.SOURCE_FILE).unlink()
    asked = []

    def off(files, times=None, work=None):
        asked.append(files)                    # tenfold off, if it were asked
        return {"times": times, "expected": [1e6] * len(times),
                "column": "Hobs"}
    monkeypatch.setattr(sandbox_check, "expected_counts", off)
    r = client.post("/api/sandbox/models/tpl/check").json()
    assert _mirrors(r)[0] == "PLACEHOLDERS_UNFILLED"
    assert r["problems"][0].startswith("the placeholders in model.bngl are "
                                       "filled for the location")
    assert r["facts"]["network"] == "generates"
    assert r["facts"]["placeholders"] == {"from": "sample"}
    assert r["facts"]["at_start"] == ("not compared: the placeholders hold "
                                      "sample values")
    assert asked == [] and "SCALE_OFF" not in _mirrors(r)
    # Register needs no data: still ready for replays
    assert r["replays"]["ready"] is True
    assert not [t for t in strict_bng.seen if "{{" in t]


def test_check_with_unreadable_data_says_so_once(strict_bng, hub):
    """data.exp that cannot be read is its own problem: the fill takes
    the sample values rather than saying it a second time."""
    _template()
    r = client.post("/api/sandbox/models/tpl/check",
                    data={"data_exp": "1 5\n2 7\n"}).json()
    assert "EXP_UNREADABLE" in _mirrors(r)
    assert "PLACEHOLDERS_UNFILLED" not in _mirrors(r)
    assert r["facts"]["placeholders"] == {"from": "sample"}


def test_a_failed_verdict_never_costs_check_its_report(strict_bng, hub,
                                                       monkeypatch):
    from app.core import library as L
    _template()

    def broken(*a, **k):
        raise RuntimeError("no verdict")
    monkeypatch.setattr(L, "readiness", broken)
    r = client.post("/api/sandbox/models/tpl/check").json()
    assert r["ok"] and r["facts"]["network"] == "generates"
    assert r["facts"]["placeholders"]["location"] == "Alabama"
    assert r["replays"]["ready"] is False
    assert [f["code"] for f in r["replays"]["findings"]] == ["CHECK_FAILED"]
    assert "no verdict" in r["replays"]["findings"][0]["text"]


def test_a_name_in_other_letter_case_is_not_ready(strict_bng, hub):
    """Where folders ignore case, TPL reads tpl's files, but Register
    takes the exact name only: Check says so rather than Ready."""
    from app.core import library as L
    files = _template()
    r = sb.check(files, work=sb.SANDBOX / "check", name="TPL")
    assert r["replays"]["ready"] is False
    first = r["replays"]["findings"][0]
    assert (first["code"], first["text"]) == (
        "NAME_INVALID", "no Sandbox model is named 'TPL' (letter case counts)")
    assert r["replays"]["registered"] is None
    # nor does a version of TPL in the library name tpl's files
    (sb.MODELS / "tpl").rename(sb.MODELS / "TPL")
    assert L.register("TPL")["ref"] == "TPL@1"
    (sb.MODELS / "TPL").rename(sb.MODELS / "tpl")
    r = sb.check(files, work=sb.SANDBOX / "check", name="TPL")
    assert r["replays"]["registered"] is None
    assert sb.check(files, work=sb.SANDBOX / "check",
                    name="tpl")["replays"]["registered"] is None


# ------------------------------------------------- Save and run, Simulate

def test_save_and_run_runs_the_filled_text_and_keeps_the_files(strict_bng,
                                                               hub):
    saved = _template()
    w = sb.prepare("tpl")
    m = (w / "tpl_r0" / "m.bngl").read_text(encoding="utf-8")
    assert "{{" not in m and "N       5157699" in m
    assert sb.simulate_suffix(m) == "SIHRS_flu"
    meta = json.loads((w / "meta.json").read_text())
    assert meta["placeholders"]["location"] == "Alabama"
    assert meta["placeholders"]["population"] == POPS["Alabama"][1]
    assert meta["digests"] == sb.digests(saved)
    assert sb.read_model("tpl") == saved


def test_save_and_run_without_a_location_leaves_no_run_folder(strict_bng, hub,
                                                              monkeypatch):
    _template()
    (sb.MODELS / "tpl" / sb.SOURCE_FILE).unlink()
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("tpl")
    assert e.value.code == "PLACEHOLDERS_UNFILLED"
    assert not sb.RUNS.exists() or not any(sb.RUNS.iterdir())
    ran = []
    monkeypatch.setattr(sb, "run", lambda w, width=1: ran.append(w))
    r = client.post("/sandbox/models/tpl/run", follow_redirects=False)
    assert r.status_code == 303
    assert "Not started: the placeholders in model.bngl" in _flash()
    assert ran == [] and (not sb.RUNS.exists() or not any(sb.RUNS.iterdir()))
    assert ui_state._sandbox_status["claim"] is None


def test_simulate_data_fills_and_keeps_the_location(strict_bng, hub,
                                                   monkeypatch):
    files = _template()
    asked = []

    def counts(f, times=None, work=None):
        asked.append(f["model.bngl"])
        times = [r[0] for r in sb.read_exp(f["data.exp"])["rows"]]
        return {"times": times, "expected": [20.0] * len(times),
                "column": "Hobs"}
    monkeypatch.setattr(sandbox_check, "expected_counts", counts)
    sb.simulate_data("tpl", seed=3)
    assert asked and "{{" not in asked[0] and "N       5157699" in asked[0]
    assert (sb.MODELS / "tpl" / sb.SOURCE_FILE).is_file()
    assert sb.read_data_source("tpl") is None          # not the archive's rows
    now = sb.read_model("tpl")
    assert now["data.exp"] != files["data.exp"]
    assert now["model.bngl"] == files["model.bngl"]
    assert sb.filled_bngl("tpl", now)[1]["location"] == "Alabama"


# --------------------------------------------- the diagrams, the downloads

def test_the_diagrams_draw_a_model_with_placeholders(strict_bng, hub):
    _template()
    for view in ("contactmap", "network"):
        r = client.get(f"/api/sandbox/models/tpl/{view}").json()
        assert "error" not in r, r
    drawn = list(strict_bng.seen)
    # the sample values: a drawing shows no value
    assert len(drawn) == 2
    assert all("1000000" in t and "{{" not in t for t in drawn)
    for view in ("contactmap", "network"):         # cached by the saved text
        assert "error" not in client.get(f"/api/sandbox/models/tpl/{view}").json()
    assert strict_bng.seen == drawn


def test_the_model_zip_keeps_the_placeholders(strict_bng, hub):
    files = _template()
    z = zipfile.ZipFile(BytesIO(sb.model_zip("tpl")))
    assert z.read("tpl/model.bngl").decode("utf-8") == files["model.bngl"]
    assert "{{POP}}" in files["model.bngl"]


def test_a_template_run_takes_no_oracle_step(strict_bng, hub):
    _template()
    w = sb.prepare("tpl")
    sb.mark(w, "ok")
    gate = sb.oracle_gate(w.name)
    assert gate == {"ok": False, "reason": "Only runs of a model started from "
                    "the Oracle SIHRS filter can take the Oracle step."}
    html = client.get(f"/sandbox?model=tpl&run={w.name}").text
    assert 'class="card sboracle"' not in html


def test_the_files_are_never_rewritten(strict_bng, hub):
    files = _template()
    before = _snapshot("tpl")
    sb.filled_bngl("tpl", files)
    assert client.post("/api/sandbox/models/tpl/check").json()["ok"]
    sb.prepare("tpl")
    for view in ("contactmap", "network"):
        client.get(f"/api/sandbox/models/tpl/{view}")
    client.post("/sandbox/models/tpl/register", follow_redirects=False)
    assert "Registered tpl@1 (" in _flash()
    assert _snapshot("tpl") == before
