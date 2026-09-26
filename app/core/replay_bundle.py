"""Export and import of a replayed season as one zip file (a "replay
bundle"), so a retrospective's playback and numbers can be viewed in the
console on another device.

A bundle holds manifest.json plus the season root's run_meta.json,
scores.json and, per completed week, weeks/<asof>/quantiles.json and the
stored samples file. The playback cache and the season report are left
out: both are rebuilt from the samples and the hub's truth on the
importing machine. An import lands as a read-only archived entry of the
season, <retro_root>/<season>__archived_<export stamp>, with an
imported.json marker, so the archive listing, the season page
(?archive=<stamp>), the report builder and the delete routes all work
unchanged. The live season root is never written.

Every check refuses with one clear sentence (BundleError); there is no
silent fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

FORMAT_VERSION = 1
SUFFIX = ".flubnf-replay.zip"
MANIFEST = "manifest.json"
IMPORTED_MARK = "imported.json"

#: caps: the whole file, one member, and the deflate ratio a member may
#: claim (JSON compresses about 5x; 100x is a bomb)
BUNDLE_MAX_BYTES = 2 * 1024 ** 3
MEMBER_MAX_BYTES = 512 * 1024 ** 2
MAX_RATIO = 100

_SEASON_RE = re.compile(r"\d{4}-\d{2}")
_CHUNK = 1024 * 1024


class BundleError(ValueError):
    """A bundle that cannot be exported or imported; str() is the reason."""


@dataclass
class ImportResult:
    season: str
    stamp: str
    weeks: list
    root: Path
    from_host: str = ""
    exported_at: str = ""
    warnings: list = field(default_factory=list)


def hostname() -> str:
    try:
        return socket.gethostname() or "unknown host"
    except OSError:
        return "unknown host"


def _utc_iso(now: float | None = None) -> str:
    t = datetime.fromtimestamp(now if now is not None else time.time(),
                               tz=timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_name(season: str, stamp: str) -> str:
    return f"{season}-FluBNF-replay-{stamp}{SUFFIX}"


# --------------------------------------------------------------- export

def bundle_files(root: Path) -> list:
    """The relative paths a bundle carries from a season root: the run
    record and scores when present, then each completed week's quantiles
    and samples. Never the playback cache or a report."""
    from app.core import retro
    root = Path(root)
    out = []
    for name in (retro.META_NAME, "scores.json"):
        if (root / name).is_file():
            out.append(name)
    for sp in retro.season_sample_files(root):
        wd = sp.parent
        q = wd / retro.QUANTILES_NAME
        if q.is_file():
            out.append(str(PurePosixPath("weeks", wd.name, q.name)))
        out.append(str(PurePosixPath("weeks", wd.name, sp.name)))
    return out


def _newest_input(root: Path, files: list) -> float:
    try:
        return max(os.stat(Path(root) / f).st_mtime for f in files)
    except (OSError, ValueError):
        return 0.0


def _reusable(out_dir: Path, season: str, source: str, newest: float):
    """An earlier bundle of this root that is newer than every input, so a
    second export offers the same file (and stamp) rather than a twin."""
    try:
        cands = sorted(out_dir.glob(f"{season}-FluBNF-replay-*{SUFFIX}"),
                       reverse=True)
    except OSError:
        return None
    for p in cands:
        try:
            if p.stat().st_mtime < newest:
                continue
            m = inspect_bundle(p)
        except (OSError, BundleError):
            continue
        if m.get("season") == season and m.get("source") == source:
            return p
    return None


def export_season(root: Path, season: str, out_dir: Path,
                  stamp: str = "", build: str = "") -> Path:
    """Write <out_dir>/<season>-FluBNF-replay-<export stamp>.flubnf-replay.zip
    from a season root and return its path. `stamp` is the archive stamp of
    an archived root ("" for the live root); it is recorded as the bundle's
    source. `build` names the exporting app's build when known."""
    from app.core import retro
    root, out_dir = Path(root), Path(out_dir)
    if not _SEASON_RE.fullmatch(season or ""):
        raise BundleError(f"{season!r} is not a season name (YYYY-YY).")
    files = bundle_files(root)
    if not any(f.startswith("weeks/") for f in files):
        raise BundleError(f"{season}: no completed weeks to export.")
    source = stamp or "live"
    newest = _newest_input(root, files)
    prior = _reusable(out_dir, season, source, newest)
    if prior is not None:
        return prior
    export_stamp = retro.utc_stamp()
    out = out_dir / bundle_name(season, export_stamp)
    n = 1
    while out.exists():                       # same-second re-export
        n += 1
        out = out_dir / bundle_name(season, f"{export_stamp}-{n}")
    export_stamp = out.name[len(f"{season}-FluBNF-replay-"):-len(SUFFIX)]
    meta = retro.read_meta(root)
    weeks = sorted({f.split("/")[1] for f in files if f.startswith("weeks/")})
    entries, total = {}, 0
    for f in files:
        p = root / f
        size = p.stat().st_size
        entries[f] = {"sha256": _sha256_file(p), "bytes": size}
        total += size
    manifest = {"format_version": FORMAT_VERSION, "season": season,
                "source": source, "stamp": export_stamp,
                "weeks": weeks, "exported_at": _utc_iso(),
                "exported_by": hostname(), "flubnf_build": build or "",
                "engine_build": ((meta.get("settings") or {}).get("build")
                                 if isinstance(meta, dict) else None) or {},
                "files": entries, "total_bytes": total}
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, indent=1,
                                            sort_keys=True))
            for f in files:
                z.write(root / f, arcname=f)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return out


# -------------------------------------------------------------- inspect

def _safe_member(name: str) -> bool:
    """A relative path inside the bundle: no absolute path, no '..', no
    drive letter, no empty or hidden segment, forward slashes only."""
    if not name or "\\" in name or name.startswith("/") or ":" in name:
        return False
    parts = name.split("/")
    return all(p and p not in (".", "..") and not p.startswith(".")
               for p in parts)


def inspect_bundle(path: Path) -> dict:
    """Read and validate a bundle's manifest and table of contents (not the
    hashes; import_bundle verifies those as it extracts). Returns the
    manifest, with "bundle_bytes" and "bundle_sha256" added."""
    path = Path(path)
    if not path.is_file():
        raise BundleError(f"{path.name}: no such file.")
    size = path.stat().st_size
    if size > BUNDLE_MAX_BYTES:
        raise BundleError(f"{path.name} is {size // 1024 ** 2} MB; bundles "
                          f"over {BUNDLE_MAX_BYTES // 1024 ** 3} GB are "
                          "refused.")
    if not zipfile.is_zipfile(path):
        raise BundleError(f"{path.name} is not a zip file.")
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if names.count(MANIFEST) != 1:
                raise BundleError(f"{path.name} has no {MANIFEST} at its "
                                  "top level, so it is not a replay bundle.")
            for i in infos:
                if i.filename.endswith("/"):
                    continue                          # a directory entry
                if not _safe_member(i.filename):
                    raise BundleError(f"{path.name} names a path outside the "
                                      f"bundle ({i.filename!r}); refused.")
                if i.file_size > MEMBER_MAX_BYTES:
                    raise BundleError(f"{path.name}: {i.filename} is "
                                      f"{i.file_size // 1024 ** 2} MB; "
                                      "members over "
                                      f"{MEMBER_MAX_BYTES // 1024 ** 2} MB "
                                      "are refused.")
                if i.compress_size and i.file_size > MAX_RATIO * i.compress_size:
                    raise BundleError(f"{path.name}: {i.filename} claims a "
                                      f"{i.file_size // max(1, i.compress_size)}x "
                                      "inflation; refused.")
            try:
                manifest = json.loads(z.read(MANIFEST).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise BundleError(f"{path.name}: {MANIFEST} is not valid "
                                  f"JSON ({e}).") from None
    except zipfile.BadZipFile as e:
        raise BundleError(f"{path.name} is not a readable zip file ({e}).") \
            from None
    if not isinstance(manifest, dict):
        raise BundleError(f"{path.name}: {MANIFEST} is not an object.")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise BundleError(f"{path.name} is format {manifest.get('format_version')!r}; "
                          f"this FluBNF reads format {FORMAT_VERSION}.")
    season = str(manifest.get("season") or "")
    if not _SEASON_RE.fullmatch(season):
        raise BundleError(f"{path.name}: season {season!r} is not a season "
                          "name (YYYY-YY).")
    from app.core import retro
    stamp = str(manifest.get("stamp") or "")
    if not retro.valid_stamp(stamp):
        raise BundleError(f"{path.name}: export stamp {stamp!r} is malformed.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise BundleError(f"{path.name}: {MANIFEST} lists no files.")
    members = {n for n in names if not n.endswith("/")} - {MANIFEST}
    for f, ent in files.items():
        if not _safe_member(f):
            raise BundleError(f"{path.name}: {MANIFEST} names a path outside "
                              f"the bundle ({f!r}); refused.")
        if not (isinstance(ent, dict) and isinstance(ent.get("sha256"), str)
                and len(ent["sha256"]) == 64
                and isinstance(ent.get("bytes"), int)):
            raise BundleError(f"{path.name}: {MANIFEST} has no sha256 and "
                              f"size for {f}.")
        if f not in members:
            raise BundleError(f"{path.name} is missing {f}, which its "
                              f"{MANIFEST} lists.")
    extra = sorted(members - set(files))
    if extra:
        raise BundleError(f"{path.name} holds {extra[0]}, which its "
                          f"{MANIFEST} does not list.")
    if not any(f.startswith("weeks/") for f in files):
        raise BundleError(f"{path.name} carries no weeks.")
    manifest["weeks"] = sorted({f.split("/")[1] for f in files
                                if f.startswith("weeks/")})
    manifest["bundle_bytes"] = size
    manifest["bundle_sha256"] = _sha256_file(path)
    return manifest


# --------------------------------------------------------------- import

def imported_info(root: Path) -> dict:
    """The imported.json marker of an archived root, or {} for a run this
    machine replayed."""
    try:
        d = json.loads((Path(root) / IMPORTED_MARK).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def imported_label(root: Path) -> str:
    """'imported from <host> on <date>' for an imported root, else ''."""
    info = imported_info(root)
    if not info:
        return ""
    when = str(info.get("imported_at") or "")[:10]
    host = str(info.get("from") or "another machine")
    return f"imported from {host}" + (f" on {when}" if when else "")


def _extract_member(z: zipfile.ZipFile, name: str, dst: Path,
                    want_sha: str, want_bytes: int, label: str) -> None:
    """Stream one member to dst, checking its size and sha256 as it goes."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    h, n = hashlib.sha256(), 0
    with z.open(name) as src, open(dst, "wb") as out:
        for chunk in iter(lambda: src.read(_CHUNK), b""):
            n += len(chunk)
            if n > want_bytes:
                raise BundleError(f"{label}: {name} is larger than its "
                                  f"{MANIFEST} entry says; refused.")
            h.update(chunk)
            out.write(chunk)
    if n != want_bytes or h.hexdigest() != want_sha:
        raise BundleError(f"{label}: {name} does not match its sha256 in "
                          f"{MANIFEST}; the bundle is damaged or altered.")


def import_bundle(path: Path, retro_root: Path, replace: bool = False,
                  build: str = "") -> ImportResult:
    """Import a bundle as the read-only archived entry
    <retro_root>/<season>__archived_<export stamp>. Refuses a second import
    of the same bundle ("already imported as <stamp>") unless `replace`.
    Every member is verified against the manifest while extracting; the
    tree appears under its final name only once complete."""
    from app.core import retro
    path, retro_root = Path(path), Path(retro_root)
    m = inspect_bundle(path)
    season, stamp = m["season"], m["stamp"]
    dst = retro.archive_dir(retro_root, season, stamp)
    if dst.exists() or dst.is_symlink():
        if not replace:
            raise BundleError(f"{season} from this bundle was already "
                              f"imported as {stamp}.")
    tmp = dst.with_name(dst.name + ".importing")
    if tmp.exists() or tmp.is_symlink():
        retro.delete_tree(tmp)
    files = m["files"]
    # scores.json last, so it is newer than every sample it scores (the
    # results page would otherwise rescore on the first visit)
    order = sorted(files, key=lambda f: (f == "scores.json", f))
    try:
        with zipfile.ZipFile(path) as z:
            for f in order:
                _extract_member(z, f, tmp / f, files[f]["sha256"],
                                files[f]["bytes"], path.name)
        marker = {"from": str(m.get("exported_by") or ""),
                  "exported_at": str(m.get("exported_at") or ""),
                  "imported_at": _utc_iso(), "imported_by": hostname(),
                  "bundle_sha256": m["bundle_sha256"],
                  "bundle_name": path.name, "source": m.get("source"),
                  "exported_build": str(m.get("flubnf_build") or ""),
                  "imported_build": build or ""}
        (tmp / IMPORTED_MARK).write_text(json.dumps(marker, indent=1,
                                                    sort_keys=True))
        sf = tmp / "scores.json"
        if sf.is_file():
            os.utime(sf)
        if dst.exists() or dst.is_symlink():
            retro.delete_tree(dst)
        os.rename(tmp, dst)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    warnings = []
    if "scores.json" not in files:
        warnings.append("the bundle carries no scores; the season page "
                        "scores it against this machine's hub truth")
    else:
        try:
            import pandas as pd
            if not retro.scores_frame_current(pd.read_json(dst / "scores.json")):
                warnings.append("the scores were written under an older "
                                "scoring rule; the season page rescores "
                                "them against this machine's hub truth")
        except Exception:
            warnings.append("the scores did not parse; the season page "
                            "rescores against this machine's hub truth")
    if build and m.get("flubnf_build") and m["flubnf_build"] != build:
        warnings.append(f"exported by FluBNF build {m['flubnf_build']}, "
                        f"this is {build}")
    return ImportResult(season=season, stamp=stamp, weeks=list(m["weeks"]),
                        root=dst, from_host=str(m.get("exported_by") or ""),
                        exported_at=str(m.get("exported_at") or ""),
                        warnings=warnings)
