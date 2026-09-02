"""Season helpers in the data panels parse Y-M-D components, never bare
new Date(ds).

Both forecast.html and data.html carry the same seasonOf/weekOfSeason pair,
and both used to call new Date(ds) on a date-only string beside comments
forbidding exactly that: a date-only string is a UTC parse, one day back in
every zone west of Greenwich, so August 1 grouped into the PREVIOUS season
and Saturdays walked across month lines off-Arizona (2026-09-01 final
pass). Source checks pin the component parse in both copies; the helpers
run for real under JavaScriptCore where it is available, in the lab's own
zone, following test_player_js.py's pattern."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"
PAGES = ("forecast.html", "data.html")
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
needs_jsc = pytest.mark.skipif(not JSC.is_file(),
                               reason="JavaScriptCore jsc not available")


def _helpers(page: str) -> str:
    src = (TEMPLATES / page).read_text(encoding="utf-8")
    m = re.search(r"function localDate\(ds\).*?864e5\)\);\}", src, re.S)
    assert m, f"{page} lost the localDate/seasonOf/weekOfSeason helpers"
    return m.group(0)


@pytest.mark.parametrize("page", PAGES)
def test_season_helpers_never_utc_parse_the_date_string(page):
    """The trap the files' own comments forbid: new Date on a date-only
    string. The season helpers must go through the component parse."""
    src = (TEMPLATES / page).read_text(encoding="utf-8")
    assert "const d=new Date(ds)" not in src, (
        f"{page} UTC-parses date strings in its season helpers again")
    assert "function localDate(ds){const p=ds.slice(0,10).split('-')" in src
    assert "function seasonOf(ds){const d=localDate(ds);" in src
    assert "function weekOfSeason(ds){const d=localDate(ds);" in src


def test_the_two_template_copies_are_identical():
    """The helpers are duplicated on purpose (each page is standalone), so
    the copies must not drift: a fix landing in one file only is how the
    UTC parse crept back in the first place."""
    assert _helpers("forecast.html") == _helpers("data.html")


@needs_jsc
def test_august_first_belongs_to_its_own_season(tmp_path):
    """August 1 opens the season. Under the old UTC parse, any zone west of
    Greenwich saw it as July 31 and filed it 52 weeks deep into the season
    before; the component parse keeps it at week 0 of its own season in
    every zone."""
    drv = tmp_path / "driver.js"
    drv.write_text(_helpers("forecast.html") + "\n"
                   "print(JSON.stringify(["
                   "seasonOf('2025-08-01'), weekOfSeason('2025-08-01'),"
                   "seasonOf('2025-07-26'), seasonOf('2026-01-03'),"
                   "weekOfSeason('2026-01-03')]));\n")
    out = subprocess.run([str(JSC), str(drv)], capture_output=True, text=True,
                         timeout=60,
                         env={**os.environ, "TZ": "America/Phoenix"})
    assert out.returncode == 0, (out.stderr or out.stdout)
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got == ["2025-26", 0, "2024-25", "2025-26", 22]
