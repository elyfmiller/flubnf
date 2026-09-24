"""PRODUCTION: which locations one submission file covers, and why the
others are missing (the Output page and the run page, app/ui/routes).

Everything here is read from what the run already recorded: the file's
own rows, the run's requested locations (its spec) and its ledger
outcome: pf_failures (prepare, fit and collect), pf_anchor_notes and
analogue_anchor_notes (a fit origin or anchor moved back by unreported
newest weeks, an abstention, the Groundhog's "no forecast: newest week
reads 0"), submission_dropped (a location whose rows failed the checks,
app/core/submit.write_submission) and data_flags (newest weeks a
missing-data rule set aside). Nothing is recomputed.
"""
from __future__ import annotations

#: the member whose engine notes and failures explain a file
_NOTE_KEY = {"pf": "pf_anchor_notes", "analogue": "analogue_anchor_notes"}


def _pf_failure(outcome: dict, loc: str) -> str:
    """The recorded PF failure of `loc`'s cells ("<tag>" for prepare,
    "<tag>_r<n>" for a fit or collect), "" when none."""
    fails = outcome.get("pf_failures") or {}
    if not isinstance(fails, dict):
        return ""
    tag = loc.replace(" ", "_")
    for k in sorted(fails):
        if k == tag or k.startswith(tag + "_r"):
            v = str(fails[k])
            return v[len("FAIL: "):] if v.startswith("FAIL: ") else v
    return ""


def missing_reason(outcome: dict, member: str, model_id: str,
                   loc: str) -> str:
    """Why `loc` is not in `model_id`'s file, in plain words."""
    dropped = ((outcome.get("submission_dropped") or {}).get(model_id)
               or {})
    if loc in dropped:
        return f"left out of the file, its rows failed a check: {dropped[loc]}"
    note = str(((outcome.get(_NOTE_KEY.get(member, "")) or {})
                .get(loc)) or "")
    if note.startswith(("abstained", "no forecast")):
        return note
    if member == "pf":
        why = _pf_failure(outcome, loc)
        if why:
            if why.startswith("prepare: "):
                return "the fit could not be prepared: " + why[9:]
            return "the fit failed: " + why
    return "no forecast was recorded for it"


def moved_notes(outcome: dict, member: str) -> dict:
    """{location: note} for the locations whose anchor (or fit origin)
    sits on an earlier week: unreported newest weeks, or weeks a
    missing-data rule set aside."""
    out = {}
    for loc, v in sorted(((outcome.get(_NOTE_KEY.get(member, "")) or {})
                          .items())):
        if str(v).startswith("anchored on"):
            out[loc] = str(v)
    flags = (outcome.get("data_flags") or {})
    rows = flags.get(member) if isinstance(flags, dict) else None
    for r in rows or ():
        try:
            loc, week, rule = r["location"], r["week"], r.get("rule", "")
        except (TypeError, KeyError):
            continue
        bit = f"newest week {week} set aside ({rule})" if rule else \
            f"newest week {week} set aside"
        out[loc] = f"{out[loc]}; {bit}" if loc in out else bit
    return out


def file_coverage(outcome: dict, member: str, model_id: str,
                  requested: list, present: set,
                  hub_total: int | None = None) -> dict:
    """One file's coverage for a page:

    {"n": requested locations in the file, "of": requested count,
     "missing": [(location, reason)], "moved": [(location, note)] for
     locations in the file, "not_requested": hub locations the run did not
     ask for (0 when unknown)}."""
    requested = [str(x) for x in (requested or [])]
    present = {str(x) for x in (present or ())}
    missing = [(loc, missing_reason(outcome, member, model_id, loc))
               for loc in requested if loc not in present]
    moved = [(loc, why) for loc, why in moved_notes(outcome, member).items()
             if loc in present]
    n = sum(1 for loc in requested if loc in present)
    extra = max(0, int(hub_total) - len(requested)) if hub_total else 0
    return {"n": n, "of": len(requested), "missing": missing,
            "moved": moved, "not_requested": extra}
