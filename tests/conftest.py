"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from flubnf.config import FluBNFConfig
from flubnf.paths import WorkspacePaths


def _find_legacy_dir() -> Optional[Path]:
    """Locate the legacy fixtures dir.

    Historically these lived under `<repo>/NAU_Influenza/` but the directory
    was renamed to `NAU_Influenza_M_Model/` (the legacy assets — CSVs, exp
    files, current_job/ — now sit next to FluBNF/ inside that). Try both."""
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        for name in ("NAU_Influenza_M_Model", "NAU_Influenza"):
            candidate = ancestor / name
            if (candidate / "cleaned_csvs").is_dir():
                return candidate
        if (ancestor / "cleaned_csvs").is_dir():
            return ancestor
    return None


LEGACY_NAU: Optional[Path] = _find_legacy_dir()


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(root=tmp_path / "season_test").ensure()


@pytest.fixture
def config(tmp_path: Path) -> FluBNFConfig:
    """A FluBNFConfig writing to tmp; templates come from the installed package."""
    return FluBNFConfig.load(
        workspace_root=tmp_path / "workspaces",
        data_cache=tmp_path / "data",
    )


@pytest.fixture
def legacy_cdc_csv() -> Path:
    """The CSV checked into NAU_Influenza/cleaned_csvs/. Skips if absent."""
    if LEGACY_NAU is None:
        pytest.skip("legacy NAU_Influenza/ not found in any parent directory")
    p = LEGACY_NAU / "cleaned_csvs" / "092425_Hdata.csv"
    if not p.exists():
        pytest.skip(f"legacy CDC CSV not present at {p}")
    return p
