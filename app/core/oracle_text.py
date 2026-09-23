"""The Oracle SIHRS in words: the reader-facing text every surface shares.

Home, Methods, the model tab, the public site and the hub card all describe
the same member, so the sentences that can go stale live HERE, once, and
the pages read them (a Jinja global, `oracle_text`, in app/ui/server.py).
No numpy and no pandas: the page shell imports this at startup.

THE DONOR BANK (the one marked place). BANK_STREAM and BANK_TEXT say which
data streams form the Oracle step's donor pool. Today that is the
admissions-only bank: growth paths read from the hub's own dated archive of
NHSN admissions, rebuilt each week from the vintage the forecast date saw
(flubnf.oracle_bank, stream "admissions-fbase"). Bank change B2 (the
admissions half mixed with a FluSurv-NET half, the Groundhog's own
auxiliary stream) is registered and NOT made. If it ships, BANK_STREAM and
every sentence of BANK_TEXT change together here, and nowhere else in the
app; app/tests/test_oracle_text.py fails until they do, because it holds
BANK_STREAM equal to flubnf.oracle_bank.STREAM and the hub card's
methods_long to BANK_TEXT["card"].

THE RECORD. RECORD carries the figures every surface prints, unrounded as
the reproduce printed them (docs/ORACLE-SIHRS.md section 5): the stored
kernel-regularizer J15 grid backfilled for 2024-25 and 2025-26 through
`flubnf oracle backfill` and scored by the app's own scorer, relWIS against
the FluSight baseline as a ratio of WIS sums, US excluded, on the cells
where both the member and the plain filter scored. Each equals the
registered screen's seed-1 value to machine precision. The test holds every
four-place figure to that document, so a number without a source cannot
ship. The screen that produced them is a FROZEN-SPECIFICATION REPLICATION
(the pre-registration's own words): the family had been looked at on the
same grid before the primary arm was fixed, so the confirmatory test is the
prospective 2026-27 season.
"""
from __future__ import annotations

#: the donor stream the Oracle step's bank is built from; must equal
#: flubnf.oracle_bank.STREAM (the test holds it)
BANK_STREAM = "admissions-fbase"

#: every sentence that names the donor bank's data streams. Change these,
#: and only these, when the bank changes (bank change B2).
BANK_TEXT = {
    # a noun phrase for running text: "donor growth paths from ..."
    "phrase": "past seasons' NHSN hospital admissions",
    # one line for a diagram box (at most about 22 characters)
    "diagram": "NHSN admission growth",
    # the full sentence for Methods and the model tab
    "pool": (
        "The donor pool is built each week from the hub's own dated archive "
        "of NHSN admissions, exactly as it stood on the forecast date: "
        "the weekly growth path of every location (the 52 jurisdictions and "
        "the national series) through the four forecast weeks, from "
        "strictly earlier seasons at weeks within two epiweeks "
        "of the forecast week, wherever the counts around the donor week "
        "are at least 10 admissions so a growth rate can be read from them. "
        "A week with fewer than two donor seasons, or fewer than 30 paths, "
        "leaves the filter unchanged."),
    # the sentence the hub card carries verbatim (methods_long)
    "card": (
        "The donor bank is NHSN admission growth only, rebuilt each week "
        "from the hub's dated vintage archive."),
}

#: the frozen pre-registration's sha256 (flubnf.oracle.PREREG_SHA256; the
#: test holds the two equal)
PREREG_SHA256 = (
    "67c9fa49a195908312f34ca783b21d85377759309df14461f86fbfd54d30c56f")

#: the record (docs/ORACLE-SIHRS.md section 5): the Oracle SIHRS against
#: the plain filter on the same scored cells, per season and for the two
#: active seasons together
RECORD = {
    "2024-25": {"oracle": 0.7191698, "filter": 0.7943943, "cells": 4859},
    "2025-26": {"oracle": 0.7739591, "filter": 0.8426255, "cells": 4420},
    "both": {"oracle": 0.7408660, "filter": 0.8134935, "cells": 9279},
}

#: where the record comes from, in one line a page can print
RECORD_SOURCE = (
    "docs/ORACLE-SIHRS.md: the stored 2024-25 and 2025-26 forecasts "
    "backfilled with the Oracle step and scored by this app's own scorer")


def fmt(x: float, places: int = 3) -> str:
    """A relWIS figure at the page's precision."""
    return f"{float(x):.{places}f}"


def cells(n: int) -> str:
    """A cell count with a thousands separator."""
    return f"{int(n):,}"
