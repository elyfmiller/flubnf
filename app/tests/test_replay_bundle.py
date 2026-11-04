"""Export and import of a replayed season (app/core/replay_bundle).

  * a bundle round-trips: the imported archived root holds byte-identical
    run record, scores, quantiles, each week's oracle.json and samples,
    and nothing from the playback cache, a report or the donor bank; an
    imported replay is then the shipped side of an experiment with the
    Oracle step on or off (a week carrying oracle.json keeps its current
    quantiles current; a stale one is not carried), and a bundle without
    oracle.json imports as before;
  * a second export offers the earlier bundle only when it carries the
    same files;
  * the manifest pins every member's sha256 and size and names the run's
    engine build; a tampered member, a path outside the bundle, a missing
    or unlisted member, a foreign format and a malformed season are each
    refused with one sentence;
  * an import lands as a read-only archived entry named for the export
    stamp, never in the live root; importing the same bundle twice is
    refused unless replaced;
  * the index card, the season page (?archive=<stamp>) and the Storage tab
    label it "imported from <host> on <date>"; the export routes offer the
    file; the CLI export and import wrap the same module.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                             # noqa: E402
from app.core import experiments as X                        # noqa: E402
from app.core import replay_bundle as rb                     # noqa: E402
from app.core import retro                                   # noqa: E402
from app.core import retro_store as RS                       # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons         # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from test_retro_archive import (SEASON, STAMP, W1, W2, _roots,   # noqa: E402
                                _season_tree, _synthetic_data,
                                _truth_map)

client = TestClient(srv.app)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    status_before = dict(ui_state._status)
    retro_before = dict(ui_retro_seasons._retro_status)
    # a flash an earlier test file left (a register's) would lead the
    # import's own: each test starts with none
    ui_state._status.pop("flash", None)
    ui_state._status.pop("flash_detail", None)
    # the exports folder (bundles, uploads) lives under this test's state
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(retro_before)
    ui_shared._invalidate_scans()


def _flash():
    return ui_state._status.get("flash", "")


def _files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def _rezip(src: Path, dst: Path, edit) -> Path:
    """A copy of a bundle with `edit(name, data) -> (name, data) | None`
    applied to every member (None drops it)."""
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in zin.infolist():
            r = edit(i.filename, zin.read(i.filename))
            if r is not None:
                zout.writestr(r[0], r[1])
    return dst


def _export(tmp_path, rr) -> Path:
    return rb.export_season(rr / SEASON, SEASON, tmp_path / "out")


# ------------------------------------------------------------ the module

def test_export_then_import_round_trips_every_carried_file(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    (root / f"{SEASON}-FluBNF-season-report.html").write_text("<p>r</p>")
    p = _export(tmp_path, rr)
    assert p.name.startswith(f"{SEASON}-FluBNF-replay-")
    assert p.name.endswith(rb.SUFFIX)

    r = rb.import_bundle(p, tmp_path / "other")
    assert r.season == SEASON and r.weeks == [W1, W2]
    # the synthetic scores predate the version column: the one warning
    assert [w for w in r.warnings if "older scoring rule" not in w] == []
    assert r.root == tmp_path / "other" / f"{SEASON}__archived_{r.stamp}"
    assert retro.archive_stamp_of(r.root.name, SEASON) == r.stamp
    got = _files(r.root)
    marker = json.loads(got.pop(rb.IMPORTED_MARK))
    src = _files(root)
    want = {f: src[f] for f in rb.bundle_files(root)}
    assert got == want                                  # byte for byte
    # nothing rebuildable travels
    assert not any(f.startswith("playback_cache") or f.endswith(".html")
                   for f in got)
    assert marker["from"] == rb.hostname()
    assert marker["bundle_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    # the live root of the importing machine was never created
    assert not (tmp_path / "other" / SEASON).exists()


def test_the_manifest_pins_sha256_and_size_per_file(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    p = _export(tmp_path, rr)
    with zipfile.ZipFile(p) as z:
        assert z.namelist().count(rb.MANIFEST) == 1
        m = json.loads(z.read(rb.MANIFEST))
    assert m["format_version"] == 1 and m["season"] == SEASON
    assert m["source"] == "live" and retro.valid_stamp(m["stamp"])
    assert m["weeks"] == [W1, W2]
    assert m["exported_by"] == rb.hostname()
    assert m["exported_at"].endswith("Z")
    assert set(m["files"]) == set(rb.bundle_files(root)) == {
        "run_meta.json", "scores.json",
        f"weeks/{W1}/samples.json", f"weeks/{W2}/samples.json"}
    for f, ent in m["files"].items():
        data = (root / f).read_bytes()
        assert ent["sha256"] == hashlib.sha256(data).hexdigest()
        assert ent["bytes"] == len(data)
    assert m["total_bytes"] == sum(e["bytes"] for e in m["files"].values())
    assert rb.inspect_bundle(p)["bundle_bytes"] == p.stat().st_size
    assert m["engine_build"] == {}              # the record names none


def test_the_manifest_names_the_runs_engine_build(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    # as run_season records it
    build = {"branch": "feature/particle-filter", "commit": "2fdadee0",
             "dirty": False, "source": "git"}
    meta = retro.read_meta(root)
    retro.write_meta(root, {**meta, "settings": {"engine_build": build}})
    with zipfile.ZipFile(_export(tmp_path, rr)) as z:
        assert json.loads(z.read(rb.MANIFEST))["engine_build"] == build


def test_a_second_export_of_an_unchanged_root_reuses_the_bundle(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    assert _export(tmp_path, rr) == _export(tmp_path, rr)


def test_an_archived_root_exports_with_its_stamp_as_the_source(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    arch = retro.archive_run(rr, SEASON, stamp=STAMP)
    p = rb.export_season(arch, SEASON, tmp_path / "out", stamp=STAMP)
    assert rb.inspect_bundle(p)["source"] == STAMP


def test_a_tampered_member_is_refused_and_nothing_lands(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    p = _export(tmp_path, rr)
    bad = _rezip(p, tmp_path / "bad.zip",
                 lambda n, d: (n, b" " + d[1:]) if n == "scores.json"
                 else (n, d))
    with pytest.raises(rb.BundleError, match="does not match its sha256"):
        rb.import_bundle(bad, tmp_path / "other")
    assert list((tmp_path / "other").iterdir()) == []   # no half import


def test_a_path_outside_the_bundle_is_refused(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    p = _export(tmp_path, rr)
    for evil in ("../evil.json", "/etc/evil.json", "weeks/../../x.json"):
        def edit(n, d, evil=evil):
            if n == rb.MANIFEST:
                m = json.loads(d)
                m["files"][evil] = m["files"].pop("scores.json")
                return n, json.dumps(m).encode()
            return (evil, d) if n == "scores.json" else (n, d)
        bad = _rezip(p, tmp_path / "bad.zip", edit)
        with pytest.raises(rb.BundleError, match="outside the bundle"):
            rb.inspect_bundle(bad)


def test_missing_unlisted_foreign_and_malformed_bundles_are_refused(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    p = _export(tmp_path, rr)
    # a listed member missing from the zip
    bad = _rezip(p, tmp_path / "bad.zip",
                 lambda n, d: None if n == "scores.json" else (n, d))
    with pytest.raises(rb.BundleError, match="is missing scores.json"):
        rb.inspect_bundle(bad)
    # a member the manifest does not list
    bad = _rezip(p, tmp_path / "bad.zip", lambda n, d: (n, d))
    with zipfile.ZipFile(bad, "a") as z:
        z.writestr("stranger.json", b"{}")
    with pytest.raises(rb.BundleError, match="does not list"):
        rb.inspect_bundle(bad)

    def version(n, d):
        if n == rb.MANIFEST:
            m = json.loads(d); m["format_version"] = 9
            return n, json.dumps(m).encode()
        return n, d
    with pytest.raises(rb.BundleError, match="format 9"):
        rb.inspect_bundle(_rezip(p, tmp_path / "bad.zip", version))

    def season(n, d):
        if n == rb.MANIFEST:
            m = json.loads(d); m["season"] = "../x"
            return n, json.dumps(m).encode()
        return n, d
    with pytest.raises(rb.BundleError, match="not a season name"):
        rb.inspect_bundle(_rezip(p, tmp_path / "bad.zip", season))

    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as z:
        z.writestr("a.txt", b"hi")
    with pytest.raises(rb.BundleError, match="not a replay bundle"):
        rb.inspect_bundle(plain)
    notzip = tmp_path / "x.zip"; notzip.write_bytes(b"nope")
    with pytest.raises(rb.BundleError, match="not a zip file"):
        rb.inspect_bundle(notzip)
    with pytest.raises(rb.BundleError, match="no such file"):
        rb.inspect_bundle(tmp_path / "absent.zip")


def test_a_bomb_ratio_is_refused(tmp_path, monkeypatch):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    (root / "scores.json").write_bytes(b"0" * 200_000)  # deflates ~1000x
    p = _export(tmp_path, rr)
    with pytest.raises(rb.BundleError, match="inflation"):
        rb.inspect_bundle(p)


def test_importing_the_same_bundle_twice_is_refused_unless_replaced(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    p = _export(tmp_path, rr)
    other = tmp_path / "other"
    r = rb.import_bundle(p, other)
    (r.root / "playback_cache").mkdir()                 # a later visit's cache
    with pytest.raises(rb.BundleError,
                       match=f"already imported as {r.stamp}"):
        rb.import_bundle(p, other)
    assert (r.root / "playback_cache").is_dir()         # untouched
    r2 = rb.import_bundle(p, other, replace=True)
    assert r2.root == r.root
    assert not (r.root / "playback_cache").exists()     # a fresh copy
    assert [d.name for d in other.iterdir()] == [r.root.name]


def test_imported_label_reads_from_the_marker(tmp_path):
    root = tmp_path / "x"; root.mkdir()
    assert rb.imported_label(root) == ""
    (root / rb.IMPORTED_MARK).write_text(json.dumps(
        {"from": "lab-mac", "imported_at": "2098-03-01T10:00:00Z"}))
    assert rb.imported_label(root) == "imported from lab-mac on 2098-03-01"


# ---------------------------------------------------------- oracle.json


def _oracle_json(root: Path, asof: str, value: float) -> Path:
    """A week's oracle.json as the Oracle step writes it, the Liu-West
    filter's own quantiles in it."""
    p = root / "weeks" / asof / RS.ORACLE_NAME
    p.write_text(json.dumps({"applied": True, "quantiles": {
        "levels": [0.5], "null": {"Ohio": {"0": {"unrounded": [value]}}}}}),
        encoding="utf-8", newline="\n")
    return p


def test_a_bundle_carries_each_weeks_oracle_json(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    for i, w in enumerate((W1, W2)):
        _oracle_json(root, w, 3.0 + i)
    bank = root / "weeks" / W1 / "oracle_bank"
    bank.mkdir()
    (bank / "donors.json").write_text("{}", encoding="utf-8", newline="\n")
    assert rb.bundle_files(root) == [
        "run_meta.json", "scores.json",
        f"weeks/{W1}/oracle.json", f"weeks/{W1}/samples.json",
        f"weeks/{W2}/oracle.json", f"weeks/{W2}/samples.json"]
    r = rb.import_bundle(_export(tmp_path, rr), tmp_path / "other")
    got = _files(r.root)
    got.pop(rb.IMPORTED_MARK)
    src = _files(root)
    assert got == {f: src[f] for f in rb.bundle_files(root)}
    assert not (r.root / "weeks" / W1 / "oracle_bank").exists()
    for w in (W1, W2):
        filtered = RS.filter_quantiles(root / "weeks" / w)
        assert filtered and RS.filter_quantiles(r.root / "weeks" / w) == \
            filtered


def test_an_imported_replay_is_the_reference_with_the_step_on_or_off(
        tmp_path):
    from test_experiments import SMOKE_WEEKS, _replay
    rr = tmp_path / "retro"
    _replay(rr / "2024-25", weeks=SMOKE_WEEKS)
    p = rb.export_season(rr / "2024-25", "2024-25", tmp_path / "out")
    r = rb.import_bundle(p, tmp_path / "other")
    ref = X.reference(tmp_path / "other", "2024-25", False, SMOKE_WEEKS)
    assert (ref["root"], ref["member"]) == (r.root, RS.FILTER_MEMBER)
    # the step on reads the quantiles, which landed before the samples
    # and were made current: the Oracle SIHRS, as at the source
    ref = X.reference(tmp_path / "other", "2024-25", True, SMOKE_WEEKS)
    assert (ref["root"], ref["member"]) == (r.root, "pf")
    for w in SMOKE_WEEKS:
        assert (RS.read_week_quantiles(r.root / "weeks" / w)
                == RS.read_week_quantiles(rr / "2024-25" / "weeks" / w))
    # a bundle without oracle.json, as one exported before: none either
    # way, its quantiles left older than its samples as they always were
    retro.delete_tree(rr / "2024-25")
    _replay(rr / "2024-25", weeks=SMOKE_WEEKS, filter_=False)
    p = rb.export_season(rr / "2024-25", "2024-25", tmp_path / "out2")
    r = rb.import_bundle(p, tmp_path / "third")
    for oracle in (False, True):
        assert X.reference(tmp_path / "third", "2024-25", oracle,
                           SMOKE_WEEKS) is None
    assert all(RS.read_week_quantiles(r.root / "weeks" / w) is None
               for w in SMOKE_WEEKS)


def test_the_quantiles_land_on_the_right_side_of_a_coarse_clock(
        tmp_path, monkeypatch):
    # the import on one clock tick, as Windows' clock can stamp quick
    # writes: every member and every "now" alike. A week without
    # oracle.json still lands older than its samples, so a bundle exported
    # before is nobody's reference; one with oracle.json ties its samples
    # and reads current
    from test_experiments import SMOKE_WEEKS, _replay
    real, utime = rb._extract_member, os.utime
    stamp = 1_700_000_000 * 10 ** 9

    def at_one_stamp(z, name, dst, *a):
        real(z, name, dst, *a)
        utime(dst, ns=(stamp, stamp))

    def now_at_the_stamp(path, times=None, *, ns=None, **kw):
        if times is None and ns is None:
            ns = (stamp, stamp)
        utime(path, times, ns=ns, **kw)
    for filter_, into in ((False, "old"), (True, "new")):
        src = _replay(tmp_path / f"{into}-retro" / "2024-25",
                      weeks=SMOKE_WEEKS, filter_=filter_)
        p = rb.export_season(src, "2024-25", tmp_path / f"{into}-out")
        assert any(f.endswith(RS.QUANTILES_NAME) for f in rb.bundle_files(src))
        with monkeypatch.context() as m:
            m.setattr(rb, "_extract_member", at_one_stamp)
            m.setattr(os, "utime", now_at_the_stamp)
            r = rb.import_bundle(p, tmp_path / into)
        for w in SMOKE_WEEKS:
            wd = r.root / "weeks" / w
            gap = ((wd / RS.QUANTILES_NAME).stat().st_mtime_ns
                   - RS.samples_file(wd).stat().st_mtime_ns)
            assert gap == (0 if filter_ else -2 * 10 ** 9)
            assert (RS.read_week_quantiles(wd) is None) is not filter_
        refs = [X.reference(tmp_path / into, "2024-25", oracle, SMOKE_WEEKS)
                for oracle in (False, True)]
        if filter_:
            assert [x["member"] for x in refs] == [RS.FILTER_MEMBER, "pf"]
        else:
            assert refs == [None, None]


def test_a_stale_sidecar_is_not_carried(tmp_path):
    from test_experiments import SMOKE_WEEKS, _replay
    root = _replay(tmp_path / "retro" / "2024-25", weeks=SMOKE_WEEKS)
    old, new = (root / "weeks" / w for w in SMOKE_WEEKS)
    t = (old / RS.SAMPLES_JSON).stat().st_mtime - 60
    os.utime(old / RS.QUANTILES_NAME, (t, t))      # its samples rewritten
    assert RS.read_week_quantiles(old) is None
    files = rb.bundle_files(root)
    assert f"weeks/{old.name}/{RS.QUANTILES_NAME}" not in files
    assert f"weeks/{new.name}/{RS.QUANTILES_NAME}" in files
    assert f"weeks/{old.name}/{RS.ORACLE_NAME}" in files
    p = rb.export_season(root, "2024-25", tmp_path / "out")
    r = rb.import_bundle(p, tmp_path / "other")
    assert not (r.root / "weeks" / old.name / RS.QUANTILES_NAME).exists()
    assert RS.read_week_quantiles(r.root / "weeks" / new.name) is not None


def test_a_bundle_without_oracle_json_imports_as_before(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    for w in (W1, W2):
        _oracle_json(root, w, 3.0)
    p = _export(tmp_path, rr)

    def older(n, d):
        """The bundle as FluBNF exported it before it carried oracle.json."""
        if n.endswith("/" + RS.ORACLE_NAME):
            return None
        if n == rb.MANIFEST:
            m = json.loads(d)
            m["files"] = {f: e for f, e in m["files"].items()
                          if not f.endswith("/" + RS.ORACLE_NAME)}
            m["total_bytes"] = sum(e["bytes"] for e in m["files"].values())
            return n, json.dumps(m).encode()
        return n, d
    old = _rezip(p, tmp_path / "old.zip", older)
    r = rb.import_bundle(old, tmp_path / "other")
    assert r.weeks == [W1, W2]
    got = _files(r.root)
    got.pop(rb.IMPORTED_MARK)
    src = _files(root)
    assert got == {f: src[f] for f in ("run_meta.json", "scores.json",
                                       f"weeks/{W1}/samples.json",
                                       f"weeks/{W2}/samples.json")}


def test_a_bundle_is_offered_again_only_with_the_same_files(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    first = _export(tmp_path, rr)
    assert _export(tmp_path, rr) == first
    # oracle.json older than the bundle, which lacks it: a new bundle
    t = first.stat().st_mtime - 100
    for w in (W1, W2):
        os.utime(_oracle_json(root, w, 3.0), (t, t))
    second = _export(tmp_path, rr)
    assert second != first and first.is_file()
    assert f"weeks/{W1}/oracle.json" in rb.inspect_bundle(second)["files"]
    assert _export(tmp_path, rr) == second


@pytest.mark.skipif(os.name == "nt", reason="links need rights on Windows")
def test_a_linked_oracle_json_is_not_carried(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real = _oracle_json(root, W2, 3.0)
    os.replace(real, elsewhere / RS.ORACLE_NAME)
    os.symlink(elsewhere / RS.ORACLE_NAME, real)
    _oracle_json(root, W1, 4.0)
    files = rb.bundle_files(root)
    assert f"weeks/{W1}/oracle.json" in files
    assert f"weeks/{W2}/oracle.json" not in files
    r = rb.import_bundle(_export(tmp_path, rr), tmp_path / "other")
    assert not os.path.lexists(r.root / "weeks" / W2 / RS.ORACLE_NAME)


# ---------------------------------------------------------------- the UI

def _import_into_app(tmp_path, monkeypatch, truth=None):
    """A season exported from one root and imported into the app's."""
    rr = _roots(tmp_path, monkeypatch)
    src = tmp_path / "elsewhere"; src.mkdir()
    _season_tree(src, SEASON, truth=truth)
    p = rb.export_season(src / SEASON, SEASON, tmp_path / "out")
    r = rb.import_bundle(p, rr)
    ui_shared._invalidate_scans()
    return rr, p, r


def test_the_index_card_labels_the_import_for_where_it_came_from(
        tmp_path, monkeypatch):
    rr, p, r = _import_into_app(tmp_path, monkeypatch)
    html = client.get("/retro").text
    label = rb.imported_label(r.root)
    assert label.startswith("imported from ")
    assert f"<strong>{label}</strong>" in html
    assert 'data-imported="1"' in html
    assert f'href="/retro/{SEASON}?archive={r.stamp}"' in html
    assert f"/retro/{SEASON}/archive/{r.stamp}/delete" in html
    # the import control sits in the Settings card
    assert 'action="/retro/import"' in html
    assert 'accept=".zip,.flubnf-replay.zip' in html
    assert 'name="path"' in html


def test_the_season_page_renders_the_import_and_says_so(tmp_path,
                                                        monkeypatch):
    truth = _synthetic_data(monkeypatch, tmp_path)
    rr, p, r = _import_into_app(tmp_path, monkeypatch, truth=truth)
    res = client.get(f"/retro/{SEASON}?archive={r.stamp}")
    assert res.status_code == 200
    html = res.text
    assert 'id="imported-banner"' in html
    assert f"Imported from {rb.hostname()}" in html
    assert "read only" in html
    assert "Archived run" not in html                 # not the archive banner
    assert f'const ARCHIVE = "{r.stamp}";' in html    # the player reads it
    assert "Season player" in html
    # the player's payload comes from the imported tree
    pb = client.get(f"/api/retro/{SEASON}/playback/{W1}?archive={r.stamp}")
    assert pb.status_code == 200 and pb.json()["asof"] == W1
    assert (r.root / "playback_cache").is_dir()


def test_the_export_button_and_routes_offer_the_bundle(tmp_path,
                                                        monkeypatch):
    truth = _synthetic_data(monkeypatch, tmp_path)
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON, truth=truth)
    html = client.get(f"/retro/{SEASON}").text
    assert 'id="exp-replay"' in html and "Export replay" in html
    assert f'data-href="/retro/{SEASON}/export"' in html
    assert "Download report" in html

    d = client.get(f"/retro/{SEASON}/export")
    assert d.status_code == 200
    assert d.headers["content-type"] == "application/zip"
    assert "attachment" in d.headers["content-disposition"]
    assert rb.SUFFIX in d.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(d.content)) as z:
        assert rb.MANIFEST in z.namelist()
    j = client.get(f"/api/retro/{SEASON}/export_path").json()
    assert Path(j["path"]).is_file() and j["bytes"] == len(d.content)
    assert j["size_h"].endswith("KB") and j["name"].endswith(rb.SUFFIX)
    assert Path(j["path"]).parent == runs_mod.APP_STATE / "exports"
    # an archived root's page and routes too
    retro.archive_run(rr, SEASON, stamp=STAMP)
    _season_tree(rr, SEASON, truth=truth)
    html = client.get(f"/retro/{SEASON}?archive={STAMP}").text
    assert f'data-href="/retro/{SEASON}/export?archive={STAMP}"' in html
    assert client.get(f"/retro/{SEASON}/export?archive={STAMP}").status_code == 200
    assert client.get(f"/retro/{SEASON}/export?archive=nope").status_code == 404
    assert client.get(f"/api/retro/{SEASON}/export_path?archive=nope").status_code == 404


def test_a_season_without_weeks_has_no_bundle(tmp_path, monkeypatch):
    _roots(tmp_path, monkeypatch)
    r = client.get(f"/retro/{SEASON}/export")
    assert r.status_code == 404 and "no completed weeks" in r.text


def test_post_import_with_an_upload_lands_and_opens_the_season(tmp_path,
                                                                monkeypatch):
    truth = _synthetic_data(monkeypatch, tmp_path)
    rr = _roots(tmp_path, monkeypatch)
    src = tmp_path / "elsewhere"; src.mkdir()
    _season_tree(src, SEASON, truth=truth)
    p = rb.export_season(src / SEASON, SEASON, tmp_path / "out")
    stamp = rb.inspect_bundle(p)["stamp"]
    with open(p, "rb") as f:
        r = client.post("/retro/import", files={"file": (p.name, f,
                                                          "application/zip")},
                        follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/retro/{SEASON}?archive={stamp}"
    assert _flash().startswith(f"Imported {SEASON} (2 weeks).")
    assert ui_state._status.get("flash_detail", "").startswith(
        f"Exported from {rb.hostname()} on ")
    assert (rr / f"{SEASON}__archived_{stamp}" / "scores.json").is_file()
    assert not (rr / SEASON).exists()                 # never the live root
    # the streamed upload left nothing behind
    assert not list((runs_mod.APP_STATE / "exports").glob("incoming-*"))
    # a second upload of the same bundle is refused, and says so
    with open(p, "rb") as f:
        r = client.post("/retro/import", files={"file": (p.name, f)},
                        follow_redirects=False)
    assert r.headers["location"] == "/retro"
    assert f"Not imported: {SEASON} from this bundle was already imported as {stamp}." in _flash()
    # and replaced on request
    with open(p, "rb") as f:
        r = client.post("/retro/import", files={"file": (p.name, f)},
                        data={"replace": "1"}, follow_redirects=False)
    assert r.headers["location"] == f"/retro/{SEASON}?archive={stamp}"


def test_post_import_takes_a_local_path_and_refuses_bad_input(tmp_path,
                                                              monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    src = tmp_path / "elsewhere"; src.mkdir()
    _season_tree(src, SEASON)
    p = rb.export_season(src / SEASON, SEASON, tmp_path / "out")
    r = client.post("/retro/import", data={"path": str(p)},
                    follow_redirects=False)
    assert r.status_code == 303 and "?archive=" in r.headers["location"]
    assert len(retro.list_archive_dirs(rr, SEASON)) == 1

    r = client.post("/retro/import", data={}, follow_redirects=False)
    assert r.headers["location"] == "/retro"
    assert "Not imported: choose a bundle" in _flash()
    notzip = tmp_path / "x.zip"; notzip.write_bytes(b"nope")
    r = client.post("/retro/import", data={"path": str(notzip)},
                    follow_redirects=False)
    assert r.headers["location"] == "/retro"
    assert "Not imported: x.zip is not a zip file." in _flash()
    r = client.post("/retro/import", data={"path": str(tmp_path / "no.zip")},
                    follow_redirects=False)
    assert "Not imported: no.zip: no such file." in _flash()
    assert len(retro.list_archive_dirs(rr, SEASON)) == 1


def test_a_path_pasted_in_quotes_imports(tmp_path, monkeypatch):
    """File Explorer's Copy as path (Ctrl+Shift+C) wraps the path in double
    quotes: the field takes it as the path inside them."""
    rr = _roots(tmp_path, monkeypatch)
    src = tmp_path / "elsewhere"; src.mkdir()
    _season_tree(src, SEASON)
    p = rb.export_season(src / SEASON, SEASON, tmp_path / "out")
    r = client.post("/retro/import", data={"path": f' "{p}" '},
                    follow_redirects=False)
    assert r.status_code == 303 and "?archive=" in r.headers["location"]
    assert _flash().startswith(f"Imported {SEASON}")
    assert len(retro.list_archive_dirs(rr, SEASON)) == 1
    from app.ui.routes import retro as ui_retro
    assert ui_retro._pasted_path('"C:\\Users\\Ely Miller\\x.zip"') == \
        "C:\\Users\\Ely Miller\\x.zip"
    assert ui_retro._pasted_path("  /Users/ely/x.zip ") == "/Users/ely/x.zip"
    assert ui_retro._pasted_path('"') == '"'          # not a pair: as typed
    assert ui_retro._pasted_path(None) == ""


def test_the_path_example_is_this_machines_shape(monkeypatch):
    from app.ui import templating as ui_templating
    monkeypatch.setattr(ui_templating, "_platform", lambda: "win32")
    html = client.get("/retro").text
    assert ('placeholder="C:\\Users\\you\\Downloads\\2025-26-FluBNF-replay-'
            '….flubnf-replay.zip"') in html
    monkeypatch.setattr(ui_templating, "_platform", lambda: "darwin")
    assert 'placeholder="/Users/you/Downloads/2025-26-FluBNF-replay-' in \
        client.get("/retro").text


def test_the_storage_tab_lists_the_import_and_deletes_it(tmp_path,
                                                         monkeypatch):
    rr, p, r = _import_into_app(tmp_path, monkeypatch)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    html = client.get("/storage").text
    label = rb.imported_label(r.root)
    row = html.split(f">{SEASON} retrospective</a></strong>", 1)[1] \
              .split("</div>", 1)[0]
    assert f"<span>{label}</span>" in row
    assert r.root.name in html
    size_h = retro.human_bytes(retro.dir_size(r.root))
    assert size_h in html
    res = client.post("/storage/delete",
                      data={"kind": "retro-archive", "ident": r.root.name,
                            "confirm": r.root.name},
                      follow_redirects=False)
    assert res.status_code == 303
    assert not r.root.exists()


def test_the_archive_delete_route_removes_an_import(tmp_path, monkeypatch):
    rr, p, r = _import_into_app(tmp_path, monkeypatch)
    res = client.post(f"/retro/{SEASON}/archive/{r.stamp}/delete",
                      data={"confirm": SEASON}, follow_redirects=False)
    assert res.status_code == 303 and not r.root.exists()


# --------------------------------------------------------------- the CLI

def test_cli_export_and_import(tmp_path, monkeypatch):
    from flubnf.cli import app as cli_app
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON)
    runner = CliRunner()
    res = runner.invoke(cli_app, ["retro", "export", SEASON, "--root", str(rr),
                                  "--out", str(tmp_path / "out")])
    assert res.exit_code == 0, res.output
    assert f"{SEASON}: 2 weeks, " in res.output and rb.SUFFIX in res.output
    p = next((tmp_path / "out").glob("*" + rb.SUFFIX))
    other = tmp_path / "other"
    res = runner.invoke(cli_app, ["retro", "import", str(p), "--root",
                                  str(other)])
    assert res.exit_code == 0, res.output
    assert f"imported {SEASON}: 2 weeks, exported from" in res.output
    assert f"/retro/{SEASON}?archive=" in res.output
    res = runner.invoke(cli_app, ["retro", "import", str(p), "--root",
                                  str(other)])
    assert res.exit_code == 2 and "already imported" in res.output
    res = runner.invoke(cli_app, ["retro", "import", str(p), "--root",
                                  str(other), "--replace"])
    assert res.exit_code == 0, res.output
    # an archived run exports by its stamp
    retro.archive_run(rr, SEASON, stamp=STAMP)
    res = runner.invoke(cli_app, ["retro", "export", SEASON, "--root", str(rr),
                                  "--archive", STAMP, "--out",
                                  str(tmp_path / "out2")])
    assert res.exit_code == 0, res.output
    res = runner.invoke(cli_app, ["retro", "export", SEASON, "--root", str(rr),
                                  "--out", str(tmp_path / "out3")])
    assert res.exit_code == 2 and "no completed weeks" in res.output


def test_cli_retro_bare_season_still_replays(tmp_path, monkeypatch):
    """`flubnf retro <season>` keeps its meaning beside the subcommands."""
    from flubnf.cli import app as cli_app
    res = CliRunner().invoke(cli_app, ["retro", "1999", "--locations", "Ohio"])
    assert res.exit_code == 2 and "is not a season" in res.output
    res = CliRunner().invoke(cli_app, ["retro", "--help"])
    assert res.exit_code == 0
    for word in ("run", "export", "import"):
        assert word in res.output
