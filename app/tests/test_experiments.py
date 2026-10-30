"""The experiment file (app/core/experiments.py): its fields and defaults,
the derived id, the fingerprint, the size presets and their week rules,
the shipped replay an experiment is compared with, and the plan.

The calendar is the literal 2024-25 one and the shipped replays are
synthetic trees: the suite reads no hub.
"""
import dataclasses
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402
from app.core.runs import RunSpec                        # noqa: E402
from flubnf import settings as hub_settings              # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SIHRS_FP = "5edca88e28ad6dbdeb97bf1aafd4f236bb89ee0b58dbb45e09c2f9179003fb7b"
#: sihrs / 2024-25 / smoke with the Oracle step: measured at 0e9e90b and
#: again at 53f1acf
SMOKE_FP = "f71935447872c098bd9908082d2fab064b3e76fd0887910225e132f5ff9180e0"
#: the 30 vintages of 2024-25 (2025-01-18 has none)
VINTAGES = ["2024-11-16", "2024-11-23", "2024-11-30", "2024-12-07",
            "2024-12-14", "2024-12-21", "2024-12-28", "2025-01-04",
            "2025-01-11", "2025-01-25", "2025-02-01", "2025-02-08",
            "2025-02-15", "2025-02-22", "2025-03-01", "2025-03-08",
            "2025-03-15", "2025-03-22", "2025-03-29", "2025-04-05",
            "2025-04-12", "2025-04-19", "2025-04-26", "2025-05-03",
            "2025-05-10", "2025-05-17", "2025-05-24", "2025-05-31",
            "2025-06-07", "2025-06-14"]
#: the weeks with no FluSight round
NO_ROUND = {"2025-05-31", "2025-06-07", "2025-06-14"}
PILOT_WEEKS = ["2024-11-16", "2024-11-30", "2024-12-14", "2024-12-28",
               "2025-01-11", "2025-01-25", "2025-02-08", "2025-02-22",
               "2025-03-08", "2025-03-22", "2025-04-05", "2025-04-19",
               "2025-05-03", "2025-05-17"]
SMOKE_WEEKS = ["2024-12-28", "2025-01-11"]
BOUNDS = ("2024-08-01", "2025-06-15")


def _has_round(w: str) -> bool:
    return w not in NO_ROUND


def _weeks(size: str, vintages=VINTAGES) -> list:
    return X.size_weeks(size, vintages, BOUNDS, _has_round)


def _refused(code: str, fn, *a, **k):
    with pytest.raises(Refusal) as e:
        fn(*a, **k)
    assert e.value.code == code, e.value.findings
    return str(e.value)


# ----------------------------------------------------------------- the file


def test_a_two_key_file_takes_the_defaults(tmp_path):
    p = tmp_path / X.SETTINGS
    p.write_text('{"model": "beta2@3", "season": "2024-25"}', encoding="utf-8")
    assert X.read(p) == {"model": "beta2@3", "season": "2024-25",
                         "size": "smoke", "oracle": False}
    assert X.read({"model": "sihrs", "season": "2024-25"}) == {
        "model": "sihrs", "season": "2024-25", "size": "smoke",
        "oracle": True}
    # a byte order mark, as Windows Notepad saves one
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert X.read(p)["model"] == "beta2@3"


def test_settings_text_leaves_the_defaults_out_and_round_trips():
    for s, kept in (
            ({"model": "sihrs", "season": "2024-25", "size": "smoke",
              "oracle": True}, {"model", "season"}),
            ({"model": "sihrs", "season": "2024-25", "oracle": False},
             {"model", "season", "oracle"}),
            ({"model": "beta2@3", "season": "2024-25", "size": "pilot",
              "oracle": False}, {"model", "season", "size"}),
            ({"model": "beta2@3", "season": "2024-25", "oracle": True},
             {"model", "season", "oracle"})):
        text = X.settings_text(s)
        assert set(json.loads(text)) == kept
        assert text == json.dumps(json.loads(text), indent=1,
                                  sort_keys=True) + "\n"
        assert X.read(json.loads(text)) == X.read(s)


@pytest.mark.parametrize("raw, code", [
    ({"model": "sihrs", "season": "2024-25", "format_version": 1},
     "FIELD_UNKNOWN"),
    ({"model": "sihrs", "season": "2024-25", "particles": 200},
     "FIELD_UNKNOWN"),
    ({"model": "sihrs"}, "FIELD_MISSING"),
    ({"season": "2024-25"}, "FIELD_MISSING"),
    ({"model": "sihrs", "season": "2024-25", "oracle": "yes"}, "FIELD_TYPE"),
    ({"model": "sihrs", "season": 2024}, "FIELD_TYPE"),
    ({"model": "sihrs", "season": "2024-25", "size": "huge"}, "SIZE_UNKNOWN"),
    ({"model": "beta2", "season": "2024-25"}, "MODEL_REF"),
    ({"model": "sihrs\n", "season": "2024-25"}, "MODEL_REF"),
    # the id puts the season in a folder name
    ({"model": "sihrs", "season": "../../x"}, "SEASON_NO_WEEKS"),
    ({"model": "sihrs", "season": "2024-25/../y"}, "SEASON_NO_WEEKS"),
    (["model", "sihrs"], "EXPERIMENT_UNREADABLE"),
])
def test_each_settings_problem(raw, code):
    assert code in [f["code"] for f in X.validate(raw)]
    if isinstance(raw, dict):
        _refused(code, X.read, raw)


def test_an_unreadable_file(tmp_path):
    p = tmp_path / X.SETTINGS
    _refused("EXPERIMENT_UNREADABLE", X.read, p)              # missing
    p.write_text("{model: sihrs}", encoding="utf-8")
    _refused("EXPERIMENT_UNREADABLE", X.read, p)              # not JSON
    p.write_text("[]", encoding="utf-8")
    _refused("EXPERIMENT_UNREADABLE", X.read, p)              # not an object
    p.write_text("[" * 10_000 + "]" * 10_000, encoding="utf-8")
    _refused("EXPERIMENT_UNREADABLE", X.read, p)              # too deep


# ------------------------------------------------------------------- ids


def test_the_id_is_derived():
    assert X.experiment_id({"model": "beta2@3", "season": "2024-25",
                            "size": "pilot"}) == "beta2-v3_2024-25_pilot"
    assert X.experiment_id({"model": "beta2@3", "season": "2024-25",
                            "oracle": True}) == "beta2-v3_2024-25_smoke_oracle"
    assert X.experiment_id({"model": "sihrs", "season": "2024-25"}
                           ) == "sihrs_2024-25_smoke_oracle"
    assert X.experiment_id({"model": "sihrs-natg", "season": "2023-24",
                            "size": "full"}) == "sihrs-natg_2023-24_full"
    assert X.experiment_id({"model": "sihrs", "season": "2024-25",
                            "oracle": False}) == "sihrs_2024-25_smoke"


# ------------------------------------------------------------ fingerprint


def test_the_fingerprint():
    base = {"model": "beta2@3", "season": "2024-25"}
    fp = X.fingerprint(base, SIHRS_FP)
    written = {"oracle": False, "size": "smoke", "season": "2024-25",
               "model": "beta2@3"}
    assert X.fingerprint(written, SIHRS_FP) == fp       # defaults, key order
    assert X.fingerprint(dict(base, model="other@9"), SIHRS_FP) == fp
    for other in (X.fingerprint(base, "0" * 64),
                  X.fingerprint(dict(base, season="2023-24"), SIHRS_FP),
                  X.fingerprint(dict(base, size="pilot"), SIHRS_FP),
                  X.fingerprint(dict(base, oracle=True), SIHRS_FP)):
        assert other != fp
    assert X.fingerprint({"model": "sihrs", "season": "2024-25"},
                         L.resolve("sihrs")["fingerprint"]) == SMOKE_FP


def test_a_changed_preset_changes_the_fingerprint(monkeypatch):
    base = {"model": "beta2@3", "season": "2024-25"}
    fp = X.fingerprint(base, SIHRS_FP)
    monkeypatch.setitem(X.SIZES, "smoke",
                        dataclasses.replace(X.SIZES["smoke"], particles=200))
    assert X.fingerprint(base, SIHRS_FP) != fp


# ---------------------------------------------------------------- presets


#: the HHS region of each state, for the pilot's one-per-region rule
HHS = {1: ("CT", "ME", "MA", "NH", "RI", "VT"),
       2: ("NJ", "NY", "PR"),
       3: ("DE", "DC", "MD", "PA", "VA", "WV"),
       4: ("AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN"),
       5: ("IL", "IN", "MI", "MN", "OH", "WI"),
       6: ("AR", "LA", "NM", "OK", "TX"),
       7: ("IA", "KS", "MO", "NE"),
       8: ("CO", "MT", "ND", "SD", "UT", "WY"),
       9: ("AZ", "CA", "HI", "NV"),
       10: ("AK", "ID", "OR", "WA")}


def test_the_presets_are_pinned():
    assert X.SMOKE_LOCATIONS == ("California", "Vermont")
    assert X.PILOT_LOCATIONS == ("Alaska", "California", "Georgia",
                                 "Illinois", "Missouri", "New York",
                                 "Pennsylvania", "Texas", "Vermont",
                                 "Wyoming")
    assert str(X.WEEK_EPOCH) == "2000-01-01" and X.WEEK_EPOCH.weekday() == 5
    assert {k: dataclasses.astuple(v) for k, v in X.SIZES.items()} == {
        "smoke": (X.SMOKE_LOCATIONS, "even_middle_2", 1, 10_000),
        "pilot": (X.PILOT_LOCATIONS, "even", 1, 10_000),
        "full": ("all", "all", 3, 10_000)}
    assert (X.SIZES["full"].replicates, X.SIZES["full"].particles) == (
        RunSpec.replicates, RunSpec.particles)
    assert X.DEFAULT_SIZE == "smoke" and X.ORACLE_ON_BY_DEFAULT == ("sihrs",)


def test_every_preset_location_is_in_the_table_and_the_pilot_spans_hhs():
    t = pd.read_csv(REPO / "flubnf/data/locations.csv", dtype=str)
    abbr = dict(zip(t.location_name, t.abbreviation))
    assert set(X.SMOKE_LOCATIONS) <= set(X.PILOT_LOCATIONS) <= set(abbr)
    region = {a: r for r, states in HHS.items() for a in states}
    assert sorted(region[abbr[n]] for n in X.PILOT_LOCATIONS) == list(range(1, 11))
    every = X._all_locations()
    assert len(every) == 53 and every[-1] == "US"
    assert X.size_locations("full", every) == every
    assert X.size_locations("pilot", every) == list(X.PILOT_LOCATIONS)


# ------------------------------------------------------------- week rules


def test_the_week_rules_on_2024_25():
    assert _weeks("full") == VINTAGES
    assert _weeks("pilot") == PILOT_WEEKS
    assert _weeks("smoke") == SMOKE_WEEKS
    assert set(_weeks("smoke")) <= set(_weeks("pilot")) <= set(_weeks("full"))
    # a vintage added on an odd week moves no pick
    more = sorted(VINTAGES + ["2025-01-18"])
    assert _weeks("pilot", more) == PILOT_WEEKS
    assert _weeks("smoke", more) == SMOKE_WEEKS
    assert _weeks("full", more) == more
    # the middle on an even week, its two neighbours tied: the earlier
    assert X.size_weeks("smoke", ["2024-12-14", "2024-12-28", "2025-01-11"],
                        ("2024-12-21", "2025-01-04"), lambda w: True) == [
        "2024-12-14", "2024-12-28"]


def test_a_round_is_the_baseline_file_of_the_week_after(tmp_path,
                                                        monkeypatch):
    monkeypatch.setattr(hub_settings, "HUB", tmp_path)
    d = tmp_path / "model-output" / "FluSight-baseline"
    d.mkdir(parents=True)
    (d / "2025-01-18-FluSight-baseline.csv").write_text("", encoding="utf-8")
    assert X._has_round("2025-01-11") and not X._has_round("2025-01-18")


def test_smoke_in_a_season_under_way_is_its_latest_two():
    v = ["2026-09-26", "2026-10-03", "2026-10-10", "2026-10-17"]
    assert X.size_weeks("smoke", v, ("2026-08-01", "2027-06-15"),
                        lambda w: w != "2026-09-26") == ["2026-10-03",
                                                         "2026-10-17"]


# ---------------------------------------------------- the shipped replay


SHIPPED = {"engine": "pf", "oracle": "applied", "particles": 10_000,
           "replicates": 3, "scope": "all", "national": True,
           "season": "2024-25"}


def _replay(root: Path, *, weeks=("2024-12-28",), filter_=True,
            started=1_790_000_000.0, **settings) -> Path:
    """A stored replay: its run record and, per week, a samples file, the
    quantile sidecar (stored horizons) and, with filter_, oracle.json."""
    retro.write_meta(root, {"started_utc": started,
                            "settings": {**SHIPPED, **settings}})
    for w in weeks:
        wd = root / "weeks" / w
        wd.mkdir(parents=True)
        (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
        RS.write_week_quantiles(wd, {"pf": {"Vermont": {"0": {0.5: 3.0}}}})
        if filter_:
            (wd / RS.ORACLE_NAME).write_text(json.dumps(
                {"applied": True, "quantiles": {"levels": [0.5], "null": {
                    "Vermont": {"0": {"unrounded": [2.0]}}}}}),
                encoding="utf-8")
    return root


def test_the_reference_is_the_live_shipped_root_then_the_newest_archive(tmp_path):
    rr = tmp_path / "retro"
    _replay(rr / "2024-25", engine="analogue")          # the Groundhog alone
    old = _replay(rr / "2024-25__archived_20260101T000000Z")
    new = _replay(rr / "2024-25__archived_20260201T000000Z", filter_=False,
                  started=1_790_100_000.0)
    r = X.reference(rr, "2024-25", True, SMOKE_WEEKS)
    assert (r["root"], r["member"]) == (new, "pf")
    assert r["started_utc"] == "2026-09-22T18:00:00Z"
    assert (r["replicates"], r["particles"], r["engine_build"]) == (3, 10_000, {})
    # the step off needs oracle.json: the newer root has none
    r = X.reference(rr, "2024-25", False, SMOKE_WEEKS)
    assert (r["root"], r["member"]) == (old, "pf_filter")
    # a root that carries knobs is not the shipped replay
    retro.write_meta(new, {"settings": {**SHIPPED, "knobs": {"pf.jitter": 0.2}}})
    assert X.reference(rr, "2024-25", True, SMOKE_WEEKS)["root"] == old
    # nor is one on other settings
    for k, v in (("oracle", "none"), ("particles", 200), ("replicates", 1),
                 ("scope", "panel"), ("national", False)):
        retro.write_meta(new, {"settings": {**SHIPPED, k: v}})
        assert X.reference(rr, "2024-25", True, SMOKE_WEEKS)["root"] == old, k
    # no planned week stored: no reference
    assert X.reference(rr, "2024-25", True, ["2025-03-08"]) is None


def test_no_root_holding_the_filter_gives_none(tmp_path):
    rr = tmp_path / "retro"
    _replay(rr / "2024-25", filter_=False)
    assert X.reference(rr, "2024-25", True, SMOKE_WEEKS)["member"] == "pf"
    assert X.reference(rr, "2024-25", False, SMOKE_WEEKS) is None
    assert X.reference(tmp_path / "none", "2024-25", True, SMOKE_WEEKS) is None


# ------------------------------------------------------------------ plan


@pytest.fixture
def season(sandbox_root, monkeypatch, tmp_path):
    """2024-25's calendar, its rounds, and BNG2.pl faked for register."""
    monkeypatch.setattr(retro, "available_seasons", lambda: ["2024-25"])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(VINTAGES) if s == "2024-25" else [])
    monkeypatch.setattr(X, "_has_round", _has_round)
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if (cwd / "cm.bngl").is_file():
            (cwd / "cm.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="BioNetGen version 2.9.3\n",
                                     stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return tmp_path / "retro"


def _register(name: str, edit=lambda t: t) -> str:
    files = L.shipped_files("sihrs")
    d = sb.MODELS / name
    d.mkdir(parents=True)
    (d / "model.bngl").write_text(edit(files["model.bngl"]), encoding="utf-8")
    (d / "priors.conf").write_text(files["priors.conf"], encoding="utf-8")
    (d / "data.exp").write_text(L.SAMPLE_EXP, encoding="utf-8")
    return L.register(name)["ref"]


def test_the_plan(season):
    _replay(season / "2024-25", weeks=SMOKE_WEEKS)
    p = X.plan({"model": "sihrs", "season": "2024-25"}, retro_root=season)
    assert p["id"] == "sihrs_2024-25_smoke_oracle"
    assert (p["experiment"], p["model_fingerprint"]) == (SMOKE_FP, SIHRS_FP)
    assert (p["model"], p["model_folder"], p["oracle"]) == ("sihrs", None, True)
    assert p["locations"] == ["California", "Vermont"]
    assert p["weeks"] == SMOKE_WEEKS
    assert (p["replicates"], p["particles"]) == (1, 10_000)
    assert p["reference"]["member"] == "pf" and p["findings"] == []
    ref = _register("beta")
    p = X.plan({"model": ref, "season": "2024-25", "size": "pilot"},
               retro_root=season)
    assert p["id"] == "beta-v1_2024-25_pilot" and p["oracle"] is False
    assert p["model_folder"] == L.root() / "beta" / "1"
    assert p["weeks"] == PILOT_WEEKS and len(p["locations"]) == 10
    # the step off: the shipped Liu-West filter is the reference
    assert p["reference"]["member"] == "pf_filter" and p["findings"] == []
    p = X.plan({"model": ref, "season": "2024-25", "size": "full"},
               retro_root=season / "none")
    assert [f["code"] for f in p["findings"]] == ["NO_REFERENCE"]
    assert len(p["locations"]) == 53 and p["replicates"] == 3


def test_the_plan_says_the_oracle_step_assumes_gamma(season):
    ref = _register("fixed", lambda t: t.replace("{{GAMMA}}", "2.1875"))
    p = X.plan({"model": ref, "season": "2024-25", "oracle": True},
               retro_root=season)
    assert [f["code"] for f in p["findings"]] == ["GAMMA_ASSUMED",
                                                  "NO_REFERENCE"]
    # the step off assumes nothing
    p = X.plan({"model": ref, "season": "2024-25"}, retro_root=season)
    assert [f["code"] for f in p["findings"]] == ["NO_REFERENCE"]


def test_the_plan_refuses(season):
    _refused("SEASON_NO_WEEKS", X.plan, {"model": "sihrs", "season": "1999-00"},
             retro_root=season)
    _refused("MODEL_NOT_FOUND", X.plan, {"model": "beta@9",
                                         "season": "2024-25"},
             retro_root=season)
    _refused("FIELD_UNKNOWN", X.plan, {"model": "sihrs", "season": "2024-25",
                                       "weeks": 3}, retro_root=season)
    folder = X.root() / "sihrs_2024-25_smoke_oracle"
    retro.write_meta(folder, {"settings": {"experiment": "0" * 64}})
    _refused("EXPERIMENT_CHANGED", X.plan, {"model": "sihrs",
                                            "season": "2024-25"},
             retro_root=season)
    retro.write_meta(folder, {"settings": {"experiment": SMOKE_FP}})
    assert X.plan({"model": "sihrs", "season": "2024-25"},
                  retro_root=season)["experiment"] == SMOKE_FP
