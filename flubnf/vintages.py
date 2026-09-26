"""SHIPPED (used by the FluBNF console, app/).

Committed truth snapshots (data/vintages/): the as-of weeks the hub's
target-data-archive does not hold, as repo artefacts.

The hub archives `target-data/target-hospital-admissions.csv` by hand as
`auxiliary-data/target-data-archive/target-hospital-admissions_<Saturday>.csv`
and skipped eight weeks that FluSight scored. Each skipped week's published
file exists in the hub's commit history; the copies here are those files,
bytes unchanged, renamed to the archive's naming. A shallow hub clone
(setup.sh) cannot reach that history, so FluBNF ships them.

Each file is listed in manifest.json (as-of week, reference date, season,
hub commit, sha256, row and location counts); :func:`shipped_path` verifies
the sha256 on every read. The manifest also lists the two weeks with no
published data and no FluSight round, so a timeline can say why they are
missing instead of skipping them.

No silent fallback: a shipped file missing from the manifest, or a byte
different from it, RAISES (the rule flubnf.bank applies to donor banks).
The lookup that unions this folder with the hub archive is
app.core.data.vintages / vintage_path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Committed snapshots live in the repository, beside the code that reads
#: them (`data/` is tracked, as data/banks/ is).
VINTAGES_DIR = REPO / "data" / "vintages"

MANIFEST_NAME = "manifest.json"

#: the archive's file naming, kept so one glob lists both folders
FILE_PREFIX = "target-hospital-admissions_"

#: Bumped when the on-disk layout changes in a way a reader must notice.
LAYOUT_VERSION = 1

#: verified digests, keyed on (path, mtime_ns, size): the same bytes are
#: not rehashed on every engine read within a replay
_verified: dict = {}


def file_name(asof: str) -> str:
    return f"{FILE_PREFIX}{asof}.csv"


def manifest_path(vintages_dir=None) -> Path:
    return (Path(vintages_dir) if vintages_dir else VINTAGES_DIR) / MANIFEST_NAME


def manifest(vintages_dir=None) -> dict:
    """The manifest as written, or an empty one when the folder has none
    (a checkout without shipped snapshots is a plain hub-only install)."""
    mp = manifest_path(vintages_dir)
    if not mp.is_file():
        return {"layout_version": LAYOUT_VERSION, "vintages": [],
                "no_data_weeks": []}
    man = json.loads(mp.read_text())
    if int(man.get("layout_version") or 0) != LAYOUT_VERSION:
        raise ValueError(
            f"{mp}: layout_version {man.get('layout_version')!r} is not "
            f"{LAYOUT_VERSION}; this build cannot read it.")
    return man


def entries(vintages_dir=None) -> dict:
    """{as_of: manifest entry} for every shipped snapshot listed."""
    return {str(e["as_of"]): e for e in manifest(vintages_dir).get("vintages", [])}


def entry(asof: str, vintages_dir=None):
    """The manifest entry for one as-of week, or None."""
    return entries(vintages_dir).get(str(asof))


def weeks(vintages_dir=None) -> list:
    """As-of weeks the shipped folder can serve, ascending: listed in the
    manifest AND present as a file. A listed file that is absent is not
    served silently; it is reported by shipped_path when asked for."""
    d = Path(vintages_dir) if vintages_dir else VINTAGES_DIR
    return sorted(a for a in entries(vintages_dir) if (d / file_name(a)).is_file())


def no_data_weeks(vintages_dir=None) -> dict:
    """{as_of: entry} for the weeks with no published data and no FluSight
    round (nothing to fill, nothing to score)."""
    return {str(e["as_of"]): e
            for e in manifest(vintages_dir).get("no_data_weeks", [])}


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shipped_path(asof: str, vintages_dir=None) -> Path:
    """The shipped snapshot for one as-of week, sha256 verified against the
    manifest. Raises FileNotFoundError when the week is not shipped and
    ValueError when the bytes disagree with the manifest; never returns a
    file it cannot vouch for."""
    d = Path(vintages_dir) if vintages_dir else VINTAGES_DIR
    p = d / file_name(asof)
    e = entry(asof, vintages_dir)
    if e is None:
        raise FileNotFoundError(
            f"No shipped snapshot for {asof} in {d}"
            + (f" ({p.name} is present but not listed in {MANIFEST_NAME}, "
               f"so it is not used)" if p.is_file() else "") + ".")
    if not p.is_file():
        raise FileNotFoundError(
            f"The shipped snapshot for {asof} is listed in "
            f"{manifest_path(vintages_dir)} but {p} is missing. Restore it "
            f"from the repository.")
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    got = _verified.get(key) or sha256_of(p)
    want = str(e.get("sha256") or "")
    if got != want:
        raise ValueError(
            f"the shipped snapshot {p} does not match its manifest.\n"
            f"  manifest says {want}\n"
            f"  the file is   {got}\n"
            f"One of them was changed without the other. Restore the pair "
            f"from the repository. This file is NOT used while they "
            f"disagree: a replay must be able to say which published data "
            f"it read.")
    if len(_verified) > 64:
        _verified.clear()
    _verified[key] = got
    return p


def provenance(asof: str, vintages_dir=None) -> str:
    """One short phrase for a shipped week: 'hub snapshot, commit 1c8e1141
    (2024-11-27)'; '' for a week not shipped."""
    e = entry(asof, vintages_dir)
    if not e:
        return ""
    when = str(e.get("hub_commit_date") or "")[:10]
    return (f"hub snapshot, commit {e.get('hub_commit', '')}"
            + (f" ({when})" if when else ""))
