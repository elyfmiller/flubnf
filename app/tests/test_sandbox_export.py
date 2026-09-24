"""Comparing, exporting and cleaning up sandbox runs (app/core/sandbox.py
diff_runs, model_zip, run_zip, summary_rows; the ?compare= view and the
download routes). The engine is faked as in test_sandbox.py: a prepared
run gets a parameter sample, an ESS record and a trajectory.
"""
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402

client = TestClient(srv.app)


def _finish(w: Path, shift: float = 0.0, n: int = 100) -> None:
    """What the engine would write for a finished kinetics run."""
    meta = json.loads((w / "meta.json").read_text())
    cell = w / f"{meta['model']}_r0"
    runs = cell / "out" / "Results" / "PF" / "Runs"
    runs.mkdir(parents=True)
    (runs / "params_0.txt").write_text(
        "k__FREE\tscale__FREE\tr__FREE\n" + "\n".join(
            f"{0.2 + shift + 0.001 * i} 0.4 8.0" for i in range(n)) + "\n")
    cols = meta["n_obs"] + meta["forecast_weeks"]
    np.savetxt(runs / "traj_noise_kinB_weekly_chain_0.txt",
               np.tile(np.arange(1.0, cols + 1) + shift, (n, 1)))
    (cell / "out" / "Results" / "PF" / "ess_0.txt").write_text(
        "# t\tess\tparticles\tdistinct\tdegenerate\n0\t80.0\t100\t100\t0\n")
    meta["status"] = "ok"
    (w / "meta.json").write_text(json.dumps(meta))


@pytest.fixture
def two_runs(sandbox_root):
    """kinetics_example run twice: the second after a prior edit and with
    another seed."""
    sb.add_example("kinetics_example")
    a = sb.prepare("kinetics_example", particles=100, seed=1)
    _finish(a)
    pri = sb.read_model("kinetics_example")["priors.conf"]
    line = next(l for l in pri.splitlines() if l.startswith("uniform_var")
                or l.startswith("loguniform_var"))
    toks = line.split()
    edited = " ".join(toks[:-1] + [str(float(toks[-1]) * 2)])
    sb.save_model("kinetics_example", {"priors.conf": pri.replace(line, edited)})
    import time
    time.sleep(1.1)                           # a new stamp for the second run
    b = sb.prepare("kinetics_example", particles=100, seed=2)
    _finish(b, shift=0.5)
    return {"a": a.name, "b": b.name, "line": line, "edited": edited}


def test_meta_records_the_file_digests_and_the_data_source(sandbox_root):
    sb.add_example("kinetics_example")
    (sb.MODELS / "kinetics_example" / sb.SOURCE_FILE).write_text(json.dumps({
        "location": "Alabama", "asof": "settled", "dates": [],
        "digest": sb._digest(sb.read_model("kinetics_example")["data.exp"])}))
    w = sb.prepare("kinetics_example")
    meta = json.loads((w / "meta.json").read_text())
    assert meta["digests"] == sb.digests(sb.read_model("kinetics_example"))
    assert meta["source"]["location"] == "Alabama"
    assert meta["origin"] == "example:kinetics_example"
    # the run keeps its own priors.conf beside the engine's files
    assert (w / "kinetics_example_r0" / "priors.conf").read_text() == \
        sb.read_model("kinetics_example")["priors.conf"]


def test_diff_runs_names_the_changed_prior_line_and_settings(two_runs):
    d = sb.diff_runs(two_runs["a"], two_runs["b"])
    by = {f["name"]: f for f in d["files"]}
    assert by["model.bngl"]["same"] and by["data.exp"]["same"]
    assert not by["priors.conf"]["same"]
    assert f"-{two_runs['line']}" in by["priors.conf"]["diff"]
    assert f"+{two_runs['edited']}" in by["priors.conf"]["diff"]
    assert d["settings"] == [{"key": "seed", "a": 1, "b": 2}]
    # a run without its own priors.conf falls back to pf.conf's prior lines
    (sb.RUNS / two_runs["a"] / "kinetics_example_r0" / "priors.conf").unlink()
    assert two_runs["line"].split("=")[0].strip() in \
        sb.run_files(two_runs["a"])["priors.conf"]


def test_compare_page_renders_both_runs_and_the_diff(two_runs):
    a, b = two_runs["a"], two_runs["b"]
    html = client.get(f"/sandbox?model=kinetics_example&run={b}&compare={a}").text
    assert "<h2>What changed</h2>" in html and f"From the compared run {a} to this one." in html
    assert f'<option value="{a}" selected>' in html
    assert "this run: median (5 to 95%)" in html and "<th>compared run</th>" in html
    assert "seed" in html and "model.bngl: unchanged." in html
    cmp = json.loads(html.split("window.SANDBOX_CMP = ", 1)[1].split(";</script>")[0])
    assert cmp["run_id"] == a and cmp["traj"]["q50"][0] == 1.0
    # without ?compare= no diff; another model's run is refused
    assert "<h2>What changed</h2>" not in client.get(
        f"/sandbox?model=kinetics_example&run={b}").text
    sb.add_example("sir_example")
    other = sb.prepare("sir_example")
    ui_state._status.pop("flash", None)
    html = client.get(f"/sandbox?model=kinetics_example&run={b}"
                      f"&compare={other.name}").text
    assert "<h2>What changed</h2>" not in html and "another model" in html


def test_model_zip_holds_the_three_files_and_the_sidecars(sandbox_root):
    sb.add_example("kinetics_example")
    z = zipfile.ZipFile(io.BytesIO(sb.model_zip("kinetics_example")))
    names = set(z.namelist())
    assert names == {"kinetics_example/model.bngl", "kinetics_example/data.exp",
                     "kinetics_example/priors.conf", "kinetics_example/model.json"}
    for f in sb.REQUIRED:
        assert z.read(f"kinetics_example/{f}") == \
            (sb.MODELS / "kinetics_example" / f).read_bytes()


def test_run_zip_contains_inputs_outputs_and_summary(two_runs, sandbox_root,
                                                     monkeypatch):
    b = two_runs["b"]
    z = zipfile.ZipFile(io.BytesIO(sb.run_zip(b)))
    names = {n.split("/", 1)[1] for n in z.namelist()}
    assert {"meta.json", "pf.conf", "m.bngl", "priors.conf", "params_0.txt",
            "ess_0.txt", "summary.csv",
            "traj_noise_kinB_weekly_chain_0.txt"} <= names
    assert any(n.endswith(".exp") for n in names)
    conf = z.read(f"{b}/pf.conf").decode()
    assert str(sandbox_root) not in conf and "bng_command = BNG2.pl" in conf
    assert "model = m.bngl : " in conf and "output_dir = out" in conf
    rows = list(csv.reader(io.StringIO(z.read(f"{b}/summary.csv").decode())))
    meta = json.loads(z.read(f"{b}/meta.json"))
    assert rows[0][:6] == ["column", "t", "date", "q10", "q50", "q90"]
    assert len(rows) - 1 == meta["n_obs"] + meta["forecast_weeks"]
    assert rows[1][4] == "1.5" and rows[1][6] != "" and rows[-1][6] == ""
    # a large trajectory stays out
    monkeypatch.setattr(sb, "TRAJ_ZIP_MAX", 10)
    z = zipfile.ZipFile(io.BytesIO(sb.run_zip(b)))
    assert not any("traj_noise" in n for n in z.namelist())
    assert f"{b}/summary.csv" in z.namelist()


def test_summary_rows_use_dates_when_known():
    res = {"meta": {"time": [0, 1, 3], "observed": [5, 6, 8],
                    "dates": ["2024-10-05", "2024-10-12", "2024-10-26"]},
           "traj": {"columns": 5, "q10": [1] * 5, "q50": [2] * 5, "q90": [3] * 5}}
    rows = sb.summary_rows(res)
    assert [r[1] for r in rows] == ["0", "1", "3", "4", "5"]
    assert [r[2] for r in rows] == ["2024-10-05", "2024-10-12", "2024-10-26",
                                    "2024-11-02", "2024-11-09"]
    assert [r[6] for r in rows] == ["5", "6", "8", "", ""]
    # a missing week (negative, or NaN) is blank, not a count of -1
    res["meta"]["observed"] = [5, -1, float("nan")]
    assert [r[6] for r in sb.summary_rows(res)] == ["5", "", "", "", ""]


def test_download_routes_serve_zips_to_localhost_only(two_runs):
    r = client.get("/sandbox/models/kinetics_example/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="kinetics_example.zip"' in r.headers["content-disposition"]
    r = client.get(f"/sandbox/runs/{two_runs['b']}/download")
    assert r.status_code == 200 and zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    for url in ("/sandbox/models/kinetics_example/download",
                f"/sandbox/runs/{two_runs['b']}/download"):
        assert client.get(url, headers={"host": "evil.example"}).status_code == 403
        assert client.get(url, headers={"origin": "http://evil.example"}
                          ).status_code == 403
    assert client.get("/sandbox/models/nobody/download").status_code == 404
    assert client.get("/sandbox/runs/..%2Fx/download").status_code == 404
    assert client.get("/sandbox/runs/C:x/download").status_code == 404
    # the workbench links both
    html = client.get(f"/sandbox?model=kinetics_example&run={two_runs['b']}").text
    assert 'href="/sandbox/models/kinetics_example/download"' in html
    assert f'href="/sandbox/runs/{two_runs["b"]}/download"' in html


def test_deleting_a_run_leaves_the_other(two_runs):
    r = client.post(f"/sandbox/runs/{two_runs['a']}/delete",
                    data={"confirm": two_runs["a"]}, follow_redirects=False)
    assert r.status_code == 303
    assert [x["run_id"] for x in sb.list_runs(model="kinetics_example")] == [two_runs["b"]]
