"""Per-workspace path layout.

A "workspace" is one season's working directory. The layout mirrors the
legacy `NAU_Influenza/current_job/` structure so existing tooling /
downstream consumers don't have to change:

    workspace/
      conf_files/        # per-state .conf
      exp_files/         # per-state .exp
      model_files/       # per-state .bngl
      results/<State>/   # PyBNF output per state
      data/              # the raw CDC CSV snapshot used to build .exp files
      state.json         # workflow state ledger
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def conf_dir(self) -> Path:
        return self.root / "conf_files"

    @property
    def exp_dir(self) -> Path:
        return self.root / "exp_files"

    @property
    def bngl_dir(self) -> Path:
        return self.root / "model_files"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    def conf_file(self, state: str) -> Path:
        return self.conf_dir / f"{state}.conf"

    def bngl_file(self, state: str) -> Path:
        return self.bngl_dir / f"{state}.bngl"

    def exp_file(self, state: str) -> Path:
        return self.exp_dir / f"{state}_flu.exp"

    def results_for(self, state: str) -> Path:
        return self.results_dir / state

    def ensure(self) -> "WorkspacePaths":
        for d in (self.conf_dir, self.exp_dir, self.bngl_dir,
                  self.results_dir, self.data_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self
