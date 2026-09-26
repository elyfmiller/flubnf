"""Archived replays: a clean replay moves the season tree aside (kept,
viewable) to a sibling <season>__archived_<UTC stamp>, discoverable by one
glob with no index file. Split out of app/core/retro.py, which re-exports
every name.

Sections: stamps (ARCHIVE_SEP, utc_stamp, valid_stamp, stamp_human,
utc_human) | directories (archive_dir, archive_stamp_of, list_archive_dirs)
| sizes (dir_size, human_bytes) | moves (archive_run, delete_tree).
"""
from __future__ import annotations

import os
import re
import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_SEP = "__archived_"

#: <date>T<time>Z[-N for same-second collisions]; every identifier from a URL
#: is checked against this, so it can never name a path outside the retro root
_STAMP_RE = re.compile(r"\d{8}T\d{6}Z(-\d+)?")

#: headline relWIS per season root, keyed by scores.json mtime + week count;
#: LRU-bounded because archived roots accumulate
_SUMMARY_CACHE_MAX = 128
_SUMMARY_CACHE: OrderedDict = OrderedDict()


def utc_stamp(now: float | None = None) -> str:
    """The archive naming stamp: UTC, second resolution, sortable."""
    from app.core import retro  # the clock stays retro._now (tests patch it)
    t = datetime.fromtimestamp(now if now is not None else retro._now(),
                               tz=timezone.utc)
    return t.strftime("%Y%m%dT%H%M%SZ")


def valid_stamp(stamp: str) -> bool:
    return bool(_STAMP_RE.fullmatch(stamp or ""))


def stamp_human(stamp: str) -> str:
    """'20260821T143012Z' -> '2026-08-21 14:30 UTC'. An unparseable stamp is
    returned unchanged rather than guessed at."""
    try:
        base = (stamp or "").split("-")[0]
        t = datetime.strptime(base, "%Y%m%dT%H%M%SZ")
        return t.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return stamp or ""


def utc_human(epoch: float | None) -> str:
    """A run record's epoch seconds as a readable UTC moment, or ''."""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return ""


def archive_dir(retro_root: Path, season: str, stamp: str) -> Path:
    return Path(retro_root) / f"{season}{ARCHIVE_SEP}{stamp}"


def archive_stamp_of(name: str, season: str) -> str:
    """The stamp inside an archive directory name, or '' when the name is not
    an archive of this season."""
    prefix = f"{season}{ARCHIVE_SEP}"
    if not name.startswith(prefix):
        return ""
    stamp = name[len(prefix):]
    return stamp if valid_stamp(stamp) else ""


def list_archive_dirs(retro_root: Path, season: str) -> list:
    """Archive directories for one season, newest first. The stamp sorts
    lexicographically in time order, so reversing the sort is the ordering."""
    root = Path(retro_root)
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        if not archive_stamp_of(p.name, season):
            continue
        if p.is_dir() or p.is_symlink():
            out.append(p)
    return sorted(out, key=lambda p: p.name, reverse=True)


#: season headline order: the two shipped models (older files' retired blend

def dir_size(path: Path) -> int:
    """Bytes held under a tree. Symlinks are never followed (a season parked
    on another volume must not be walked)."""
    p = Path(path)
    if p.is_symlink() or not p.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(p, followlinks=False):
        for f in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass                       # a file vanishing mid-walk is fine
    return total


def human_bytes(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def archive_run(retro_root: Path, season: str, stamp: str | None = None,
                now: float | None = None) -> Path:
    """Move <retro_root>/<season> aside to <season>__archived_<stamp>/.

    A same-parent os.rename: atomic and instant (a copy of a 12 GB season can
    half-fill the volume). A failure raises with the original untouched; the
    caller must not start a replay over it."""
    src = Path(retro_root) / season
    if not (src.is_dir() or src.is_symlink()):
        raise FileNotFoundError(f"no season tree to archive at {src}")
    stamp = stamp or utc_stamp(now)
    dst = archive_dir(retro_root, season, stamp)
    n = 1
    while dst.exists() or dst.is_symlink():       # same-second collision
        n += 1
        dst = archive_dir(retro_root, season, f"{stamp}-{n}")
    os.rename(src, dst)
    _SUMMARY_CACHE.pop(str(src), None)
    return dst


def delete_tree(path: Path) -> None:
    """Remove a season or archive tree permanently.

    A symlinked tree loses only its link (never follow into data we do not own)."""
    p = Path(path)
    _SUMMARY_CACHE.pop(str(p), None)
    if p.is_symlink():
        p.unlink()
        return
    shutil.rmtree(p)
