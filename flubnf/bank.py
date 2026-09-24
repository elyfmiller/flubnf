"""SHIPPED (used by the FluBNF console, app/).

Committed donor banks (data/banks/): the auxiliary streams as repo artefacts.

Committed so a fresh clone forecasts offline, a Delphi outage on submission
day is not a failure, and every run records which bank it used.

Each bank has a sibling manifest (source, build time, epiweek span,
locations, cell count, content digest); :func:`read` verifies the digest on
every load. The digest covers content, not bytes, so `flubnf bank verify`
compares a fresh build directly.

No silent fallback: a missing or mismatched bank RAISES, never degrades to
the single-pool forecast (the rule flusurv.build_bank applies to an empty
bank).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Committed banks live in the repository, beside the code that reads them.
#: `data/` is tracked (.gitignore excludes only data/covidhub/).
BANKS_DIR = REPO / "data" / "banks"

#: Bumped when the on-disk layout changes in a way a reader must notice.
LAYOUT_VERSION = 1

STREAMS = ("flusurv", "iliplus")


def bank_path(stream: str, banks_dir=None) -> Path:
    return (Path(banks_dir) if banks_dir else BANKS_DIR) / f"{stream}.json"


def manifest_path(stream: str, banks_dir=None) -> Path:
    return (Path(banks_dir) if banks_dir else BANKS_DIR) / f"{stream}.manifest.json"


def digest(bank) -> str:
    """A stable content hash of ``{(location, date): value}``.

    Content, not bytes: formatting and key order cannot change it. Floats go
    through ``repr`` so the hash round-trips exactly through JSON.
    """
    h = hashlib.sha256()
    for (loc, d) in sorted(bank, key=lambda k: (str(k[0]), str(k[1]))):
        h.update(f"{loc}|{d}={repr(float(bank[(loc, d)]))}\n".encode())
    return h.hexdigest()


def summarise(bank) -> dict:
    """The facts about a bank that belong in its manifest."""
    if not bank:
        raise ValueError("refusing to summarise an empty bank")
    locs = sorted({str(k[0]) for k in bank})
    dates = sorted(str(k[1]) for k in bank)
    return {"cells": len(bank), "locations": locs, "location_count": len(locs),
            "span": [dates[0], dates[-1]], "digest": digest(bank)}


def write(stream: str, bank, *, source_url: str, built_utc: str,
          builder: str = "", banks_dir=None) -> dict:
    """Write a bank and its manifest, atomically, and return the manifest.

    `built_utc` is a parameter so a caller can build reproducibly.
    """
    if stream not in STREAMS:
        raise ValueError(f"unknown stream {stream!r}; known: {STREAMS}")
    from .iliplus import write_bank            # one writer for the format
    bp = bank_path(stream, banks_dir)
    bp.parent.mkdir(parents=True, exist_ok=True)
    write_bank(bank, bp)
    man = {"stream": stream, "layout_version": LAYOUT_VERSION,
           "source_url": source_url, "built_utc": built_utc,
           "builder": builder, **summarise(bank)}
    mp = manifest_path(stream, banks_dir)
    tmp = mp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    tmp.replace(mp)
    return man


def read(stream: str, banks_dir=None) -> tuple:
    """``(bank, manifest)`` for a committed stream, digest verified.

    Raises rather than returning a partial or unverifiable bank; a caller
    that catches this and carries on unspliced is the bug.
    """
    bp, mp = bank_path(stream, banks_dir), manifest_path(stream, banks_dir)
    if not bp.is_file():
        raise FileNotFoundError(
            f"no committed {stream!r} donor bank at {bp}. Build it with "
            f"`flubnf bank build {stream}` (it needs network access once; "
            f"the result is committed and every later run reads it from "
            f"the repository).")
    if not mp.is_file():
        raise FileNotFoundError(
            f"the {stream!r} bank at {bp} has no manifest at {mp}. A bank "
            f"without provenance is a pile of numbers: rebuild it with "
            f"`flubnf bank build {stream}` rather than using it.")
    man = json.loads(mp.read_text())
    raw = json.loads(bp.read_text())
    bank = {}
    for k, v in raw.items():
        loc, _, ds = k.partition("|")
        if not ds:
            raise ValueError(f"{bp}: key {k!r} is not 'location|YYYY-MM-DD'")
        y, m, d = (int(x) for x in ds.split("-"))
        bank[(loc, date(y, m, d))] = float(v)
    got = digest(bank)
    if got != man.get("digest"):
        raise ValueError(
            f"the committed {stream!r} bank does not match its manifest.\n"
            f"  manifest says {man.get('digest')}\n"
            f"  the file is   {got}\n"
            f"One of them was changed without the other. Rebuild with "
            f"`flubnf bank build {stream}` and commit both, or restore the "
            f"pair from git. This bank is NOT used while they disagree: a "
            f"forecast labelled spliced must be able to say which donors "
            f"it spliced.")
    return bank, man


def compare(committed, fresh) -> dict:
    """What a fresh build says about the committed bank. Pure; no I/O."""
    ck, fk = set(committed), set(fresh)
    changed = [k for k in (ck & fk)
               if float(committed[k]) != float(fresh[k])]
    return {"identical": digest(committed) == digest(fresh),
            "committed_cells": len(committed), "fresh_cells": len(fresh),
            "added": len(fk - ck), "removed": len(ck - fk),
            "changed": len(changed),
            "added_sample": sorted(f"{a}|{b}" for a, b in list(fk - ck))[:5],
            "removed_sample": sorted(f"{a}|{b}" for a, b in list(ck - fk))[:5],
            "changed_sample": [
                {"cell": f"{a}|{b}", "committed": committed[(a, b)],
                 "fresh": fresh[(a, b)]}
                for a, b in sorted(changed, key=lambda k: (str(k[0]), str(k[1])))[:5]]}


def build_from_source(stream: str, **kw):
    """Build a bank from its upstream source. Network unless cached."""
    if stream == "flusurv":
        from . import flusurv
        return flusurv.build_bank(**kw), flusurv.BASE_URL
    if stream == "iliplus":
        from . import iliplus
        kw.setdefault("asof", None)            # latest issue for a shipped bank
        first = kw.pop("first_season", "2016-08-01")
        asof = kw.pop("asof")
        return iliplus.build_bank(first, asof, **kw), iliplus.BASE_URL
    raise ValueError(f"unknown stream {stream!r}; known: {STREAMS}")
