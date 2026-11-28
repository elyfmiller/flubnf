"""A week whose newest real-time run was made with modified model settings
is archived like any other (the 2026-11-27 decision; the pages that show
such a run: test_newest_run_shown.py).

  * the pipeline's archive step counts a member's file under its hub name
    or its -modified name, so a modified run of both models is complete;
  * the archive keeps the run's files under their -modified names and its
    knobs.json, and its record says the run was modified; the keep rule
    is the same (a later run replaces it, a vintage backtest never does);
  * Output's Archived weeks picker reads "(modified settings)" for such a
    week and opens that week's report; Storage's report archive row says
    "modified settings" as its workroot rows do; the card's own week is
    offered once;
  * an archive record from before the flag is read from its folder (a
    modified run's knobs.json travels with its files);
  * a week's archived files under the hub names (the files that went to
    the hub) are never replaced by a run whose files carry the -modified
    names; such a run still fills a week with no archive or one of
    -modified files, and a hub-named run still replaces -modified files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import archive_record as AR                      # noqa: E402
from app.core import run_label                                 # noqa: E402
from app.core.runs import Ledger                               # noqa: E402
from app.ui import pipeline as P                               # noqa: E402

from test_newest_run_shown import DATE, GH, MOD, _run, client, root  # noqa: E402,F401
from test_optional_outputs import _default_run, pipeline_env   # noqa: E402,F401
from test_oracle_step import hubfiles                          # noqa: E402,F401

#: pipeline_env stubs the archive; the archive tests put the real one back
REAL_ARCHIVE = P._archive_run


def test_the_pipeline_counts_a_modified_runs_files_as_complete(pipeline_env,
                                                               monkeypatch):
    """Through _run_all: the archive step is reached for a run with
    modified settings, and its two -modified files count as both models'
    (the run is complete)."""
    seen = []
    monkeypatch.setattr(P, "_archive_run", lambda w, d, **k: seen.append(
        k.get("complete", True)) or "archived")
    _spec, out = _default_run(pipeline_env["names"], knobs=MOD)
    assert set(out["submissions"]) == {"NAU_PyBNF-OracleSIHRS-modified",
                                       GH + "-modified"}
    assert out["archived"] == "archived" and seen == [True]
    assert P._members_written(out["submissions"]) == {
        "NAU_PyBNF-OracleSIHRS", GH}


def test_a_modified_run_is_archived_with_its_modified_files(pipeline_env,
                                                            monkeypatch):
    monkeypatch.setattr(P, "_archive_run", REAL_ARCHIVE)
    spec, out = _default_run(pipeline_env["names"], knobs=MOD)
    arch = runs_mod.APP_STATE / "archive" / spec.forecast_date
    assert out["archived"] == str(arch)
    rid = next(iter(Ledger().rows(1)))["run_id"]
    rec = AR.read_record(arch)
    assert rec["run_id"] == rid and rec["complete"] is True
    assert rec["modified"] is True and AR.modified_of(arch)
    # the files keep their -modified names; the settings travel with them
    assert sorted(p.parent.name for p in arch.glob("submission/*/*.csv")) \
        == ["NAU_PyBNF-GroundHogCGR-modified", "NAU_PyBNF-OracleSIHRS-modified"]
    assert (arch / "knobs.json").is_file()
    # a later run on the shipped settings replaces it by the same rule,
    # and its record says it is not modified
    import time
    time.sleep(1.1)
    _spec, again = _default_run(pipeline_env["names"])
    assert again["archived"] == str(arch)
    rec = AR.read_record(arch)
    assert rec["modified"] is False and not AR.modified_of(arch)
    assert sorted(p.parent.name for p in arch.glob("submission/*/*.csv")) \
        == ["NAU_PyBNF-GroundHogCGR", "NAU_PyBNF-OracleSIHRS"]


def test_a_backtest_never_replaces_a_modified_real_time_week(root):
    week = _run(root, "in its week", knobs=MOD)
    P._archive_run(root / "workroots" / week, DATE)
    later = _run(root, "backtest", mode="vintage")
    out = P._archive_run(root / "workroots" / later, DATE, realtime=False)
    assert out.startswith("kept: this run is a vintage run of a past week")
    assert AR.read_record(root / "archive" / DATE)["run_id"] == week


def test_the_picker_and_storage_mark_a_modified_archived_week(root):
    other = "2097-12-27"
    shipped = _run(root, "shipped", asof=other)
    P._archive_run(root / "workroots" / shipped, other)
    mod = _run(root, "modified", knobs=MOD)
    P._archive_run(root / "workroots" / mod, DATE)
    arch = root / "archive" / DATE
    assert (arch / "submission" / (GH + "-modified")).is_dir()
    assert AR.read_record(arch)["modified"] is True
    # a newer week on the card, so both archived weeks are in the picker
    _run(root, "next week", asof="2098-01-10")
    html = client.get("/output").text
    picker = html.split('<select id="archreport">', 1)[1].split("</select>", 1)[0]
    assert (f'<option value="{DATE}">{run_label.text(DATE)} '
            '(modified settings)</option>') in picker
    assert f'<option value="{other}">{run_label.text(other)}</option>' in picker
    # the week it opens is that week's, the modified run's report
    assert "REPORT modified" in client.get(f"/output/report?date={DATE}").text
    r = client.get(f"/output/report/download?date={DATE}")
    assert r.status_code == 200 and "REPORT modified" in r.text
    assert "-weekly-report-modified.html" in r.headers["content-disposition"]
    # Storage's report archive rows say it as their workroot rows do
    rows = client.get("/storage").text.split(
        "Weekly report and submissions · ")[1:]
    by = {row.split("</strong>", 1)[0]: row.split('class="st-size"', 1)[0]
          for row in rows}
    (mine,) = [v for k, v in by.items() if run_label.text(DATE) in k]
    (theirs,) = [v for k, v in by.items() if run_label.text(other) in k]
    assert ('<span class="uk-badge uk-badge--neutral" data-state="neutral">'
            in mine and ">modified settings</span>" in mine)
    assert "modified settings" not in theirs


def test_the_card_offers_the_week_once_when_the_archive_holds_its_run(root):
    mod = _run(root, "modified", knobs=MOD)
    P._archive_run(root / "workroots" / mod, DATE)
    html = client.get("/output").text
    card = html.split('id="weekly-report"', 1)[1]
    assert f'href="/runs/{mod}/report"' in card
    assert f'<option value="{DATE}"' not in html      # the card offers it


def test_an_older_archive_record_is_read_from_its_folder(tmp_path):
    d = tmp_path / DATE
    d.mkdir()
    AR._write_json(d / AR.RECORD, {"run_id": "x", "complete": True})
    assert AR.modified_of(d) is False
    (d / "knobs.json").write_text("{}")
    assert AR.modified_of(d) is True
    # a record that says so is believed
    AR.write_record(d, "x", True, modified=False)
    assert AR.modified_of(d) is False
    assert AR.modified_of(tmp_path / "nowhere") is False


def _names(arch: Path) -> list:
    return sorted(p.parent.name for p in arch.glob("submission/*/*.csv"))


def test_a_modified_named_run_never_replaces_a_hub_named_week(root):
    arch = root / "archive" / DATE
    shipped = _run(root, "shipped")
    P._archive_run(root / "workroots" / shipped, DATE)
    mod = _run(root, "modified", knobs=MOD)
    out = P._archive_run(root / "workroots" / mod, DATE)
    assert out == ("kept: this run's files carry the -modified names, so "
                   "the archive kept the earlier run whose files carry the "
                   f"hub names {shipped}")
    assert AR.read_record(arch)["run_id"] == shipped
    assert _names(arch) == [GH]
    assert AR.read_record(arch)["hub_names"] is True
    # a modified run exported under the hub names by override replaces it,
    # and a -modified run never replaces that one either
    ov = _run(root, "override", knobs=MOD, override="the hub's own weight")
    assert P._archive_run(root / "workroots" / ov, DATE) == str(arch)
    rec = AR.read_record(arch)
    assert rec["run_id"] == ov and rec["hub_names"] is True
    assert rec["modified"] is True
    mod2 = _run(root, "modified again", knobs=MOD)
    assert P._archive_run(root / "workroots" / mod2, DATE).startswith(
        "kept: this run's files carry the -modified names")
    assert AR.read_record(arch)["run_id"] == ov


def test_a_modified_named_run_replaces_modified_files_and_yields_to_hub(root):
    arch = root / "archive" / DATE
    first = _run(root, "modified", knobs=MOD)
    P._archive_run(root / "workroots" / first, DATE)
    later = _run(root, "modified later", knobs=MOD)
    assert P._archive_run(root / "workroots" / later, DATE) == str(arch)
    assert AR.read_record(arch)["run_id"] == later
    assert _names(arch) == [GH + "-modified"]
    assert AR.read_record(arch)["hub_names"] is False
    shipped = _run(root, "shipped")
    assert P._archive_run(root / "workroots" / shipped, DATE) == str(arch)
    assert AR.read_record(arch)["run_id"] == shipped
    assert _names(arch) == [GH]
    assert AR.read_record(arch)["hub_names"] is True


def test_an_older_record_is_hub_named_by_its_folders_files(root):
    """A record from before "hub_names": the folder's own file names say
    (any CSV under a hub model's name, a retired one included)."""
    arch = root / "archive" / DATE
    for folder, hub in (("NAU-PF-SIHRS", True), (GH, True),
                        (GH + "-modified", False)):
        if arch.exists():
            import shutil
            shutil.rmtree(arch)
        (arch / "submission" / folder).mkdir(parents=True)
        (arch / "submission" / folder / "f.csv").write_text("x")
        AR._write_json(arch / AR.RECORD, {"run_id": "older",
                                          "complete": True})
        assert AR.hub_named_of(arch) is hub
        mod = _run(root, "modified", knobs=MOD)
        out = P._archive_run(root / "workroots" / mod, DATE)
        assert out.startswith("kept: this run's files carry") is hub
        assert (AR.read_record(arch)["run_id"] == "older") is hub
    assert AR.files_hub_named(root / "nowhere") is None

