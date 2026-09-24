"""A file written under a retired model name is never handed over as a
submission.

The hub identity is the DIRECTORY model-output/<team>-<model>/, registered
in model-metadata/. Old runs left trees under retired names (submit.LEGACY_DIRS); they stay
visible as archived files (a record of what ran), named by the model they
are, never offered as a submission, enforced by the route as well as the
template.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core.submit import hub_model_id             # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui.routes import output as ui_output        # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402

client = TestClient(srv.app)

RID = "20980103T101500-abcdef"
GOOD = hub_model_id("pf")                            # NAU_PyBNF-OracleSIHRS
RETIRED = "NAU-Ensemble"                             # what the old runs wrote
HEADER = ("reference_date,target,horizon,target_end_date,location,"
          "output_type,output_type_id,value\n")


def _sub(w: Path, model: str, date: str) -> Path:
    d = w / "submission" / model
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date}-{model}.csv"
    p.write_text(HEADER + f"{date},wk inc flu hosp,0,{date},06,"
                          "quantile,0.5,146.45249599494792\n")
    return p


@pytest.fixture
def run(tmp_path, monkeypatch):
    """One workroot holding both shapes: the registered identity and the
    retired one, exactly as the archives on disk hold them."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / RID
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps(
        {"models": {}, "forecast_date": "2098-01-10", "spec": ""}))
    good = _sub(w, GOOD, "2098-01-10")
    retired = _sub(w, RETIRED, "2098-01-03")
    ui_shared._invalidate_scans()
    yield w, good, retired
    ui_shared._invalidate_scans()


def _download_targets(html: str) -> list:
    """Every file the page offers through /output/download, decoded, so the
    assertion does not depend on which characters the template escaped."""
    import re
    from urllib.parse import unquote
    return [unquote(m) for m in
            re.findall(r"/output/download\?path=([^\"'&>\s]+)", html)]


def test_output_page_offers_the_registered_file_and_withholds_the_other(run):
    w, good, retired = run
    html = client.get("/output").text
    assert good.name in html and retired.name in html      # both SEEN
    assert _download_targets(html) == [str(good)]
    assert "Archived files (1)" in html
    assert "retired hub name" in html


def test_run_page_shows_the_retired_file_without_a_link(run):
    w, good, retired = run
    html = client.get(f"/runs/{RID}").text
    assert retired.name in html                            # still recorded
    assert _download_targets(html) == [str(good)]
    assert "Archived files (1)" in html


def test_the_download_route_refuses_a_retired_identity(run):
    """The template is not the only gate: a URL kept from before the fix,
    or typed by hand, must not deliver the file either."""
    w, good, retired = run
    ok = client.get("/output/download", params={"path": str(good)})
    assert ok.status_code == 200
    assert "attachment" in ok.headers["content-disposition"]
    assert good.name in ok.headers["content-disposition"]

    bad = client.get("/output/download", params={"path": str(retired)})
    assert bad.status_code == 409
    assert "not a registered hub model" in bad.text
    assert "146.45249599494792" not in bad.text            # no file body


def test_every_registered_id_is_a_metadata_file_name():
    """The set the listings trust is the set the hub knows. Both halves are
    checked against model-metadata/ in test_submit_join; this asserts the
    server asks that question and not a hand-written list."""
    from app.core.submit import RETIRED_ABBR, TEAM_ABBR
    root = Path(__file__).resolve().parents[2] / "model-metadata"
    registered = {f.stem for f in root.glob("*.yml")}
    retired = {f"{TEAM_ABBR}-{a}" for a in RETIRED_ABBR}
    # a retired card stays registered on the hub but is not an identity
    # this project may write, so the listings do not offer its files
    assert ui_output._registered_model_ids() == registered - retired
    assert RETIRED not in registered


# ------------------ a refused file costs the file, never the run's record

def test_a_refused_submission_is_named_on_the_run_page(tmp_path, monkeypatch):
    """A submission the writer refuses is contained per model: the run keeps
    its results, report and archive, and the page names the model with no
    file and why."""
    from app.core.runs import Ledger, RunSpec
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {})
    w = tmp_path / "workroots" / rid
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps({"models": {}}))
    _sub(w, hub_model_id("pf"), "2098-01-10")
    led.close_run(rid, "ok", {
        "submissions": {hub_model_id("pf"): "…"},
        "submission_errors": {
            hub_model_id("analogue"):
                "submission failed validation:\n  06 h=0: incomplete "
                "quantile set, 5 of 23 levels"}})
    ui_shared._invalidate_scans()
    html = client.get(f"/runs/{rid}").text
    assert "no file written" in html
    assert "incomplete quantile set, 5 of 23 levels" in html
    assert hub_model_id("analogue") in html
    # and the run itself still reads as a completed run with its PF file
    assert hub_model_id("pf") in html
    chips = ui_shared._outcome_chips(json.dumps({
        "submissions": {"a": "x"},
        "submission_errors": {"b": "y"}}))
    assert "1 submissions" in chips and "1 submission refused" in chips


# ------------------ old run folders read as the model they are, archived

def _archived_block(html: str) -> tuple:
    """(page without the archived <details>, the archived block)."""
    i = html.find('<details class="preview archived">')
    if i < 0:
        return html, ""
    j = html.index("</details>", i) + len("</details>")
    return html[:i] + html[j:], html[i:j]


@pytest.mark.parametrize("old, applied, label", [
    ("LosAlamos_NAU-SIHRS", True, hub_model_id("pf")),
    ("LosAlamos_NAU-SIHRS", False, "SIHRS filter, before the Oracle step"),
    ("LosAlamos_NAU-CModel_Flu", None, "Retired blend of the two models"),
    ("NAU_FluBNF-ensemble", None, "Retired blend of the two models"),
])
def test_an_old_folder_is_named_by_its_model_and_archived(
        tmp_path, monkeypatch, old, applied, label):
    """The Output page and the run page never show a retired hub name as a
    model: the folder reads as the current model when the run is that
    model (the Oracle step applied), else as what it was, inside the
    closed Archived block; the file stays on disk, readable, and is not
    offered for download."""
    from app.core import oracle
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / RID
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps(
        {"models": {}, "forecast_date": "2098-01-03", "spec": ""}))
    if applied is not None:
        oracle.write_provenance(w, {"applied": applied})
    f = _sub(w, old, "2098-01-10")
    ui_shared._invalidate_scans()
    try:
        for url in ("/output", f"/runs/{RID}"):
            html = client.get(url).text
            rest, block = _archived_block(html)
            assert label in block and "(archived)" in block
            assert f.name in block                     # the record, readable
            assert old not in rest                     # never as a model
            assert _download_targets(html) == []
        assert f.is_file()
    finally:
        ui_shared._invalidate_scans()


def test_a_groundhog_folder_with_its_donors_is_the_groundhog(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / RID
    w.mkdir(parents=True)
    spec = json.dumps({"extra": {"aux_pools": [{"label": "flusurv"}]}})
    (w / "results.json").write_text(json.dumps(
        {"models": {}, "forecast_date": "2098-01-03", "spec": spec}))
    _sub(w, "LosAlamos_NAU-GroundhogCGR", "2098-01-10")
    (entry,) = ui_output._submission_files(w)
    assert entry["model"] == hub_model_id("analogue")
    assert entry["archived"] and not entry["submittable"]


def test_a_refusal_recorded_under_an_old_name_reads_as_its_model(
        tmp_path, monkeypatch):
    from app.core.runs import Ledger, RunSpec
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {})
    w = tmp_path / "workroots" / rid
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps({"models": {}}))
    led.close_run(rid, "ok", {"submission_errors": {
        "LosAlamos_NAU-CModel_Flu": "submission failed validation"}})
    ui_shared._invalidate_scans()
    html = client.get(f"/runs/{rid}").text
    assert "LosAlamos_NAU" not in html
    assert "Retired blend of the two models" in html


def test_every_legacy_name_is_retired_and_none_is_written():
    """LEGACY_DIRS only reads old folders: none of its names is an
    identity this project writes or a card in model-metadata/."""
    from app.core.submit import LEGACY_DIRS, MODEL_ABBR
    root = Path(__file__).resolve().parents[2] / "model-metadata"
    registered = {f.stem for f in root.glob("*.yml")}
    written = {hub_model_id(k) for k in MODEL_ABBR}
    assert not set(LEGACY_DIRS) & (registered | written)
    assert set(LEGACY_DIRS.values()) <= {"pf", "analogue", "blend"}
