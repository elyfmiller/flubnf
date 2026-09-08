"""The sandbox's data source: a model's data.exp filled from the hub
archive by location and date range (app/core/sandbox.py locations,
series_for, fill_data, read_data_source; the /sandbox/models/<name>/
fill-data route; the fieldset the editor includes). Hub-free: the
locations table, the settled truth and the vintage reader are faked.
What is tested is the row contract (t from 0, the header kept, missing
weeks dropped and counted, never imputed), the sidecar, the refusals,
and the page with and without an archive.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import data as data_mod                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core import scoring                             # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)

LOCS = [{"name": "US", "fips": "US"}, {"name": "Alabama", "fips": "01"},
        {"name": "Wyoming", "fips": "56"}]
#: four Saturdays; the third (2024-10-19) is unreported for Alabama
WEEKS = ["2024-10-05", "2024-10-12", "2024-10-19", "2024-10-26"]


def fake_truth():
    truth = {("01", pd.Timestamp(WEEKS[0])): 8.0,
             ("01", pd.Timestamp(WEEKS[1])): 10.0,
             ("01", pd.Timestamp(WEEKS[3])): 14.5,
             ("01", pd.Timestamp("2024-11-02")): 20.0,      # past the range
             ("56", pd.Timestamp(WEEKS[0])): 1.0}
    return truth, {"Alabama": "01", "Wyoming": "56", "US": "US"}


def fake_vintage_series(date, location_name):
    assert date == "2024-11-09"
    if location_name != "Alabama":
        return {"dates": [], "values": []}
    return {"dates": [WEEKS[0], WEEKS[1], WEEKS[3]], "values": [7.0, 9.0, 12.0]}


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A sandbox rooted in tmp_path with the archive faked: three
    locations, settled truth with one missing week, one vintage."""
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "MODELS", tmp_path / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")
    monkeypatch.setattr(sb, "locations", lambda: list(LOCS))
    monkeypatch.setattr(sb, "vintages", lambda: ["2024-11-09", "2024-11-02"])
    monkeypatch.setattr(scoring, "load_truth", fake_truth)
    monkeypatch.setattr(data_mod, "vintage_series", fake_vintage_series)
    srv._status.pop("flash", None)
    srv._status["running"] = None
    srv._sandbox_status["running"] = None
    return tmp_path / "sandbox"


# ----------------------------------------------------------- the archive

def test_locations_read_the_hub_table_us_first(tmp_path, monkeypatch):
    csv = tmp_path / "locations.csv"
    csv.write_text('"abbreviation","location","location_name","population"\n'
                   '"WY","56","Wyoming",584057\n'
                   '"US","US","US",340110988\n'
                   '"AL","1","Alabama",5157699\n'
                   '"AK","02","Alaska",740133\n')
    monkeypatch.setattr(data_mod, "LOCATIONS", csv)
    assert sb.locations() == [{"name": "US", "fips": "US"},
                              {"name": "Alabama", "fips": "01"},
                              {"name": "Alaska", "fips": "02"},
                              {"name": "Wyoming", "fips": "56"}]
    monkeypatch.setattr(data_mod, "LOCATIONS", tmp_path / "missing.csv")
    assert sb.locations() == []                          # no hub, no error


def test_vintages_newest_first_and_the_default_range(monkeypatch):
    monkeypatch.setattr(data_mod, "vintages", lambda: ["2026-06-27", "2026-07-04"])
    assert sb.vintages() == ["2026-07-04", "2026-06-27"]

    def boom():
        raise FileNotFoundError("no archive")
    monkeypatch.setattr(data_mod, "vintages", boom)
    assert sb.vintages() == []
    assert sb.default_range(["2026-07-04", "2026-06-27"]) == {
        "start": "2026-02-21", "end": "2026-07-04"}       # 20 Saturdays
    assert sb.default_range([]) == {"start": "", "end": ""}
    assert sb.default_range(["not a date"]) == {"start": "", "end": ""}


def test_series_drops_missing_weeks_and_counts_them(box):
    s = sb.series_for("Alabama", WEEKS[0], WEEKS[3])
    assert s["dates"] == [WEEKS[0], WEEKS[1], WEEKS[3]]   # 10-19 dropped
    assert s["values"] == [8.0, 10.0, 14.5] and s["dropped"] == 1
    # the range is inclusive at both ends and a non-Saturday start rolls
    # forward to the first Saturday when counting the missing weeks
    s = sb.series_for("Alabama", "2024-10-03", WEEKS[1])
    assert s["dates"] == [WEEKS[0], WEEKS[1]] and s["dropped"] == 0
    assert sb.series_for("Wyoming", WEEKS[1], WEEKS[3]) == {
        "dates": [], "values": [], "dropped": 3}
    v = sb.series_for("Alabama", WEEKS[0], WEEKS[3], asof="2024-11-09")
    assert v["values"] == [7.0, 9.0, 12.0] and v["dropped"] == 1
    with pytest.raises(sb.SandboxError, match="unknown location"):
        sb.series_for("Atlantis", WEEKS[0], WEEKS[3])
    with pytest.raises(sb.SandboxError, match="after end"):
        sb.series_for("Alabama", WEEKS[3], WEEKS[0])
    with pytest.raises(sb.SandboxError, match="YYYY-MM-DD"):
        sb.series_for("Alabama", "October 5", WEEKS[3])


def test_fill_data_writes_rows_from_zero_and_the_sidecar(box):
    sb.new_model("mine")                                  # header: time T_weekly
    info = sb.fill_data("mine", "Alabama", WEEKS[0], WEEKS[3])
    text = (sb.MODELS / "mine" / "data.exp").read_text()
    assert text == "# time T_weekly\n0 8\n1 10\n2 14.5\n"
    assert text.count("#") == 1                           # one header line only
    assert sb.read_exp(text)["rows"] == [[0, 8], [1, 10], [2, 14.5]]
    for k in ("location", "start", "end", "asof", "rows", "dropped", "written_utc"):
        assert k in info, k
    assert (info["location"], info["start"], info["end"]) == ("Alabama", WEEKS[0], WEEKS[3])
    assert info["asof"] == "settled" and info["rows"] == 3 and info["dropped"] == 1
    side = json.loads((sb.MODELS / "mine" / sb.SOURCE_FILE).read_text())
    assert side == info
    assert sb.read_data_source("mine") == info
    assert sorted(p.name for p in (sb.MODELS / "mine").iterdir()) == sorted(
        list(sb.REQUIRED) + [sb.SOURCE_FILE])
    # a vintage fill names its as-of date
    info = sb.fill_data("mine", "Alabama", WEEKS[0], WEEKS[3], asof="2024-11-09")
    assert info["asof"] == "2024-11-09" and info["rows"] == 3
    assert (sb.MODELS / "mine" / "data.exp").read_text() == "# time T_weekly\n0 7\n1 9\n2 12\n"
    # data.exp edited by hand since: the sidecar no longer describes it
    sb.save_model("mine", {"data.exp": "# time T_weekly\n0 7\n1 9\n2 99\n"})
    assert sb.read_data_source("mine") is None
    assert sb.read_data_source("nobody") is None
    # a data.exp without a header line gets the console's default
    sb.save_model("mine", {"data.exp": "0 1\n1 2\n"})
    sb.fill_data("mine", "Alabama", WEEKS[0], WEEKS[1])
    assert (sb.MODELS / "mine" / "data.exp").read_text() == "# time H_weekly\n0 8\n1 10\n"


def test_fill_data_refuses_empty_unknown_and_reversed(box):
    sb.new_model("mine")
    before = (sb.MODELS / "mine" / "data.exp").read_text()
    with pytest.raises(sb.SandboxError, match="no reported week"):
        sb.fill_data("mine", "Wyoming", WEEKS[1], WEEKS[3])
    with pytest.raises(sb.SandboxError, match="no reported week"):
        sb.fill_data("mine", "Wyoming", WEEKS[0], WEEKS[3], asof="2024-11-09")
    with pytest.raises(sb.SandboxError, match="unknown location"):
        sb.fill_data("mine", "Atlantis", WEEKS[0], WEEKS[3])
    with pytest.raises(sb.SandboxError, match="after end"):
        sb.fill_data("mine", "Alabama", WEEKS[3], WEEKS[0])
    with pytest.raises(sb.SandboxError, match="YYYY-MM-DD"):
        sb.fill_data("mine", "Alabama", "", WEEKS[0])
    with pytest.raises(sb.SandboxError):
        sb.fill_data("nope", "Alabama", WEEKS[0], WEEKS[3])
    assert (sb.MODELS / "mine" / "data.exp").read_text() == before
    assert not (sb.MODELS / "mine" / sb.SOURCE_FILE).exists()


# --------------------------------------------------------------- the page

def test_the_route_fills_flashes_and_the_page_shows_the_source(box):
    sb.new_model("mine")
    r = client.post("/sandbox/models/mine/fill-data",
                    data={"location": "Alabama", "start": WEEKS[0],
                          "end": WEEKS[3], "source": "settled"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox?model=mine"
    html = client.get("/sandbox?model=mine").text
    assert ("data.exp filled: Alabama, 2024-10-05 to 2024-10-26, settled "
            "truth, 3 weeks, 1 missing weeks dropped") in html
    assert ("data.exp holds Alabama, 2024-10-05 to 2024-10-26, settled truth "
            "(3 weeks, 1 dropped missing)") in html
    assert "0 8\n1 10\n2 14.5" in html                    # the editor holds it
    assert 'value="Alabama" selected' in html             # the form recalls it
    r = client.post("/sandbox/models/mine/fill-data",
                    data={"location": "Alabama", "start": WEEKS[0],
                          "end": WEEKS[3], "source": "2024-11-09"},
                    follow_redirects=False)
    assert r.status_code == 303
    html = client.get("/sandbox?model=mine").text
    assert "vintage of 2024-11-09, 3 weeks, 1 missing weeks dropped" in html
    assert "(3 weeks, 1 dropped missing)" in html and 'value="2024-11-09" selected' in html
    # a refused fill flashes the reason and leaves the file alone
    r = client.post("/sandbox/models/mine/fill-data",
                    data={"location": "Atlantis", "start": WEEKS[0],
                          "end": WEEKS[3], "source": "settled"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox?model=mine"
    html = client.get("/sandbox?model=mine").text
    assert "unknown location" in html and "0 7\n1 9\n2 12" in html


def test_the_editor_shows_the_fieldset_or_the_no_archive_hint(box, monkeypatch):
    sb.new_model("mine")
    html = client.get("/sandbox?model=mine").text
    assert "<fieldset" in html and "Fill from the archive" in html
    assert 'formaction="/sandbox/models/mine/fill-data"' in html
    assert "Fill data.exp" in html and "No hub archive here" not in html
    assert html.index('value="US"') < html.index('value="Alabama"') < html.index('value="Wyoming"')
    assert '<option value="settled" >settled truth</option>' in html
    assert html.index('value="2024-11-09"') < html.index('value="2024-11-02"')
    assert 'name="start" type="date" step="7"' in html
    assert 'value="2024-06-29"' in html and 'value="2024-11-09"' in html  # 20 weeks
    assert "data.exp holds" not in html                   # nothing filled yet
    assert "sandbox_data" not in html                     # the include resolved
    monkeypatch.setattr(sb, "locations", lambda: [])
    monkeypatch.setattr(sb, "vintages", lambda: [])
    r = client.get("/sandbox?model=mine")
    assert r.status_code == 200
    assert "No hub archive here: type the rows or copy an example." in r.text
    assert 'name="location"' not in r.text
    assert client.get("/sandbox").status_code == 200      # no editor, no fieldset
