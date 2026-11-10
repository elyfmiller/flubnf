"""The Groundhog's figure of record, held the same in every doc that quotes it.

The shipped Groundhog since 2026-10-23 is the own-state weighting with
size-matched donors. README's Measured record gives its figures, and these
tests read them from there: 0.642 pooled (0.680 / 0.627 / 0.645 by season)
on 17,116 cells under FluSight's cell rule. 0.660 is the own-state form
without the size weighting, shipped 2026-10-15 to 2026-10-23.
docs/FLUSIGHT-2026-27.md, docs/ORACLE-SIHRS.md, docs/SITE.md and
CITATION.cff quote it. Dated logs (docs/team) and the archived release
note (docs/archive/RELEASE-1.0.md) keep the figures of their date and are
not checked. Text only.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SHIPPED_ROW = "| Groundhog, own-state weighting with size-matched donors"
#: README's own words for the size weighting in the Groundhog's method
SIZE_WORDS = ("donor weeks whose count is near the jurisdiction's newest "
              "weighted most (since 2026-10-23")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Prose is hard-wrapped, so a phrase may straddle a line break."""
    return " ".join(text.split())


def _between(text: str, start: str, stop: str) -> str:
    at = text.index(start)
    return text[at:text.index(stop, at)]


def _record() -> dict:
    """README's Measured record row for the shipped Groundhog."""
    for line in _read("README.md").splitlines():
        if line.startswith(SHIPPED_ROW):
            cells = [c.strip() for c in line.strip("|").split("|")]
            return {"seasons": cells[2:5],
                    "pooled": f"{float(cells[5]):.3f}",
                    "cells": cells[6]}
    raise AssertionError("README's Measured record has no shipped Groundhog row")


def _citation() -> dict:
    return yaml.safe_load(_read("CITATION.cff"))


def _version(text: str) -> tuple:
    return tuple(int(p) for p in str(text).split("."))


def test_readme_record_is_the_figure_these_docs_quote():
    """The source the other tests read: 0.642 on 17,116 cells."""
    rec = _record()
    assert rec["pooled"] == "0.642"
    assert rec["seasons"] == ["0.680", "0.627", "0.645"]
    assert rec["cells"] == "17,116"


# ---------------------------------------------------- docs/FLUSIGHT-2026-27.md


def test_flusight_doc_gives_the_shipped_groundhog_figure():
    rec = _record()
    para = _between(_flat(_read("docs/FLUSIGHT-2026-27.md")),
                    "Recorded pooled relative WIS", "The 2026-27 season is")
    assert f"Groundhog {rec['pooled']}" in para
    assert "Groundhog 0.660" not in para
    assert " / ".join(rec["seasons"]) in para
    assert f"{rec['cells']} cells" in para
    assert "size-matched donors" in para
    # 0.660 may be quoted only as the form it belongs to
    if "0.660" in para:
        assert "own-state form without the size weighting" in para


def test_flusight_doc_model_row_names_the_size_matched_donors():
    row = next(line for line in _read("docs/FLUSIGHT-2026-27.md").splitlines()
               if line.startswith("| `NAU_PyBNF-GroundHogCGR` |"))
    assert SIZE_WORDS in _flat(_read("README.md"))
    assert SIZE_WORDS in row


# --------------------------------------------------------- docs/ORACLE-SIHRS.md


def test_oracle_doc_points_to_the_shipped_groundhog_form():
    flat = _flat(_read("docs/ORACLE-SIHRS.md"))
    assert "the shipped own-state form's" not in flat
    passage = _between(flat, "not the Groundhog, whose own record",
                       "README, Measured record)")
    assert "size-matched donors" in passage
    assert _record()["pooled"] in passage


# ------------------------------------------------------------- docs/SITE.md


def test_site_doc_names_the_groundhog_labels_site_build_gives():
    sb = pytest.importorskip("app.core.site_build")
    labels = {sb.GH_LABEL_SHIPPED, sb.GH_LABEL_POOLED, sb.GH_LABEL_OWN,
              sb.GH_LABEL_MIXED}
    section = _between(_flat(_read("docs/SITE.md")),
                       "The Groundhog column is named", "**Placements")
    for label in labels:
        assert f'"{label}"' in section, label
    quoted = set(re.findall(r'"(Groundhog[^"]*)"', section))
    assert quoted <= labels, quoted - labels
    assert "size-matched donors" in section
    assert "since 2026-10-23" in section


# -------------------------------------------------------------- CITATION.cff


def test_citation_quotes_the_shipped_groundhog_figure():
    rec = _record()
    abstract = _flat(_citation()["abstract"])
    assert f"at {rec['pooled']}" in abstract
    assert "0.660" not in abstract
    assert ", ".join(rec["seasons"][:2]) + " and " + rec["seasons"][2] in abstract
    assert f"{rec['cells']} cells" in abstract
    assert "size-matched donors" in abstract
    assert "posterior" not in abstract.lower()


def test_citation_release_is_not_an_ensemble_release_or_older_than_the_package():
    """The abstract says the 1.0 and 1.1 releases shipped a different
    product, so this citation cannot carry their version; and it cannot
    predate the form it quotes (shipped 2026-10-23), nor lag the package."""
    cff = _citation()
    version = _version(cff["version"])
    assert version[:2] > (1, 1), cff["version"]
    package = tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    assert version >= _version(package), (cff["version"], package)
    assert str(cff["date-released"]) >= "2026-10-23", cff["date-released"]


def test_the_version_is_the_same_in_every_file_that_states_it():
    """flubnf/__init__.py keeps its version in lockstep with pyproject.toml,
    CITATION.cff and FluBNF.app's Info.plist: one release, one number."""
    import plistlib
    module = re.search(r'^__version__ = "(.*)"$', _read("flubnf/__init__.py"), re.M)
    info = plistlib.loads((REPO / "FluBNF.app/Contents/Info.plist").read_bytes())
    stated = {
        "pyproject.toml": tomllib.loads(_read("pyproject.toml"))["project"]["version"],
        "flubnf/__init__.py": module and module.group(1),
        "CITATION.cff": str(_citation()["version"]),
        "CFBundleShortVersionString": info["CFBundleShortVersionString"],
        "CFBundleVersion": info["CFBundleVersion"],
    }
    assert len(set(stated.values())) == 1, stated


def test_citation_states_the_oracle_sihrs_record_and_its_engines():
    """The Oracle SIHRS's figure is the B2 screen's (oracle_text.RECORD,
    three seasons), its registered form against the plain Liu-West filter;
    the method names both engines it ran on, the public one at the pinned
    commit, and the weight its growth carries."""
    oracle_text = pytest.importorskip("app.core.oracle_text")
    lwf = pytest.importorskip("app.core.engines.lwf")
    rec = oracle_text.RECORD["three"]
    abstract = _flat(_citation()["abstract"])
    assert (f"the Oracle SIHRS pools at {oracle_text.fmt(rec['oracle'])} against "
            f"the plain Liu-West filter's {oracle_text.fmt(rec['filter'])} on "
            f"{oracle_text.cells(rec['cells'])} cells under the earlier cell "
            "rule") in abstract
    assert "under its registered form (weight one half" in abstract
    assert f"(lanl/PyBNF at {lwf.PUBLIC_ENGINE_COMMIT[:8]}, job type lwf)" in abstract
    assert "the lab's private PyBNF fork on bngsim before it" in abstract
    assert "at weight one quarter on the filter's growth" in abstract
    for stale in ("half and half", "a fork of PyBNF on the bngsim engine",
                  "plain filter's"):
        assert stale not in abstract, stale


def test_citation_references_the_public_engine_at_its_pinned_commit():
    lwf = pytest.importorskip("app.core.engines.lwf")
    refs = _citation().get("references") or []
    for ref in refs:                  # CFF 1.2.0 requires these on a reference
        assert {"type", "title", "authors"} <= set(ref), ref
    pybnf = [r for r in refs if r["title"] == "PyBNF"]
    assert len(pybnf) == 1, refs
    ref = pybnf[0]
    assert ref["type"] == "software"
    assert ref["repository-code"] == "https://github.com/lanl/PyBNF"
    assert ref["commit"] == lwf.PUBLIC_ENGINE_COMMIT
    assert {"name": "Los Alamos National Laboratory"} in ref["authors"]
