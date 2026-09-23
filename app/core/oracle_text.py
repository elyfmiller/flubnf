"""The Oracle SIHRS in words: the reader-facing text every surface shares.

Home, Methods, the model tab, the public site and the hub card all describe
the same member, so the sentences that can go stale live HERE, once, and
the pages read them (a Jinja global, `oracle_text`, in app/ui/server.py).
No numpy and no pandas: the page shell imports this at startup.

THE DONOR BANK (the one marked place). BANK_STREAM and BANK_TEXT say which
data streams form the Oracle step's donor pool. Since addendum A2 (the
lead's decision of 2026-09-23) that is bank change B2, the Groundhog's own
donor bank: past-season NHSN admissions growth, rebuilt each week from the
hub's dated archive exactly as the forecast date saw it
(flubnf.oracle_bank, stream "admissions-fbase"), mixed half and half per
sample path with past-season FluSurv-NET hospitalization-rate growth from
the committed, digest-checked bank the Groundhog splices
(flubnf.oracle_mix, stream "admissions-fbase+flusurv"). If the bank changes
again, BANK_STREAM and every sentence of BANK_TEXT change together here,
and nowhere else in the app; app/tests/test_oracle_text.py fails until
they do, because it holds BANK_STREAM equal to flubnf.oracle_mix.STREAM
and the hub card's methods_long to BANK_TEXT["card"].

THE RECORD. RECORD carries the figures every surface prints, unrounded as
the B2 screen wrote them (oracle_member/b2/results/screen_b2_scores.json,
relwis_tables, the common cell set, the seed mean over the five seeds;
read from that file, never typed, and held equal to it by the test where
the file is on the machine): the shipped member (LBGH) against the plain
filter on the same cells of the stored kernel-regularizer J15 grid,
relWIS against the FluSight baseline as a ratio of WIS sums, US excluded.
docs/ORACLE-SIHRS.md prints each one, and the test holds every four-place
figure to that document, so a number without a source cannot ship. The
choice of this bank over the admissions-only one was the lead's decision
on a screen that did not resolve it (RECORD_B2_1: LBGH minus the
admissions-only member, an interval including zero), and the screen is a
FROZEN-SPECIFICATION REPLICATION on seasons the family had been looked at
on, so the confirmatory test is the prospective 2026-27 season. CAVEAT
says that once for every surface.
"""
from __future__ import annotations

#: the donor stream the Oracle step's bank is built from; must equal
#: flubnf.oracle_mix.STREAM, the shipped bank (the test holds it)
BANK_STREAM = "admissions-fbase+flusurv"

#: every sentence that names the donor bank's data streams. Change these,
#: and only these, when the bank changes.
BANK_TEXT = {
    # a noun phrase for running text: "donor growth paths from ..."
    "phrase": ("past seasons' NHSN hospital admissions and FluSurv-NET "
               "hospitalization rates"),
    # one line for a diagram box (at most about 22 characters)
    "diagram": "NHSN + FluSurv-NET",
    # the full sentence for Methods and the model tab
    "pool": (
        "The donor pool is the Groundhog's own donor bank, mixed half and "
        "half: each forecast sample path draws its donor from one of two "
        "streams with equal probability. The first is past-season NHSN "
        "admissions growth, rebuilt each week from the hub's own dated "
        "archive exactly as it stood on the forecast date: the weekly growth "
        "path of every location (the 52 jurisdictions and the national "
        "series) through the four forecast weeks, from strictly earlier "
        "seasons at weeks within two epiweeks of the forecast week, wherever "
        "the counts around the donor week are at least 10 admissions so a "
        "growth rate can be read from them. The second is past-season "
        "FluSurv-NET hospitalization-rate growth from the same calendar "
        "weeks (its catchment sites and network totals), read from the donor "
        "bank this repository carries and checked against its digest, the "
        "rate's growth scaled by the shrink the Groundhog fits so the two "
        "streams' spreads of growth match. A week where neither stream "
        "supplies 30 paths (the admissions stream also needs two donor "
        "seasons) leaves the filter unchanged; where only one does, that "
        "stream supplies every donor."),
    # what the bank means for 2023-24, the season with one admissible
    # admissions donor season
    "coverage": (
        "In 2023-24 only one earlier NHSN season (2022-23) is admissible, "
        "fewer than the two the admissions stream needs, so the FluSurv-NET "
        "stream, with up to twelve earlier seasons, supplies every donor there; "
        "on the four April weeks of 2023-24 it has no admissible path "
        "either, and the step leaves the filter unchanged."),
    # the sentence the hub card carries verbatim (methods_long)
    "card": (
        "The donor bank is the Groundhog's own: past-season NHSN admission "
        "growth, rebuilt each week from the hub's dated vintage archive, and "
        "FluSurv-NET hospitalization-rate growth from a committed, "
        "digest-checked bank, mixed half and half per sample path."),
}

#: the frozen pre-registration's sha256 (flubnf.oracle.PREREG_SHA256; the
#: test holds the two equal)
PREREG_SHA256 = (
    "67c9fa49a195908312f34ca783b21d85377759309df14461f86fbfd54d30c56f")
#: the B2 document and addendum A2 (flubnf.oracle.B2_SHA256 and
#: ADDENDUM_A2_SHA256; the test holds them equal)
B2_SHA256 = (
    "2ce3564622296f490a435b773a3b34d431d889b3e0d4fe4b32ff6aeb8ede9249")
ADDENDUM_A2_SHA256 = (
    "85ac546416bbb20ed1b87ce9289f50645ff1e22169b0bed9ae0a054e3e449f27")

#: the record: the shipped Oracle SIHRS (LBGH) against the plain filter on
#: the same scored cells, per season, for the two seasons with admissions
#: donors together ("both", the screen's active2), and over the three
#: seasons ("three", the screen's pooled3); the B2 screen's seed means
RECORD = {
    "2023-24": {"oracle": 0.7667219131312434, "filter": 0.83951715405057, "cells": 6021},
    "2024-25": {"oracle": 0.6974500648653201, "filter": 0.7943942998006515, "cells": 4859},
    "2025-26": {"oracle": 0.781303040324272, "filter": 0.8426254870631105, "cells": 4420},
    "both": {"oracle": 0.7306552766001946, "filter": 0.8134935240858803, "cells": 9279},
    "three": {"oracle": 0.7380100709090158, "filter": 0.818800324607587, "cells": 15300},
}

#: the member on the admissions stream alone (the frozen document's LB), on
#: the same cells as RECORD["both"], and the B2 screen's reading of the
#: shipped member against it (claim B2-1: point and 95 percent reading
#: interval): UNRESOLVED, the interval includes zero
RECORD_ADMISSIONS_ONLY = {"both": 0.7409222112041687}
RECORD_B2_1 = {"point": -0.01026693460397421,
               "reading95": (-0.028931613372733724, 0.008397744164785306),
               "outcome": 'UNRESOLVED'}

#: where the record comes from, in one line a page can print
RECORD_SOURCE = (
    "docs/ORACLE-SIHRS.md: the B2 screen on the stored 2023-24, 2024-25 and "
    "2025-26 forecasts, reproduced by backfilling them with the Oracle step "
    "and scoring with this app's own scorer")


def fmt(x: float, places: int = 3) -> str:
    """A relWIS figure at the page's precision."""
    return f"{float(x):.{places}f}"


def cells(n: int) -> str:
    """A cell count with a thousands separator."""
    return f"{int(n):,}"


def caveat() -> str:
    """The one sentence every surface that prints the record carries: how
    this bank was chosen and what tests it."""
    lo, hi = RECORD_B2_1["reading95"]
    return (
        "The choice of this donor bank over admissions growth alone was the "
        "project lead's decision on a screen that did not resolve it: "
        + fmt(RECORD["both"]["oracle"]) + " against "
        + fmt(RECORD_ADMISSIONS_ONLY["both"]) + " on the same "
        + cells(RECORD["both"]["cells"]) + " cells, a difference whose 95 "
        "percent interval (" + f"{lo:+.3f} to {hi:+.3f}" + ") includes zero. "
        "The record is a frozen-specification replication on forecasts the "
        "method was screened on; the 2026-27 season is its prospective test.")
