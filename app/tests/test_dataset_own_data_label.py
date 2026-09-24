"""Wherever the Groundhog runs on a custom dataset, the console calls it
"Groundhog (own data)": the Forecast form and its fans, the run page (its
headings, results and settings), the Retrospective card and a replay's
page. The export file keeps the model name FluBNF-Groundhog, and no hub
page says "own data".
"""
from __future__ import annotations

import json
import re

import app.core.runs as runs_mod
from app.core import custom_run as CR
from app.ui import datasets_ui as DU

from test_datasets_ui import TEMPLATE, client, isolated, stored  # noqa: F401

OWN = "Groundhog (own data)"


def _text(html: str) -> str:
    return " ".join(html.split())


def test_one_name_everywhere_in_the_code():
    assert runs_mod.GROUNDHOG_OWN_DATA == OWN
    assert CR.MEMBER_LABELS["analogue"] == OWN
    assert DU.MEMBER_NAMES["analogue"] == OWN
    assert DU.ENGINE_NAMES["analogue"] == f"{OWN} only"
    assert runs_mod.DATASET_ENGINE_LABELS["analogue"] == f"{OWN} only"
    assert CR.analogue_label({}) == (f"{OWN}: calendar analogue on the "
                                     "dataset's own weeks")
    # the export name is the model's, unchanged
    assert CR.EXPORT_IDS["analogue"] == "FluBNF-Groundhog"


def test_forecast_run_and_replay_pages_say_own_data():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    page = _text(client.get(f"/forecast?source={ds.id}").text)
    assert f">{OWN} only</option>" in page
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2024-03-02",
                                      "locations": "all",
                                      "engine": "analogue"})
    (row,) = runs_mod.Ledger().rows(5)
    assert list(json.loads(row["outcome"])["exports"]) == ["FluBNF-Groundhog"]
    # the fans' model buttons and the latest-run card on the Forecast page
    page = client.get(f"/forecast?source={ds.id}").text
    names = json.loads(re.search(r"const MNAMES = (\{.*?\});",
                                 page).group(1))
    assert names["analogue"] == OWN
    assert f'<th scope="row">{OWN}</th>' in page
    assert f"<dt>{OWN}</dt>" in _text(page)
    # the ledger chips name it too
    assert f"{OWN} relWIS" in DU.outcome_chips(row["outcome"])
    # the run page: the table heading, the results row, the settings row
    run = _text(client.get(f"/runs/{row['run_id']}").text)
    assert f"{OWN}: median values" in run
    assert f"<th scope=\"row\">{OWN}</th>" in run
    assert f"<dt>{OWN}</dt><dd>calendar analogue on the dataset" in run
    assert "FluBNF-Groundhog" in run                  # the export's own name
    # the Retrospective card and a replay's page
    card = _text(client.get("/retro?tab=own").text)
    assert f'<option value="analogue">{OWN} only</option>' in card
    # disabled until the engine is ready (this page, without script)
    assert re.search('<option value="all"( disabled)?>' + re.escape(
        f"{OWN} and plain SIHRS particle filter"), card)
    r = client.post("/retro/dataset/run", data={
        "dataset": ds.id, "first": "2024-01-06", "last": "2024-02-24",
        "engine": "analogue"}, follow_redirects=False)
    rp = _text(client.get(r.headers["location"]).text)
    assert f"<dt>{OWN}</dt><dd>calendar analogue on the dataset" in rp
    assert f"<td>{OWN}</td>" in rp                       # the scores table
    assert f"{OWN} relWIS" in _text(client.get("/retro?tab=own").text)


def test_the_hub_forecast_keeps_its_own_names():
    """The hub's Groundhog is the registered model: its form and fans keep
    the plain name (the upload box's tips there talk about your data)."""
    stored()
    page = client.get("/forecast").text
    form = page.split('id="fcform"')[1].split("</form>")[0]
    assert ">Groundhog only</option>" in form and "own data" not in form
    names = json.loads(re.search(r"const MNAMES = (\{.*?\});",
                                 page).group(1))
    assert names["analogue"] == "Groundhog"
