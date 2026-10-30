"""A run that names its model (spec.extra["model"], app/core/engines/pf.py
_named_model): a shipped name prepares exactly the cells its variant
does; a library version (app/core/library.py) prepares its own verified
text, read once, with FluBNF's actions, data and filter settings, and its
cumulative output and priors written again; everything else is refused
before any cell is written.

The hub, the fakes and the cases are test_prepare_golden.py's; library
versions are written by hand (test_library.py's _by_hand) under the
sandbox_root fixture's sandbox. BNG2.pl is faked and records each model
it was handed.
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import library as L                        # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402
from app.tests.test_library import _by_hand, suffixed    # noqa: E402
from app.tests.test_prepare_golden import (              # noqa: E402
    CASES, HUB_LOCS, _env, _extra, _paths, cell_texts, normalize,
    prepare_case)
from flubnf.sihrs_fit import (GAMMAH_PER_WEEK, OMEGA_PER_WEEK,  # noqa: E402
                              RHO_IHR)
from flubnf.sihrs_priors import S0_DEFAULT, gamma_per_week     # noqa: E402

REPO = Path(__file__).resolve().parents[2]
#: the shipped name each variant is
SHIPPED_NAME = {None: "sihrs", "2strain": "sihrs-2strain",
                "natg": "sihrs-natg"}
#: the four prior kinds the engines read
PRIOR_KINDS = ("uniform_var", "loguniform_var", "normal_var", "lognormal_var")


@pytest.fixture
def env(sandbox_root, monkeypatch, tmp_path):
    """test_prepare_golden's hub and fakes, the library in tmp_path."""
    return _env(monkeypatch, tmp_path)


def _stored(files: dict) -> dict:
    """The files as register stores them."""
    return {f: L.replay_text(f, t) for f, t in files.items()}


def _ctl() -> dict:
    """ctl@1: the shipped SIHRS, stored as a library version."""
    files = _stored(L.shipped_files("sihrs"))
    _by_hand("ctl", files)
    return files


def _prepared(case: str, env: dict, mp, root: Path, extra=None) -> dict:
    """A golden case prepared into `root`, with `extra` in place of its
    own: its cells, each cell's normalized texts and the three records
    prepare writes (normalized; None when not written)."""
    root.mkdir(parents=True)
    root = root.resolve()
    cells = prepare_case(case, env, mp, root, extra)
    paths = _paths(root, env)
    out = {"cells": cells, "texts": cell_texts(root, cells, env)}
    for name in ("cells.json", pf.PREPARE_FAILURES_NAME,
                 pf.ANCHOR_NOTES_NAME):
        p = root / name
        out[name] = (normalize(p.read_text(encoding="utf-8"), paths)
                     if p.is_file() else None)
    return out


def _records(got: dict) -> tuple:
    return (got["cells.json"], got[pf.PREPARE_FAILURES_NAME],
            got[pf.ANCHOR_NOTES_NAME])


def _filled(stored: str, cell: dict) -> str:
    """What a library cell's m.bngl must be: the stored text up to end
    model, materialize_model's seven placeholders written in its own
    formats, then FluBNF's actions with the cell's suffix."""
    kept = stored[:L.END_MODEL_RE.search(stored).end()]
    pop = {n: p for _f, _a, n, p in HUB_LOCS}[cell["location"]]
    for tok, val in {"{{POP}}": str(pop), "{{S0FRAC}}": f"{S0_DEFAULT:g}",
                     "{{I0FRAC}}": f"{cell['i0']:.8e}",
                     "{{GAMMA}}": f"{gamma_per_week():.6f}",
                     "{{RHO}}": f"{RHO_IHR:g}",
                     "{{GAMMAH}}": f"{GAMMAH_PER_WEEK:g}",
                     "{{OMEGA}}": f"{OMEGA_PER_WEEK:g}"}.items():
        kept = kept.replace(tok, val)
    sfx = cell["key"].rsplit("_r", 1)[0] + "_flu"
    return (kept + "\n\n" + L.REPLAY_ACTIONS.replace('"SIHRS_flu"', f'"{sfx}"')
            + "\n")


def _keys(conf: str) -> list:
    return [ln.split("=", 1)[0].strip() for ln in conf.splitlines()
            if "=" in ln]


# ------------------------------------------------------------ shipped names


@pytest.mark.parametrize("case", list(CASES))
def test_a_shipped_name_prepares_the_same_cells(case, env, monkeypatch,
                                                tmp_path):
    extra = _extra(case, env)
    named = {k: v for k, v in extra.items() if k != "variant"}
    named["model"] = SHIPPED_NAME[extra.get("variant")]
    by_variant = _prepared(case, env, monkeypatch, tmp_path / "v", extra)
    by_name = _prepared(case, env, monkeypatch, tmp_path / "n", named)
    assert by_name["texts"] == by_variant["texts"]
    assert _records(by_name) == _records(by_variant)


def test_the_shipped_path_never_reads_the_library(env, monkeypatch,
                                                  tmp_path):
    def gone(*a, **k):
        raise AssertionError("the shipped path read the library")
    for name in ("resolve", "replay_conf", "tokens"):
        monkeypatch.setattr(L, name, gone)
    for case in ("base", "natg"):
        cells = _prepared(case, env, monkeypatch, tmp_path / case)["cells"]
        assert len(cells) == 4


# ----------------------------------------------------------- library models


@pytest.mark.parametrize("case", [
    c for c, v in CASES.items()
    if not set(v["extra"]) & {*pf.LIBRARY_REFUSED, "variant"}])
def test_a_library_copy_of_sihrs_prepares_the_shipped_cell(
        case, env, monkeypatch, tmp_path):
    """The library path's own correctness: the shipped SIHRS stored as a
    version prepares the shipped cell but for the actions' comment, which
    the replay normal form drops, in every golden case a library model
    takes."""
    _ctl()
    knobs = _extra(case, env)
    shipped = _prepared(case, env, monkeypatch, tmp_path / "s", knobs)
    copy = _prepared(case, env, monkeypatch, tmp_path / "c",
                     {**knobs, "model": "ctl@1"})
    assert _records(copy) == _records(shipped)
    assert list(copy["texts"]) == list(shipped["texts"])
    for key, files in shipped["texts"].items():
        mine = copy["texts"][key]
        assert {n: t for n, t in mine.items() if n != "m.bngl"} == {
            n: t for n, t in files.items() if n != "m.bngl"}, key
        gone = [ln for ln in files["m.bngl"].split("\n")
                if ln not in mine["m.bngl"].split("\n")]
        assert gone == ["# inert for the particle filter (one-week windows); "
                        "a ceiling for adaptive MCMC"], key
        assert mine["m.bngl"] == files["m.bngl"].replace(gone[0] + "\n", "")


def _own() -> dict:
    """own@1: SIHRS with a fitted k__FREE in a cumulative output of its
    own, Hcum2, its prior second in the file."""
    files = L.shipped_files("sihrs")
    files["model.bngl"] = (
        files["model.bngl"]
        .replace("r__FREE 8.0\n", "r__FREE 8.0\nk__FREE 0.5\n")
        .replace("end functions", "Hcum2() = k__FREE*mult*H_Cum\n"
                 "end functions"))
    lines = files["priors.conf"].replace("= Hobs", "= Hcum2").splitlines()
    lines.insert(1, "uniform_var = k__FREE 0.10 9E-1")
    files["priors.conf"] = "\n".join(lines) + "\n"
    files = _stored(files)
    _by_hand("own", files)
    return files


def test_a_library_model_runs_its_own_text(env, monkeypatch, tmp_path):
    files = _own()
    shipped = _prepared("base", env, monkeypatch, tmp_path / "s")
    got = _prepared("base", env, monkeypatch, tmp_path / "o",
                    {"model": "own@1"})
    seen = dict(env["netgen"][-4:])
    assert len(got["cells"]) == 4 and set(seen) == set(got["texts"])
    for c in got["cells"]:
        texts = got["texts"][c["key"]]
        conf = texts["pf.conf"].splitlines()
        assert conf[9] == "pf_cumulative_observable = Hcum2"
        priors = [ln for ln in conf if ln.split(" = ")[0] in PRIOR_KINDS]
        assert priors == ["uniform_var = Reff__FREE 0.6 2.5",
                          "uniform_var = k__FREE 0.1 0.9",
                          "uniform_var = eps1__FREE 0.0 1.0",
                          "uniform_var = phi1__FREE 0.0 52.0",
                          "loguniform_var = mult__FREE 0.002 1.0",
                          "loguniform_var = r__FREE 0.1 40.0"]
        ship = shipped["texts"][c["key"]]["pf.conf"]
        assert ([k for k in _keys(texts["pf.conf"]) if k not in PRIOR_KINDS]
                == [k for k in _keys(ship) if k not in PRIOR_KINDS])
        assert "pf_binom_neff_cap" not in texts["pf.conf"]
        assert "i0__FREE" not in texts["pf.conf"] + texts["m.bngl"]
        want = _filled(files["model.bngl"], c)
        assert texts["m.bngl"] == want
        assert want.count("begin parameters\nReff__FREE 1.20\n") == 1
        assert seen[c["key"]] == want            # what BNG2.pl was handed
        assert c["variant"] == "1strain"


def _kinds() -> dict:
    """kinds@1: SIHRS with a normal_var and a lognormal_var prior, r__FREE's
    the second."""
    files = L.shipped_files("sihrs")
    files["priors.conf"] = (
        files["priors.conf"]
        .replace("uniform_var = eps1__FREE 0.0 1.0",
                 "normal_var = eps1__FREE 0.15 0.05")
        .replace("loguniform_var = r__FREE 0.1 40.0",
                 "lognormal_var = r__FREE 0.9 0.2"))
    files = _stored(files)
    _by_hand("kinds", files)
    return files


@pytest.mark.parametrize("ref, make", [("ctl@1", _ctl), ("own@1", _own),
                                       ("kinds@1", _kinds)],
                         ids=["ctl", "own", "kinds"])
def test_a_library_cell_is_what_the_public_engine_reads(ref, make, env,
                                                        monkeypatch,
                                                        tmp_path):
    """The public engine (app/core/engines/lwf.py, on engine-public) runs
    each cell from its files as prepare wrote them; a library cell keeps
    to what it reads, its own cumulative output and priors included."""
    make()
    cum, priors = L.replay_conf(L.resolve(ref)["files"])
    shipped = _prepared("base", env, monkeypatch, tmp_path / "s")
    got = _prepared("base", env, monkeypatch, tmp_path / "c",
                    {"model": ref})
    for key, texts in got["texts"].items():
        conf = texts["pf.conf"]
        # the lines checked below are the model's own, written again
        assert f"\npf_cumulative_observable = {cum}\n" in conf
        assert priors in conf
        model = [ln for ln in conf.splitlines() if ln.startswith("model =")]
        assert len(model) == 1 and re.fullmatch(r"model = \S+ : \S+",
                                                model[0]), model
        exp = [n for n in texts if n.endswith(".exp")]
        assert len(exp) == 1
        rows = texts[exp[0]].splitlines()
        assert rows[0] == "# time H_weekly"
        times = [int(r.split()[0]) for r in rows[1:]]
        assert all(len(r.split()) == 2 for r in rows[1:])
        assert times == sorted(set(times)) and times
        keys = _keys(conf)
        assert re.search(r"(?m)^pf_cumulative_observable = \S+$", conf)
        assert re.search(r"(?m)^\w+_var = r__FREE ", conf)
        # no key but the shipped cell's and the four prior kinds: no
        # pf_* key of its own, no var or logvar prior
        ship = _keys(shipped["texts"][key]["pf.conf"])
        assert set(keys) <= set(ship) | set(PRIOR_KINDS), key
        assert ({k for k in keys if k.startswith("pf_")}
                <= {k for k in ship if k.startswith("pf_")}), key


def test_the_version_is_read_once_and_never_again(env, monkeypatch,
                                                  tmp_path):
    files = _ctl()
    real, calls = L.resolve, []

    def counting(ref):
        r = real(ref)
        calls.append(ref)
        if r["folder"] is not None:     # rewritten as soon as it was read
            (r["folder"] / "model.bngl").write_text(
                "begin model\nend model\n# rewritten\n", encoding="utf-8")
            p = r["folder"] / "priors.conf"
            p.write_text(p.read_text(encoding="utf-8").replace(
                "r__FREE 0.1 40.0", "r__FREE 0.2 30.0"), encoding="utf-8")
        return r
    monkeypatch.setattr(L, "resolve", counting)
    got = _prepared("base", env, monkeypatch, tmp_path / "c",
                    {"model": "ctl@1"})
    assert calls == ["ctl@1"] and len(got["cells"]) == 4
    for c in got["cells"]:
        texts = got["texts"][c["key"]]
        assert texts["m.bngl"] == _filled(files["model.bngl"], c)
        assert "loguniform_var = r__FREE 0.1 40.0\n" in texts["pf.conf"]


# ---------------------------------------------------------------- refusals


def _refusals(env) -> list:
    """(spec.extra, what is raised, words it says) for each refusal."""
    lib = {"model": "ctl@1"}
    return [
        ({"model": "sihrs", "variant": "natg"}, ValueError,
         "both name the model; give the model only"),
        ({"model": "Sihrs"}, "MODEL_REF", "small letters"),
        ({"model": "beta"}, "MODEL_REF", "names no version"),
        ({"model": "x@0"}, "MODEL_REF", "not a model reference"),
        ({"model": "ctl@2"}, "MODEL_NOT_FOUND", "its versions are 1"),
        ({"model": "edited@1"}, "MODEL_CHANGED", "priors.conf"),
        ({"model": "rule@1"}, "MODEL_CHANGED", "model.bngl (OUTSIDE_MODEL)"),
        ({"model": "future@1"}, "FORMAT_UNKNOWN", "format_version 2"),
        ({"model": "sihrs-2strain", "dataset": env["dataset"]}, ValueError,
         "cannot run on a custom dataset"),
        ({"model": "sihrs-natg", "dataset": env["dataset"]}, ValueError,
         "cannot run on a custom dataset"),
        ({**lib, "fit_i0": [1e-6, 1e-2], "iota": 0.25}, ValueError,
         "fit_i0, iota: these change the shipped template"),
        ({**lib, "prior_ranges": {"r__FREE": [0.1, 200]}}, ValueError,
         "prior_ranges: these change"),
        ({**lib, "neff_cap": 150}, ValueError, "neff_cap: these change"),
        ({"variant": "1strain"}, ValueError, "not '1strain'"),
        ({"variant": "3strain"}, ValueError,
         "variant must be 2strain or natg"),
    ]


def test_refusals(env, monkeypatch, tmp_path):
    stored = _ctl()
    _by_hand("edited", stored)
    p = L.root() / "edited" / "1" / "priors.conf"
    p.write_bytes(p.read_bytes().replace(b"0.6 2.5", b"0.6 2.6"))
    _by_hand("rule", dict(stored, **{"model.bngl": stored["model.bngl"]
                                     .replace("begin model\n", "begin model"
                                              "\nversion(\"2\")\n")}))
    _by_hand("future", stored)
    m = L.root() / "future" / "1" / "model.json"
    m.write_text(m.read_text().replace('"format_version": 1',
                                       '"format_version": 2'))
    for i, (extra, raised, says) in enumerate(_refusals(env)):
        root = tmp_path / f"r{i}"
        case = "dataset" if "dataset" in extra else "base"
        with pytest.raises(ValueError) as e:
            prepare_case(case, env, monkeypatch, root, extra)
        if isinstance(raised, str):
            assert isinstance(e.value, Refusal), (extra, e.value)
            assert e.value.code == raised, (extra, e.value.findings)
        else:
            assert not isinstance(e.value, Refusal), extra
        assert says in str(e.value), (extra, str(e.value))
        assert [p.name for p in root.iterdir()] == [], extra
    assert env["netgen"] == []
    # a falsy variant is today's single-strain model
    cells = prepare_case("base", env, monkeypatch, tmp_path / "falsy",
                         {"variant": ""})
    assert {c["variant"] for c in cells} == {"1strain"}


def test_a_forged_version_never_reaches_bng2(env, monkeypatch, tmp_path):
    stored = _stored(L.shipped_files("sihrs"))
    _by_hand("sfx", dict(stored, **{"model.bngl": suffixed(
        stored["model.bngl"])}))
    _by_hand("wide", dict(stored, **{"priors.conf": stored["priors.conf"]
                                     .replace("r__FREE 0.1 40.0",
                                              "r__FREE 0.1 1e999 u")}))
    # a comment BNG2.pl skips whole, which PyBNF would end at the form
    # feed and write the statement after it back out for BNG2.pl to run
    _by_hand("ff", dict(stored, **{"model.bngl": stored["model.bngl"]
                                   .replace("end parameters\n",
                                            "end parameters\n# note\x0c"
                                            "setOption(\"x\")\n", 1)}))
    for ref, says in (("sfx@1", "model.bngl (SUFFIX_IN_MODEL)"),
                      ("wide@1", "priors.conf (PRIOR_MALFORMED)"),
                      ("ff@1", "model.bngl (LINE_BREAK_NOT_ALLOWED)")):
        with pytest.raises(Refusal) as e:
            prepare_case("base", env, monkeypatch, tmp_path / ref[:-2],
                         {"model": ref})
        assert e.value.code == "MODEL_CHANGED" and says in str(e.value)
    assert env["netgen"] == []


def test_every_suffix_is_flubnfs(env, monkeypatch, tmp_path):
    """The suffix a cell's actions carry is FluBNF's {tag}_flu, letters,
    digits and _ only, so the rewrite never meets a quote."""
    with open(REPO / "flubnf/data/locations.csv", encoding="utf-8") as fh:
        names = [r["location_name"] for r in csv.DictReader(fh)]
    assert len(names) == 53
    for n in names + [n for _f, _a, n, _p in HUB_LOCS]:
        assert re.fullmatch(r"[A-Za-z0-9_]+", pf._hub_tag(n) + "_flu"), n
    assert re.fullmatch(r"[A-Za-z0-9_]+",
                        pf.dataset_tag('US (national), "all" ages') + "_flu")
    _ctl()
    got = _prepared("base", env, monkeypatch, tmp_path / "c",
                    {"model": "ctl@1"})
    for key, texts in got["texts"].items():
        sfx = key.rsplit("_r", 1)[0] + "_flu"
        assert re.findall(r'suffix=>"[^"]*"', texts["m.bngl"]) == [
            f'suffix=>"{sfx}"'], key
