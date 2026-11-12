"""The Oracle SIHRS step's weight, said as the Model lane says it.

The submitted weight on the Liu-West filter's growth is one quarter from
the 2026-10-17 round, one half before it (model-metadata's method card).
CITATION.cff's abstract says so in the Model lane's words, and README's
model list and docs/FLUSIGHT-2026-27.md's model table take them; neither
says the step is half and half or 50/50 any more (the donor bank's own
mix, NHSN and FluSurv-NET half and half, is another thing and stays).
pyproject.toml's one-line description names the Liu-West filter in PyBNF.
Text only.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
#: the Model lane's words for the weight, as CITATION.cff's abstract has them
WEIGHT = ("at weight one quarter on the filter's growth from the 2026-10-17 "
          "round (one half before)")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_citation_gives_the_words_these_docs_take():
    abstract = _flat(yaml.safe_load(_read("CITATION.cff"))["abstract"])
    assert "combined, by a weighted geometric mean, with donor growth" in abstract
    assert WEIGHT in abstract


def test_readme_gives_the_oracle_steps_weight():
    flat = _flat(_read("README.md"))
    at = flat.index("After the fit, the Oracle step")
    step = flat[at:flat.index("([docs/ORACLE-SIHRS.md]", at)]
    assert "weighted geometric mean of the filter's growth and the donor's" in step
    assert WEIGHT in step
    assert "geometric mean, half and half" not in step
    # the bank's own mix stays
    assert step.rstrip().endswith("hospitalization-rate growth, half and half")


def test_the_flusight_doc_row_gives_the_oracle_steps_weight():
    row = next(line for line in _read("docs/FLUSIGHT-2026-27.md").splitlines()
               if line.startswith("| `NAU_PyBNF-OracleSIHRS` |"))
    assert "50/50" not in row
    assert ("each path's growth combined, by a weighted geometric mean, with "
            "a donor growth path") in row
    assert WEIGHT in row
    assert "donors half NHSN, half FluSurv-NET" in row


def test_the_package_description_names_the_liu_west_filter():
    desc = tomllib.loads(_read("pyproject.toml"))["project"]["description"]
    assert "fitted by the Liu-West filter in PyBNF" in desc
    assert "particle filter" not in desc
    # one line, no longer than the one it replaced (151 characters)
    assert "\n" not in desc and len(desc) < 151, len(desc)
