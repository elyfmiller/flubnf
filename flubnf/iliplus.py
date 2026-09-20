"""Vintage-true ILI+ donor bank.

    ILI+ = ILINet %ILI  x  clinical percent positive

The product is the point. Raw %ILI counts every patient who walked in with
an influenza-like illness, most of whom do not have influenza, and that
non-influenza background is large, seasonal and has nothing to do with the
epidemic being forecast. Multiplying by the share of clinical specimens that
actually test positive removes it, which is what makes ILI+ growth ratios
comparable to hospital-admission growth ratios rather than merely correlated
with them.

TWO HALVES, ONE OF WHICH ALREADY EXISTED
----------------------------------------
The clinical half comes from :mod:`flubnf.nrevss`, which already implements
the vintage discipline, the per-(region, issue) disk cache, the holiday-gap
issue fallback and the MMWR arithmetic against Delphi's ``fluview_clinical``
endpoint. This module does not reimplement any of that: it calls
``nrevss.fetch_typed`` and derives percent positive as
``(total_a + total_b) / total_specimens``.

Deriving rather than reading Delphi's own ``percent_positive`` field is
deliberate and is a small improvement: the API rounds that field to two
decimal places, and the derived value agrees with it to within 0.005
(measured live 2026-09-19 over the rows of a ten-week window), which is
exactly that rounding. The bank the pre-registered measurements were made on
used the rounded field, so a bank built here differs from it by at most that
rounding. Whether that matters was measured rather than assumed, and it does
not. Full 48-region banks built both ways, scored against the production
filter on 15,460 ensemble cells: pooled B5 relWIS 0.668774 with the rounded
field against 0.668775 derived, with coverage identical to three decimals.
Every scored cell moves, but by a median of 0.014 percent and at most 0.23
percent, because a donor pool holds hundreds of ratios and perturbing a
minority of them barely moves an empirical quantile. The bank's own cells
differ by up to 43 percent, so the dilution is the whole explanation.
``percent_positive="reported"`` therefore exists for reproducing the frozen
numbers, not because the choice changes an answer.

The ILINet half (``fluview``) is added here in the same shape, because no
module owned it. Its MMWR helpers are imported from ``nrevss`` rather than
copied, so the two endpoints cannot disagree about what epiweek a date is in
(the helpers were also checked against ``flubnf.analogue.epiweek`` over every
day from 2010 to 2026: zero disagreements).

VINTAGE
-------
``fetch_ili`` requests ``issues=<asof epiweek>`` exactly as ``fetch_typed``
does, so a bank built for a given as-of holds what was published by then and
nothing later. Weeks a snapshot lacks are absent, never imputed.

Passing ``asof=None`` asks for the latest issue instead. That is NOT
vintage-true and the function says so in its signature rather than hiding it.
It is available because the donor pool is drawn from strictly prior seasons,
and calendar matching means a donor is at least 46 weeks old when it is used
(measured: minimum 46.0 weeks over 88,857 real donor uses, median 5.9 years).
At that age ILINet revision is negligible: 98.0 percent of bank cells and
97.09 percent of donor log-ratios are bit-identical between a lag-46 vintage
and final issue, and the arm result moves by +0.0000 relWIS. The
pre-registration and the measurement are in the lab archive
(research/iliplus-splice, prereg 08e03ca7e8ffcfce). That equivalence holds
only while donors stay in strictly prior seasons: widen the calendar
bandwidth, or let ``allow_same_season`` be True, and the 46-week floor breaks
and the vintage path is the only defensible one.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from . import nrevss
from .nrevss import _as_date, _ew, _ew_shift, mmwr_week, week_ending

BASE_URL = "https://api.delphi.cmu.edu/epidata/fluview/"
HTTP_TIMEOUT = nrevss.HTTP_TIMEOUT

#: Raw ILINet responses, one file per (region, issue), beside the NREVSS
#: cache. Both live under app/state, which is gitignored: a donor bank is a
#: local data artefact, not repository content.
CACHE_DIR = Path(__file__).resolve().parents[1] / "app" / "state" / "iliplus"

_COLUMNS = ["date", "ili"]


def build_url(region: str, ew_start: int, ew_end: int, issue=None) -> str:
    """The exact query URL (pure; unit-tested).

    ``issue=None`` omits the parameter, which asks Delphi for the latest
    issue of each week rather than a vintage.
    """
    params = {"regions": region, "epiweeks": f"{ew_start}-{ew_end}"}
    if issue is not None:
        params["issues"] = str(issue)
    return BASE_URL + "?" + urllib.parse.urlencode(params)


#: Delphi rate-limits bulk callers. Building a whole bank is 2 requests per
#: jurisdiction, about 100 in a burst, which earns an HTTP 429 in practice
#: (observed 2026-09-19 partway through a 52-state build). Both the retry and
#: the inter-region pause below exist because of that, not on principle.
RETRY_ON_429 = 5
RETRY_BACKOFF_S = 3.0

#: Regions per request when warming the caches. Delphi accepts a comma list,
#: so a 52-jurisdiction bank costs about a dozen requests instead of about a
#: hundred. Fewer requests is the actual fix for the 429; the retry above is
#: the belt to that pair of braces.
BATCH = 12


def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "flubnf-iliplus"})
    for attempt in range(RETRY_ON_429):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RETRY_ON_429 - 1:
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            raise RuntimeError(
                f"ILINet fetch failed (HTTP {e.code} from Delphi Epidata): "
                f"{url}: {e}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"ILINet fetch failed (network error contacting Delphi "
                f"Epidata): {url}: {e}") from e
    raise RuntimeError(f"ILINet fetch gave up after {RETRY_ON_429} "
                       f"rate-limited attempts: {url}")   # pragma: no cover


def _retry_429(fn, *args, **kw):
    """Run a fetch that raises RuntimeError on HTTP failure, retrying when the
    message carries a 429. Used for the NREVSS half, whose own fetcher has no
    retry and which this module must not reach into and change."""
    for attempt in range(RETRY_ON_429):
        try:
            return fn(*args, **kw)
        except RuntimeError as e:
            if "429" in str(e) and attempt < RETRY_ON_429 - 1:
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            raise


def _snapshot(region: str, issue, ew_start: int, ew_end: int,
              cache_dir=None) -> list:
    """Rows of the (region, issue) snapshot covering [ew_start, ew_end].

    Mirrors ``nrevss._snapshot`` exactly, including caching the raw response
    BEFORE any fallback logic runs so a replay is served entirely from disk.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    tag = "latest" if issue is None else str(issue)
    path = cache_dir / f"{region}_{tag}.json"
    if path.exists():
        blob = json.loads(path.read_text())
        a, b = blob.get("epiweeks", (0, -1))
        # A "latest" snapshot covers through whatever the newest week was
        # when it was written, and callers ask for it with an open-ended
        # upper bound, so comparing that bound against the stored one would
        # miss the cache every single time and refetch the whole bank on
        # every build. That is what earns an HTTP 429. Only the lower bound
        # is a real constraint here; refreshing a latest snapshot means
        # deleting the file.
        covered = a <= ew_start and (issue is None or ew_end <= b)
        if covered:
            rows = (blob["response"].get("epidata") or [])
            return [r for r in rows if ew_start <= r["epiweek"] <= ew_end]
    env = _http_json(build_url(region, ew_start, ew_end, issue))
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows_seen = env.get("epidata") or []
    upper = max((r["epiweek"] for r in rows_seen), default=ew_start)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "region": region,
        "issue": issue,
        # Record what was actually covered, not what was asked for, so an
        # open-ended request does not store a fictional upper bound.
        "epiweeks": [ew_start, ew_end if issue is not None else upper],
        "response": env,
    }, indent=1))
    tmp.replace(path)
    return env.get("epidata") or []


def fetch_ili(region: str, season_start_iso, asof_iso=None,
              cache_dir=None) -> pd.DataFrame:
    """ILINet %ILI for `region`, AS KNOWN at `asof_iso`.

    Columns [date, ili], date being each epiweek's Saturday end, sorted.
    ``asof_iso=None`` fetches the latest issue and covers through the most
    recent week Delphi holds; see the module docstring on when that is
    defensible.

    With an as-of, requests ``issues=<asof epiweek>`` and, if that issue
    returns nothing (holiday publishing gaps), retries the two preceding
    issues, exactly as ``nrevss.fetch_typed`` does.
    """
    ew_start = _ew(season_start_iso)
    if asof_iso is None:
        rows = _snapshot(region, None, ew_start, 999999, cache_dir=cache_dir)
    else:
        ew_end = _ew(asof_iso)
        rows = []
        for back in range(3):
            issue = _ew_shift(ew_end, -back)
            # An issue cannot hold epiweeks after itself, so clamp: this also
            # lets a replay hit the cached primary-issue file.
            rows = _snapshot(region, issue, ew_start, min(ew_end, issue),
                             cache_dir=cache_dir)
            if rows:
                break
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    best: dict = {}
    for r in rows:
        k = r["epiweek"]
        if r.get("wili") is None and r.get("ili") is None:
            continue
        if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
            best[k] = r
    # PREFER wili. For a STATE the two are the same number (checked over
    # 26,776 rows across 52 regions: identical, to the bit), so this changes
    # nothing for the shipped bank. They differ on every HHS, census-division
    # and national row, because that is where ILINet's population weighting
    # is applied, and `regions=` will accept those. Taking ili there would
    # silently use the unweighted quantity where the weighted one is the
    # standard, which is what a collaborator's long-standing pipeline uses.
    recs = [{"date": week_ending(*divmod(k, 100)),
             "ili": float(r["wili"] if r.get("wili") is not None else r["ili"])}
            for k, r in sorted(best.items())]
    return pd.DataFrame(recs, columns=_COLUMNS)


def _warm(url: str, regions, issue, ew_start: int, ew_end: int,
          cache_dir: Path, name_issue) -> None:
    """Fetch several regions in ONE request and write per-region cache files.

    The files are written in the exact layout ``nrevss._snapshot`` and this
    module's ``_snapshot`` read, so the bulk builder only ever WARMS those
    caches: the per-region readers, and in particular ``nrevss.fetch_typed``,
    stay the authority on parsing and on vintage semantics. Nothing here
    reaches into another module's logic, only into its cache directory in
    that module's own format.

    A region the response never mentions still gets a file, holding an empty
    epidata list. Without that, a genuinely empty region would be refetched
    on every pass forever.
    """
    env = _http_json(url)
    rows = env.get("epidata") or []
    by_region: dict = {r: [] for r in regions}
    for row in rows:
        by_region.setdefault(str(row.get("region", "")).lower(), []).append(row)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for region in regions:
        path = cache_dir / f"{region}_{name_issue}.json"
        if path.exists():
            continue
        tmp = path.with_suffix(".json.tmp")
        mine = by_region.get(region, [])
        tmp.write_text(json.dumps({
            "region": region,
            "issue": issue,
            "epiweeks": [ew_start,
                         ew_end if issue is not None
                         else max((r["epiweek"] for r in mine),
                                  default=ew_start)],
            "response": {"result": 1, "message": "warmed", "epidata": mine},
        }, indent=1))
        tmp.replace(path)


def warm_caches(regions, season_start_iso, asof_iso=None, *,
                cache_dir=None, nrevss_cache_dir=None,
                batch: int = BATCH, pause_s: float = 0.4) -> None:
    """Populate both response caches for `regions` in batched requests.

    Call this before a bulk :func:`build_bank`; ``build_bank`` does it for
    you. Already-cached regions are left alone, so a rerun after a partial
    failure only fetches what is missing.
    """
    ew_start = _ew(season_start_iso)
    icache = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    ncache = (Path(nrevss_cache_dir) if nrevss_cache_dir is not None
              else nrevss.CACHE_DIR)
    if asof_iso is None:
        issue, tag, ew_end = None, "latest", 999999
    else:
        issue = _ew(asof_iso)
        tag, ew_end = str(issue), min(_ew(asof_iso), issue)
    todo_i = [r for r in regions if not (icache / f"{r}_{tag}.json").exists()]
    todo_n = [r for r in regions if not (ncache / f"{r}_{tag}.json").exists()]
    for src, todo, base, cdir in (
            ("ilinet", todo_i, BASE_URL, icache),
            ("clinical", todo_n, nrevss.BASE_URL, ncache)):
        for i in range(0, len(todo), batch):
            grp = todo[i:i + batch]
            params = {"regions": ",".join(grp),
                      "epiweeks": f"{ew_start}-{ew_end}"}
            if issue is not None:
                params["issues"] = str(issue)
            url = base + "?" + urllib.parse.urlencode(params)
            _retry_429(_warm, url, grp, issue, ew_start, ew_end, cdir, tag)
            if pause_s:
                time.sleep(pause_s)


def state_regions(locations_csv=None) -> list:
    """Lowercase Delphi region codes for the jurisdictions of the donor pool.

    US national is excluded. The admissions pool keeps its national row (a
    measured tie, see flubnf.analogue's module docstring), but ILINet's
    national row is a weighted average of the states rather than their sum,
    so it is a different quantity and is left out rather than quietly mixed
    into a pool of state series.
    """
    loc = nrevss._locations(locations_csv)
    out = []
    for a in loc["abbreviation"]:
        a = str(a).strip().lower()
        if a and a != "us":
            out.append(a)
    return sorted(set(out))


def _reported_pct(region: str, asof_iso, cache_dir=None) -> dict:
    """date -> Delphi's own two-decimal ``percent_positive`` for `region`.

    Read from the SAME cached clinical snapshot ``nrevss.fetch_typed`` uses,
    so this adds one field and duplicates none of that function's vintage or
    holiday-fallback logic. Present so the bank the pre-registered
    measurements were made on can still be rebuilt exactly; the derived
    value is the better default (see build_bank).
    """
    cache_dir = (Path(cache_dir) if cache_dir is not None
                 else nrevss.CACHE_DIR)
    tag = "latest" if asof_iso is None else str(_ew(asof_iso))
    out: dict = {}
    for name in (f"{region}_{tag}.json",):
        path = cache_dir / name
        if not path.exists():
            continue
        rows = (json.loads(path.read_text())["response"].get("epidata") or [])
        best: dict = {}
        for r in rows:
            k = r["epiweek"]
            if r.get("percent_positive") is None:
                continue
            if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
                best[k] = r
        for k, r in best.items():
            out[week_ending(*divmod(k, 100))] = float(r["percent_positive"])
    return out


def build_bank(season_start_iso, asof_iso=None, *, regions=None,
               locations_csv=None, cache_dir=None, nrevss_cache_dir=None,
               min_specimens: int = 1, pause_s: float = 0.4,
               percent_positive: str = "derived") -> dict:
    """(region, date) -> ILI+, the auxiliary donor bank.

    Keys are (lowercase region code, ``datetime.date`` of the epiweek's
    Saturday), the shape ``flubnf.analogue.donor_ratios`` reads. The region
    keys need not match the admissions bank's, because the pool is
    cross-location by construction and a location key is used only to find a
    week's own future value.

    A cell survives only when BOTH halves are present and positive and the
    week has at least ``min_specimens`` clinical specimens. A week either
    stream lacks is dropped, never imputed, and a state that withholds
    clinical data simply contributes nothing. There is deliberately no HHS
    fallback here, unlike ``nrevss.a_share_series``: substituting a region's
    series for a state's would put a different geography into a pool whose
    keys say state, and the pool is large enough that dropping is cheaper
    than explaining.

    ``percent_positive`` selects how the clinical factor is obtained:

    * ``"derived"`` (default) computes it from the typed counts. This is the
      more precise of the two and the difference is not cosmetic. Delphi
      rounds its own field to two decimals, which is 0.005 absolute, so at
      0.5 percent positivity that is a one percent relative error and below
      0.1 percent it is tens of percent. Measured over 8,481 cells the
      disagreement tracks 1/positivity with correlation 0.870: median 0.009
      percent above 20 percent positivity, median 0.872 percent and up to 43
      percent below 0.5 percent, which is the off-season.
    * ``"reported"`` uses Delphi's rounded field, reproducing the bank the
      pre-registered measurements were made on. Use it to check those
      numbers, not to build a new bank.
    """
    if percent_positive not in ("derived", "reported"):
        raise ValueError(
            f"percent_positive must be 'derived' or 'reported', got "
            f"{percent_positive!r}")
    regions = state_regions(locations_csv) if regions is None else list(regions)
    # One batched pass fills both caches; every read below is then local.
    warm_caches(regions, season_start_iso, asof_iso, cache_dir=cache_dir,
                nrevss_cache_dir=nrevss_cache_dir, pause_s=pause_s)
    bank: dict = {}
    for region in regions:
        ili = _retry_429(fetch_ili, region, season_start_iso, asof_iso,
                         cache_dir=cache_dir)
        if ili.empty:
            continue
        clin = _retry_429(nrevss.fetch_typed, region, season_start_iso,
                          asof_iso, cache_dir=nrevss_cache_dir) \
            if asof_iso is not None else _retry_429(
                _latest_typed, region, season_start_iso, nrevss_cache_dir)
        if clin.empty:
            continue
        m = ili.merge(clin, on="date", how="inner")
        reported = (_reported_pct(region, asof_iso, nrevss_cache_dir)
                    if percent_positive == "reported" else None)
        for r in m.itertuples():
            spec = int(r.total_specimens or 0)
            if spec < min_specimens:
                continue
            if reported is not None:
                pct = reported.get(r.date)
                if pct is None:
                    continue
            else:
                pct = (int(r.total_a or 0) + int(r.total_b or 0)) / spec * 100.0
            v = float(r.ili) * pct
            if not (v > 0):
                continue
            d = _as_date(r.date)
            # Cheap insurance across two MMWR implementations: the analogue
            # keys donors by ITS epiweek, so a date whose week disagrees
            # would land in the wrong calendar bin. Checked clean over
            # 2010-2026, so this should never fire.
            y, w = mmwr_week(d)
            from .analogue import epiweek as _an_epiweek
            if _an_epiweek(d) != w:                      # pragma: no cover
                continue
            bank[(region, d)] = v
    return bank


def _latest_typed(region: str, season_start_iso, cache_dir):
    """Latest-issue clinical counts, the no-vintage counterpart of
    ``nrevss.fetch_typed``. Kept here rather than added to nrevss because
    nrevss's contract is vintage-true and should stay that way."""
    ew_start = _ew(season_start_iso)
    cache_dir = Path(cache_dir) if cache_dir is not None else nrevss.CACHE_DIR
    path = cache_dir / f"{region}_latest.json"
    if path.exists():
        blob = json.loads(path.read_text())
        rows = blob["response"].get("epidata") or []
    else:
        url = (nrevss.BASE_URL + "?" + urllib.parse.urlencode(
            {"regions": region, "epiweeks": f"{ew_start}-999999"}))
        env = nrevss._http_json(url)
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"region": region, "issue": None,
                                   "epiweeks": [ew_start, 999999],
                                   "response": env}, indent=1))
        tmp.replace(path)
        rows = env.get("epidata") or []
    best: dict = {}
    for r in rows:
        k = r["epiweek"]
        if k < ew_start:
            continue
        if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
            best[k] = r
    recs = [{"date": week_ending(*divmod(k, 100)),
             "total_a": int(r["total_a"] or 0),
             "total_b": int(r["total_b"] or 0),
             "total_specimens": int(r["total_specimens"] or 0)}
            for k, r in sorted(best.items())]
    return pd.DataFrame(recs, columns=nrevss._COLUMNS)


def write_bank(bank: dict, path) -> Path:
    """Write a bank as the ``"region|YYYY-MM-DD": value`` JSON that
    ``app.core.engines.analogue.load_aux_bank`` reads.

    One writer, one reader, so the on-disk format cannot drift between the
    thing that builds the bank and the thing that consumes it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {f"{r}|{d.isoformat()}": float(v)
               for (r, d), v in sorted(bank.items(), key=lambda kv: (kv[0][0],
                                                                     kv[0][1]))}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)
    return path
