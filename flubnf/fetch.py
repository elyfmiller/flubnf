"""Fetch weekly CDC respiratory hospitalization data.

Primary source: data.cdc.gov Socrata API for dataset `mpgq-jmmr`
("Weekly Hospital Respiratory Data (HRD) Metrics by Jurisdiction").

Fallback: the FluSight forecast-hub GitHub repo (raw `target-data` CSVs).

Both paths produce a cached CSV in `config.data_cache` named
`{YYYY-MM-DD}_HRD.csv`, where the date is the upstream `last_modified` date
(or today's date if unavailable). The cached file is what downstream code
reads — fetching is idempotent for a given source date.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from .config import FluBNFConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    csv_path: Path
    source: str           # "socrata" or "flusight"
    as_of: date           # upstream last-modified date if known, else today
    rows: int             # number of rows in the downloaded CSV
    cached: bool          # True if we returned an already-cached file


def fetch_cdc_data(
    config: FluBNFConfig,
    *,
    force: bool = False,
    prefer: str = "socrata",
    timeout: float = 60.0,
    max_retries: int = 3,
    retry_backoff: float = 2.0,
) -> FetchResult:
    """Fetch the latest CDC weekly respiratory data into the data cache.

    Args:
        config:        FluBNFConfig instance.
        force:         If True, redownload even when cache hits.
        prefer:        "socrata" or "flusight" — which source to try first.
        timeout:       Per-request timeout in seconds.
        max_retries:   Per-source retry count for transient failures
                       (network blips, 5xx). Exponential backoff between.
        retry_backoff: Multiplier for sleep between retries.
    """
    import time as _time
    config.data_cache.mkdir(parents=True, exist_ok=True)
    sources = ["socrata", "flusight"] if prefer == "socrata" else ["flusight", "socrata"]
    errors: list[str] = []
    for src in sources:
        for attempt in range(max_retries):
            try:
                if src == "socrata":
                    return _fetch_socrata(config, force=force, timeout=timeout)
                return _fetch_flusight(config, force=force, timeout=timeout)
            except _TransientFetchError as e:
                wait = retry_backoff ** attempt
                log.warning(
                    "Transient %s failure (attempt %d/%d): %s — retrying in %.1fs",
                    src, attempt + 1, max_retries, e, wait,
                )
                _time.sleep(wait)
                continue
            except SchemaChangeError as e:
                # Schema changed — falling back to other source doesn't help
                # since they share the same schema notion. Surface clearly.
                errors.append(f"{src} schema mismatch: {e}")
                log.error("CDC schema appears to have changed: %s", e)
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{src}: {e}")
                log.warning("Non-retryable %s failure: %s", src, e)
                break
        else:
            errors.append(f"{src}: exhausted {max_retries} retries")
    raise RuntimeError(
        "All CDC fetch sources failed:\n  " + "\n  ".join(errors)
    )


class _TransientFetchError(Exception):
    """Retryable error (network timeout, 5xx, connection reset)."""


class SchemaChangeError(Exception):
    """CDC dataset schema has changed (missing expected columns)."""


# Columns we treat as required for downstream exp_files generation.
# A missing column from this set triggers SchemaChangeError.
_CRITICAL_COLUMN_ALIASES = (
    # Each tuple is a set of acceptable aliases; the CSV must contain
    # at least one from each tuple.
    ("Week Ending Date", "weekendingdate"),
    ("Geographic aggregation", "jurisdiction"),
    ("Total Influenza Admissions", "totalconfflunewadm"),
)


def _check_schema(csv_path: Path) -> None:
    """Verify the downloaded CSV has the columns we depend on.

    Raises SchemaChangeError if the upstream schema appears to have changed.
    """
    try:
        # Read just the header.
        import pandas as pd
        header = pd.read_csv(csv_path, nrows=0).columns
    except Exception as e:
        raise SchemaChangeError(f"could not read header from {csv_path}: {e}") from e
    available = set(header)
    missing = []
    for aliases in _CRITICAL_COLUMN_ALIASES:
        if not any(a in available for a in aliases):
            missing.append("/".join(aliases))
    if missing:
        raise SchemaChangeError(
            f"missing critical column(s) — none of {missing} present in "
            f"{csv_path.name}. CDC may have renamed columns; update "
            f"FluBNFConfig.cdc.*_columns aliases."
        )


# ---------------------------------------------------------------------------
# Socrata
# ---------------------------------------------------------------------------
def _fetch_socrata(
    config: FluBNFConfig, *, force: bool, timeout: float,
) -> FetchResult:
    host = config.cdc.socrata_host
    ds = config.cdc.socrata_dataset

    # Probe the upstream `last_modified` first so we can name the cache file
    # deterministically and skip the heavy download when unchanged.
    try:
        head = requests.head(
            f"https://{host}/resource/{ds}.csv",
            params={"$limit": 1},
            timeout=timeout,
        )
    except (requests.ConnectionError, requests.Timeout) as e:
        raise _TransientFetchError(f"head request failed: {e}") from e
    if head.status_code >= 500:
        raise _TransientFetchError(f"Socrata HEAD returned {head.status_code}")
    head.raise_for_status()
    as_of = _parse_as_of(head.headers.get("Last-Modified"))

    cache_path = config.data_cache / f"{as_of.isoformat()}_HRD.csv"
    if cache_path.exists() and not force:
        _check_schema(cache_path)
        rows = _count_data_rows(cache_path)
        log.info("Using cached Socrata CSV: %s (%d rows)", cache_path, rows)
        return FetchResult(cache_path, "socrata", as_of, rows, cached=True)

    # Paginate through the full dataset. Socrata defaults to 1000 rows; we
    # request 50k chunks until we get fewer rows than the chunk size.
    chunk = 50_000
    offset = 0
    header_written = False
    rows = 0
    tmp = cache_path.with_suffix(".csv.tmp")
    with open(tmp, "wb") as out:
        while True:
            try:
                r = requests.get(
                    f"https://{host}/resource/{ds}.csv",
                    params={"$limit": chunk, "$offset": offset, "$order": ":id"},
                    timeout=timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                raise _TransientFetchError(
                    f"chunk request at offset={offset} failed: {e}"
                ) from e
            if r.status_code >= 500:
                raise _TransientFetchError(
                    f"Socrata returned {r.status_code} at offset={offset}"
                )
            r.raise_for_status()
            body = r.content
            if not body.strip():
                break
            lines = body.splitlines(keepends=True)
            # Strip the per-chunk header except on the first chunk.
            if header_written:
                lines = lines[1:]
            else:
                header_written = True
            if not lines:
                break
            out.write(b"".join(lines))
            n = len(lines) - (0 if offset == 0 else 0)
            # rows added this chunk = lines written minus header (if any)
            added = len(lines) - (1 if offset == 0 else 0)
            rows += added
            if added < chunk:
                break
            offset += chunk
    tmp.replace(cache_path)
    # Schema check on the freshly downloaded file.
    _check_schema(cache_path)
    log.info("Downloaded Socrata CSV: %s (%d rows, as_of=%s)",
             cache_path, rows, as_of)
    return FetchResult(cache_path, "socrata", as_of, rows, cached=False)


# ---------------------------------------------------------------------------
# FluSight GitHub fallback
# ---------------------------------------------------------------------------
def _fetch_flusight(
    config: FluBNFConfig, *, force: bool, timeout: float,
) -> FetchResult:
    """Fetch from the FluSight forecast hub.

    The hub publishes target-data CSVs under `target-data/`. We grab the most
    recently committed file for the current season.
    """
    repo = config.cdc.flusight_repo
    # List the target-data directory via the GitHub API.
    api_url = f"https://api.github.com/repos/{repo}/contents/target-data"
    r = requests.get(api_url, timeout=timeout)
    r.raise_for_status()
    items = [it for it in r.json() if it["name"].endswith(".csv")]
    if not items:
        raise RuntimeError(f"No CSVs found in {repo}/target-data")
    # Sort by name (FluSight files are date-prefixed) and take the latest.
    items.sort(key=lambda it: it["name"])
    latest = items[-1]
    as_of = _date_from_name(latest["name"]) or date.today()
    cache_path = config.data_cache / f"{as_of.isoformat()}_FluSight.csv"
    if cache_path.exists() and not force:
        rows = _count_data_rows(cache_path)
        log.info("Using cached FluSight CSV: %s", cache_path)
        return FetchResult(cache_path, "flusight", as_of, rows, cached=True)
    raw_url = latest["download_url"]
    rr = requests.get(raw_url, timeout=timeout)
    rr.raise_for_status()
    cache_path.write_bytes(rr.content)
    rows = _count_data_rows(cache_path)
    log.info("Downloaded FluSight CSV: %s (%d rows)", cache_path, rows)
    return FetchResult(cache_path, "flusight", as_of, rows, cached=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_as_of(header_value: Optional[str]) -> date:
    if not header_value:
        return date.today()
    # RFC 7231 IMF-fixdate: "Wed, 06 May 2026 14:27:22 GMT"
    try:
        return datetime.strptime(header_value, "%a, %d %b %Y %H:%M:%S %Z").date()
    except ValueError:
        return date.today()


def _date_from_name(name: str) -> Optional[date]:
    """Try to extract a YYYY-MM-DD prefix from a FluSight filename."""
    import re
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _count_data_rows(p: Path) -> int:
    with open(p, "rb") as f:
        return max(0, sum(1 for _ in f) - 1)
