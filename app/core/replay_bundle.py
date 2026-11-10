"""Export and import of a replayed season as one zip file (a "replay
bundle"), so a retrospective's playback and numbers can be viewed in the
console on another device.

A bundle holds manifest.json plus the season root's run_meta.json,
scores.json and, per completed week, weeks/<asof>/quantiles.json (when
it is current), oracle.json (the Oracle step's record, with the
Liu-West filter's own quantiles) and the stored samples file. A week
that carries oracle.json keeps its quantiles current on import, so an
imported replay is the shipped side of an experiment with the step on
or off. The playback cache, the
season report and the Oracle step's donor bank are left out: the first
two are rebuilt from the samples and the hub's truth on the importing
machine. An import lands as a read-only archived entry of the
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
import secrets
import shutil
import socket
import threading
import time
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from flubnf.vintages import sha256_of as _sha256_file

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

#: what reading a member whose compressed bytes are damaged raises (a bad
#: CRC or header, a corrupt deflate stream, data that ends early), and
#: what one changed byte in the zip's table of contents raises: the
#: encrypted flag set (RuntimeError), a compression method, flag or "zip
#: version needed" zipfile does not read (NotImplementedError, the last
#: from the ZipFile constructor itself); refused as a damaged bundle,
#: never a raw error
_UNREADABLE = (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError,
               NotImplementedError)


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


def bundle_name(season: str, stamp: str) -> str:
    return f"{season}-FluBNF-replay-{stamp}{SUFFIX}"


# --------------------------------------------------------------- export

def bundle_files(root: Path) -> list:
    """The relative paths a bundle carries from a season root: the run
    record and scores when present, then each completed week's quantiles
    (only when current: not older than the samples), oracle.json (a
    regular file, never a link) and samples. Never the playback cache, a
    report or the donor bank."""
    from app.core import retro
    from app.core.retro_store import ORACLE_NAME
    root = Path(root)
    out = []
    for name in (retro.META_NAME, "scores.json"):
        if (root / name).is_file():
            out.append(name)
    for sp in retro.season_sample_files(root):
        wd = sp.parent
        q = wd / retro.QUANTILES_NAME
        if q.is_file() and q.stat().st_mtime >= sp.stat().st_mtime:
            out.append(str(PurePosixPath("weeks", wd.name, q.name)))
        o = wd / ORACLE_NAME
        if o.is_file() and not o.is_symlink():
            out.append(str(PurePosixPath("weeks", wd.name, o.name)))
        out.append(str(PurePosixPath("weeks", wd.name, sp.name)))
    return out


def _newest_input(root: Path, files: list) -> float:
    try:
        return max(os.stat(Path(root) / f).st_mtime for f in files)
    except (OSError, ValueError):
        return 0.0


def _reusable(out_dir: Path, season: str, source: str, newest: float,
              files: list):
    """An earlier bundle of this root that is newer than every input and
    carries the same files, so a second export offers the same file (and
    stamp) rather than a twin; one exported before bundles carried
    oracle.json is not offered for a root whose weeks hold it."""
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
        if (m.get("season") == season and m.get("source") == source
                and set(m.get("files") or {}) == set(files)):
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
    prior = _reusable(out_dir, season, source, newest, files)
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
    # the engine build as run_season records it (settings.engine_build);
    # "build", the key read here before, as a fallback
    st = meta.get("settings") if isinstance(meta, dict) else None
    st = st if isinstance(st, dict) else {}
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
                "engine_build": (st.get("engine_build") or st.get("build")
                                 or {}),
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


def inspect_bundle(path: Path, name: str = "") -> dict:
    """Read and validate a bundle's manifest and table of contents (not the
    hashes; import_bundle verifies those as it extracts). Returns the
    manifest, with "bundle_bytes" and "bundle_sha256" added. `name` is
    the file as its messages call it (an upload's own name, not the
    server's copy); the path's name by default."""
    path = Path(path)
    name = name or path.name
    if path.is_dir():
        raise BundleError(f"{path} is a folder, not a bundle.")
    if not path.is_file():
        raise BundleError(f"{name}: no such file.")
    size = path.stat().st_size
    if size > BUNDLE_MAX_BYTES:
        raise BundleError(f"{name} is {size // 1024 ** 2} MB; bundles "
                          f"over {BUNDLE_MAX_BYTES // 1024 ** 3} GB are "
                          "refused.")
    if not zipfile.is_zipfile(path):
        raise BundleError(f"{name} is not a zip file.")
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if names.count(MANIFEST) != 1:
                raise BundleError(f"{name} has no {MANIFEST} at its "
                                  "top level, so it is not a replay bundle.")
            for i in infos:
                if i.filename.endswith("/"):
                    continue                          # a directory entry
                if not _safe_member(i.filename):
                    raise BundleError(f"{name} names a path outside the "
                                      f"bundle ({i.filename!r}); refused.")
                if i.file_size > MEMBER_MAX_BYTES:
                    raise BundleError(f"{name}: {i.filename} is "
                                      f"{i.file_size // 1024 ** 2} MB; "
                                      "members over "
                                      f"{MEMBER_MAX_BYTES // 1024 ** 2} MB "
                                      "are refused.")
                if i.compress_size and i.file_size > MAX_RATIO * i.compress_size:
                    raise BundleError(f"{name}: {i.filename} claims a "
                                      f"{i.file_size // max(1, i.compress_size)}x "
                                      "inflation; refused.")
            try:
                raw = z.read(MANIFEST)
            except _UNREADABLE:
                raise BundleError(f"{name}: {MANIFEST} could not be "
                                  "unpacked; the bundle is damaged or "
                                  "altered.") from None
            try:
                manifest = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise BundleError(f"{name}: {MANIFEST} is not valid "
                                  f"JSON ({e}).") from None
    except zipfile.BadZipFile as e:
        raise BundleError(f"{name} is not a readable zip file ({e}).") \
            from None
    except _UNREADABLE:
        # the constructor's: a "zip version needed" this reader does not
        # know (one changed byte in the table of contents)
        raise BundleError(f"{name}: its table of contents asks for a zip "
                          "feature no FluBNF bundle uses; the bundle is "
                          "damaged or altered.") from None
    if not isinstance(manifest, dict):
        raise BundleError(f"{name}: {MANIFEST} is not an object.")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise BundleError(f"{name} is format {manifest.get('format_version')!r}; "
                          f"this FluBNF reads format {FORMAT_VERSION}.")
    season = str(manifest.get("season") or "")
    if not _SEASON_RE.fullmatch(season):
        raise BundleError(f"{name}: season {season!r} is not a season "
                          "name (YYYY-YY).")
    from app.core import retro
    stamp = str(manifest.get("stamp") or "")
    if not retro.valid_stamp(stamp):
        raise BundleError(f"{name}: export stamp {stamp!r} is malformed.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise BundleError(f"{name}: {MANIFEST} lists no files.")
    members = {n for n in names if not n.endswith("/")} - {MANIFEST}
    for f, ent in files.items():
        if not _safe_member(f):
            raise BundleError(f"{name}: {MANIFEST} names a path outside "
                              f"the bundle ({f!r}); refused.")
        if not (isinstance(ent, dict) and isinstance(ent.get("sha256"), str)
                and len(ent["sha256"]) == 64
                and isinstance(ent.get("bytes"), int)):
            raise BundleError(f"{name}: {MANIFEST} has no sha256 and "
                              f"size for {f}.")
        if f not in members:
            raise BundleError(f"{name} is missing {f}, which its "
                              f"{MANIFEST} lists.")
    extra = sorted(members - set(files))
    if extra:
        raise BundleError(f"{name} holds {extra[0]}, which its "
                          f"{MANIFEST} does not list.")
    if not any(f.startswith("weeks/") for f in files):
        raise BundleError(f"{name} carries no weeks.")
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
        d = json.loads((Path(root) / IMPORTED_MARK).read_text(encoding="utf-8"))
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


#: one lock per destination tree (key -> [lock, holders]; under
#: _IMPORT_LOCKS_GUARD): two imports of one bundle at once (a double
#: click; the console's route runs in a thread pool) shared one temp tree
#: and each deleted the other's work
_IMPORT_LOCKS: dict = {}
_IMPORT_LOCKS_GUARD = threading.Lock()


@contextmanager
def _import_lock(dst: Path):
    """Held around one import into `dst` (by its resolved path): a second
    import of the same bundle in this process waits for the first, then
    finds its tree. The entry goes once no one holds or waits for it."""
    try:
        key = str(Path(dst).resolve())
    except OSError:
        key = str(Path(dst).absolute())
    with _IMPORT_LOCKS_GUARD:
        entry = _IMPORT_LOCKS.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _IMPORT_LOCKS_GUARD:
            entry[1] -= 1
            if not entry[1]:
                _IMPORT_LOCKS.pop(key, None)


#: an import's temp tree is <dst>.importing-<pid>-<random>, its own: two
#: processes importing one bundle (a terminal `flubnf retro import` and the
#: console) once shared <dst>.importing, each deleting the other's work, so
#: one said "Imported" over a tree with files missing. <dst>.importing
#: alone is an older build's name. A Replace's old tree, renamed aside
#: while the new one goes in, is <dst>.replaced-<pid>-<random>
#: (_move_aside); a process killed before it deleted that tree leaves it
#: for the same sweep
_TEMP_RE = re.compile(r"\.importing(?:-(\d+)-[0-9a-f]+)?"
                      r"|\.replaced-(\d+)-[0-9a-f]+")

#: a temp tree nothing has written for this long is a leftover, whatever
#: its process (a pid can be reused)
STALE_TEMP_S = 3600.0


def _temp_tree(dst: Path) -> Path:
    """A new, empty temp tree beside `dst` for this call alone (the retro
    root made when it is not there yet, as an import always did)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(8):
        tmp = dst.with_name(f"{dst.name}.importing-{os.getpid()}-"
                            f"{secrets.token_hex(4)}")
        try:
            tmp.mkdir()
            return tmp
        except FileExistsError:
            continue
    raise BundleError(f"could not make a temporary folder beside {dst}.")


def _process_alive(pid: int) -> bool:
    """Whether `pid` is a live process on this machine (never signals it;
    Windows asks without terminating). True when it cannot be told: the
    age rule then decides."""
    try:
        from flubnf.cli import _pid_alive
    except Exception:                    # noqa: BLE001 - cannot tell
        return True
    return _pid_alive(pid)


def _newest_mtime(p: Path) -> float:
    """The newest modification time in a tree (links not followed): when
    an import last wrote into it."""
    try:
        newest = os.lstat(p).st_mtime
    except OSError:
        return 0.0
    if not os.path.isdir(p) or os.path.islink(p):
        return newest
    for top, dirs, names in os.walk(p, onerror=lambda e: None):
        for n in dirs + names:
            try:
                newest = max(newest, os.lstat(os.path.join(top, n)).st_mtime)
            except OSError:
                pass
    return newest


def _remove_quietly(p: Path) -> None:
    """Remove a temp tree (a link loses only itself); a failure leaves it
    for a later sweep."""
    try:
        if p.is_symlink():
            p.unlink()
        else:
            shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def _sweep_stale_temps(dst: Path, now: float | None = None,
                       kept: list | None = None) -> list:
    """Remove the temp trees earlier imports into `dst` left behind (and
    the old trees a killed Replace left aside): one whose process is no
    longer alive, and any (an older build's <dst>.importing included)
    nothing has written for STALE_TEMP_S. Another import's tree, still
    being written by a live process, is never touched. A leftover inside a
    protected folder (reclaim's roots: the sealed records, the hub clone,
    FLUBNF_PROTECT_ROOTS) is never deleted either: it is left where it is
    and added to `kept`, for the import to refuse. Returns the paths
    removed."""
    from app.core import reclaim
    prefix = dst.name + "."
    try:
        cands = sorted(p for p in dst.parent.iterdir()
                       if p.name.startswith(prefix))
    except OSError:
        return []
    now = time.time() if now is None else now
    gone = []
    for p in cands:
        m = _TEMP_RE.fullmatch(p.name[len(dst.name):])
        if m is None:
            continue
        pid = int(m.group(1) or m.group(2) or 0)
        if ((pid and not _process_alive(pid))
                or now - _newest_mtime(p) > STALE_TEMP_S):
            if reclaim.is_protected(p):
                if kept is not None:
                    kept.append(p)
                continue
            _remove_quietly(p)
            gone.append(p)
    return gone


def _move_aside(dst: Path) -> Path | None:
    """A Replace's first step: the tree at `dst` renamed (one rename in its
    own folder, so all or nothing) to <dst>.replaced-<pid>-<random>, a name
    the sweep knows, and touched, so another import's sweep leaves it while
    this process lives. A link is moved as a link. None when nothing is at
    the name any more (another process's Replace moved it first)."""
    from app.core import retro
    aside = dst.with_name(f"{dst.name}.replaced-{os.getpid()}-"
                          f"{secrets.token_hex(4)}")
    try:
        os.rename(dst, aside)
    except FileNotFoundError:
        return None
    retro._SUMMARY_CACHE.pop(str(dst), None)
    if not aside.is_symlink():
        try:
            os.utime(aside)
        except OSError:
            pass
    return aside


def _drop_aside(aside: Path) -> None:
    """The old run a Replace set aside, deleted as any run is
    (retro.delete_tree: a link loses only itself); a failure leaves it for
    a later sweep."""
    from app.core import retro
    try:
        retro.delete_tree(aside)
    except OSError:
        pass


def _put_back(aside: Path, dst: Path) -> None:
    """The old tree back at its name when the new one could not go in; a
    failure leaves it aside, for a later sweep."""
    try:
        os.rename(aside, dst)
    except OSError:
        pass


def import_bundle(path: Path, retro_root: Path, replace: bool = False,
                  build: str = "", name: str = "",
                  removing=None) -> ImportResult:
    """Import a bundle as the read-only archived entry
    <retro_root>/<season>__archived_<export stamp>. Refuses a second import
    of the same bundle ("already imported as <stamp>") unless `replace`.
    Two imports into one tree at once run one after the other (a lock per
    tree in this process), so the second, without `replace`, is refused
    once the first is done. Each call extracts into a temp tree of its own
    (<dst>.importing-<pid>-<random>), so an import in another process (a
    terminal's and the console's) never writes into or deletes this one's;
    only leftovers are swept. The tree's name is looked at again just
    before the rename, so a tree that appeared meanwhile is never deleted
    without `replace`, and of two that reach the rename at once one
    stands and the other is refused in words. A Replace renames the old
    tree aside (<dst>.replaced-<pid>-<random>), the new one in, and only
    then deletes the old one, so a process killed part way never leaves
    part of a run at the name; the sweep removes what it left aside.
    Every member is verified against the manifest while extracting (a
    member whose compressed bytes are damaged is refused as a damaged
    bundle); the tree appears under its final name only once complete,
    every member present at its size. A week whose
    oracle.json travelled was exported with its quantiles only when
    current, so they are made newer than the samples extracted after
    them; a bundle without oracle.json lands as it always did (its
    quantiles older than its samples, rebuilt where they are read), each
    such week's quantiles set older outright rather than left to the
    order of extraction, which a coarse clock (Windows') stamps alike.

    `removing` (the console passes retro_prep._removing): a Replace
    deletes the archived tree, so it is entered with the tree's path
    before anything is extracted and held until the new tree is in place
    (no finalize starts on the tree meanwhile). It yields a word ("results")
    while a finalize still runs on the tree, or what is under way
    ("already being deleted or replaced") while a delete holds it:
    refused, nothing replaced.

    Nothing in a protected folder (reclaim's roots) is deleted: a Replace
    of a protected tree is refused, and a leftover temp tree the sweep
    would remove that lies in a protected folder is left where it is and
    the import refused, nothing imported."""
    path, retro_root = Path(path), Path(retro_root)
    name = name or path.name           # an upload's own name (inspect_bundle)
    m = inspect_bundle(path, name)
    from app.core import retro
    dst = retro.archive_dir(retro_root, m["season"], m["stamp"])
    with _import_lock(dst):
        return _import_into(path, m, dst, replace, build, name, removing)


def _import_into(path: Path, m: dict, dst: Path, replace: bool, build: str,
                 name: str, removing) -> ImportResult:
    """import_bundle's work, under the destination's lock."""
    from contextlib import nullcontext
    from app.core import reclaim, retro
    from app.core.retro_store import ORACLE_NAME, samples_file
    season, stamp = m["season"], m["stamp"]
    if dst.exists() or dst.is_symlink():
        if not replace:
            # refused, but what a killed import or Replace left beside the
            # run (the old tree it set aside) is swept all the same; one
            # in a protected folder stays where it is
            _sweep_stale_temps(dst)
            raise BundleError(f"{season} from this bundle was already "
                              f"imported as {stamp}.")
        # replacing deletes it: never a protected folder (reclaim's roots:
        # the sealed records, the hub clone, FLUBNF_PROTECT_ROOTS, the
        # barrier Storage's Delete also asks), checked before anything is
        # built
        if reclaim.is_protected(dst):
            raise BundleError(f"{season} from this bundle is imported as "
                              f"{stamp} in a protected folder, which the "
                              "console never deletes; nothing was "
                              "replaced.")
    # a Replace may delete the tree at its name (there now, or by the time
    # the new one is ready): marked whether or not it is there yet
    with (removing(dst) if replace and removing is not None
          else nullcontext("")) as busy:
        if busy == "results":
            raise BundleError(f"{season} from this bundle is imported as "
                              f"{stamp}, and its {busy} are still being "
                              "prepared; nothing was replaced. Try again "
                              "in a minute.")
        if busy:
            # another delete of the tree is under way (Storage's, the
            # archived run's): two removers of one tree cannot both succeed
            raise BundleError(f"{season} from this bundle is imported as "
                              f"{stamp}, and that run is {busy}; nothing "
                              "was replaced. Import it again once the "
                              "delete is done.")
        # this call's own temp tree; another process's import of the same
        # bundle has its own, and only leftovers are swept (a dead process's,
        # or one nothing has written for an hour). A leftover in a protected
        # folder is never deleted: it stays, and nothing is imported
        held = []
        _sweep_stale_temps(dst, kept=held)
        if held:
            raise BundleError(f"An earlier import of {season} left "
                              f"{held[0].name} in a protected folder, "
                              "which the console never deletes; nothing "
                              "was imported.")
        tmp = _temp_tree(dst)
        files = m["files"]
        # scores.json last, so it is newer than every sample it scores (the
        # results page would otherwise rescore on the first visit)
        order = sorted(files, key=lambda f: (f == "scores.json", f))
        try:
            try:
                with zipfile.ZipFile(path) as z:
                    for f in order:
                        try:
                            _extract_member(z, f, tmp / f, files[f]["sha256"],
                                            files[f]["bytes"], name)
                        except _UNREADABLE:
                            raise BundleError(
                                f"{name}: {f} could not be unpacked; the "
                                "bundle is damaged or altered.") from None
            except _UNREADABLE:
                # the constructor's (the file changed since it was
                # inspected); a member's is refused above
                raise BundleError(f"{name} is not a readable zip "
                                  "file.") from None
            # every member still there at its size, before anything else
            # touches the tree: a temp tree that lost files while it was
            # written is refused in words (the times set below would
            # otherwise meet a missing file first) and never goes into place
            for f in order:
                try:
                    whole = (tmp / f).stat().st_size == files[f]["bytes"]
                except OSError:
                    whole = False
                if not whole:
                    raise BundleError(f"{season} from this bundle: {f} was "
                                      "removed from the import's temporary "
                                      "folder while it was imported; "
                                      "nothing was imported. Import it "
                                      "again.")
            for f in files:
                parts = f.split("/")
                if not (len(parts) == 3 and parts[0] == "weeks"
                        and parts[2] == retro.QUANTILES_NAME):
                    continue
                if f"weeks/{parts[1]}/{ORACLE_NAME}" in files:
                    os.utime(tmp / f)
                    continue
                # 2 s before the samples: older on every file system, FAT's
                # 2 s steps included
                sp = samples_file(tmp / "weeks" / parts[1])
                if sp is not None:
                    t = sp.stat().st_mtime_ns - 2_000_000_000
                    os.utime(tmp / f, ns=(t, t))
            marker = {"from": str(m.get("exported_by") or ""),
                      "exported_at": str(m.get("exported_at") or ""),
                      "imported_at": _utc_iso(), "imported_by": hostname(),
                      "bundle_sha256": m["bundle_sha256"],
                      "bundle_name": name, "source": m.get("source"),
                      "exported_build": str(m.get("flubnf_build") or ""),
                      "imported_build": build or ""}
            (tmp / IMPORTED_MARK).write_text(json.dumps(marker, indent=1,
                                                        sort_keys=True),
                                             encoding="utf-8")
            sf = tmp / "scores.json"
            if sf.is_file():
                os.utime(sf)
            # looked at again: a tree that appeared while this one was
            # extracted (another process's import) is replaced only by a
            # Replace. The old tree is renamed aside, the new one renamed
            # in, and only then is the old one deleted: a process killed at
            # any step leaves whole trees (the new run at its name, or no
            # run there and the old one aside), never part of a run at its
            # name; what it left aside goes in a later import's sweep
            aside = None
            if dst.exists() or dst.is_symlink():
                if not replace:
                    raise BundleError(f"{season} from this bundle was "
                                      f"already imported as {stamp}.")
                aside = _move_aside(dst)
            try:
                os.rename(tmp, dst)
            except OSError:
                if not (dst.exists() or dst.is_symlink()):
                    if aside is not None:
                        _put_back(aside, dst)       # the old run stays
                    raise
                # another process's import put its whole tree at the name
                # between the look and the rename: it stands
                if aside is not None:
                    _drop_aside(aside)
                if not replace:
                    raise BundleError(f"{season} from this bundle was "
                                      f"already imported as {stamp}.") \
                        from None
                raise BundleError(f"{season} from this bundle was imported "
                                  f"as {stamp} by another import that "
                                  "finished at the same moment; that one "
                                  "stands.") from None
            if aside is not None:
                _drop_aside(aside)           # the old run, now replaced
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    # read under the lock too: a Replace waiting for it would delete the
    # scores read here
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
