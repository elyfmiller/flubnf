"""A file written under a retired model name is never handed over as a
submission.

The hub's model identity is the DIRECTORY: model-output/<team>-<model>/,
with <team>-<model> registered in model-metadata/. Runs made before that
identity was corrected left submission trees called NAU-Ensemble and
NAU-PF-SIHRS. Twenty such files were still on disk in app state on
2026-08-26, and every listing offered them for download with nothing to
distinguish them from a genuine submission: same page, same button, a file
name the hub would reject.

They stay visible, because a run page is a record of what a run did. They
are not downloadable, and the route enforces that as well as the template,
so a bookmarked URL cannot get around it.
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

client = TestClient(srv.app)

RID = "20980103T101500-abcdef"
GOOD = hub_model_id("ensemble")                      # LosAlamos_NAU-CModel_Flu
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
    srv._invalidate_scans()
    yield w, good, retired
    srv._invalidate_scans()


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
    assert "Not submittable" in html
    assert "retired model name" in html


def test_run_page_shows_the_retired_file_without_a_link(run):
    w, good, retired = run
    html = client.get(f"/runs/{RID}").text
    assert retired.name in html                            # still recorded
    assert _download_targets(html) == [str(good)]
    assert "Not submittable" in html


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
    root = Path(__file__).resolve().parents[2] / "model-metadata"
    registered = {f.stem for f in root.glob("*.yml")}
    assert srv._registered_model_ids() == registered
    assert RETIRED not in registered


# ------------------ a refused file costs the file, never the run's record

def test_a_refused_submission_is_named_on_the_run_page(tmp_path, monkeypatch):
    """The writer now refuses rows the hub would bounce, and that refusal is
    contained per model the way scoring and the report already are: the run
    keeps its results, its report and its archive, and the page says which
    model has no file and why. A run costs hours; one bad row set must not
    erase it, and must not quietly write a file either."""
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
            hub_model_id("ensemble"):
                "submission failed validation:\n  06 h=0: incomplete "
                "quantile set, 5 of 23 levels"}})
    srv._invalidate_scans()
    html = client.get(f"/runs/{rid}").text
    assert "no file written" in html
    assert "incomplete quantile set, 5 of 23 levels" in html
    assert hub_model_id("ensemble") in html
    # and the run itself still reads as a completed run with its PF file
    assert hub_model_id("pf") in html
    chips = srv._outcome_chips(json.dumps({
        "submissions": {"a": "x"},
        "submission_errors": {"b": "y"}}))
    assert "1 submissions" in chips and "1 submission refused" in chips
