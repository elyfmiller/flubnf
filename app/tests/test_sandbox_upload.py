"""Your own data in the sandbox: a CSV uploaded through the dataset store
(app/core/datasets.py, MicroHub or hubverse shape), or a stored dataset,
loaded into a model's data.exp (sandbox.ingest_upload, dataset_series,
fill_data(dataset=); the upload-data and fill-data routes). Hub-free:
the store lives in tmp_path. What is tested is the row contract with
calendar offsets, the sidecar, the inline refusals, the size cap before
and while reading, and that a client's file name is never a path.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import datasets as D                       # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)
FIX = Path(__file__).resolve().parent / "fixtures"

#: one hubverse location, five weeks (the store refuses gaps, MicroHub's rule)
HUBVERSE = ("target_end_date,location,observation\n"
            "2024-10-05,Springfield,8\n2024-10-12,Springfield,10\n"
            "2024-10-19,Springfield,12\n"
            "2024-10-26,Springfield,14\n2024-11-02,Springfield,19\n")


@pytest.fixture
def box(sandbox_root, tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(sb, "locations", lambda: [])       # no hub here
    monkeypatch.setattr(sb, "vintages", lambda: [])
    srv._sandbox_upload_report.clear()
    sb.new_model("mine")
    return sandbox_root


def _upload(text, name="counts.csv", kind="count", model="mine", extra=None):
    data = {"kind": kind, **(extra or {})}
    return client.post(f"/sandbox/models/{model}/upload-data", data=data,
                       files={"csv": (name, text.encode(), "text/csv")},
                       follow_redirects=False)


def _rows(model="mine"):
    return sb.read_exp(sb.read_model(model)["data.exp"])["rows"]


def test_a_one_location_hubverse_upload_loads_with_calendar_weeks(box):
    r = _upload(HUBVERSE)
    ds = D.list_datasets()
    assert len(ds) == 1 and ds[0].groups == ["Springfield"]
    assert r.status_code == 303
    assert r.headers["location"] == f"/sandbox?model=mine&dataset={ds[0].id}"
    assert _rows() == [[0, 8], [1, 10], [2, 12], [3, 14], [4, 19]]
    info = sb.read_data_source("mine")
    assert info["asof"] == "dataset" and info["dataset"]["id"] == ds[0].id
    assert info["dates"][2] == "2024-10-19" and info["dropped"] == 0
    html = client.get(r.headers["location"]).text
    assert "data.exp filled: Springfield, 2024-10-05 to 2024-11-02, dataset counts" in html
    assert "data.exp holds Springfield, 2024-10-05 to 2024-11-02, dataset counts (5 weeks)" in html
    assert f'<option value="dataset:{ds[0].id}" selected>counts</option>' in html


def test_a_microhub_upload_with_groups_is_stored_then_one_group_loaded(box):
    text = (FIX / "microhub-template-population-head.csv").read_text()
    r = _upload(text, name="microhub.csv")
    (ds,) = D.list_datasets()
    assert sorted(ds.groups) == ["Adult", "Overall", "Pediatric"]
    before = sb.read_model("mine")["data.exp"]
    assert sb.read_model("mine")["data.exp"] == before            # nothing loaded yet
    html = client.get(r.headers["location"]).text
    assert "pick a group under Load data" in html
    assert '<details class="adv sbfill" open>' in html
    assert f'value="Overall" data-ds="{ds.id}"' in html
    r = client.post("/sandbox/models/mine/fill-data",
                    data={"source": f"dataset:{ds.id}", "group": "Overall"},
                    follow_redirects=False)
    assert r.headers["location"] == "/sandbox?model=mine"
    rows = _rows()
    assert rows[0] == [0, 414] and [t for t, _ in rows] == list(range(len(rows)))
    info = sb.read_data_source("mine")
    assert info["population"] == 6861528 and info["start"] == "2022-01-01"
    assert "; population 6,861,528" in client.get("/sandbox?model=mine").text
    # a range within the group's weeks, and a group the dataset lacks
    sb.fill_data("mine", "Adult", "2022-01-08", "2022-01-15", dataset=ds.id)
    assert _rows() == [[0, 421], [1, 550]]
    with pytest.raises(sb.SandboxError, match="has no group 'Seniors'"):
        sb.fill_data("mine", "Seniors", "", "", dataset=ds.id)
    with pytest.raises(sb.SandboxError):
        sb.fill_data("mine", "Adult", "", "", dataset="not-an-id")


def test_a_bad_csv_is_refused_inline_and_nothing_changes(box):
    before = sb.read_model("mine")["data.exp"]
    _upload("when,where,how many\n1,2,3\n")
    html = client.get("/sandbox?model=mine").text
    assert "Not loaded:" in html and "<li>" in html.split("Not loaded:")[1]
    assert D.list_datasets() == [] and sb.read_model("mine")["data.exp"] == before
    _upload("date,target_group,value\n2024-10-05,A,-4\n")
    html = client.get("/sandbox?model=mine").text
    assert "Not loaded:" in html
    # the report shows once
    assert "Not loaded:" not in client.get("/sandbox?model=mine").text
    # no file chosen
    r = client.post("/sandbox/models/mine/upload-data", data={"kind": "count"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Choose a CSV file" in client.get("/sandbox?model=mine").text


def test_the_upload_saves_the_editor_first(box):
    files = sb.read_model("mine")
    bngl = files["model.bngl"].replace("# mine:", "# mine, edited:")
    _upload(HUBVERSE, extra={"model_bngl": bngl, "priors_conf": files["priors.conf"]})
    assert sb.read_model("mine")["model.bngl"] == bngl
    assert _rows()[0] == [0, 8]


def test_the_size_cap_holds_and_nothing_is_stored(box, monkeypatch):
    monkeypatch.setattr(sb, "UPLOAD_MAX_BYTES", 400)
    monkeypatch.setattr(srv, "_SANDBOX_BODY_SLACK", 200)
    big = "target_end_date,location,observation\n" + "".join(
        f"2024-10-05,Loc{i},1\n" for i in range(100))
    _upload(big)
    assert "larger than the" in client.get("/sandbox?model=mine").text
    assert D.list_datasets() == []


def _request(headers, chunks):
    from starlette.requests import Request
    sent = []

    async def receive():
        body = chunks[len(sent)] if len(sent) < len(chunks) else b""
        sent.append(body)
        return {"type": "http.request", "body": body,
                "more_body": len(sent) < len(chunks)}
    scope = {"type": "http", "method": "POST", "path": "/", "query_string": b"",
             "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    return Request(scope, receive), sent


def test_the_cap_refuses_by_content_length_before_reading():
    req, sent = _request({"content-length": str(10 ** 12),
                          "content-type": "multipart/form-data; boundary=x"}, [b"x"])
    with pytest.raises(srv._SandboxTooLarge):
        asyncio.run(srv._sandbox_capped_form(req, 1000))
    assert sent == []                                       # not one byte read


def test_the_cap_cuts_a_chunked_body_off_while_reading():
    chunk = b"--x\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n" + b"y" * 500
    req, sent = _request({"content-type": "multipart/form-data; boundary=x"},
                         [chunk] * 50)
    with pytest.raises(srv._SandboxTooLarge):
        asyncio.run(srv._sandbox_capped_form(req, 2000))
    assert len(sent) <= 5                                   # stopped early


def test_a_client_file_name_is_never_a_path(box, tmp_path):
    assert sb.display_name("../../etc/passwd.csv") == "passwd.csv"
    assert sb.display_name("C:\\Users\\x\\data <1>.csv") == "data 1.csv"
    assert sb.display_name("..") == ""
    _upload(HUBVERSE, name="../../../evil.csv")
    (ds,) = D.list_datasets()
    assert ds.path.parent == Path(D.ROOT).resolve()
    assert ds.meta["filename"] == "evil.csv"
    assert not (tmp_path.parent / "evil.csv").exists()


def test_rates_load_with_a_word_about_the_objective(box):
    rates = HUBVERSE.replace(",8\n", ",0.8\n")
    r = _upload(rates, kind="rate")
    assert "rates, not counts" in client.get(r.headers["location"]).text


def test_the_stored_dataset_is_offered_to_other_models(box):
    _upload(HUBVERSE)
    (ds,) = D.list_datasets()
    sb.new_model("other")
    html = client.get("/sandbox?model=other").text
    assert '<optgroup label="Your datasets">' in html
    assert f'value="dataset:{ds.id}"' in html and 'name="group"' in html
    assert 'formenctype="multipart/form-data"' in html
    assert json.loads(json.dumps(sb.dataset_choices()))[0]["groups"][0]["name"] == "Springfield"
