"""A replay's recorded settings: the engine presets, the settings list a
run record prints, the one-click resume form, and the resume rules (which
mismatches refuse to pool completed weeks with new ones). Split out of
app/core/retro.py, which re-exports every name.

Sections: engine presets (ENGINES, ENGINE_LABELS, engine_label, pf_ran) |
output-floor record values (FLOOR_*) | resume rules (ResumeMismatch family,
engine_build_change, location_scope_change) | the settings list
(SCOPE_LABELS, settings_summary, season_knobs) | resume_form_fields.
"""
from __future__ import annotations

import json

from app.core import missing as MS
from app.core.runs import LOCATION_LIST_LIMIT, locations_phrase

#: "pf": the filter beside the analogue (hours per season); "analogue": the
#: Groundhog alone (minutes, no engine install)
ENGINES = ("pf", "analogue")

#: the presets in plain words, as the form, the flash lines and every Run
#: settings block (console and reports) name them
ENGINE_LABELS = {"pf": "Oracle SIHRS and the Groundhog",
                 "analogue": "Groundhog only"}


def engine_label(engine) -> str:
    """A preset's plain name; an unknown key reads as itself."""
    return ENGINE_LABELS.get(str(engine), str(engine))


def pf_ran(engine) -> bool:
    """False only for the Groundhog-only preset: no particle filter, so no
    particle or replicate count describes the replay. A record without an
    engine predates the preset and ran the filter."""
    return str(engine or "pf") != "analogue"


#: settings.output_floor in a season's run record: every week was stored
#: through the output floor (run_week). A season whose record lacks the key
#: was stored unfloored, before replays applied it (2026-09-25).
FLOOR_APPLIED = "applied"
#: ...or a season started unfloored and resumed after the change
FLOOR_FROM_RESUME = ("applied to the weeks stored from a resume on; the "
                     "weeks stored before it are unfloored")
#: what the settings list says for a record without the key
FLOOR_NOT_RECORDED = "not applied (stored before replays applied it)"


class ResumeMismatch(ValueError):
    """A resume asked for something other than what the tree was built
    with; completed weeks would be pooled with differently made ones."""


class KnobsMismatch(ResumeMismatch):
    """A resume asked for other model settings than the tree was built with."""


class LocationsMismatch(ResumeMismatch):
    """A resume asked for another location list than the tree was built
    with (a scope change, or the national row switched on or off)."""


class EngineBuildMismatch(ResumeMismatch):
    """A resume on another engine build (commit or local edits) than the
    completed weeks were fitted by."""


class EngineBuildChanged(EngineBuildMismatch):
    """The engine build changed while a season was running (a branch
    switched or a file edited mid-replay): the season stops before the next
    week rather than fit it with another engine."""


def engine_build_change(prior_settings, engine: str = "pf",
                        build: dict | None = None) -> str | None:
    """None when a resume may proceed on this machine's engine build: an
    analogue-only replay (no engine), a record with no build (older
    seasons resume as before), or the same commit and edited state.
    Otherwise the difference in plain words. `build` defaults to this
    machine's (app.core.engine_build)."""
    from app.core import engine_build as _eb
    if not pf_ran(engine):
        return None
    had = (prior_settings or {}).get("engine_build") \
        if isinstance(prior_settings, dict) else None
    if not isinstance(had, dict):
        return None
    return _eb.change(had, _eb.engine_build() if build is None else build)


def location_scope(locations) -> set:
    """A location list as a comparable set, every national spelling one."""
    from app.core.us_national import is_us
    return {"US" if is_us(l) else str(l) for l in (locations or [])}


def location_scope_change(prior_locations, locations) -> str | None:
    """None when a resume over `locations` keeps the recorded list (or none
    was recorded); otherwise the plain-words difference, for the console
    and the CLI alike."""
    had, want = location_scope(prior_locations), location_scope(locations)
    if not had or had == want:
        return None
    return (f"replayed over {len(had)} location(s); this run asks for "
            f"{len(want)} with a different list")


#: labels for the retro form's scopes, when a replay recorded no location list
SCOPE_LABELS = {"panel6": "6-state panel", "all": "all 52 jurisdictions",
                "custom": "custom selection"}


def _build_label(build) -> str:
    """A recorded engine build as the settings list names it; "" when the
    record has none (seasons from before builds were recorded)."""
    from app.core import engine_build as _eb
    return _eb.recorded_label(build)


def season_build_label(meta: dict) -> str:
    """The PyBNF build a replay's filter weeks were fitted with, from its
    run record: the season's recorded build, else the builds its weeks
    recorded (several named when they differ), else "not recorded". Never
    this machine's engine: an archived or imported replay describes the
    build that ran it."""
    m = meta or {}
    lab = _build_label((m.get("settings") or {}).get("engine_build"))
    if lab:
        return lab
    wb = m.get("week_engine_builds")
    labs = []
    if isinstance(wb, dict):
        for b in wb.values():
            x = _build_label(b)
            if x and x not in labs:
                labs.append(x)
    if len(labs) == 1:
        return labs[0]
    if labs:
        return "mixed: " + "; ".join(labs)
    return "not recorded"


def settings_summary(meta: dict) -> list:
    """The settings that produced a replay, as (label, value) pairs, from
    its run record; [] when none were recorded (the sealed runs)."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return []
    locs = [str(l) for l in (s.get("locations") or [])]
    scope = str(s.get("scope") or "")
    where = locations_phrase(locs) if locs else SCOPE_LABELS.get(scope, scope)
    if scope == "custom" and len(locs) > LOCATION_LIST_LIMIT:
        where = f"{SCOPE_LABELS['custom']}, {where}"
    # particles, replicates and shard width describe the filter: a
    # Groundhog-only replay records the form's defaults, but no filter ran,
    # so they are omitted
    pf = pf_ran(s.get("engine"))
    pairs = [("season", str(s.get("season") or (meta or {}).get("season") or "")),
             ("locations", where),
             ("particles", f"{int(s.get('particles') or 0):,}"
              if pf and s.get("particles") else ""),
             ("replicates", str(s.get("replicates") or "") if pf else ""),
             ("shard width", str(s.get("width") or "") if pf else ""),
             ("engine", engine_label(s["engine"]) if s.get("engine") else ""),
             ("PyBNF build", season_build_label(meta) if pf else "")]
    # only a record made through the knob channel says "model settings"
    # (the zero-anchor rule is a data decision, listed on its own line)
    from app.core import knobs as _knobs
    mk = _knobs.model_values(s.get("knobs") or {}) \
        if isinstance(s.get("knobs"), dict) else {}
    if mk:
        try:
            pairs.append(("model settings",
                          _knobs.label(_knobs.from_record(mk))))
        except Exception:
            pairs.append(("model settings", "modified (unreadable record)"))
    # the Groundhog's zero-anchor rule: recorded with the replay; a season
    # replayed before the rule existed did what abstain does
    za = (s.get("knobs") or {}).get(MS.ZERO_ANCHOR_KEY) \
        if isinstance(s.get("knobs"), dict) else None
    pairs.append(("zero-anchor rule",
                  str(za) if za in MS.ZERO_ANCHOR_RULES else
                  f"{MS.ZERO_ANCHOR_LEGACY} (replayed before the rule existed)"))
    pairs.append(("zero-anchor weeks", MS.replay_zero_anchor_count(
        (meta or {}).get("data_flags"))))
    # whether the stored weeks went through the output floor (absent from
    # the record: stored before replays applied it)
    pairs.append(("output floor", str(s.get("output_floor")
                                      or FLOOR_NOT_RECORDED)))
    # the newest weeks a missing-data rule treated as unreported, counted
    # (the rows stay in the record's data_flags); absent when no rule is on
    pairs.append(("flagged weeks",
                  MS.replay_count((meta or {}).get("data_flags"))))
    return [(k, v) for k, v in pairs if v not in ("", None)]


def season_knobs(meta: dict) -> dict:
    """The model-knobs record of a replay's run record ({} when shipped or
    from before the registry: an older tree is never marked modified). The
    zero-anchor rule, a data decision, is left out: it never marks a
    season modified (settings_summary lists it)."""
    from app.core import knobs as _knobs
    s = (meta or {}).get("settings")
    k = s.get("knobs") if isinstance(s, dict) else None
    return _knobs.model_values(dict(k)) if isinstance(k, dict) else {}


def resume_form_fields(meta: dict) -> dict | None:
    """The /retro/run form fields that resume a replay with its recorded
    settings (one-click resume). A recorded scope passes through; a bare
    location list resubmits as a custom selection. None when the record
    cannot name a scope (then only the form path is offered)."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return None
    season = str(s.get("season") or (meta or {}).get("season") or "")
    if not season:
        return None
    locs = [str(l) for l in (s.get("locations") or [])]
    scope = str(s.get("scope") or "")
    out = {"season": season, "mode": "resume"}
    # national is posted explicitly from the run's own list, not today's
    # default: a 52-jurisdiction replay must never resume as 53
    from app.core.us_national import is_us as _is_us
    out["national"] = "1" if (any(_is_us(l) for l in locs) if locs
                              else bool(s.get("national"))) else "0"
    if scope in ("panel6", "all"):
        out["locations"] = scope
        out["custom_locations"] = []
    elif locs:
        out["locations"] = "custom"
        out["custom_locations"] = locs
    else:
        return None
    for key in ("particles", "replicates", "width"):
        try:
            v = int(s.get(key) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            out[key] = v
    engine = str(s.get("engine") or "")
    if engine:
        out["engine"] = engine
    # the model knobs ride as one JSON field (only when recorded)
    if isinstance(s.get("knobs"), dict) and s["knobs"]:
        out["knobs"] = json.dumps(s["knobs"], sort_keys=True)
    return out
