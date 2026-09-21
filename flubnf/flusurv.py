"""FluSurv-NET donor bank: laboratory-confirmed influenza hospitalisation rates.

Delphi's ``flusurv`` endpoint, ``rate_overall``: weekly laboratory-confirmed
influenza hospitalisations per 100,000 in the FluSurv-NET catchment areas.

WHY THIS STREAM
---------------
It is the closest public series to the forecast target. Both count
laboratory-confirmed influenza hospitalisations, and it shows: the shrink
factor that puts a stream on the admissions scale is 0.979 for this one
against 0.820 for ILI+, so its growth ratios need almost no rescaling.

More importantly it is DEEPER. After the registered donor-season exclusions
it carries 15 usable seasons against ILI+'s 8, from a catchment that has been
stable at 17 to 20 sites since 2009. Season depth is what the donor pool
actually needs: donors cluster by season, so the effective sample size tracks
the number of seasons rather than the number of donors, and this stream
supplies 1,117 donors from 15 seasons where ILI+ supplies 1,683 from 8 and is
measurably less stable for it (leave-one-season-out spread 0.0266 against
0.0576; prereg ea72d194af8318a5, lab archive).

The catchment is about 20 sites, not 50 states, and some are sub-state
(``ny_albany``, ``ny_rochester``). That does not matter to a donor pool: the
pool is cross-location by construction and a location key is used only to
find a week's own future value. It is not a coverage map.

NO VINTAGE, AND THIS MODULE WILL NOT PRETEND OTHERWISE
------------------------------------------------------
Delphi serves flusurv as a snapshot with NO revision history. An ``issues=``
query returns nothing, and 900 of 956 sampled rows carry a single recent
issue. So unlike :mod:`flubnf.nrevss` and :mod:`flubnf.iliplus`, there is no
vintage-true path here and none is offered; ``build_bank`` takes no as-of.

The donor pool draws only from strictly prior seasons, and calendar matching
puts every donor at least 46 weeks old when it is used, typically 6 to 16
years for this stream. Revision at that age is near-certainly immaterial.
But for ILI+ that claim was MEASURED (98.0 percent of cells bit-identical at
lag 46, prereg 08e03ca7e8ffcfce) and here it cannot be, because the data does
not carry its own history. Any decision to ship this stream has to state that
difference rather than inherit the ILI+ result.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from . import nrevss
from .nrevss import week_ending

BASE_URL = "https://api.delphi.cmu.edu/epidata/flusurv/"
LOCATIONS_URL = ("https://raw.githubusercontent.com/cmu-delphi/delphi-epidata/"
                 "main/labels/flusurv_locations.txt")
HTTP_TIMEOUT = 90.0

#: Raw responses, beside the other stream caches. app/state is gitignored: a
#: donor bank is a local data artefact, not repository content.
CACHE_DIR = Path(__file__).resolve().parents[1] / "app" / "state" / "flusurv"

RETRY_ON_429 = 5
RETRY_BACKOFF_S = 3.0

#: The earliest epiweek worth asking for. rate_overall begins at 200935.
FIRST_EPIWEEK = 200335


def build_url(locations, ew_start: int, ew_end: int) -> str:
    """The exact query URL (pure; unit-tested).

    Note the parameter is ``locations``, not the ``regions`` that fluview and
    fluview_clinical take. Getting that wrong returns an empty result rather
    than an error, which is exactly the kind of silence a donor pool should
    never absorb, so it is pinned by a test.
    """
    return BASE_URL + "?" + urllib.parse.urlencode({
        "locations": ",".join(locations),
        "epiweeks": f"{ew_start}-{ew_end}",
    })


def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "flubnf-flusurv"})
    for attempt in range(RETRY_ON_429):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RETRY_ON_429 - 1:
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            raise RuntimeError(
                f"FluSurv fetch failed (HTTP {e.code} from Delphi Epidata): "
                f"{url}: {e}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"FluSurv fetch failed (network error contacting Delphi "
                f"Epidata): {url}: {e}") from e
    raise RuntimeError(f"FluSurv fetch gave up after {RETRY_ON_429} "
                       f"rate-limited attempts: {url}")   # pragma: no cover


def catchment(cache_dir=None) -> list:
    """The FluSurv-NET site codes, from Delphi's own label file, cached.

    Read from the label file rather than hard-coded so a site joining or
    leaving does not need a code change to be noticed.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    path = cache_dir / "locations.json"
    if path.exists():
        return list(json.loads(path.read_text()))
    req = urllib.request.Request(LOCATIONS_URL,
                                 headers={"User-Agent": "flubnf-flusurv"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            locs = r.read().decode("utf-8").split()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(
            f"FluSurv location list fetch failed: {LOCATIONS_URL}: {e}") from e
    locs = [x.strip() for x in locs if x.strip()]
    if not locs:
        raise ValueError(f"FluSurv location list came back empty: {LOCATIONS_URL}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(locs))
    tmp.replace(path)
    return locs


def _snapshot(locations, ew_start: int, ew_end: int, cache_dir=None) -> list:
    """Rows covering [ew_start, ew_end], cached in one file.

    One file rather than one per site, because this endpoint has no vintage
    to key on and the whole catchment is a single modest request.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    path = cache_dir / "snapshot.json"
    if path.exists():
        blob = json.loads(path.read_text())
        a, b = blob.get("epiweeks", (0, -1))
        if a <= ew_start and set(blob.get("locations", [])) >= set(locations):
            rows = blob["response"].get("epidata") or []
            return [r for r in rows if ew_start <= r["epiweek"] <= ew_end]
    env = _http_json(build_url(locations, ew_start, ew_end))
    rows = env.get("epidata") or []
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "locations": list(locations),
        # What was actually covered, not what was asked for.
        "epiweeks": [ew_start, max((r["epiweek"] for r in rows),
                                   default=ew_start)],
        "response": env,
    }, indent=1))
    tmp.replace(path)
    return rows


def build_bank(first_epiweek: int = FIRST_EPIWEEK, *, locations=None,
               cache_dir=None) -> dict:
    """(site, date) -> hospitalisation rate, the auxiliary donor bank.

    Keys are (lowercase site code, ``datetime.date`` of the epiweek's
    Saturday), the shape ``flubnf.analogue.donor_ratios`` reads.

    There is no `asof` argument on purpose. See the module docstring: this
    endpoint carries no revision history, so a vintage-true fetch is not
    available and offering one would be a lie in the signature.
    """
    locations = catchment(cache_dir) if locations is None else list(locations)
    rows = _snapshot(locations, first_epiweek, 999999, cache_dir=cache_dir)
    bank: dict = {}
    for r in rows:
        v = r.get("rate_overall")
        if v is None or not (float(v) > 0):
            continue
        ew = r["epiweek"]
        y, w = divmod(ew, 100)
        d = date.fromisoformat(week_ending(y, w))
        # Cheap insurance across two MMWR implementations: the analogue keys
        # donors by ITS epiweek, so a date whose week disagrees would land in
        # the wrong calendar bin. Checked clean over 2010-2026.
        from .analogue import epiweek as _an_epiweek
        if _an_epiweek(d) != w:                          # pragma: no cover
            continue
        bank[(str(r["location"]).lower(), d)] = float(v)
    if not bank:
        raise ValueError(
            f"the FluSurv bank built from {first_epiweek} is empty; a spliced "
            f"run with an empty auxiliary pool would silently be the "
            f"single-pool forecast while still being labelled spliced")
    return bank


def write_bank(bank: dict, path) -> Path:
    """Write a bank as the ``"site|YYYY-MM-DD": value`` JSON that
    ``app.core.engines.analogue.load_aux_bank`` reads. Shared format with
    :func:`flubnf.iliplus.write_bank`, so one reader serves both."""
    from .iliplus import write_bank as _w
    return _w(bank, path)
