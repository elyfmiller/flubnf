"""The Oracle SIHRS's recorded 0.738 says which form it was scored under.

docs/FLUSIGHT-2026-27.md's model table gives the step's weight as one
quarter from the 2026-10-17 round; the record under it was scored under
the registered form, weight one half. CITATION.cff's abstract says so;
the FluSight doc's record paragraph now says it in the same words, and
that the settings submitted since October have not been scored on those
cells (the review of #105 at 9c16dd6c, finding 3). Text only.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
#: CITATION.cff's words for the form the record was scored under
FORM = ("under its registered form (weight one half, the season-to-date "
        "seed, no narrowing or cap, on the private fork)")
UNSCORED = ("the settings submitted since October have not been scored on "
            "those cells")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _record_paragraph() -> str:
    flat = _flat((REPO / "docs/FLUSIGHT-2026-27.md").read_text(
        encoding="utf-8"))
    at = flat.index("Recorded pooled relative WIS")
    return flat[at:flat.index("The 2026-27 season is", at)]


def test_the_citation_gives_the_words_the_doc_takes():
    abstract = _flat(yaml.safe_load(
        (REPO / "CITATION.cff").read_text(encoding="utf-8"))["abstract"])
    assert FORM in abstract
    assert UNSCORED.lower() in abstract.lower()     # its sentence opens it


def test_the_flusight_doc_labels_0738_with_its_form():
    para = _record_paragraph()
    form = FORM.replace("under its registered form (", "").rstrip(")")
    assert (f"Oracle SIHRS 0.738 under its registered form ({form}; "
            "15,300 cells, the earlier cell rule;") in para
    assert UNSCORED in para
    # every 0.738 in the paragraph is the labelled one
    assert para.count("0.738") == 1
