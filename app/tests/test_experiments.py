"""The experiment file (app/core/experiments.py): its fields and defaults,
the derived id, the fingerprint, the size presets and their week rules,
the shipped replay an experiment is compared with, the plan, and the
replay itself (run_week faked, and once the real prepare on
test_prepare_golden.py's hub).

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


# ---------------------------------------------------------------- replay


def _weeks_run(monkeypatch, after=lambda root, asof: None) -> list:
    """retro.run_week faked: each call's (asof, locations, replicates,
    particles, extra) recorded and its samples file written, then
    after(root, asof)."""
    calls = []

    def fake_week(root, season, asof, locations, replicates, particles,
                  width, drop_same_day=False, extra=None, engine="pf"):
        calls.append({"asof": asof, "locations": list(locations),
                      "replicates": replicates, "particles": particles,
                      "extra": extra})
        wd = Path(root) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
        after(Path(root), asof)
        return {"asof": asof}
    monkeypatch.setattr(retro, "run_week", fake_week)
    return calls


def test_replay_writes_the_settings_then_runs_the_plan(season, monkeypatch):
    from app.core.engines import analogue as an
    calls = _weeks_run(monkeypatch)
    s = {"model": "sihrs", "season": "2024-25"}
    got = X.replay(s, retro_root=season)
    folder = X.root() / "sihrs_2024-25_smoke_oracle"
    assert ((folder / X.SETTINGS).read_text(encoding="utf-8")
            == X.settings_text(s))
    assert [c["asof"] for c in calls] == SMOKE_WEEKS
    base = an.aux_preset(an.SHIPPED_AUX)
    for i, c in enumerate(calls):
        assert (c["locations"], c["replicates"], c["particles"]) == (
            ["California", "Vermont"], 1, 10_000)
        assert c["extra"] == {**base(c["asof"], i, SMOKE_WEEKS),
                              "model": "sihrs"}
    st = retro.read_meta(folder)["settings"]
    assert (st["model"], st["model_fingerprint"], st["experiment"]) == (
        "sihrs", SIHRS_FP, SMOKE_FP)
    assert (st["weeks"], st["oracle"]) == (SMOKE_WEEKS, "applied")
    assert st["week_extra"].startswith("aux_preset:flusurv")
    assert st["groundhog_local_pools"] == an.effective_local_pools(
        {"local_pools": an.shipped_local_pools()})
    assert got == X.plan(s, retro_root=season)


def test_the_oracle_switch_reaches_every_week(season, monkeypatch, tmp_path):
    calls = _weeks_run(monkeypatch)
    ref = _register("beta")
    X.replay({"model": ref, "season": "2024-25"}, retro_root=season)
    off = retro.read_meta(X.root() / "beta-v1_2024-25_smoke")["settings"]
    assert [c["extra"]["oracle"] for c in calls] == ["none", "none"]
    assert [c["extra"]["model"] for c in calls] == [ref, ref]
    assert off["week_extra"].endswith("+oracle:none")
    # the words a replay records on its own with the step off
    retro.run_season(tmp_path / "plain", "2024-25", ["Vermont"],
                     week_extra=lambda asof, i, v: {"oracle": "none"})
    plain = retro.read_meta(tmp_path / "plain")["settings"]["oracle"]
    assert off["oracle"] == plain
    calls.clear()
    on = {"model": ref, "season": "2024-25", "oracle": True}
    X.replay(on, retro_root=season)
    assert [("oracle" in c["extra"]) for c in calls] == [False, False]
    folder = X.root() / "beta-v1_2024-25_smoke_oracle"
    assert retro.read_meta(folder)["settings"]["oracle"] == "applied"
    # a finished experiment run again keeps what it recorded
    calls.clear()
    X.replay(on, retro_root=season)
    assert calls == []
    assert retro.read_meta(folder)["settings"]["oracle"] == "applied"


def test_a_refused_experiment_writes_nothing(season, monkeypatch):
    from flubnf import bank
    calls = _weeks_run(monkeypatch)
    _refused("MODEL_NOT_FOUND", X.replay, {"model": "beta@9",
                                           "season": "2024-25"},
             retro_root=season)
    assert not X.root().exists()
    folder = X.root() / "sihrs_2024-25_smoke_oracle"
    retro.write_meta(folder, {"settings": {"experiment": "0" * 64}})
    _refused("EXPERIMENT_CHANGED", X.replay, {"model": "sihrs",
                                              "season": "2024-25"},
             retro_root=season)
    assert sorted(p.name for p in folder.iterdir()) == [retro.META_NAME]

    def no_bank(stream):
        raise FileNotFoundError(f"no {stream} bank")
    monkeypatch.setattr(bank, "read", no_bank)
    with pytest.raises(FileNotFoundError, match="no flusurv bank"):
        X.replay({"model": "sihrs", "season": "2024-25", "oracle": False},
                 retro_root=season)
    assert not (X.root() / "sihrs_2024-25_smoke").exists()
    assert calls == []


def test_stop_pause_and_resume(season, monkeypatch):
    held = [w for w in VINTAGES if w != "2025-03-08"]
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(held))
    folder = X.root() / "sihrs_2024-25_pilot_oracle"
    slept = []

    def sleep(seconds):                 # the person presses Resume
        slept.append(seconds)
        retro.clear_pause(folder)
    monkeypatch.setattr(retro, "_sleep", sleep)
    first, second = PILOT_WEEKS[:2]

    def after(root, asof):
        if asof == first:
            retro.request_pause(root)
        if asof == second:
            retro.request_stop(root)
    calls = _weeks_run(monkeypatch, after)
    s = {"model": "sihrs", "season": "2024-25", "size": "pilot"}
    with pytest.raises(retro.SeasonStopped):
        X.replay(s, retro_root=season)
    planned = [w for w in PILOT_WEEKS if w != "2025-03-08"]
    assert [c["asof"] for c in calls] == [first, second] and slept
    m = retro.read_meta(folder)
    assert m["status"] == "stopped" and m["settings"]["weeks"] == planned
    # a week added since: the plan picks it, the replay keeps its own
    held.append("2025-03-08")
    assert X.plan(s, retro_root=season)["weeks"] == PILOT_WEEKS
    calls.clear()
    got = X.replay(s, retro_root=season)
    assert [c["asof"] for c in calls] == planned[2:]
    assert got["weeks"] == planned
    assert retro.read_meta(folder)["status"] == "done"


def test_a_week_whose_model_changed_is_not_fitted(season, monkeypatch):
    from app.tests.test_library import _by_hand
    import shutil
    ref = _register("beta")
    other = {f: L.replay_text(f, t)
             for f, t in L.shipped_files("sihrs").items()}
    other["model.bngl"] = other["model.bngl"].replace("# FluBNF SIHRS",
                                                      "# My SIHRS")

    def rewrite(root, asof):
        if asof == SMOKE_WEEKS[0]:
            shutil.rmtree(L.root() / "beta" / "1")
            _by_hand("beta", other)
    calls = _weeks_run(monkeypatch, rewrite)
    X.replay({"model": ref, "season": "2024-25"}, retro_root=season)
    folder = X.root() / "beta-v1_2024-25_smoke"
    new = L.resolve(ref)["fingerprint"]
    assert new != SIHRS_FP
    assert [c["asof"] for c in calls] == SMOKE_WEEKS[:1]
    log = (folder / "failures.log").read_text(encoding="utf-8")
    assert log == (f"{SMOKE_WEEKS[1]}: {ref} is {new[:8]} now, and this "
                   f"experiment started with {SIHRS_FP[:8]}: "
                   f"{SMOKE_WEEKS[1]} is not fitted\n")
    assert retro.read_meta(folder)["status"] == "done"
    # a shipped template changed by an update reads the same
    real = L.resolve

    def updated(root, asof):
        if asof == SMOKE_WEEKS[0]:
            monkeypatch.setattr(L, "resolve", lambda r: {
                **real(r), "fingerprint": "0" * 64})
    calls = _weeks_run(monkeypatch, updated)
    X.replay({"model": "sihrs", "season": "2024-25"}, retro_root=season)
    folder = X.root() / "sihrs_2024-25_smoke_oracle"
    assert [c["asof"] for c in calls] == SMOKE_WEEKS[:1]
    assert "sihrs is 00000000 now" in (folder / "failures.log").read_text(
        encoding="utf-8")


def test_a_library_experiment_prepares_its_model(season, monkeypatch,
                                                 tmp_path):
    """The whole week path with the real prepare, on test_prepare_golden's
    hub: the runners, the collected draws, the Groundhog and the pruning
    faked."""
    from app.core import horizons as hz
    from app.core import reclaim
    from app.core.engines import pf as PF
    from app.core.runs import derive_seed
    from app.tests.test_pf_named_model import _filled
    from app.tests.test_prepare_golden import VINTAGES as HUB_WEEKS, _env
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.settings import BNG
    ref = _register("beta")            # before the hub's BNG2.pl fake
    _env(monkeypatch, tmp_path / "hub")
    locs = ("Vermont", "New York")
    monkeypatch.setitem(X.SIZES, "smoke", dataclasses.replace(
        X.SIZES["smoke"], locations=locs))
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(HUB_WEEKS))

    class Runner:
        """Every cell of its shard fitted at once."""
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], "ok")
            return 0

        def kill(self):
            pass
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s)
                                                  for s in shards])
    draws = {hz.ORIGIN: [3.0] * 50, **{h: [4.0] * 50 for h in hz.HORIZONS}}
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {n: dict(draws) for n in locs})
    monkeypatch.setattr(retro.an_engine, "run", lambda spec: {
        n: {h: {float(q): 2.0 for q in QL} for h in hz.HORIZONS}
        for n in spec.locations})
    monkeypatch.setattr(reclaim, "prune_week", lambda wd: 0)
    got = X.replay({"model": ref, "season": "2024-25"}, retro_root=season)
    assert got["weeks"] == ["2024-12-14", "2024-12-28"]
    folder = X.root() / got["id"]
    stored = L.resolve(ref)["files"]
    for asof in got["weeks"]:
        wd = folder / "weeks" / asof
        cells = json.loads((wd / "cells.json").read_text(encoding="utf-8"))
        assert [c["key"] for c in cells] == ["Vermont_r0", "New_York_r0"]
        for c in cells:
            d, at = wd / c["key"], PF.conf_safe_path(c["dir"])
            assert (d / "m.bngl").read_text(encoding="utf-8") == _filled(
                stored["model.bngl"], c)
            conf = (d / "pf.conf").read_text().splitlines()
            sfx = c["key"][:-3] + "_flu"
            assert conf[:15] == [
                f"bng_command = {PF.conf_safe_path(BNG)}",
                f"model = {at}/m.bngl : {at}/{sfx}.exp",
                f"output_dir = {at}/out",
                "fit_type = pf", "objfunc = neg_bin_dynamic",
                "pf_particles = 10000", "pf_jitter = 0.15",
                "pf_bounds = reflect", "pf_start_time = -1",
                "pf_cumulative_observable = Hobs",
                "pf_forecast_intervals = 4", "population_size = 1",
                "max_iterations = 1",
                f"pf_seed = {derive_seed(c['location'], asof, 0)}",
                "initialization = rand"]
            assert "\n".join(conf[15:]) + "\n" == PF.VARS_1S
        prov = json.loads((wd / RS.ORACLE_NAME).read_text(encoding="utf-8"))
        assert prov["applied"] is False
        week = retro.read_week_samples(folder, asof)
        assert {"pf", "analogue"} <= set(week)
        assert set(week["pf"]) == set(week["analogue"]) == set(locs)
