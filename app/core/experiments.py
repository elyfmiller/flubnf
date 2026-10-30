"""SANDBOX: experiments, one model replayed over one season at a preset
size and compared with the shipped replay (the queue, the runner and the
page come in later steps; the formats are fixed here).

  sandbox/experiments/<id>/
    experiment.json   the settings people write: model (name@version or a
                      shipped name) and season, required; size (smoke,
                      pilot or full; smoke by default) and oracle (the
                      Oracle step; on by default for sihrs only). A key at
                      its default is left out; nothing else is accepted,
                      a format_version neither (FIELD_UNKNOWN)
    summary.json      the results FluBNF writes (format_version 1): sums
                      over the cells both sides scored, never ratios, so
                      pooling experiments later is still a ratio of sums
    run_meta.json, weeks/<asof>/...
                      the replay's own files: the folder is its root

The id is derived, never typed: <name>[-v<n>]_<season>_<size>[_oracle],
so the same settings give the same folder and running again resumes.

A size is a preset of frozen constants (SIZES): its locations, its week
rule, replicates and particles. A changed preset or week rule gets a new
name, never an edit, and the experiment fingerprint hashes the constants
with the model's fingerprint, the season and the resolved Oracle setting,
so an edit cannot pass unnoticed.

The shipped side of a summary is the shipped replay of the season
(reference): the live root first, then the archived ones, newest first,
read through the read-only readers only. Findings and refusals carry the
codes of app/core/problem_codes.py.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from app.core import library
from app.core import sandbox as sb
from app.core.problem_codes import Refusal, finding

SETTINGS = "experiment.json"
SUMMARY = "summary.json"
SUMMARY_VERSION = 1
FIELDS = ("model", "season", "size", "oracle")
REQUIRED = ("model", "season")
DEFAULT_SIZE = "smoke"
#: the models whose experiments run the Oracle step unless told not to
ORACLE_ON_BY_DEFAULT = ("sihrs",)
#: a season's name, as retro.available_seasons writes it: the id puts it
#: in a folder name
_SEASON_RE = re.compile(r"[0-9]{4}-[0-9]{2}")

#: California is large and Vermont small (no admissions some weeks), so a
#: scale or zero-handling slip shows at once; both are pilot states
SMOKE_LOCATIONS = ("California", "Vermont")
#: the Retrospective's 6-state panel plus Georgia, Illinois, Missouri and
#: Texas: one state per HHS region. No US: the pooled headline leaves it
#: out (us_national.POOLED_INCLUDES_US)
PILOT_LOCATIONS = ("Alaska", "California", "Georgia", "Illinois", "Missouri",
                   "New York", "Pennsylvania", "Texas", "Vermont", "Wyoming")
#: week parity is counted from here on the calendar (a Saturday, as every
#: vintage is), so a vintage added later never moves another pick
WEEK_EPOCH = date(2000, 1, 1)


@dataclass(frozen=True)
class Size:
    """A size preset's frozen constants."""
    locations: tuple | str      # a name tuple, or "all"
    weeks: str                  # a week rule's name (size_weeks)
    replicates: int
    particles: int


SIZES = {
    "smoke": Size(SMOKE_LOCATIONS, "even_middle_2", 1, 10_000),
    "pilot": Size(PILOT_LOCATIONS, "even", 1, 10_000),
    "full": Size("all", "all", 3, 10_000),       # runs.RunSpec's
}

#: the run_meta settings a shipped replay holds: what a reference must match
SHIPPED_SETTINGS = {"engine": "pf", "oracle": "applied", "particles": 10_000,
                    "replicates": 3, "scope": "all", "national": True}


def root() -> Path:
    """The experiments folder, read at call time (the tests move the
    sandbox)."""
    return sb.SANDBOX / "experiments"


# ------------------------------------------------------------- the settings


def validate(raw: object) -> list[dict]:
    """The settings' problems, without reading anything: the file's shape,
    the fields, their types, the size, and the grammar of the model
    reference and of the season."""
    if not isinstance(raw, dict):
        return [finding("EXPERIMENT_UNREADABLE", "the experiment is not a "
                        "JSON object ({...})", file=SETTINGS)]
    out = [finding("FIELD_UNKNOWN", f"{k!r} is not an experiment field: "
                   f"it takes {', '.join(FIELDS)} only", file=SETTINGS)
           for k in raw if k not in FIELDS]
    out += [finding("FIELD_MISSING", f"the experiment names no {k}",
                    file=SETTINGS) for k in REQUIRED if k not in raw]
    for k in FIELDS:
        if k not in raw:
            continue
        want = bool if k == "oracle" else str
        if not isinstance(raw[k], want):
            out.append(finding(
                "FIELD_TYPE", f"{k} is {json.dumps(raw[k])}; it is "
                f"{'true or false' if want is bool else 'text in quotes'}",
                file=SETTINGS))
        elif k == "size" and raw[k] not in SIZES:
            out.append(finding("SIZE_UNKNOWN", f"size {raw[k]!r} is not "
                               f"one of {', '.join(SIZES)}", file=SETTINGS))
        elif k == "model":
            try:
                library.parse_ref(raw[k])
            except Refusal as e:
                out += e.findings
        elif k == "season" and not _SEASON_RE.fullmatch(raw[k]):
            out.append(finding("SEASON_NO_WEEKS", f"season {raw[k]!r} is "
                               "not a season such as 2024-25", file=SETTINGS))
    return out


def _resolved(settings: Mapping) -> dict:
    """The four settings with the defaults filled in."""
    out = {"model": settings["model"], "season": settings["season"],
           "size": settings.get("size", DEFAULT_SIZE)}
    out["oracle"] = settings.get("oracle",
                                 out["model"] in ORACLE_ON_BY_DEFAULT)
    return out


def read(source: Path | Mapping) -> dict:
    """The settings of an experiment.json (a path) or of its parsed
    object, with the defaults filled in; Refusal for any problem."""
    raw = source
    if not isinstance(source, Mapping):
        try:
            # utf-8-sig: Windows Notepad saves a byte order mark first
            raw = json.loads(Path(source).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, RecursionError) as e:
            # RecursionError: JSON nested too deep for the parser
            raise Refusal(finding(
                "EXPERIMENT_UNREADABLE", f"{source} cannot be read as JSON "
                f"({e})", file=SETTINGS)) from None
    found = validate(dict(raw) if isinstance(raw, Mapping) else raw)
    if any(f["tier"] == "problem" for f in found):
        raise Refusal(found)
    return _resolved(raw)


def settings_text(settings: Mapping) -> str:
    """experiment.json's text: the keys that differ from their defaults,
    in the house JSON style."""
    s = _resolved(settings)
    defaults = _resolved({"model": s["model"], "season": s["season"]})
    return json.dumps({k: v for k, v in s.items()
                       if k in REQUIRED or v != defaults[k]},
                      indent=1, sort_keys=True) + "\n"


def experiment_id(settings: Mapping) -> str:
    """<name>[-v<n>]_<season>_<size>[_oracle]: no @ in a folder name
    that Perl and shells read, and never two experiments in one folder
    (a library id ends in -v<n>, which no shipped name does)."""
    s = _resolved(settings)
    name, version = library.parse_ref(s["model"])
    return (f"{name}{f'-v{version}' if version else ''}_{s['season']}_"
            f"{s['size']}{'_oracle' if s['oracle'] else ''}")


def fingerprint(settings: Mapping, model_fingerprint: str) -> str:
    """The experiment's identity: sha256 over the canonical JSON of the
    model's fingerprint, the resolved Oracle setting, the season and the
    size preset's constants. The model's label and the id are outside it;
    a later field enters only when it differs from its default."""
    s = _resolved(settings)
    size = SIZES[s["size"]]
    obj = {"model": model_fingerprint, "oracle": bool(s["oracle"]),
           "season": s["season"],
           "size": {"name": s["size"],
                    "locations": (size.locations if size.locations == "all"
                                  else list(size.locations)),
                    "weeks": size.weeks, "replicates": size.replicates,
                    "particles": size.particles}}
    return hashlib.sha256(library._canonical(obj)).hexdigest()


# ------------------------------------------------------- locations and weeks


def size_locations(size: str, all_locations: Sequence[str]) -> list[str]:
    """The size's locations: its preset's names in their order, or
    all_locations for "all"."""
    locs = SIZES[size].locations
    return list(all_locations) if locs == "all" else list(locs)


def _even(asof: str) -> bool:
    return ((date.fromisoformat(asof) - WEEK_EPOCH).days // 7) % 2 == 0


def size_weeks(size: str, vintages: Sequence[str], bounds: tuple[str, str],
               has_round: Callable[[str], bool]) -> list[str]:
    """The size's weeks of a season, in date order, from its vintages:
    "all" every one; "even" the even calendar weeks that have a FluSight
    round (a week without one can never be scored); "even_middle_2" the
    two even weeks nearest the middle of the season's bounds, ties to the
    earlier."""
    rule = SIZES[size].weeks
    weeks = sorted(vintages)
    if rule == "all":
        return weeks
    even = [w for w in weeks if _even(w) and has_round(w)]
    if rule == "even":
        return even
    lo, hi = (date.fromisoformat(b) for b in bounds)
    mid = lo + timedelta(days=(hi - lo).days // 2)
    near = sorted(even, key=lambda w: (abs((date.fromisoformat(w) - mid).days),
                                       w))
    return sorted(near[:2])


def _has_round(asof: str) -> bool:
    """A FluSight round for the as-of: the hub's FluSight-baseline file of
    as-of + 7 days, the test flubnf/baseline.py makes."""
    from flubnf import settings
    ref = (date.fromisoformat(asof) + timedelta(days=7)).isoformat()
    return (settings.HUB / "model-output" / "FluSight-baseline"
            / f"{ref}-FluSight-baseline.csv").is_file()


def _all_locations() -> list[str]:
    """The Retrospective's "all" scope with US: the locations table's
    two-character jurisdictions but US, then the US row's name."""
    from flubnf.settings import load_locations
    t = load_locations()
    states = t.location_name[(t.location.str.len() == 2)
                             & (t.abbreviation != "US")]
    return list(states) + list(t.location_name[t.abbreviation == "US"])


def _utc(epoch) -> str | None:
    """A run record's Unix time as %Y-%m-%dT%H:%M:%SZ, or None."""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc
                                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def reference(retro_root: Path, season: str, oracle: bool,
              weeks: Sequence[str]) -> dict | None:
    """The shipped replay an experiment is compared with: the first of the
    season's live root and its archived roots (newest first) whose run
    record holds SHIPPED_SETTINGS, no knobs, and the member in at least one
    planned week ("pf", the Oracle step, when the step is on; "pf_filter",
    the Liu-West filter alone, when it is off). {"root", "member",
    "started_utc", "replicates", "particles", "engine_build"}, or None.
    Read-only: a sidecar is never written into the shipped tree."""
    from app.core import retro
    from app.core.retro_store import (FILTER_MEMBER, _week_dir,
                                      filter_quantiles, read_week_quantiles)
    member = "pf" if oracle else FILTER_MEMBER
    roots = retro.list_archive_dirs(retro_root, season)
    if (Path(retro_root) / season).is_dir():
        roots.insert(0, Path(retro_root) / season)
    for r in roots:
        meta = retro.read_meta(r)
        st = meta.get("settings") or {}
        if "knobs" in st or any(st.get(k) != v
                                for k, v in SHIPPED_SETTINGS.items()):
            continue
        for w in weeks:
            wd = _week_dir(r, w)
            held = (filter_quantiles(wd) if member == FILTER_MEMBER
                    else (read_week_quantiles(wd) or {}).get("pf"))
            if held:
                return {"root": r, "member": member,
                        "started_utc": _utc(meta.get("started_utc")),
                        "replicates": st["replicates"],
                        "particles": st["particles"],
                        "engine_build": st.get("engine_build") or {}}
    return None


def plan(settings: Mapping, *, retro_root: Path) -> dict:
    """What an experiment runs: {"id", "experiment" (its fingerprint),
    "model", "model_fingerprint", "model_folder", "season", "size",
    "oracle", "locations", "weeks", "replicates", "particles",
    "reference", "findings"}. Refusal for MODEL_REF, MODEL_NOT_FOUND,
    MODEL_CHANGED, FORMAT_UNKNOWN, SEASON_NO_WEEKS and EXPERIMENT_CHANGED;
    NO_REFERENCE and GAMMA_ASSUMED are findings."""
    from app.core import retro
    s = read(settings)
    model = library.resolve(s["model"])
    weeks = []
    if s["season"] in retro.available_seasons():
        weeks = size_weeks(s["size"], retro.season_vintages(s["season"]),
                           retro.season_bounds(s["season"]), _has_round)
    if not weeks:
        raise Refusal(finding(
            "SEASON_NO_WEEKS", f"season {s['season']!r} has no week here for "
            f"a {s['size']} experiment: seasons here are "
            f"{', '.join(retro.available_seasons())}"))
    fp = fingerprint(s, model["fingerprint"])
    eid = experiment_id(s)
    had = (retro.read_meta(root() / eid).get("settings") or {}).get(
        "experiment")
    if had and had != fp:
        raise Refusal(finding(
            "EXPERIMENT_CHANGED", f"{eid} holds a replay of experiment "
            f"{library.short(had)}, and these settings are {library.short(fp)} "
            "(a size preset or the model's files changed): delete its folder "
            "to run it again"))
    found = []
    if s["oracle"] and "{{GAMMA}}" not in library.tokens(
            model["files"]["model.bngl"]):
        found.append(finding(
            "GAMMA_ASSUMED", f"{s['model']} lacks {{{{GAMMA}}}}, and the "
            "Oracle step assumes a removal rate of 7/3.2 per week"))
    ref = reference(retro_root, s["season"], s["oracle"], weeks)
    if ref is None:
        found.append(finding(
            "NO_REFERENCE", f"no shipped replay of {s['season']} here holds "
            f"the {'Oracle SIHRS' if s['oracle'] else 'Liu-West filter'} on "
            "the shipped settings: the summary will have no shipped side"))
    size = SIZES[s["size"]]
    return {"id": eid, "experiment": fp, "model": s["model"],
            "model_fingerprint": model["fingerprint"],
            "model_folder": model["folder"], "season": s["season"],
            "size": s["size"], "oracle": s["oracle"],
            "locations": size_locations(s["size"], _all_locations()),
            "weeks": weeks, "replicates": size.replicates,
            "particles": size.particles, "reference": ref,
            "findings": found}


# ------------------------------------------------------------- the summary

#: the per-cell columns summarise reads, beside location, fips, asof and
#: horizon
_SUMS = ("wis", "log_wis", "cov50", "cov80", "cov95")
_KEY = ["fips", "asof", "horizon"]


def _sum(col) -> float | None:
    """A column's sum, None when any cell lacks its value (as
    scoring.pooled_metrics then gives no figure)."""
    v = pd.to_numeric(col, errors="coerce")
    return None if v.isna().any() else float(v.sum())


def _count(col) -> int | None:
    """A 0/1 column's count, None when any cell lacks its value."""
    s = _sum(col)
    return None if s is None else int(round(s))


def _side(df, prefix: str) -> dict:
    """One side's sums: the model's columns, or the shipped side's s_*."""
    return {"wis": _sum(df[prefix + "wis"]),
            "log_wis": _sum(df[prefix + "log_wis"]),
            **{c: _count(df[prefix + c]) for c in ("cov50", "cov80", "cov95")}}


def _group(df, shipped: bool) -> dict:
    """One group: its cell count, the baseline's sums once, and each
    side's sums."""
    g = {"n": int(len(df)), "base_wis": _sum(df["base_wis"]),
         "base_log_wis": _sum(df["base_log_wis"]), "model": _side(df, "")}
    if shipped:
        g["shipped"] = _side(df, "s_")
    return g


def summarise(model_cells, shipped_cells) -> dict:
    """{"cells", "overall", "by_location", "by_week", "by_horizon", "us"}
    over the cells both sides scored, keyed (fips, asof, horizon): sums,
    from which a reader derives relWIS (wis / base_wis), log relWIS and
    coverage (covXX / n), equal to scoring.pooled_metrics on the same
    cells. The groupings cover the compared cells but US, each adding up
    to overall; "us" is the US cells alone (None when none was compared).
    Without a shipped frame the model's own scored cells are used and no
    group has a "shipped" side. Each frame has the columns location,
    fips, asof, horizon, wis, log_wis, cov50, cov80, cov95, base_wis,
    base_log_wis (scoring.score_quantiles with asof added)."""
    from app.core.us_national import US_FIPS
    cols = ["location"] + _KEY + list(_SUMS) + ["base_wis", "base_log_wis"]

    def frame(df):
        df = (pd.DataFrame(columns=cols) if df is None or not len(df)
              else df[cols].copy())
        df["horizon"] = df["horizon"].astype(int)
        df["asof"] = df["asof"].astype(str)
        return df.drop_duplicates(_KEY)

    def keys(df) -> set:
        """The frame's cells but US."""
        return set(map(tuple, df[df.fips != US_FIPS][_KEY].values))

    m = frame(model_cells)
    shipped = shipped_cells is not None
    if shipped:
        s = frame(shipped_cells)
        # the baseline is the same on both sides: kept once, the model's
        both = m.merge(s[_KEY + list(_SUMS)].rename(
            columns={c: "s_" + c for c in _SUMS}), on=_KEY)
        mk, sk = keys(m), keys(s)
        cells = {"compared": len(mk & sk), "model_only": len(mk - sk),
                 "shipped_only": len(sk - mk)}
    else:
        both = m
        cells = {"compared": int((m.fips != US_FIPS).sum()),
                 "model_only": 0, "shipped_only": 0}
    us, rest = both[both.fips == US_FIPS], both[both.fips != US_FIPS]
    by = {col: {str(k): _group(g, shipped) for k, g in rest.groupby(col)}
          for col in ("location", "asof", "horizon")}
    return {"cells": cells, "overall": _group(rest, shipped),
            "by_location": by["location"], "by_week": by["asof"],
            "by_horizon": by["horizon"],
            "us": _group(us, shipped) if len(us) else None}


def write_summary(folder: Path, summary: Mapping) -> Path:
    """summary.json in the folder, format_version stated, in the house
    JSON style; its path."""
    path = Path(folder) / SUMMARY
    library.write_json(path, {**summary, "format_version": SUMMARY_VERSION})
    return path


def read_summary(path: Path) -> dict:
    """A summary.json; FORMAT_UNKNOWN for any format_version but 1."""
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    got = obj.get("format_version") if isinstance(obj, dict) else None
    if type(got) is not int or got != SUMMARY_VERSION:   # true is not 1
        raise Refusal(finding(
            "FORMAT_UNKNOWN", f"{path} is format_version {got!r}; this "
            f"FluBNF reads {SUMMARY_VERSION} only", file=SUMMARY))
    return obj
