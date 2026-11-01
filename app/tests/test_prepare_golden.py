"""Today's prepared cells, pinned (app/core/engines/pf.py prepare): the
files the engine reads, for every research key prepare reads, held byte
for byte while prepare learns to run a model named by reference.

golden/prepare_cells.json holds, per case: the sha256 of each cell's
m.bngl, .exp and pf.conf; the cells.json, pf_prepare_failures.json and
pf_anchor_notes.json prepare wrote (None when it wrote none); and, for
base, 2strain and natg, the first cell's three texts line by line, for a
reviewer to read. Paths are normalized as written, in conf_safe_path form
and JSON-escaped: the workroot reads <ROOT>, BNG2.pl <BNG> and the carry
folders <CARRY>, each followed by / whatever the platform's separator.

The hub is synthetic, so every number is exact on every platform: two
locations (one with a space in its name) and the US row, integer counts,
populations that are powers of two, three vintages, the 2023-24 season
complete in each; the real resolve_state and growth_gap_series read it.
BNG2.pl writes a stub network, the NREVSS typing and the completeness
factors are faked, and the engine checks answer present. The dataset case
is test_pf_anchor_lag's dataset.

The cases cover every spec.extra key prepare and its helpers read
(test_every_extra_key_prepare_reads_has_a_case scans their source), and
none of them is vacuous. What this hub cannot reach is left to the manual
check on the real hub: with two states the national growth gap never has
enough peers (natgrowth.MIN_PEERS), so natg's gap is zero in every week; no
case fails a location or writes an anchor note; and every case is a
replay (engine "retro"), which reads the archive only, so the weekly
submission's own source (data.spec_mode, extra["mode"] realtime, the live
file) is not pinned here. Regenerate only for a deliberate change, and
review its diff:

    python app/tests/test_prepare_golden.py --write-golden
"""
import inspect
import json
import os
import re
import sys
import types
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

if __name__ == "__main__":
    # the golden regeneration runs without conftest: as it does, keep the
    # state folder and the hub out of the checkout and this machine's clone
    import atexit
    import shutil
    import tempfile
    _state = tempfile.mkdtemp(prefix="flubnf-golden-state-")
    atexit.register(shutil.rmtree, _state, True)
    os.environ.setdefault("FLUBNF_STATE_DIR", _state)
    os.environ.setdefault("FLUBNF_HUB", os.path.join(_state, "no-hub"))

import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402

from app.core import completeness as comp                # noqa: E402
from app.core import data                                # noqa: E402
from app.core import datasets as D                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.runs import RunSpec                        # noqa: E402
from flubnf import nrevss                                # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden" / "prepare_cells.json"

SEASON_START = "2024-08-01"
#: the hub's three vintages; the cases run as of the newest
VINTAGES = ("2024-12-14", "2024-12-21", "2024-12-28")
ASOF = VINTAGES[-1]
#: (fips, abbreviation, name, population): powers of two, so a per-capita
#: count is exact
HUB_LOCS = (("50", "VT", "Vermont", 2 ** 19),
            ("36", "NY", "New York", 2 ** 24),
            ("US", "US", "US", 2 ** 28))
LOCATIONS = ["Vermont", "New York"]
#: the first row of every vintage: the 2023-24 season complete, which the
#: season-total seed denominators read
FIRST_WEEK = date(2023, 8, 5)
#: Vermont's newest week in each vintage: under a fifth of the week before
#: (the partial-week rule fires on it)
PARTIAL = 5
#: the faked completeness factors: lag 0 a quarter reported, lag 1 a half
FAC = {"factors": {0: 0.25, 1: 0.5}, "pairs": {0: 40, 1: 40}}
#: the faked NREVSS A share of the first typed week
A0 = 0.75
#: the dataset case's newest week and groups (test_pf_anchor_lag's)
DATASET_ASOF = "2023-12-02"
DATASET_GROUPS = ["Pediatric", "Adult"]

#: what a case's extra names that exists only once the case runs
CARRY_IN, CARRY_OUT, DATASET = "<CARRY>/in", "<CARRY>/out", "<DATASET>"

#: case -> its spec.extra, RunSpec fields off their defaults ("spec"),
#: whether the engine takes the sampling-interval line ("si") and whether
#: the NREVSS feed is down
CASES = {
    "base": {"extra": {}},
    "sampling_interval": {"extra": {}, "si": True},
    "filter_keys": {"extra": {"pf_keys": {"pf_shrink": 1,
                                          "pf_forecast_jitter": 0.25,
                                          "pf_resample_threshold": 0.5},
                              "initialization": "lh",
                              "seed_anchor": "season_start",
                              "seed_salt": "s1"},
                    "spec": {"jitter": 0.3}},
    "prior_ranges": {"extra": {"prior_ranges": {"r__FREE": [0.1, 200],
                                                "Reff__FREE": [0.5, 2]}}},
    "fit_i0": {"extra": {"fit_i0": [1e-6, 1e-2]}},
    "seed_den[season_total]": {"extra": {"seed_denominator": "season_total"}},
    "seed_den[season_total_early]": {
        "extra": {"seed_denominator": "season_total_early"}},
    "anchor_asof": {"extra": {"anchor_asof": VINTAGES[-2]}},
    "reporting[anchor]": {"extra": {"reporting": {"mode": "anchor"}}},
    "reporting[lik]": {"extra": {"reporting": {"mode": "lik"}}},
    "reporting[both]": {"extra": {"reporting": {"mode": "both"}}},
    "trims": {"extra": {}, "spec": {"weeks_to_drop": 1,
                                    "drop_same_day": True}},
    # the partial-week rule fires on Vermont; New York's newest week was
    # set aside on the Forecast tab
    "missing": {"extra": {
        "knobs": {"data.partial_week": "missing"},
        "data_choices": {"week": ASOF, "states": {"New York": {
            "issue": "collapsed", "reported": [[ASOF, 334.0]],
            "choice": "set_aside", "from_week": ASOF,
            "recommended": "keep", "followed": False}}}}},
    "swarm": {"extra": {"continue_states": CARRY_IN,
                        "save_states": CARRY_OUT}},
    "dataset": {"extra": {"dataset": DATASET}},
    "2strain": {"extra": {"variant": "2strain"}},
    "2strain_feed_down": {"extra": {"variant": "2strain"},
                          "nrevss_down": True},
    "2strain_knobs": {"extra": {"variant": "2strain", "neff_cap": 150,
                                "prior_ranges": {"ReffA__FREE": [0.5, 2.0]},
                                "fit_i0": [1e-6, 1e-2]}},
    "natg": {"extra": {"variant": "natg"}},
    "natg_knobs": {"extra": {"variant": "natg", "iota": 0.25,
                             "fit_i0": [1e-6, 1e-2]}},
}
#: the cases whose first cell's texts the golden keeps
TEXT_CASES = ("base", "2strain", "natg")


# ------------------------------------------------------------- the fixture


def _count(j: int, i: int) -> int:
    """Location j's count in week i after FIRST_WEEK: a triangular yearly
    wave, its trough each August, four times larger in 2023-24 (so the
    season-total seed denominators pin on that season)."""
    tri = 26 - abs(i % 52 - 26)
    return ((2 + 2 * tri, 20 + 15 * tri, 400 + 300 * tri)[j]
            * (4 if i < 52 else 1))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _hub(root: Path) -> dict:
    """The locations table and one target file per vintage, each holding
    every week through its date; its newest week still filling in (New
    York one short, Vermont a partial week)."""
    files = {"locations": _write(root / "locations.csv",
                                 "abbreviation,location,location_name,"
                                 "population\n" + "".join(
                                     f"{a},{f},{n},{p}\n"
                                     for f, a, n, p in HUB_LOCS))}
    for v in VINTAGES:
        rows, d, i = [], FIRST_WEEK, 0
        while d.isoformat() <= v:
            for j, (f, _a, n, _p) in enumerate(HUB_LOCS):
                c = _count(j, i)
                if d.isoformat() == v and n == "Vermont":
                    c = PARTIAL
                elif d.isoformat() == v and n == "New York":
                    c -= 1
                rows.append(f"{d.isoformat()},{f},{n},{c}\n")
            d, i = d + timedelta(weeks=1), i + 1
        files[v] = _write(root / f"target-hospital-admissions_{v}.csv",
                          "date,location,location_name,value\n"
                          + "".join(rows))
    return files


def _a_share_series(loc, season_start, asof, **kw):
    """Typed NREVSS weeks from October to the as-of, A three times B."""
    weeks = pd.date_range("2024-10-05", asof, freq="7D")
    k = range(len(weeks))
    return pd.DataFrame({"date": weeks,
                         "total_a": [3 * x + len(loc) for x in k],
                         "total_b": [x + 1 for x in k]})


def _feed_down(*a, **k):
    raise OSError("NREVSS unreachable")


def _env(mp, tmp: Path) -> dict:
    """The synthetic hub, the dataset and every fake prepare meets:
    {"hub", "carry", "dataset" (its ref), "netgen" (each m.bngl BNG2.pl
    was handed, in order)}."""
    hub = _hub(tmp / "hub")
    mp.setattr(data, "LOCATIONS", hub["locations"])

    def vintage_path(d):
        if str(d) not in hub:
            raise FileNotFoundError(f"no vintage for {d}")
        return hub[str(d)]
    mp.setattr(data, "vintage_path", vintage_path)
    mp.setattr(data, "SHIPPED", tmp / "no-shipped")
    mp.setattr(pf, "perl_available", lambda: True)
    mp.setattr(pf, "engine_available", lambda: True)
    mp.setattr(pf, "engine_current", lambda: True)
    mp.setattr(pf, "sampling_interval_line", lambda: "")
    netgen = []
    real = pf.subprocess.run

    def fake_bng(cmd, *a, **kw):
        if not (cmd and cmd[0] == "perl"):
            return real(cmd, *a, **kw)
        cwd = Path(kw.get("cwd", "."))
        netgen.append((cwd.name, (cwd / "m.bngl").read_text(encoding="utf-8")))
        (cwd / "m.net").write_text("# stub\n", encoding="utf-8")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    mp.setattr(pf.subprocess, "run", fake_bng)
    mp.setattr(nrevss, "a_share_series", _a_share_series)
    mp.setattr(nrevss, "a0_share", lambda *a, **k: A0)
    mp.setattr(comp, "factors_cached", lambda asof, start: FAC)
    mp.setattr(D, "ROOT", tmp / "datasets")
    from app.tests.test_dataset_engines import grouped_bytes
    ds = D.ingest(grouped_bytes(groups=tuple(DATASET_GROUPS),
                                end=date.fromisoformat(DATASET_ASOF)),
                  "wave", kind="count")
    carry = tmp / "carry"
    (carry / "in").mkdir(parents=True)
    (carry / "in" / "Vermont_r0.npz").write_bytes(b"a carried cloud\n")
    return {"hub": hub, "carry": carry.resolve(), "dataset": ds.ref(),
            "netgen": netgen}


def _extra(case: str, env: dict) -> dict:
    """A case's spec.extra with its placeholders filled in."""
    def fill(v):
        if v == DATASET:
            return env["dataset"]
        if isinstance(v, str) and v.startswith("<CARRY>/"):
            return str(env["carry"] / v.split("/", 1)[1])
        return v
    return {k: fill(v) for k, v in CASES[case]["extra"].items()}


def _spec(case: str, env: dict, extra: dict | None = None) -> RunSpec:
    """The case's run: 2 replicates of the hub's two locations, or of the
    dataset's two groups; `extra` in place of the case's own."""
    extra = _extra(case, env) if extra is None else extra
    if "dataset" in extra:
        return RunSpec(engine="retro", forecast_date=DATASET_ASOF,
                       locations=list(DATASET_GROUPS), replicates=2,
                       particles=100, extra=extra)
    return RunSpec(engine="retro", forecast_date=ASOF,
                   locations=list(LOCATIONS), season_start=SEASON_START,
                   replicates=2, particles=100, extra=extra,
                   **CASES[case].get("spec", {}))


def prepare_case(case: str, env: dict, mp, root: Path,
                 extra: dict | None = None) -> list:
    """prepare() of a case into `root`; its cells."""
    c = CASES[case]
    mp.setattr(pf, "sampling_interval_line",
               lambda: "pf_sampling_interval = 1\n" if c.get("si") else "")
    mp.setattr(nrevss, "a_share_series",
               _feed_down if c.get("nrevss_down") else _a_share_series)
    return pf.prepare(_spec(case, env, extra), root)


# ---------------------------------------------------------- normalization


def normalize(text: str, paths: dict) -> str:
    """`text` with each path in `paths` ({path: token}) as its token, in
    conf_safe_path form and JSON-escaped, and the separators after a token
    as /."""
    forms = {}
    for p, tok in paths.items():
        for s in (str(p), pf.conf_safe_path(p)):
            forms[s] = tok
            forms[json.dumps(s)[1:-1]] = tok
    for s in sorted(forms, key=len, reverse=True):
        text = text.replace(s, forms[s])
    return re.sub(r"(<(?:ROOT|BNG|CARRY)>)([\w.\-\\/]*)",
                  lambda m: m[1] + (m[2].replace("\\\\", "/")
                                    .replace("\\", "/")), text)


def _paths(root: Path, env: dict) -> dict:
    from flubnf.settings import BNG
    return {root: "<ROOT>", BNG: "<BNG>", env["carry"]: "<CARRY>"}


def _read(path: Path, paths: dict):
    """A JSON file prepare wrote, normalized; None when it wrote none."""
    if not path.is_file():
        return None
    return json.loads(normalize(path.read_text(encoding="utf-8"), paths))


def cell_texts(root: Path, cells: list, env: dict) -> dict:
    """{key: {file: normalized text}} of each cell's m.bngl, .exp and
    pf.conf, in the cells' order."""
    paths = _paths(root, env)
    out = {}
    for c in cells:
        d = root / c["key"]
        names = (["m.bngl"] + sorted(p.name for p in d.glob("*.exp"))
                 + ["pf.conf"])
        out[c["key"]] = {n: normalize((d / n).read_bytes().decode("utf-8"),
                                      paths) for n in names}
    return out


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_case(case: str, env: dict, mp, tmp: Path) -> dict:
    """A case prepared into its own workroot: what the golden pins, and
    "all_texts", every cell's texts."""
    root = tmp / "cells" / re.sub(r"[^A-Za-z0-9_]", "_", case)
    root.mkdir(parents=True)
    root = root.resolve()
    cells = prepare_case(case, env, mp, root)
    paths = _paths(root, env)
    texts = cell_texts(root, cells, env)
    got = {"files": {f"{k}/{n}": _sha(t) for k, ft in texts.items()
                     for n, t in ft.items()},
           "cells": _read(root / "cells.json", paths),
           "prepare_failures": _read(root / pf.PREPARE_FAILURES_NAME, paths),
           "anchor_notes": _read(root / pf.ANCHOR_NOTES_NAME, paths)}
    if case in TEXT_CASES:
        first = texts[cells[0]["key"]]
        got["texts"] = {n: t.split("\n") for n, t in first.items()}
    return dict(got, all_texts=texts)


def _pinned(got: dict) -> dict:
    return {k: v for k, v in got.items() if k != "all_texts"}


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


# -------------------------------------------------------------------- tests


@pytest.mark.parametrize("case", list(CASES))
def test_todays_cells_are_pinned(case, monkeypatch, tmp_path):
    env = _env(monkeypatch, tmp_path)
    got = _pinned(run_case(case, env, monkeypatch, tmp_path))
    want = _golden()["cases"][case]
    changed = [f for f in sorted(set(got["files"]) | set(want["files"]))
               if got["files"].get(f) != want["files"].get(f)]
    assert not changed, (f"{case}: these cell files are no longer today's "
                         f"bytes: {changed}")
    assert got == want


def test_the_golden_is_not_vacuous(monkeypatch, tmp_path):
    env = _env(monkeypatch, tmp_path)
    golden = _golden()["cases"]
    assert sorted(golden) == sorted(CASES)
    base = golden["base"]
    same = [c for c, g in golden.items() if c != "base" and g == base]
    assert not same, f"cases that pin nothing base does not: {same}"
    texts, cells = {}, {}
    for case in CASES:
        got = run_case(case, env, monkeypatch, tmp_path)
        texts[case], cells[case] = got["all_texts"], got["cells"]
        assert len(cells[case]) == 4, case      # 2 locations x 2 replicates

    def every(case, name_end):
        return [t for ft in texts[case].values() for n, t in ft.items()
                if n.endswith(name_end)]
    # the two-strain typed columns hold NREVSS rows; feed down, none
    rows = [ln.split()[2:] for t in every("2strain", ".exp")
            for ln in t.splitlines()[1:]]
    assert any(r != ["-1", "-1"] for r in rows)
    assert all(ln.split()[2:] == ["-1", "-1"]
               for t in every("2strain_feed_down", ".exp")
               for ln in t.splitlines()[1:])
    # the scale column and the engine key, in lik and both only
    for case in ("reporting[lik]", "reporting[both]"):
        assert all(t.startswith(f"# time H_weekly {comp.COLUMN}\n")
                   for t in every(case, ".exp")), case
        assert all(f"pf_mean_scale_column = {comp.COLUMN}\n" in t
                   for t in every(case, "pf.conf")), case
    assert not any("pf_mean_scale_column" in t
                   for t in every("reporting[anchor]", "pf.conf"))
    # i0 fitted in every fit_i0 case
    for case in ("fit_i0", "2strain_knobs", "natg_knobs"):
        assert all("loguniform_var = i0__FREE" in t
                   for t in every(case, "pf.conf")), case
        assert all("i0__FREE" in t for t in every(case, "m.bngl")), case
    # one cell continues the carried cloud, every cell keeps its own
    confs = every("swarm", "pf.conf")
    assert all("pf_state_file = <ROOT>/" in t for t in confs)
    assert sum("pf_continue = 1\n" in t for t in confs) == 1
    # the sampling-interval line in its own case only
    for case in CASES:
        has = [f"{pf.SAMPLING_INTERVAL_KEY} = 1\n" in t
               for t in every(case, "pf.conf")]
        assert has == [case == "sampling_interval"] * 4, case
    for case in CASES:
        seed = [("seed_pin" in c) for c in cells[case]]
        assert seed == [case.startswith("seed_den")] * 4, case
        flags = [("data_flags" in c) for c in cells[case]]
        assert flags == [case == "missing"] * 4, case
    rules = {f["rule"] for c in cells["missing"] for f in c["data_flags"]}
    assert rules == {"partial week", "set aside (Forecast tab)"}
    # the seed moves off today's pin where the case says it does
    for case in ("seed_den[season_total]", "seed_den[season_total_early]",
                 "anchor_asof", "reporting[anchor]"):
        assert ([c["i0"] for c in cells[case]]
                != [c["i0"] for c in cells["base"]]), case
    assert {c["seed_pin"]["stage"]
            for c in cells["seed_den[season_total_early]"]} == {"expected"}


#: what a key prepare reads looks like in its source
_READS = (re.compile(r"""\.get\(\s*["']([A-Za-z0-9_]+)["']"""),
          re.compile(r"""(?:ex|extra)\[\s*["']([A-Za-z0-9_]+)["']\]"""))
#: keys no case here holds, and where each is covered
ELSEWHERE = {"model": "test_pf_named_model.py",
             "mode": ("reporting's own key: the reporting cases; also the "
                      "run's, which data.spec_mode reads and a replay spec "
                      "never consults: the manual check on the real hub")}


def test_every_extra_key_prepare_reads_has_a_case():
    fns = [pf.prepare, pf.priors_for, pf.pf_key_lines, pf.initialization_for,
           pf.seed_date_for, pf.continuation_for]
    named = getattr(pf, "_named_model", None)    # a model named by reference
    if named is not None:
        fns.append(named)
    read = {k for fn in fns for rx in _READS
            for k in rx.findall(inspect.getsource(fn))}
    held = set().union(*(c["extra"] for c in CASES.values()))
    assert read, "the scan found no key: its patterns no longer match"
    missing = sorted(read - held - set(ELSEWHERE))
    assert not missing, (f"prepare reads {missing}, which no case sets: add "
                         "a case and regenerate the golden on a deliberate "
                         "change")
    # read through other modules: datasets.from_spec and missing.rules_for
    assert {"dataset", "knobs", "data_choices"} <= held


# ------------------------------------------------------------- regenerate


def snapshot(mp, tmp: Path) -> dict:
    """The golden's object: every case prepared afresh."""
    env = _env(mp, tmp)
    return {"_about": ("today's prepared cells for test_prepare_golden.py; "
                       "regenerate only for a deliberate change: python "
                       "app/tests/test_prepare_golden.py --write-golden"),
            "cases": {case: _pinned(run_case(case, env, mp, tmp))
                      for case in CASES}}


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-golden"]:
        sys.exit(__doc__)
    import tempfile
    with tempfile.TemporaryDirectory() as d, \
            pytest.MonkeyPatch.context() as mp:
        obj = snapshot(mp, Path(d))
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN.relative_to(REPO)}")
