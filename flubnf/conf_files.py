"""Read, write, and edit per-state PyBNF .conf files.

Replaces the relevant pieces of `NAU_Influenza/scripts/110624_everything.py`:

  - `check_and_create_files`        -> `materialize_conf_from_template`
  - `update_conf_file_keys`         -> `update_keys`
  - `update_conf_with_free_params`  -> `update_uniform_vars`
  - `update_starting_params_from_mle_*` -> `set_starting_params`

These operate on a single conf path at a time. The CLI iterates over states.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .config import FluBNFConfig
from .paths import WorkspacePaths

log = logging.getLogger(__name__)

# Template tokens (see flubnf/templates/Alabama.conf).
_TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


@dataclass(frozen=True)
class FreeParam:
    """Single uniform_var entry. `name` is the bare PyBNF name (with __FREE)."""

    name: str  # e.g. "b0__FREE"
    low: float
    high: float

    @property
    def short(self) -> str:
        """Short name used as the BNGL parameter symbol (e.g. "b0")."""
        return self.name.split("__", 1)[0]

    def line(self) -> str:
        return f"uniform_var = {self.name} {self.low} {self.high}\n"


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------
def materialize_conf_from_template(
    state: str, paths: WorkspacePaths, config: FluBNFConfig,
    *, force: bool = False,
) -> Path:
    """Create a per-state .conf from the template if it doesn't exist."""
    out = paths.conf_file(state)
    if out.exists() and not force:
        return out
    raw = Path(config.template_conf).read_text()
    substituted = (
        raw.replace(config.template_state, state)
           .replace("{{BNG_COMMAND}}", config.pybnf.bng_command
                    or str(__import__("flubnf.settings",
                                      fromlist=["BNG"]).BNG))
           .replace("{{MODEL_DIR}}", str(paths.bngl_dir))
           .replace("{{EXP_DIR}}", str(paths.exp_dir))
           .replace("{{RESULTS_DIR}}", str(paths.results_dir))
    )
    leftover = _TOKEN_RE.findall(substituted)
    if leftover:
        raise ValueError(
            f"Unresolved template tokens in conf for {state}: {leftover}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(substituted)
    log.info("Wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------
def read_uniform_vars(conf_path: Path) -> list[FreeParam]:
    out: list[FreeParam] = []
    for line in conf_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("uniform_var"):
            continue
        # "uniform_var = name low high"
        m = re.match(
            r"uniform_var\s*=\s*(\S+)\s+(\S+)\s+(\S+)",
            stripped,
        )
        if not m:
            continue
        try:
            out.append(FreeParam(m.group(1), float(m.group(2)), float(m.group(3))))
        except ValueError:
            continue
    return out


def replace_uniform_vars(
    conf_path: Path, free_params: Sequence[FreeParam],
) -> None:
    """Atomically replace the `uniform_var` block with exactly `free_params`.

    Unlike `update_uniform_vars` (which only adds / updates), this also
    REMOVES any uniform_var lines for parameters not present in the new
    list. Use this when the parameter set itself is changing (e.g., when
    switching between different K piecewise-step structures).
    """
    lines = conf_path.read_text().splitlines(keepends=True)
    first_uniform = -1
    last_uniform = -1
    for i, line in enumerate(lines):
        if line.lstrip().startswith("uniform_var"):
            if first_uniform < 0:
                first_uniform = i
            last_uniform = i
    new_lines = [fp.line() for fp in free_params]
    if first_uniform < 0:
        out = lines + new_lines
    else:
        out = lines[:first_uniform] + new_lines + lines[last_uniform + 1:]
    conf_path.write_text("".join(out))


def update_uniform_vars(
    conf_path: Path, free_params: Mapping[str, tuple[float, float]],
) -> None:
    """Update existing uniform_var lines in-place; append new ones at the end
    of the existing uniform_var block."""
    lines = conf_path.read_text().splitlines(keepends=True)
    seen: set[str] = set()
    last_uniform_idx = -1
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("uniform_var"):
            continue
        m = re.match(r"(\s*uniform_var\s*=\s*)(\S+)\s+(\S+)\s+(\S+)", line)
        if not m:
            continue
        name = m.group(2)
        last_uniform_idx = i
        if name in free_params:
            low, high = free_params[name]
            lines[i] = f"{m.group(1)}{name} {low} {high}\n"
            seen.add(name)

    new_lines = [
        FreeParam(name, lo, hi).line()
        for name, (lo, hi) in free_params.items()
        if name not in seen
    ]
    if new_lines:
        insert_at = last_uniform_idx + 1 if last_uniform_idx >= 0 else len(lines)
        lines = lines[:insert_at] + new_lines + lines[insert_at:]
    conf_path.write_text("".join(lines))


def update_keys(conf_path: Path, updates: Mapping[str, object]) -> None:
    """Update top-level `key = value` lines. Unknown keys are appended."""
    lines = conf_path.read_text().splitlines(keepends=True)
    remaining = dict(updates)
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*)=", line)
        if not m:
            continue
        key = m.group(2)
        if key in remaining:
            lines[i] = f"{m.group(1)}{key} = {remaining.pop(key)}\n"
    if remaining:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        for k, v in remaining.items():
            lines.append(f"{k} = {v}\n")
    conf_path.write_text("".join(lines))


def set_starting_params(conf_path: Path, params: Sequence[float] | str) -> None:
    """Set or replace a `starting_params = ...` line.

    `params` may be a sequence of floats or a pre-joined string.
    """
    value = (
        params if isinstance(params, str)
        else " ".join(f"{x:.10g}" for x in params)
    )
    lines = conf_path.read_text().splitlines(keepends=True)
    replaced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("starting_params"):
            lines[i] = f"starting_params = {value}\n"
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(f"starting_params = {value}\n")
    conf_path.write_text("".join(lines))


# ---------------------------------------------------------------------------
# Bulk helpers
# ---------------------------------------------------------------------------
def materialize_all(
    states: Iterable[str], paths: WorkspacePaths, config: FluBNFConfig,
    *, force: bool = False,
) -> list[Path]:
    return [
        materialize_conf_from_template(s, paths, config, force=force)
        for s in states
    ]
