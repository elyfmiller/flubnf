"""SHIPPED (used by the FluBNF console, app/).

FluSurv-NET donor bank: laboratory-confirmed influenza hospitalisation rates.

Delphi's ``flusurv`` endpoint, ``rate_overall``: weekly lab-confirmed
influenza hospitalisations per 100,000 in the ~20-site FluSurv-NET catchment.

The closest public stream to the target (shrink factor 0.979 vs ILI+'s
0.820) and the deepest: 15 usable seasons vs ILI+'s 8. Donors cluster by
season, so season depth sets the effective sample size (prereg
ea72d194af8318a5, lab archive). Sub-state sites (``ny_albany``) are fine:
the pool is cross-location and a location key only finds a week's own
future value.

NO VINTAGE: Delphi keeps no revision history for flusurv (``issues=``
returns nothing), so ``build_bank`` takes no as-of. Donors are at least 46
weeks old at use, so revision is very likely immaterial, but unlike ILI+
that cannot be measured here; a decision to ship must say so.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from .nrevss import week_ending

BASE_URL = "https://api.delphi.cmu.edu/epidata/flusurv/"
LOCATIONS_URL = ("https://raw.githubusercontent.com/cmu-delphi/delphi-epidata/"
                 "main/labels/flusurv_locations.txt")
HTTP_TIMEOUT = 90.0

#: Raw responses, beside the other stream caches (app/state, gitignored).
CACHE_DIR = Path(__file__).resolve().parents[1] / "app" / "state" / "flusurv"

RETRY_ON_429 = 5
RETRY_BACKOFF_S = 3.0

#: Query start epiweek, earlier than the data (rate_overall begins at
#: 200935). Changing the fetch range can change the committed bank's digest.
FIRST_EPIWEEK = 200335


def build_url(locations, ew_start: int, ew_end: int) -> str:
    """The exact query URL (pure; unit-tested).

    The parameter is ``locations``, not fluview's ``regions``: the wrong one
    returns an empty result, not an error (pinned in test_flusurv.py).
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

    Not hard-coded, so a site joining or leaving needs no code change.
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

    One file: no vintage to key on, and the catchment is one small request.
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

    Keys are (lowercase site code, epiweek-Saturday ``datetime.date``), the
    shape ``flubnf.analogue.donor_ratios`` reads. No `asof` on purpose: the
    endpoint has no revision history (see the module docstring).
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
        # the analogue keys donors by ITS epiweek; a disagreeing date would
        # land in the wrong calendar bin (never seen 2010-2026)
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
