"""Configuration schema for FluBNF.

All paths and tunables live here. No hardcoded `/Users/...` paths anywhere
else in the codebase — that was the bug we are fixing relative to the legacy
scripts.

Config resolution order (later wins):
1. `config/default.yaml` shipped with the package
2. `~/.config/flubnf/config.yaml` (optional user override)
3. `--config <path>` on the CLI
4. Environment variables prefixed `FLUBNF_` (e.g. `FLUBNF_WORKSPACE_ROOT`)
5. Explicit kwargs to `FluBNFConfig.load()`
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class CDCConfig(BaseModel):
    """How to fetch new respiratory hospitalization data.

    The dataset is published with two schemas depending on download path:
      - Web export: `Week Ending Date`, `Geographic aggregation`,
        `Total Influenza Admissions`
      - Socrata API: `weekendingdate`, `jurisdiction`, `totalconfflunewadm`
    We list both as aliases and use whichever matches the CSV header.
    """

    socrata_dataset: str = "mpgq-jmmr"
    socrata_host: str = "data.cdc.gov"
    flusight_repo: str = "cdcepi/FluSight-forecast-hub"
    date_columns: list[str] = ["Week Ending Date", "weekendingdate"]
    geo_columns: list[str] = ["Geographic aggregation", "jurisdiction"]
    value_columns: list[str] = ["Total Influenza Admissions", "totalconfflunewadm"]


class SeasonConfig(BaseModel):
    """Season window. FluSight season runs from MMWR week 26 of `year` through
    week 47 of `year + 1`."""

    year: int = 2025
    onset_week: int = 26
    end_year_offset: int = 1
    end_week: int = 47


class PyBNFConfig(BaseModel):
    """Per-run PyBNF settings. Mirrors the keys in the legacy `config_updates`
    dict from `NAU_Influenza/scripts/110624_everything.py` so we can drop in."""

    # resolved via flubnf.settings (FLUBNF_BNG env var overrides)
    bng_command: str = ""
    fit_type: str = "de"
    objfunc: str = "neg_bin_dynamic"
    step_size: float = 0.02
    population_size: int = 15
    parallel_count: int = 6
    verbosity: int = 2
    burn_in: int = 2000
    adaptive: int = 2000
    max_iterations: int = 1000
    continue_run: int = 0
    sample_every: int = 1
    output_noise_trajectory: str = "H_weekly"
    refine: int = 0


class ModelConfig(BaseModel):
    """Which compartmental model + time-varying beta form to fit.

    `sir_piecewise` (default) is the legacy SIR with a piecewise-constant
    nested-if beta and S0 normalized to 1. `sirs_logistic` is the migration
    target: SIRS (waning R->S at a fixed rate) with a smooth sum-of-logistics
    beta whose transition centers/width are FIXED (only signed amplitudes
    `db_k` are fitted), and S0 = the state's absolute population so `mult`
    becomes an interpretable ascertainment x IHR fraction.

    See docs/SIRS_MIGRATION_PLAN.md. The default keeps every existing run
    byte-identical; `sirs_logistic` is opt-in via this flag.
    """

    model_type: str = "sir_piecewise"
    # Weekly waning rate R->S. ~0.019/wk ~= 52-week mean immunity. Used only
    # when model_type == "sirs_logistic"; held FIXED (never fitted) to avoid
    # the SIRS-vs-beta degeneracy.
    omega_fixed: float = 0.019
    # Fixed logistic-beta transition centers (in weeks from season start) and
    # the shared ramp width. Index k (1-based) supplies tc_k for db_k. The
    # number actually used per state is the transition count (n_steps).
    transition_centers: list[float] = [8.0, 18.0, 28.0]
    transition_width: float = 2.5
    # How the transition centers are chosen:
    #   "fixed"       — tier-constant `transition_centers` (original behavior).
    #   "data_driven" — place each center at an observed inflection of the
    #                   series up to the forecast week (flubnf.centers), to
    #                   stop the smooth beta lagging the surge. Centers are
    #                   still FIXED at fit time (param count unchanged); only
    #                   their *values* become per-state, per-week.
    center_mode: str = "fixed"

    @field_validator("model_type")
    @classmethod
    def _known_model(cls, v: str) -> str:
        allowed = {"sir_piecewise", "sirs_logistic"}
        if v not in allowed:
            raise ValueError(f"model_type must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("center_mode")
    @classmethod
    def _known_center_mode(cls, v: str) -> str:
        allowed = {"fixed", "data_driven"}
        if v not in allowed:
            raise ValueError(f"center_mode must be one of {sorted(allowed)}, got {v!r}")
        return v


class FluBNFConfig(BaseModel):
    """Top-level FluBNF configuration."""

    workspace_root: Path = Field(
        default=Path("./workspaces"),
        description="Where per-season working directories are created.",
    )
    data_cache: Path = Field(
        default=Path("./data"),
        description="Where downloaded CDC CSVs are cached.",
    )
    template_bngl: Path = Field(
        default=Path("./flubnf/templates/Alabama.bngl"),
        description="Seed BNGL template (state name will be substituted).",
    )
    template_bngl_sirs: Path = Field(
        default=Path("./flubnf/templates/AlabamaSIRS.bngl"),
        description="SIRS + smooth-logistic-beta BNGL template, used when "
                    "model.model_type == 'sirs_logistic'. Tokens {{POP}}, "
                    "{{TC1..3}}, {{SW}}, {{OMEGA}} are substituted per state.",
    )
    template_conf: Path = Field(
        default=Path("./flubnf/templates/Alabama.conf"),
        description="Seed conf template (state name will be substituted).",
    )
    template_state: str = "Alabama"
    locations_csv: Path = Field(
        default=Path("./flubnf/data/locations.csv"),
        description="FluSight locations.csv (state -> FIPS, population). "
                    "Bundled inside the package by default.",
    )
    season: SeasonConfig = Field(default_factory=SeasonConfig)
    cdc: CDCConfig = Field(default_factory=CDCConfig)
    pybnf: PyBNFConfig = Field(default_factory=PyBNFConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        **overrides: Any,
    ) -> "FluBNFConfig":
        package_default = Path(__file__).parent.parent / "config" / "default.yaml"
        user_default = Path.home() / ".config" / "flubnf" / "config.yaml"

        data: dict[str, Any] = {}
        for candidate in (package_default, user_default, config_path):
            if candidate and Path(candidate).exists():
                with open(candidate) as f:
                    loaded = yaml.safe_load(f) or {}
                _deep_update(data, loaded)

        # FLUBNF_* environment variables: only flat top-level keys for now.
        for key in cls.model_fields:
            env_key = f"FLUBNF_{key.upper()}"
            if env_key in os.environ:
                data[key] = os.environ[env_key]

        data.update(overrides)
        config = cls.model_validate(data)
        return config._resolve_paths(package_default.parent.parent)

    def _resolve_paths(self, package_root: Path) -> "FluBNFConfig":
        """Make relative paths absolute, anchored at the package root."""
        def _abs(p: Path) -> Path:
            return p if p.is_absolute() else (package_root / p).resolve()

        return self.model_copy(update={
            "workspace_root": _abs(self.workspace_root),
            "data_cache": _abs(self.data_cache),
            "template_bngl": _abs(self.template_bngl),
            "template_bngl_sirs": _abs(self.template_bngl_sirs),
            "template_conf": _abs(self.template_conf),
            "locations_csv": _abs(self.locations_csv),
        })

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------
    def workspace(self, name: str | None = None) -> Path:
        """Return the workspace directory for a given week.

        Defaults to `season_{year}` if no name is provided.
        """
        name = name or f"season_{self.season.year}"
        return self.workspace_root / name

    @field_validator("workspace_root", "data_cache", "template_bngl",
                     "template_bngl_sirs", "template_conf", "locations_csv",
                     mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Path:
        return Path(v) if not isinstance(v, Path) else v


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)
        else:
            dst[k] = v
