"""The Data page's read-only views: the freshness panel (latest vintage
stats), the interactive latest-vintage preview (location selector, recent
weeks table, server-rendered sparkline), and the vintage browser (pick an
archived vintage, see exactly what that week knew). All read-only, all
served from cached scans of the immutable vintage files."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as data_mod                # noqa: E402
from app.ui import server as srv                     # noqa: E402

client = TestClient(srv.app)

V1, V2 = "2098-01-03", "2098-01-10"


def _write_vintage(root: Path, date: str, rows) -> None:
    p = root / f"target-hospital-admissions_{date}.csv"
    lines = ["date,location,location_name,value,weekly_rate"]
    lines += [f"{d},{f},{n},{v},0.0" for d, f, n, v in rows]
    p.write_text("\n".join(lines) + "\n")


@pytest.fixture()
def archive(tmp_path, monkeypatch):
    """Two vintages: the newer one adds a week and revises a value, exactly
    the situation the browser exists to show."""
    _write_vintage(tmp_path, V1, [
        ("2097-12-20", "39", "Ohio", 100), ("2097-12-27", "39", "Ohio", 140),
        ("2097-12-20", "49", "Utah", 8), ("2097-12-27", "49", "Utah", 11),
        ("2097-12-20", "US", "US", 900), ("2097-12-27", "US", "US", 1300),
        ("2097-12-27", "56", "Wyoming", ""),        # unreported: dropped
    ])
    _write_vintage(tmp_path, V2, [
        ("2097-12-20", "39", "Ohio", 100), ("2097-12-27", "39", "Ohio", 155),
        ("2098-01-03", "39", "Ohio", 190),
        ("2097-12-20", "49", "Utah", 8), ("2097-12-27", "49", "Utah", 11),
        ("2098-01-03", "49", "Utah", 15),
        ("2097-12-20", "US", "US", 900), ("2097-12-27", "US", "US", 1350),
        ("2098-01-03", "US", "US", 1600),
    ])
    monkeypatch.setattr(data_mod, "ARCHIVE", tmp_path)
    srv._invalidate_scans()
    yield tmp_path
    srv._invalidate_scans()      # answers for this root must not outlive it


def test_freshness_panel_states_the_latest_vintages_own_numbers(archive):
    html = client.get("/data").text
    assert f"<code>{V2}</code>" in html
    assert "9 reported rows" in html                 # V2's reported rows
    assert "3 jurisdictions covered" in html
    assert "newest week\n   2098-01-03" in " ".join(html.split()) \
        or "newest week 2098-01-03" in " ".join(html.split())
    assert "2 archived truth vintages" in html


def test_default_preview_is_the_latest_vintage(archive):
    html = client.get("/data").text
    # both vintages are offered; the latest is selected
    assert f"<option selected>{V2}</option>" in html.replace(' selected>',
                                                             ' selected>')
    assert V1 in html
    # US leads the location order
    joined = " ".join(html.split())
    assert joined.index(">US</option>") < joined.index(">Ohio</option>")
    # the sparkline is server-rendered SVG on theme tokens
    assert 'role="img"' in html and "polyline" in html
    assert 'stroke="var(--ink)"' in html and 'fill="var(--gold)"' in html


def test_location_preview_shows_series_table_newest_first(archive):
    html = client.get("/data?loc=Ohio").text
    joined = " ".join(html.split())
    # newest week first in the recent-weeks table
    assert joined.index("2098-01-03") < joined.index("2097-12-27")
    assert "190" in html                              # Ohio's newest value
    assert "peak 190 admissions" in joined
    assert "3 reported weeks" in joined


def test_vintage_browser_shows_what_that_week_knew(archive):
    html = client.get(f"/data?vintage={V1}&loc=Ohio").text
    joined = " ".join(html.split())
    # the older vintage: no 2098-01-03 data row, and the UNREVISED value
    assert f"As archived on {V1}" in joined
    assert "weeks 2097-12-20 to 2097-12-27" in joined
    assert ">140<" in html                            # what V1 knew for Ohio
    assert ">155<" not in html and ">190<" not in html   # V2's revisions
    # Wyoming's unreported row was dropped, so V1 covers 3 jurisdictions
    assert "3 jurisdictions" in joined


def test_bad_selections_fall_back_with_a_note_never_an_error(archive):
    r = client.get("/data?vintage=1999-01-01&loc=Nowhere")
    assert r.status_code == 200
    assert "No archived vintage for 1999-01-01" in r.text
    assert "not in the" in r.text                     # unknown location note
    # and the traversal-shaped inputs are refused by the same fallback
    assert client.get("/data?vintage=..%2F..&loc=x").status_code == 200


def test_data_page_stays_read_only(archive):
    """The only POST forms on the page are the two hub controls; the
    browser and preview are pure GET."""
    html = client.get("/data").text
    assert html.count('method="post"') == 2
    assert 'action="/freshness"' in html and 'action="/data/pull"' in html
    assert 'method="get" action="/data"' in html


def test_vintage_scans_are_ttl_cached():
    """The heavy per-vintage scans carry a long TTL (the files are
    immutable) and register with the shared invalidation."""
    for fn in (srv._vintage_summary, srv._vintage_locations,
               srv._vintage_series):
        assert hasattr(fn, "cache_clear")
        assert fn.ttl_s >= 60
