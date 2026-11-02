"""SANDBOX: experiments, one model replayed over one season at a preset
size and compared with the shipped replay: the formats, the plan, the
replay itself and its scoring (replay, run and score; the runner's queue,
app/core/runner.py, calls these).

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
                      (retro.run_season over the plan's weeks, frozen in
                      run_meta.json at the first start)
    QUEUED            on the runner only: empty, the experiment waits in
                      its queue (its mtime the time queued)

The id is derived, never typed: <name>[-v<n>]_<season>_<size>[_oracle],
so the same settings give the same folder and running again resumes.

A size is a preset of frozen constants (SIZES): its locations, its week
rule, replicates and particles. A changed preset or week rule gets a new
name, never an edit, and the experiment fingerprint hashes the constants
with the model's fingerprint, the season and the resolved Oracle setting,
so an edit cannot pass unnoticed.

A replay runs every planned week with the model named
(spec.extra["model"], which engines/pf.py prepare resolves), the shipped
Groundhog beside it and the Oracle step on or off; each week first checks
that the model still has the fingerprint the experiment planned.

The shipped side of a summary is the shipped replay of the season
(reference): the live root first, then the archived ones, newest first,
read through the read-only readers only; once compared, the same replay
is found again by its start time, archived or not. score rescores both
sides against one truth at every segment end (run), and stale says when
a summary no longer holds (truth moved, weeks stored since, the shipped
replay moved). Findings and refusals carry the codes of
app/core/problem_codes.py.

Student folders are read with care: a file is read only when it is a
regular file (a pipe in its place would wait for a writer), a folder is
an experiment's only when its experiment.json derives its name (find),
and a frozen week is read only when it is a date (_weeks).

On the runner each stored week is made lean (drop_samples): its
forecasting samples dropped once its quantile sidecar equals what they
give, which is all score reads of the model side (LEAN_KEEP).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from app.core import library
from app.core import sandbox as sb
from app.core.engines.pf import PREPARE_FAILURES_NAME
from app.core.problem_codes import Refusal, finding
from app.core.retro_store import DROPPED_NAME, ORACLE_NAME, QUANTILES_NAME

SETTINGS = "experiment.json"
SUMMARY = "summary.json"
#: the runner's queue flag in an experiment's folder (app/core/runner.py)
QUEUED = "QUEUED"
SUMMARY_VERSION = 1
FIELDS = ("model", "season", "size", "oracle")
REQUIRED = ("model", "season")
DEFAULT_SIZE = "smoke"
#: the models whose experiments run the Oracle step unless told not to
ORACLE_ON_BY_DEFAULT = ("sihrs",)
#: a season's name, as retro.available_seasons writes it: the id puts it
#: in a folder name
_SEASON_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
#: a folder name an id can be (find): no separator, no dot, so a name
#: posted to a page never leaves root()
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,200}")
#: a frozen week as run_season records it: a vintage's date, so a week
#: read from a run record never names a folder outside weeks/ (_weeks)
_WEEK_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

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


def _meta(folder: Path) -> dict:
    """A folder's run record, read only when run_meta.json is a regular
    file (a pipe in its place would wait for a writer); {} otherwise."""
    from app.core import retro
    if not os.path.isfile(retro.meta_path(folder)):   # False on any OSError
        return {}
    return retro.read_meta(folder)


def _weeks(st: Mapping) -> list[str]:
    """A run record's frozen weeks (settings.weeks) that are dates: a
    hand-edited record naming "../.." leads no reader or writer out of the
    folder. [] when it records none."""
    weeks = st.get("weeks") if isinstance(st, Mapping) else None
    if not isinstance(weeks, list):
        return []
    return [w for w in weeks if isinstance(w, str) and _WEEK_RE.fullmatch(w)]


def _shipped(meta: Mapping) -> bool:
    """A run record of the shipped replay: SHIPPED_SETTINGS held, no knobs,
    its settings an object."""
    st = (meta or {}).get("settings")
    return (isinstance(st, dict) and "knobs" not in st
            and all(st.get(k) == v for k, v in SHIPPED_SETTINGS.items()))


def _shipped_quantiles(root: Path, asof: str, member: str) -> dict | None:
    """One shipped week's member, {location: {"0".."3": {level: value}}},
    through the read-only readers only: oracle.json's Liu-West filter for
    pf_filter, the current sidecar's pf for pf. None when the week holds
    neither (a sidecar older than its samples included): never rebuilt,
    so nothing is written into the shipped tree."""
    from app.core.retro_store import (FILTER_MEMBER, _week_dir,
                                      filter_quantiles, read_week_quantiles)
    wd = _week_dir(Path(root), asof)
    if member == FILTER_MEMBER:
        return filter_quantiles(wd)
    return (read_week_quantiles(wd) or {}).get("pf")


def reference(retro_root: Path, season: str, oracle: bool,
              weeks: Sequence[str], *,
              started_utc: str | None = None) -> dict | None:
    """The shipped replay an experiment is compared with: the first of the
    season's live root and its archived roots (newest first) whose run
    record holds SHIPPED_SETTINGS, no knobs, and the member in at least one
    planned week ("pf", the Oracle step, when the step is on; "pf_filter",
    the Liu-West filter alone, when it is off). With started_utc, only the
    root that replay started at qualifies: the one a summary compared
    with, live or since archived. {"root", "member", "started_utc",
    "replicates", "particles", "engine_build"}, or None. Read-only: a
    sidecar is never written into the shipped tree."""
    from app.core import retro
    from app.core.retro_store import FILTER_MEMBER
    member = "pf" if oracle else FILTER_MEMBER
    roots = retro.list_archive_dirs(retro_root, season)
    if (Path(retro_root) / season).is_dir():
        roots.insert(0, Path(retro_root) / season)
    for r in roots:
        meta = retro.read_meta(r)
        if not _shipped(meta):
            continue
        if (started_utc is not None
                and _utc(meta.get("started_utc")) != started_utc):
            continue
        st = meta["settings"]
        for w in weeks:
            if _shipped_quantiles(r, w, member):
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
    # as run_season refuses it, before anything is written: a record of
    # another experiment, or one that names none (damaged, or weeks on
    # disk without one)
    folder = root() / eid
    st = _meta(folder).get("settings")
    recorded = (retro.meta_path(folder).exists()
                or bool(retro.season_week_files(folder)))
    if recorded and (not isinstance(st, dict) or st.get("experiment") != fp):
        had = st.get("experiment") if isinstance(st, dict) else None
        raise Refusal(finding(
            "EXPERIMENT_CHANGED",
            f"{eid} holds a replay of experiment {library.short(had)}, and "
            f"these settings are {library.short(fp)} (a size preset or the "
            "model's files changed): delete its folder to run it again"
            if isinstance(had, str) and had else
            f"{eid} holds a run record FluBNF cannot read as an "
            "experiment's: delete it to run it again"))
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


# --------------------------------------------------------------- the replay


def replay(settings: Path | Mapping, *, retro_root: Path,
           cancelled: Callable[[], bool] | None = None,
           after_week: Callable[[str], None] | None = None) -> dict:
    """Replay an experiment into its folder, root()/<id>: the settings read
    and the plan worked out (Refusal for any problem, before anything is
    written), the Groundhog's bank read and checked, experiment.json
    written, then retro.run_season over the plan's locations and weeks at
    its size, each week naming the model, refusing it (MODEL_CHANGED) if
    its fingerprint moved since the plan, running the shipped Groundhog
    and the Oracle step on or off. The run record gains model,
    model_fingerprint, experiment, oracle and the frozen weeks; the same
    settings run again resume on the weeks recorded at the first start.
    Synchronous: STOP and PAUSE in the folder (retro.request_stop,
    request_pause) work as for any replay, and a stop raises
    retro.SeasonStopped; so does cancelled() answering true before a week
    not yet stored (a stop asked before run_season cleared the flags).
    after_week(asof) is called after every week, stored, skipped or failed
    (run_season's progress; the runner makes each stored week lean there),
    and None calls nothing. Returns the plan, its weeks those recorded.
    run() adds the summary."""
    from app.core import retro
    from app.core.runs import oracle_label
    s = read(settings)
    p = plan(s, retro_root=retro_root)
    week_extra = _week_extra(p, cancelled)       # reads and checks the bank
    folder = root() / p["id"]
    folder.mkdir(parents=True, exist_ok=True)
    library.write_json(folder / SETTINGS, json.loads(settings_text(s)))
    retro.run_season(folder, p["season"], p["locations"],
                     replicates=p["replicates"], particles=p["particles"],
                     settings={"model": p["model"],
                               "model_fingerprint": p["model_fingerprint"],
                               "experiment": p["experiment"],
                               "oracle": ("applied" if p["oracle"] else
                                          oracle_label({"oracle": "none"}))},
                     week_extra=week_extra, weeks=p["weeks"],
                     progress=after_week)
    return {**p, "weeks": retro.read_meta(folder)["settings"]["weeks"]}


def _week_extra(p: Mapping, cancelled: Callable[[], bool] | None = None):
    """Each week's spec.extra for a plan: the shipped Groundhog's
    (an_engine.aux_preset, as a shipped replay runs it) with the model
    named, and oracle = none with the step off; the preset's name and the
    own-state pools it declares carried over, so the run record says which
    Groundhog ran. cancelled() answering true stops the season before the
    week (retro.SeasonStopped: the record says stopped, nothing is
    fitted). A week whose model no longer has the planned fingerprint (a
    version rewritten whole, a shipped template changed by an update) is
    refused, MODEL_CHANGED, before anything of it is prepared."""
    from app.core import retro
    from app.core.engines import analogue as an
    base = an.aux_preset(an.SHIPPED_AUX)
    ref, fp = p["model"], p["model_fingerprint"]
    add = {"model": ref} if p["oracle"] else {"model": ref, "oracle": "none"}

    def week_extra(asof, i, vintages):
        if cancelled and cancelled():
            raise retro.SeasonStopped("stop requested")
        now = library.resolve(ref)["fingerprint"]
        if now != fp:
            raise Refusal(finding(
                "MODEL_CHANGED", f"{ref} is {library.short(now)} now, and "
                f"this experiment started with {library.short(fp)}: {asof} "
                "is not fitted"))
        return {**base(asof, i, vintages), **add}
    week_extra.__name__ = (base.__name__
                           + ("" if p["oracle"] else "+oracle:none"))
    week_extra.local_pools = base.local_pools
    return week_extra


def preflight(settings: Path | Mapping, *, retro_root: Path) -> dict:
    """What a start would run, checked before the engine is claimed for
    hours: plan() (its refusals pass through) plus "weeks" (the frozen
    list when the folder records one), "resume" (a week is stored),
    "weeks_done" and "complete", its "reference" the shipped replay the
    folder's summary was compared with when that replay is still here (as
    score keeps it). MACHINE when the folder's run record says a replay
    of it is under way in another process (a console refuses its own
    first, by its claim), when the Groundhog's bank cannot be read or
    checked, at a resume when this machine's engine build is not the one
    the stored weeks were fitted by, when a week not stored began its fits
    on the other engine, for the two-strain model on the public engine
    (which refuses every cell of it), and when the engine here is older
    than this console (pf.prepare would refuse every week; with no engine
    at all the callers say so in their own words), but never for the
    engine once every week is stored: nothing is left to fit. Writes
    nothing."""
    from app.core import retro
    from app.core.engines import pf as pf_engine
    p = plan(settings, retro_root=retro_root)
    # one writer per folder: a second run_season would clear the first's
    # STOP and PAUSE (a dead worker's record reads interrupted, not active)
    if status(root() / p["id"])["status"] in retro.ACTIVE_STATUSES:
        raise Refusal(finding(
            "MACHINE", f"{p['id']} is replaying in another process; stop "
            "it first"))
    try:
        _week_extra(p)                           # reads and checks the bank
    except Refusal:
        raise
    except Exception as e:
        raise Refusal(finding("MACHINE", str(e)[:300])) from None
    st = _meta(root() / p["id"]).get("settings")
    st = st if isinstance(st, dict) else {}
    weeks = _weeks(st) if isinstance(st.get("weeks"), list) else p["weeks"]
    done = [w for w in weeks if retro.week_done(root() / p["id"], w)]
    complete = bool(weeks) and len(done) == len(weeks)
    if done and not complete:
        change = retro.engine_build_change(st, "pf")
        if change:
            raise Refusal(finding(
                "MACHINE", f"{p['id']} has weeks that {change}: resuming "
                "would mix two engine builds. Switch the engine back to "
                "resume it, or delete the experiment to replay it on this "
                "one."))
    here = "public" if pf_engine._public() else "private"
    if not complete:
        # a week stopped on one engine before it was stored: run_season
        # would stop on it (retro._week_engine), and no stored week tells
        # the build check above
        for w in weeks:
            if w in done:
                continue
            had = _begun_elsewhere(root() / p["id"], w, here)
            if had:
                raise Refusal(finding(
                    "MACHINE", f"week {w} of {p['id']} began on the {had} "
                    f"engine, and resuming it on the {here} one would pool "
                    "fits from two engines in one week: switch this "
                    f"install to the {had} engine ({_switch_step(had)}) to "
                    "finish it, or delete the experiment to replay it on "
                    "this one"))
    if not complete and here == "public" and _two_strain(p["model"]):
        # refused here, not cell by cell after each network is generated
        from app.core.engines import lwf
        key = "pf_binom_neff_cap"
        raise Refusal(finding(
            "MACHINE", f"{p['model']} runs on the private engine only: its "
            f"cells set {key} ({lwf._NO_COUNTERPART[key]}), which has no "
            "counterpart in the public engine, so every cell would be "
            "refused. Switch this install to the private engine "
            f"({_switch_step('private')}) to run it."))
    if (not complete and pf_engine.engine_available()
            and not pf_engine.engine_current()):
        raise Refusal(finding("MACHINE", pf_engine.engine_stale_message()))
    ref = p["reference"]
    try:
        was = _previous(root() / p["id"]).get("shipped")
    except Refusal:
        was = None                               # a newer FluBNF's summary
    if ref is not None and isinstance(was, dict) and was.get("started_utc"):
        ref = reference(retro_root, p["season"], p["oracle"], weeks,
                        started_utc=was["started_utc"]) or ref
    return {**p, "reference": ref, "weeks": weeks, "resume": bool(done),
            "weeks_done": len(done), "complete": complete}


def _begun_elsewhere(folder: Path, asof: str, here: str) -> str | None:
    """The engine other than `here` a week's fits began on
    (retro.WEEK_ENGINE_NAME, beside its fit markers) when one of them
    finished there and did not fail (run_week tries a failed fit again
    on either engine); None otherwise. The record is read only when it
    is a regular file."""
    from app.core import retro
    from app.core.retro_store import _week_dir
    wd = _week_dir(folder, asof)
    f = wd / retro.WEEK_ENGINE_NAME
    if not os.path.isfile(f):
        return None
    try:
        had = json.loads(f.read_text(encoding="utf-8")).get("engine")
    except (OSError, ValueError, AttributeError):
        return None
    if not had or had == here:
        return None
    ok = retro.cells_done(wd) - set(retro.cells_failed(wd))
    return str(had) if ok else None


def _switch_step(engine: str) -> str:
    """The step that switches this install to `engine`: its launcher's
    record, which every open reads over the shell's FLUBNF_ENGINE (and
    which a terminal start must match, runner._engine_record_problem)."""
    from flubnf.settings import _windows
    return (f"setup.ps1 -Engine {engine}" if _windows()
            else f"./setup_engine.sh --{engine}")


def _two_strain(ref: str) -> bool:
    """A model prepare writes as the two-strain variant: a shipped one
    with {{A0SHARE}} (engines/pf.py _named_model)."""
    model = library.resolve(ref)
    return model["shipped"] and "{{A0SHARE}}" in library.tokens(
        model["files"]["model.bngl"])


def _engine_of(build) -> str:
    """The engine a recorded build names: public when it says so, else
    private (a build recorded without one, or none recorded)."""
    named = build.get("engine") if isinstance(build, Mapping) else None
    return "public" if named == "public" else "private"


def started(p: Mapping) -> dict:
    """Start's answer for a preflight p about to run (not complete):
    {"text" (started or resumed, or that there is nothing to compare it
    with), "detail" (the notes: the shipped replay compared with, that it
    ran on the other engine when it did, and each finding with its code),
    "kind" ("ok" with a shipped replay to compare with, else "warn"),
    "plan" (the plan as Start's JSON gives it)}."""
    eid = p["id"]
    ref, weeks, done = p["reference"], len(p["weeks"]), p["weeks_done"]
    if p["resume"]:
        text = f"Resumed {eid}: {done} of {weeks} weeks were stored already."
    else:
        text = (f"Started {eid}: {weeks} weeks of {p['season']}, "
                f"{len(p['locations'])} locations.")
    notes = []
    if ref is not None:
        notes.append(f"Compared with the shipped replay of {p['season']} ("
                     + ("the Oracle SIHRS" if ref["member"] == "pf"
                        else "the Liu-West filter alone")
                     + ") on the cells both score.")
        # allowed, and said: the shipped replays record no engine and
        # ran on the private one
        from flubnf.settings import engine_choice
        here, there = engine_choice(), _engine_of(ref.get("engine_build"))
        if here != there:
            notes.append(f"Compared across engines: this experiment runs on "
                         f"the {here} engine, the shipped replay ran on the "
                         f"{there} one.")
    else:
        # nothing to compare with leads; a resume's count goes to the "?"
        if p["resume"]:
            notes.append(f"{done} of {weeks} weeks were stored already.")
        text = (f"{'Resumed' if p['resume'] else 'Started'} {eid}; nothing "
                "to compare it with.")
    for f in p["findings"]:
        said = f"{f['text']} ({f['code']})"
        notes.append(said if f["code"] == "NO_REFERENCE"
                     else f"Worth a look: {said}")
    plan = {k: p[k] for k in ("model", "model_fingerprint", "experiment",
                              "season", "size", "oracle", "locations",
                              "weeks", "replicates", "particles")}
    plan["reference"] = None if ref is None else {
        "member": ref["member"], "root": _repo_path(ref["root"]),
        "started_utc": ref["started_utc"]}
    return {"text": text, "detail": " ".join(notes),
            "kind": "ok" if ref is not None else "warn", "plan": plan}


def finished_mark(folder: Path):
    """The run record's finished_utc, or None (no record, or a segment
    under way): a segment has ended when it changes."""
    return _meta(folder).get("finished_utc")


def segment_ended(folder: Path, before) -> bool:
    """Whether a segment ended since finished_mark gave `before`: the run
    record's finished_utc changed (run_season sets it on every way out,
    done, stopped or error) and at least one week is stored. A call
    refused before its record opened changes nothing."""
    from app.core import retro
    now = finished_mark(folder)
    return (now is not None and now != before
            and bool(retro.season_week_files(folder)))


def run(settings: Path | Mapping, *, retro_root: Path,
        flubnf_build: str | None = None,
        cancelled: Callable[[], bool] | None = None,
        after_week: Callable[[str], None] | None = None) -> dict:
    """replay(), then summary.json scored whenever the segment ended, on
    every way out (finished, stopped, the engine changed, every week
    failed): the queue's runner and flubnf experiment call this. A scoring
    failure goes to stderr and never hides the replay's outcome; an
    interrupt is not scored (stale() names it on the next view). Returns
    what replay returns, and raises what it raises."""
    s = read(settings)
    folder = root() / experiment_id(s)
    before = finished_mark(folder)
    try:
        out = replay(s, retro_root=retro_root, cancelled=cancelled,
                     after_week=after_week)
    except Exception:
        _score_if_ended(folder, before, retro_root, flubnf_build)
        raise
    _score_if_ended(folder, before, retro_root, flubnf_build)
    return out


def _score_if_ended(folder: Path, before, retro_root: Path,
                    flubnf_build: str | None) -> None:
    """score() when segment_ended holds; its failure in words on stderr."""
    if not segment_ended(folder, before):
        return
    try:
        score(folder, retro_root=retro_root, flubnf_build=flubnf_build)
    except Exception as e:
        print(f"experiments: {folder.name} not scored: {e}", file=sys.stderr)


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


def summary_or_problem(folder: Path) -> tuple[dict | None, str]:
    """An experiment's summary.json as its page shows it: (the summary as
    read, "") when it reads; (None, the words) when a newer FluBNF wrote
    it (its format_version said) or it cannot be read; (None, "") with
    none."""
    summary, problem = None, ""
    path = Path(folder) / SUMMARY
    if path.is_file():
        try:
            summary = read_summary(path)
        except Refusal:                         # FORMAT_UNKNOWN
            try:
                v = json.loads(path.read_text(encoding="utf-8")).get(
                    "format_version")
            except (OSError, ValueError, AttributeError, RecursionError):
                v = None
            problem = (f"summary.json was written by a newer FluBNF "
                       f"(format_version {v}); this one reads "
                       f"{SUMMARY_VERSION} only."
                       if type(v) is int and v > SUMMARY_VERSION
                       else "summary.json cannot be read")
        except (OSError, ValueError, RecursionError):
            problem = "summary.json cannot be read"
    return summary, problem


# ------------------------------------------------------------- the scoring

#: a failures.log entry's first line (retro.run_season, retro.run_week);
#: a line that does not start so belongs to the entry before it
_LOG_RE = re.compile(r"(\d{4}-\d{2}-\d{2}): (.*)")
#: a fit's tag, <location tag>_r<replicate> (engines/pf.py prepare)
_CELL_RE = re.compile(r"(.+)_r(\d+)")
#: the most failure entries a summary keeps, and the words of each
_FAILURES_MAX, _TEXT_MAX = 100, 200
#: the truth file's sha256 keyed by (path, mtime_ns, size): 1-30 ms a
#: hash, and stale() asks on every view
_TRUTH_SHA: dict = {}


def _truth() -> tuple[Path, str, str]:
    """(file, source words, sha256) of exactly the file scoring.load_truth
    reads: the hub's target file ("settled"), else the newest archived
    vintage ("vintage <date>"); FileNotFoundError, in load_truth's words,
    with neither."""
    from app.core import scoring
    from app.core.data import vintage_path, vintages
    from flubnf.vintages import sha256_of
    target = scoring.HUB / "target-data/target-hospital-admissions.csv"
    source = "settled"
    if not target.is_file():
        vs = vintages()
        if not vs:
            raise FileNotFoundError(
                f"no settled truth: {target} missing and no dated vintages "
                f"in {scoring.HUB}/auxiliary-data/target-data-archive. "
                "Update the hub clone from the Data tab.")
        target, source = Path(vintage_path(vs[-1])), f"vintage {vs[-1]}"
    st = target.stat()
    key = (str(target), st.st_mtime_ns, st.st_size)
    sha = _TRUTH_SHA.get(key)
    if sha is None:
        sha = sha256_of(target)
        if len(_TRUTH_SHA) > 16:
            _TRUTH_SHA.clear()
        _TRUTH_SHA[key] = sha
    return target, source, sha


def _cells(by_week: Mapping[str, Mapping | None], locations, truth,
           n2f) -> pd.DataFrame:
    """One side's scored cells: each week's quantiles (None: no cells)
    kept to the run's locations, scored by scoring.score_quantiles with
    asof added; pd.DataFrame() when nothing is scored."""
    from app.core import scoring
    keep = set(locations)
    frames = []
    for w, q in by_week.items():
        if q is None:
            continue
        df = scoring.score_quantiles({k: v for k, v in q.items() if k in keep},
                                     w, n2f, truth)
        if len(df):
            df["asof"] = w
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _log_entries(folder: Path) -> dict:
    """{week: the text of its last failures.log entry}, continuation lines
    joined; {} when there is no log (a regular file) to read."""
    p = Path(folder) / "failures.log"
    if not os.path.isfile(p):
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out, week = {}, None
    for line in text.splitlines():
        m = _LOG_RE.fullmatch(line)
        if m:
            week = m.group(1)
            out[week] = [m.group(2)]         # the last entry wins
        elif week is not None:
            out[week].append(line)
    return {w: "\n".join(lines) for w, lines in out.items()}


def _failures(folder, weeks, locations, replicates,
              own) -> tuple[int, list[dict]]:
    """(failed_fits, entries): the fits with no forecast, summed over the
    planned weeks. A stored week whose model side was read (own[week]) counts
    each planned location it lacks as `replicates` fits (its prepare
    failure and failed markers its entries, else "no forecast stored for
    this location") and each other failed marker as 1; one whose model
    side cannot be read counts its markers (1 each) and prepare failures
    (`replicates` each). A week not stored that failures.log names counts
    every fit, with that week's last entry; a week only stopped is not a
    failure, and the log, append-only, is never read for a stored week.
    Entries {week, location?, replicate?, text} sorted by week, location
    and replicate, at most 100, each text at most 200 characters."""
    from app.core import retro
    from app.core.engines import pf as pf_engine
    from app.core.retro_store import _week_dir
    folder = Path(folder)
    name = {pf_engine._hub_tag(l): l for l in locations}
    n, entries, log = 0, [], None

    def add(week, text, location=None, replicate=None):
        e = {"week": week, "text": str(text)[:_TEXT_MAX]}
        if location is not None:
            e["location"] = location
        if replicate is not None:
            e["replicate"] = replicate
        entries.append(e)

    for w in weeks:
        if not retro.week_done(folder, w):
            if log is None:
                log = _log_entries(folder)
            if w in log:
                n += len(locations) * replicates
                add(w, log[w])
            continue
        wd = _week_dir(folder, w)
        prep = {name.get(t, t): x for t, x in
                pf_engine.read_prepare_failures(wd).items()}
        marks: dict = {}
        for key, text in retro.cells_failed(wd).items():
            m = _CELL_RE.fullmatch(key)
            loc, rep = ((name.get(m.group(1), m.group(1)), int(m.group(2)))
                        if m else (key, None))
            marks.setdefault(loc, []).append((rep, text))
        q = own.get(w)
        absent = [] if q is None else [l for l in locations if l not in q]
        if q is None:                    # the model side cannot be read
            for loc, text in prep.items():
                n += replicates
                add(w, text, loc)
        for loc in absent:
            n += replicates
            if loc in prep:
                add(w, prep[loc], loc)
            for rep, text in marks.get(loc, ()):
                add(w, text, loc, rep)
            if loc not in prep and loc not in marks:
                add(w, "no forecast stored for this location", loc)
        for loc, ms in marks.items():
            if loc not in absent:
                n += len(ms)
                for rep, text in ms:
                    add(w, text, loc, rep)
    entries.sort(key=lambda e: (e["week"], e.get("location", ""),
                                e.get("replicate", -1)))
    return n, entries[:_FAILURES_MAX]


def _previous(folder: Path) -> dict:
    """The summary.json there now, as read_summary reads it; {} when there
    is none (a regular file) or it cannot be read. FORMAT_UNKNOWN for one
    a newer FluBNF wrote, which is never overwritten."""
    p = Path(folder) / SUMMARY
    if not os.path.isfile(p):
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    got = obj.get("format_version") if isinstance(obj, dict) else None
    if type(got) is int and got > SUMMARY_VERSION:
        raise Refusal(finding(
            "FORMAT_UNKNOWN", f"{p} was written by a newer FluBNF "
            f"(format_version {got}); this one reads {SUMMARY_VERSION} only "
            "and leaves it as it is", file=SUMMARY))
    return obj if type(got) is int and got == SUMMARY_VERSION else {}


def score(folder: Path, *, retro_root: Path,
          flubnf_build: str | None = None) -> dict:
    """Score an experiment's folder and write its summary.json (step 1's
    format, version 1); the record written. Both sides are rescored
    against one truth, hashed before it is read: the model's own stored
    weeks (retro_store.week_member_quantiles, which may write a sidecar
    into this folder) and the shipped replay's weeks this one stored,
    through the read-only readers, the replay first compared with found
    again by its start time (reference), else the season's reference now.
    With the step on, a shipped week's US is compared only when it is the
    same kind of US forecast (us_national.us_step_week). flubnf_build None
    (a view's rescore) keeps the build the previous summary named.
    EXPERIMENT_UNREADABLE when the folder holds no experiment's settings
    and run record; FORMAT_UNKNOWN when a newer FluBNF wrote the summary
    there."""
    from app.core import retro, scoring
    from app.core import retro_store as RS
    from app.core.us_national import is_us, us_step_week
    t0 = time.time()
    folder = Path(folder)
    if not os.path.isfile(folder / SETTINGS):
        raise Refusal(finding("EXPERIMENT_UNREADABLE",
                              f"{folder.name} has no {SETTINGS}",
                              file=SETTINGS))
    s = read(folder / SETTINGS)
    eid = experiment_id(s)
    if eid != folder.name:
        raise Refusal(finding(
            "EXPERIMENT_UNREADABLE", f"{folder / SETTINGS} is experiment "
            f"{eid}, not {folder.name}", file=SETTINGS))
    meta = _meta(folder)
    st = meta.get("settings")
    if not isinstance(st, dict) or not st.get("experiment"):
        raise Refusal(finding(
            "EXPERIMENT_UNREADABLE",
            f"{eid} has no run record of an experiment to score"))
    prev = _previous(folder)
    weeks = _weeks(st)
    locations = [str(l) for l in st.get("locations") or ()]
    replicates = int(st.get("replicates") or 0)
    # hashed before it is read: a file replaced between the two leaves the
    # old hash recorded, so the next stale() rescores
    _path, source, sha = _truth()
    truth, n2f = scoring.load_truth()
    stored = [w for w in weeks if retro.week_done(folder, w)]
    own = {}
    for w in weeks:
        try:
            own[w] = (RS.week_member_quantiles(folder, w).get("pf")
                      if w in stored else None)
        except Exception:
            own[w] = None                 # a stored week that cannot be read
    was = prev.get("shipped") if isinstance(prev.get("shipped"), dict) else {}
    ref = None
    if was.get("started_utc"):
        ref = reference(retro_root, s["season"], s["oracle"], weeks,
                        started_utc=was["started_utc"])
    if ref is None:
        ref = reference(retro_root, s["season"], s["oracle"], weeks)
    shipped_cells = None
    if ref is not None:
        sq = {}
        for w in stored:
            q = _shipped_quantiles(ref["root"], w, ref["member"])
            if q and ref["member"] == "pf" and any(map(is_us, locations)):
                kind = us_step_week(RS._week_dir(Path(ref["root"]), w))
                if kind is None or kind != us_step_week(
                        RS._week_dir(folder, w)):
                    q = {k: v for k, v in q.items() if not is_us(k)}
            sq[w] = q
        shipped_cells = _cells(sq, locations, truth, n2f)
    out = summarise(_cells(own, locations, truth, n2f), shipped_cells)
    failed, failures = _failures(folder, weeks, locations, replicates, own)
    ran_before = prev.get("ran") if isinstance(prev.get("ran"), dict) else {}
    record = {
        **out,
        "complete": bool(weeks) and len(stored) == len(weeks),
        "id": eid, "experiment": st.get("experiment"),
        "model_fingerprint": st.get("model_fingerprint"),
        "model": s["model"], "season": s["season"], "size": s["size"],
        "oracle": s["oracle"],
        "ran": {"locations": locations, "weeks": weeks,
                "replicates": replicates,
                "particles": int(st.get("particles") or 0),
                "failed_fits": failed,
                "seconds": round(retro.elapsed_now(meta), 1),
                "started_utc": _utc(meta.get("started_utc")),
                "finished_utc": _utc(meta.get("finished_utc")),
                "disk_bytes": retro.dir_size(folder),
                "engine_build": st.get("engine_build") or {},
                "flubnf_build": (flubnf_build if flubnf_build is not None
                                 else str(ran_before.get("flubnf_build")
                                          or ""))},
        "shipped": None if ref is None else {
            "member": ref["member"], "root": _repo_path(ref["root"]),
            "started_utc": ref["started_utc"],
            "replicates": ref["replicates"], "particles": ref["particles"],
            "engine_build": ref["engine_build"]},
        "scored": {"utc": _utc(t0), "truth": source, "truth_sha256": sha,
                   "scores_v": retro.SCORES_V},
        "failures": failures}
    write_summary(folder, record)
    return {**record, "format_version": SUMMARY_VERSION}


def figures(group: Mapping | None) -> dict | None:
    """A summary group's figures from its sums, equal to
    scoring.pooled_metrics on the same cells: {"n", "model": {"rel",
    "log_rel", "cov": {"50", "80", "95"}}, "shipped": {same} or None,
    "vs_shipped": {"wis", "log_wis"} (this model's sums over the shipped
    replay's) or None}. A ratio is None when n is 0 or a sum it needs is
    absent or its denominator 0; cov is None when any band is. None for
    no group."""
    if not isinstance(group, Mapping):
        return None
    try:
        n = int(group.get("n") or 0)
    except (TypeError, ValueError):
        n = 0

    def ratio(num, den):
        try:
            return (float(num) / float(den)
                    if n and num is not None and den else None)
        except (TypeError, ValueError):
            return None

    def side(g):
        cov = [ratio(g.get(f"cov{b}"), n) for b in ("50", "80", "95")]
        return {"rel": ratio(g.get("wis"), group.get("base_wis")),
                "log_rel": ratio(g.get("log_wis"), group.get("base_log_wis")),
                "cov": (None if None in cov
                        else dict(zip(("50", "80", "95"), cov)))}
    m = group.get("model") if isinstance(group.get("model"), Mapping) else {}
    s = group.get("shipped")
    s = s if isinstance(s, Mapping) else None
    return {"n": n, "model": side(m),
            "shipped": side(s) if s is not None else None,
            "vs_shipped": None if s is None else {
                "wis": ratio(m.get("wis"), s.get("wis")),
                "log_wis": ratio(m.get("log_wis"), s.get("log_wis"))}}


def _newest(root: Path) -> float:
    """The newest stored week's mtime under a replay root, its samples
    file's or, for a week stored lean, its sidecar's (float seconds, which
    retro.newest_samples_mtime truncates); 0.0 with none."""
    from app.core.retro_store import season_week_files
    best = 0.0
    for p in season_week_files(root):
        try:
            best = max(best, p.stat().st_mtime)
        except OSError:
            pass
    return best


def _repo_path(p: Path) -> str:
    """A path as a summary records it: relative to the repository, in
    forward slashes, else absolute (a root outside it, as in the tests)."""
    p = Path(p)
    try:
        return p.relative_to(sb.REPO).as_posix()
    except ValueError:
        return str(p.absolute())


def stale(folder: Path, *, retro_root: Path | None = None) -> str:
    """Why the folder's summary.json no longer holds, in words; "" when it
    does, or when there is nothing to score again: a replay under way (the
    files say so, whichever process runs it), no week stored, or a summary
    a newer FluBNF wrote (never overwritten). Otherwise the first of: not
    scored yet, unreadable, a segment ended after it was scored, weeks
    stored since, another scoring rule, the truth data changed (when
    there is truth to read), and the shipped replay compared with moved
    or stored weeks since. With retro_root, the shipped replay the
    summary names must be a child of it, by name and with no "..": any
    other reads as moved, and nothing under it is read. Stat calls, one
    small run record and one hash cached by stat."""
    from app.core import retro
    folder = Path(folder)
    meta = _meta(folder)
    try:
        if retro.effective_status(meta) in retro.ACTIVE_STATUSES:
            return ""
    except (TypeError, ValueError):
        pass                              # a damaged record runs nothing
    if not retro.season_week_files(folder):
        return ""
    path = folder / SUMMARY
    if not os.path.isfile(path):
        return "not scored yet"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        mtime = path.stat().st_mtime
    except (OSError, ValueError, RecursionError):
        return "its summary cannot be read"
    got = obj.get("format_version") if isinstance(obj, dict) else None
    if type(got) is int and got > SUMMARY_VERSION:
        return ""
    if type(got) is not int or got != SUMMARY_VERSION:
        return "its summary cannot be read"
    try:
        if float(meta.get("finished_utc")) > mtime:
            return "a segment ended after it was scored"
    except (TypeError, ValueError):
        pass
    if _newest(folder) > mtime:
        return "weeks were stored since it was scored"
    scored = obj.get("scored") if isinstance(obj.get("scored"), dict) else {}
    if scored.get("scores_v") != retro.SCORES_V:
        return "the scoring rule changed"
    try:
        sha = _truth()[2]
    except (OSError, ValueError):
        sha = None                        # no truth here: kept, not lost
    if sha is not None and sha != scored.get("truth_sha256"):
        return "the truth data changed"
    shipped = obj.get("shipped")
    if isinstance(shipped, dict) and isinstance(shipped.get("root"), str):
        ref = Path(shipped["root"])
        ref = ref if ref.is_absolute() else sb.REPO / ref
        # lexical, not resolved: an archived root may be a link
        if retro_root is not None and (
                ".." in ref.parts
                or ref.parent != Path(os.path.abspath(retro_root))):
            return "the shipped replay it was compared with moved"
        if _utc(_meta(ref).get("started_utc")) != shipped.get("started_utc"):
            return "the shipped replay it was compared with moved"
        if _newest(ref) > mtime:
            return "the shipped replay stored weeks since"
    return ""


# ------------------------------------------------- lean storage (the runner)

#: what a week stored lean keeps (drop_samples): the quantile sidecar
#: score reads the model side from, oracle.json (the US step test and the
#: Liu-West filter's quantiles), the donor bank (provenance, as
#: reclaim.WEEK_KEEP keeps it), the fit markers and prepare failures
#: _failures counts (retro.CELL_DONE_DIRNAME, pf.PREPARE_FAILURES_NAME),
#: and the marker itself
LEAN_KEEP = (QUANTILES_NAME, ORACLE_NAME, "oracle_bank", "cells_done",
             PREPARE_FAILURES_NAME, DROPPED_NAME)


def _real_dir(p: Path) -> bool:
    """A folder itself, not a link to one (lstat)."""
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except OSError:
        return False


def drop_samples(folder: Path, asof: str) -> int:
    """Store one week of an experiment lean, on the runner only: its
    forecasting samples dropped once its quantile sidecar is checked
    against them, and every entry but LEAN_KEEP pruned. The bytes freed.

    0, with nothing touched, unless the folder is an experiment's (find;
    a run record naming an experiment), asof one of its frozen weeks,
    weeks/ and the week real folders (lstat), the week outside every
    protected tree (reclaim.is_protected), and the folder not replayed by
    another process: this process's own replay drops its weeks as it
    goes. A shipped, archived or imported root holds no experiment.json,
    so no marker is ever written there. A week stored lean already has
    only its leftovers pruned.

    The sidecar must hold pf and equal what the draws give
    (retro_store.member_quantiles) exactly, pf and analogue, and pf_filter
    whenever the draws give it; otherwise nothing is written, for a
    sidecar is never rebuilt here. The marker (retro_store.DROPPED_NAME:
    the samples' bytes and the time) is written before the samples are
    unlinked, so a kill between the two leaves a week that reads as
    before, and the next drop finishes it. Never raises."""
    from app.core import reclaim, retro
    from app.core import retro_store as RS
    folder, freed = Path(folder), 0
    try:
        if find(folder.name, under=folder.parent) != folder:
            return 0
        meta = _meta(folder)
        st = meta.get("settings")
        if (not isinstance(st, dict) or not st.get("experiment")
                or not isinstance(asof, str) or asof not in _weeks(st)):
            return 0
        wd = RS._week_dir(folder, asof)
        if (not _real_dir(folder / "weeks") or not _real_dir(wd)
                or reclaim.is_protected(wd)):
            return 0
        try:
            active = retro.effective_status(meta) in retro.ACTIVE_STATUSES
        except (TypeError, ValueError):
            active = True                 # a damaged record: left alone
        if active and meta.get("pid") != os.getpid():
            return 0
        if not RS._lean(wd):
            sp = RS.samples_file(wd)
            if sp is None:
                return 0
            mq = RS.read_week_quantiles(wd)
            if mq is None or "pf" not in mq:
                return 0
            want = RS.member_quantiles(RS.read_samples(sp), wd)
            if (mq["pf"] != want.get("pf")
                    or mq.get("analogue") != want.get("analogue")
                    or (RS.FILTER_MEMBER in want
                        and mq.get(RS.FILTER_MEMBER)
                        != want[RS.FILTER_MEMBER])):
                return 0
            samples = [wd / n for n in (RS.SAMPLES_JSON, RS.SAMPLES_GZ)
                       if (wd / n).is_file()]
            size = sum(p.stat().st_size for p in samples)
            tmp = wd / (DROPPED_NAME + ".tmp")
            tmp.unlink(missing_ok=True)   # a drop killed before its replace
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o644)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"bytes": size, "utc": _utc(time.time())},
                                   sort_keys=True))
            os.replace(tmp, wd / DROPPED_NAME)
            for p in samples:
                p.unlink()
            freed += size
        for p in sorted(wd.iterdir()):
            if p.name in LEAN_KEEP:
                continue
            if p.is_symlink() or not p.is_dir():
                n = os.lstat(p).st_size
                p.unlink()
            else:
                n = retro.dir_size(p)
                retro.delete_tree(p)
            freed += n
    except Exception:
        pass                              # what was freed so far stays freed
    return freed


# -------------------------------------------------------------- the folders


def status(folder: Path) -> dict:
    """Where an experiment's replay stands, from its run record and week
    folders (never summary.json): {"status" (retro.effective_status, ""
    with no record, "stopping" for a running record with STOP written,
    "error" with its text in "error"), "error", "stop_reason",
    "weeks_total", "weeks_done", "complete", "queued" (QUEUED a regular
    file and the record not under way: it waits in the runner's queue),
    "week" (the first frozen week not stored, while under way, else
    None), "fits_done", "fits_total"
    (that week's), "elapsed_s", "eta_s" (the mean week times the weeks
    left, once a week is timed and while under way, else None),
    "started_utc", "finished_utc"}."""
    from app.core import retro
    from app.core.retro_store import _week_dir
    folder = Path(folder)
    meta = _meta(folder)
    st = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
    try:
        state = retro.effective_status(meta) if meta else ""
        t = retro.timing(meta)
    except (TypeError, ValueError):       # a record edited by hand
        state, t = "interrupted", {"elapsed_s": 0.0, "mean_s": None}
    error = ""
    if state.startswith("error"):
        state, _, error = state.partition(":")
        error = error.strip()
    if state == "running" and retro.stop_path(folder).exists():
        state = "stopping"
    weeks = _weeks(st)
    done = [w for w in weeks if retro.week_done(folder, w)]
    active = state in retro.ACTIVE_STATUSES
    try:
        queued = (not active
                  and stat.S_ISREG(os.lstat(folder / QUEUED).st_mode))
    except OSError:
        queued = False
    week = next((w for w in weeks if w not in done), None) if active else None
    total = fits = 0
    if week:
        try:
            total = (len(st.get("locations") or ())
                     * int(st.get("replicates") or 0))
        except (TypeError, ValueError):
            total = 0
        fits = min(len(retro.cells_done(_week_dir(folder, week))), total)
    left = len(weeks) - len(done) - (fits / total if total else 0)
    eta = (t["mean_s"] * max(0.0, left)
           if active and t["mean_s"] is not None else None)
    return {"status": state, "error": error,
            "stop_reason": str(meta.get("stop_reason") or ""),
            "weeks_total": len(weeks), "weeks_done": len(done),
            "complete": bool(weeks) and len(done) == len(weeks),
            "queued": queued,
            "week": week, "fits_done": fits, "fits_total": total,
            "elapsed_s": round(float(t["elapsed_s"]), 1), "eta_s": eta,
            "started_utc": _utc(meta.get("started_utc")),
            "finished_utc": _utc(meta.get("finished_utc"))}


def line(st: dict, claimed=False, queue: dict | None = None) -> str:
    """The running card's one line: queued for the runner (`queue`,
    runner.position's: its place, when it starts, about how long it runs,
    the disk it needs, and why it waits), starting (on the runner when
    `claimed` is "runner": runner.json's job names it), stopping, paused,
    or the week under way, its fits, the time so far and, once a week is
    timed, about how long is left; "" otherwise."""
    from app.core import retro, runner
    state = st["status"]
    if queue is not None:
        parts = ["Queued", f"{runner._ordinal(queue['position'])} in line"]
        if not queue["runner"]:
            parts.append("the runner is not running")
        elif queue["wait_s"] >= 60:
            parts.append("starts in " + sb.eta_words(queue["wait_s"],
                                                     queue["wait_s"]))
        else:
            parts.append("starts within a minute")
        if queue["seconds"] > 0:
            parts.append("runs " + sb.eta_words(queue["seconds"],
                                                queue["seconds"]))
        if queue["peak_bytes"] > 0:
            parts.append("needs about "
                         f"{retro.human_bytes(queue['peak_bytes'])} of disk")
        if queue["why"]:
            parts.append(queue["why"])
        return " · ".join(parts)
    if claimed and state not in retro.ACTIVE_STATUSES:
        return ("Starting on the runner…" if claimed == "runner"
                else "Starting…")
    so_far = f"{sb.clock(st['elapsed_s'])} so far"
    if state == "stopping":
        return f"Stopping after the fits in flight · {so_far}"
    if state == "paused":
        return f"Paused · {so_far}"
    if state != "running":
        return ""
    line = (f"{st['week']}: {st['fits_done']} of {st['fits_total']} fits · "
            f"{so_far}" if st["week"] else so_far)
    if st["eta_s"] is not None:
        line += f" · about {sb.clock(st['eta_s'])} left"
    return line


def badge(st: dict, claimed=False, queue: dict | None = None,
          refused: str = "") -> tuple[str, str]:
    """(state, words) of an experiment's badge: queued (its place in line,
    or that the runner is not running), starting, refused by the runner
    (runner.refusal's words given), running, stopping, paused, stopped or
    interrupted (with the weeks stored when not every one is), done,
    error, or not started."""
    from app.core import retro, runner
    state = st["status"]
    part = ("" if st["complete"]
            else f" · {st['weeks_done']} of {st['weeks_total']} weeks")
    if queue is not None:
        if not queue["runner"]:
            return ("warn", "queued · runner not running")
        return ("pending",
                f"queued · {runner._ordinal(queue['position'])} in line")
    if claimed and state not in retro.ACTIVE_STATUSES:
        return ("pending", "starting")
    if refused:
        return ("warn", "refused by the runner")
    if state in ("running", "stopping"):
        return ("pending", state)
    if state == "paused":
        return ("warn", "paused")
    if state in ("stopped", "interrupted"):
        return ("warn", state + part)
    if state == "done":
        return ("ok", "done") if st["complete"] else ("warn", "done" + part)
    if state == "error":
        return ("error", "error")
    return ("neutral", state or "not started")


def find(eid: str, *, under: Path | None = None) -> Path | None:
    """The folder of the experiment named eid, or None: eid a folder name
    an id can be, <under>/eid a folder (not a link), and its
    experiment.json a regular file that reads and derives eid (where
    folders ignore case, Beta-v1_... is not beta-v1_...). `under` is the
    experiments folder to look in, root() when None (the runner names a
    student's). Creates nothing."""
    if not isinstance(eid, str) or not _ID_RE.fullmatch(eid):
        return None
    folder = (root() if under is None else Path(under)) / eid
    if folder.is_symlink() or not folder.is_dir():
        return None
    if not os.path.isfile(folder / SETTINGS):
        return None
    try:
        s = read(folder / SETTINGS)
    except Refusal:
        return None
    return folder if experiment_id(s) == eid else None


def list_experiments() -> list[dict]:
    """Every experiment under root() that find accepts, newest start first
    (else newest experiment.json): {"id", "settings", "status" (status()),
    "summary" (summary.json as read, None when missing or unreadable)}.
    Reads only; [] with no root()."""
    if not root().is_dir():
        return []
    rows = []
    for p in sorted(root().iterdir()):
        folder = find(p.name)
        if folder is None:
            continue
        try:
            s = read(folder / SETTINGS)
            mtime = (folder / SETTINGS).stat().st_mtime
        except (Refusal, OSError):
            continue                          # gone or changed meanwhile
        summary = None
        if os.path.isfile(folder / SUMMARY):
            try:
                summary = read_summary(folder / SUMMARY)
            except (OSError, ValueError, RecursionError):
                summary = None                # a Refusal is a ValueError
        st = status(folder)
        rows.append(({"id": p.name, "settings": s, "status": st,
                      "summary": summary}, st["started_utc"] or _utc(mtime)))
    rows.sort(key=lambda r: r[1] or "", reverse=True)
    return [r for r, _key in rows]


def delete(eid: str, *, live: str = "") -> int:
    """Delete the experiment named eid, its folder only (the library keeps
    the model): the bytes freed. sb.SandboxError for an id find does not
    accept, for eid == live (the console's own replay) and for a folder
    whose files say a replay is under way (another process)."""
    from app.core import retro
    folder = find(eid)
    if folder is None:
        raise sb.SandboxError(f"no experiment is named '{eid}'")
    if eid == live:
        raise sb.SandboxError(f"{eid} is replaying; stop it first")
    if status(folder)["status"] in retro.ACTIVE_STATUSES:
        raise sb.SandboxError(f"{eid} is replaying in another process; "
                              "stop it first")
    n = retro.dir_size(folder)
    retro.delete_tree(folder)
    return n


def default_season(retro_root: Path) -> str | None:
    """The season a new experiment is offered: the newest whose live root
    holds the shipped replay (the reference's test, so an experiment of it
    has something to compare with), else the newest season; None with
    none."""
    from app.core import retro
    seasons = sorted(retro.available_seasons(), reverse=True)
    for s in seasons:
        if _shipped(_meta(Path(retro_root) / s)):
            return s
    return seasons[0] if seasons else None
