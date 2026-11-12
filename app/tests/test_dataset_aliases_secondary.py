"""An outside group's real headers map with no choice (UX review F21,
package P4): parsing.SECONDARY_ALIASES (state, county, deaths, ...) are
read for a role no primary alias matched, from exactly one header, and a
group's column must hold text. A file that read before is read and stored
byte for byte as before.

The three files are rebuilt here in the shape the review checked: AZ RSV
by county, UK deaths by region dated Sundays, and Australian flu by state.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import datasets as D
from app.core.datasets import reading

TEMPLATE = Path(__file__).resolve().parents[1] / "ui" / "static" / \
    "dataset-template.csv"


@pytest.fixture(autouse=True)
def _store_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")


def weeks(start: date, n: int, step: int = 7) -> list:
    return [start + timedelta(days=step * i) for i in range(n)]


def wave(i: int, j: int) -> int:
    return 5 + (i * 7 + j * 11) % 40


def build(header: str, groups, first: date, n: int, pop=True) -> bytes:
    lines = [header]
    for i, d in enumerate(weeks(first, n)):
        for j, g in enumerate(groups):
            lines.append(f"{d.isoformat()},{g},{wave(i, j)}"
                         + (f",{100000 * (j + 1)}" if pop else ""))
    return ("\n".join(lines) + "\n").encode()


def az_rsv_counties() -> bytes:
    return build("week_ending,county,ed_visits,population",
                 ("Maricopa", "Pima", "Coconino"), date(2023, 9, 2), 60)


def uk_deaths_sunday() -> bytes:
    # Sundays under 'date': each moves to the Saturday ending its week
    return build("date,region,deaths,population",
                 ("London", "North West", "Wales"), date(2023, 9, 3), 60)


def au_flu(first: date) -> bytes:
    return build("week_ending,state,cases,population",
                 ("NSW", "VIC", "QLD"), first, 60)


def no_choice(rep):
    """Every role found: nothing to map, nothing ambiguous."""
    assert not rep.needs_mapping, [str(p) for p in rep.problems]
    assert not {"missing_columns", "ambiguous_columns"} & set(rep.codes)
    assert set(rep.guess) >= {"date", "group", "value"}
    return rep


# ------------------------------------------------- the review's three files

def test_the_review_files_map_with_no_choice():
    rep = no_choice(D.validate(az_rsv_counties()))
    assert rep.ok and rep.columns["group"] == "county"
    assert rep.columns["value"] == "ed_visits"
    assert rep.summary["groups"] == ["Coconino", "Maricopa", "Pima"]
    rep = no_choice(D.validate(uk_deaths_sunday()))
    assert rep.ok and rep.columns["value"] == "deaths"
    assert rep.columns["group"] == "region"
    rep = no_choice(D.validate(au_flu(date(2023, 9, 2))))
    assert rep.ok and rep.columns["group"] == "state"
    # Sunday week ends: mapped with no choice, then refused for the weekday
    # (F24, a separate rule), never for a column
    rep = no_choice(D.validate(au_flu(date(2023, 9, 3))))
    assert rep.codes == ["weekday_end"]


def test_the_upload_check_reads_them_as_ready():
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    client = TestClient(srv.app)
    for raw in (az_rsv_counties(), uk_deaths_sunday(),
                au_flu(date(2023, 9, 2))):
        j = client.post("/data/datasets/check",
                        files={"file": ("f.csv", raw, "text/csv")},
                        data={"kind": ""}).json()
        assert j["ok"] and not j["needs_mapping"]
        assert j["status"].startswith("Ready to use: 3 groups, 60 weeks")


def test_a_primary_header_still_wins():
    raw = build("date,location,state,value", ("01", "02"),
                date(2024, 8, 3), 6, pop=False)
    raw = raw.replace(b",01,", b",01,AL,").replace(b",02,", b",02,AK,")
    rep = D.validate(raw)
    assert rep.ok and rep.columns["group"] == "location"
    assert rep.summary["format"] == "hubverse"
    assert "Ignored column(s): state." in rep.warnings
    rep = D.validate(b"date,group,cases,deaths\n2024-08-03,A,1,2\n"
                     b"2024-08-10,A,3,4\n")
    assert rep.ok and rep.columns["value"] == "cases"


def test_two_secondary_headers_are_never_picked_between():
    raw = b"date,state,county,cases\n2024-08-03,AZ,Pima,1\n" \
          b"2024-08-10,AZ,Pima,2\n"
    rep = D.validate(raw)
    assert "missing_columns" in rep.codes and "group" not in rep.guess
    rep = D.validate(b"date,group,deaths,visits\n2024-08-03,A,1,2\n")
    assert "missing_columns" in rep.codes and "value" not in rep.guess


def test_a_group_column_of_numbers_is_not_taken():
    """A numeric 'county' (FIPS codes) is no group under this tier: the
    file stays a choice, as before."""
    raw = b"week_ending,county,ed_visits\n2024-08-03,4013,5\n" \
          b"2024-08-10,4013,6\n"
    rep = D.validate(raw, series="az")
    assert "group" not in rep.guess and rep.needs_mapping


# ------------------------------------------- what read before, as before

def _one_series_area_blank() -> bytes:
    return ("date,cases,area\n" + "".join(
        f"{d.isoformat()},{wave(i, 0)},\n"
        for i, d in enumerate(weeks(date(2023, 8, 5), 30)))).encode()


def _one_series_county_number() -> bytes:
    return ("date,cases,county\n" + "".join(
        f"{d.isoformat()},{wave(i, 0)},4013\n"
        for i, d in enumerate(weeks(date(2023, 8, 5), 30)))).encode()


def _stored(raw, name, columns=None) -> dict:
    ds = D.ingest(raw, name, kind="count", filename="myseries.csv",
                  columns=columns)
    files = {p.relative_to(ds.path).as_posix(): p.read_bytes()
             for p in sorted(ds.path.rglob("*")) if p.is_file()}
    meta = json.loads(files.pop("meta.json"))
    meta.pop("created")
    return {"id": ds.id, "groups": ds.groups, "files": files, "meta": meta}


@pytest.mark.parametrize("raw, columns, groups", [
    (_one_series_area_blank(), None, ["myseries"]),
    (_one_series_county_number(), {"value": "cases"}, ["myseries"]),
    (TEMPLATE.read_bytes(), None, ["Adult", "Overall", "Pediatric"]),
], ids=["blank-area", "numeric-county", "template"])
def test_a_file_that_read_before_stores_byte_identical(raw, columns, groups,
                                                       tmp_path, monkeypatch):
    now = _stored(raw, "same", columns)
    assert now["groups"] == groups
    # the reading before this tier: no secondary aliases
    monkeypatch.setattr(reading, "SECONDARY_ALIASES", {})
    monkeypatch.setattr(D, "ROOT", tmp_path / "before")
    before = _stored(raw, "same", columns)
    assert now == before


def test_the_numeric_county_file_stays_one_series():
    out = _stored(_one_series_county_number(), "fips", {"value": "cases"})
    assert out["groups"] == ["myseries"]
    assert "Ignored column(s): county." in out["meta"]["warnings"]
