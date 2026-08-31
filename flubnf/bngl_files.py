"""Read, write, and edit per-state .bngl files.

Replaces the BNGL-side of `NAU_Influenza/scripts/110624_everything.py`:

  - `check_and_create_files`        -> `materialize_bngl_from_template`
  - `add_params_to_bngl`            -> `add_parameters`
  - `update_beta_function`          -> `set_beta_function`
  - `update_simulation_actions`     -> `set_simulation_window`

Plus a `build_piecewise_beta` helper that constructs the nested-if BNGL
expression for a K-step piecewise-constant beta:

    beta(t) = b0 for t in [t0, t0+t1)
            = b1 for t in [t0+t1, t0+t1+t2)
            ...
            = b_{K-1} for t >= t0 + t1 + ... + t_{K-1}
            = 0     otherwise
"""

# Every write in this module is a PyBNF or BNG2.pl input, parsed line-wise.
# newline="\n" is pinned on each: a bare write_text takes newline=None, which
# on Windows turns every \n into \r\n on the way to disk and hands the engine
# CRLF input. The same defect was measured doing exactly that in
# app/core/engines/pf.py (Windows CI, test_natgrowth byte-identity failure).


from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from .config import FluBNFConfig
from .constants import load_locations
from .paths import WorkspacePaths

log = logging.getLogger(__name__)

# Tokens left unresolved after substitution are a hard error — a stray
# `{{...}}` would otherwise reach PyBNF and fail with an opaque parser error.
_UNRESOLVED_TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------
def materialize_bngl_from_template(
    state: str, paths: WorkspacePaths, config: FluBNFConfig,
    *, force: bool = False,
) -> Path:
    """Write the per-state .bngl from the configured template.

    For the default `sir_piecewise` model this is a plain state-name
    substitution of the legacy template. For `sirs_logistic` it uses the SIRS
    template and additionally substitutes the per-state structural tokens
    ({{POP}}, {{TC1..3}}, {{SW}}, {{OMEGA}}).
    """
    out = paths.bngl_file(state)
    if out.exists() and not force:
        return out

    if config.model.model_type == "sirs_logistic":
        raw = Path(config.template_bngl_sirs).read_text()
        substituted = _substitute_sirs_tokens(
            raw.replace(config.template_state, state), state, config,
        )
    else:
        raw = Path(config.template_bngl).read_text()
        substituted = raw.replace(config.template_state, state)

    leftover = _UNRESOLVED_TOKEN_RE.findall(substituted)
    if leftover:
        raise ValueError(
            f"unresolved template token(s) {sorted(set(leftover))} for {state} "
            f"in {config.model.model_type} template"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(substituted, newline="\n")
    log.info("Wrote %s", out)
    return out


def _substitute_sirs_tokens(
    text: str, state: str, config: FluBNFConfig,
) -> str:
    """Fill {{POP}}, {{TC1}}, {{TC2}}, {{TC3}}, {{SW}}, {{OMEGA}}.

    Population comes from locations.csv; centers/width/omega from
    config.model. The number of declared centers in the template is fixed at
    3; transitions beyond what a given fit uses simply leave their tc_k
    declared-but-unreferenced, which BNGL tolerates.
    """
    locs = load_locations(config.locations_csv)
    info = locs.get(state)
    if info is None:
        raise KeyError(f"no population for {state} in {config.locations_csv}")
    centers = list(config.model.transition_centers)
    # Pad to 3 so the template's tc1..tc3 always resolve, even if the config
    # lists fewer (extra centers are harmless if unreferenced by beta()).
    while len(centers) < 3:
        centers.append(centers[-1] if centers else 0.0)

    repl = {
        "{{POP}}": str(int(info.population)),
        "{{TC1}}": _fmt(centers[0]),
        "{{TC2}}": _fmt(centers[1]),
        "{{TC3}}": _fmt(centers[2]),
        "{{SW}}": _fmt(config.model.transition_width),
        "{{OMEGA}}": _fmt(config.model.omega_fixed),
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def _fmt(x: float) -> str:
    """Render a float without a trailing .0 when it's integral (cleaner BNGL)."""
    f = float(x)
    return str(int(f)) if f.is_integer() else repr(f)


def materialize_all(
    states: Iterable[str], paths: WorkspacePaths, config: FluBNFConfig,
    *, force: bool = False,
) -> list[Path]:
    return [
        materialize_bngl_from_template(s, paths, config, force=force)
        for s in states
    ]


# ---------------------------------------------------------------------------
# Parameter block
# ---------------------------------------------------------------------------
_PARAM_BLOCK_START = re.compile(r"^\s*begin\s+parameters")
_PARAM_BLOCK_END = re.compile(r"^\s*end\s+parameters")


def read_parameters(bngl_path: Path) -> list[str]:
    """Return short parameter names (e.g. ['b0', 't0', 'mult', ...])."""
    inside = False
    names: list[str] = []
    for line in bngl_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _PARAM_BLOCK_START.match(stripped):
            inside = True
            continue
        if _PARAM_BLOCK_END.match(stripped):
            inside = False
            continue
        if not inside:
            continue
        # Skip the legacy "###..." separator lines.
        if stripped.startswith("###"):
            continue
        first = stripped.split()[0]
        names.append(first)
    return names


def add_parameters(bngl_path: Path, params: Iterable[str]) -> list[str]:
    """Add `<short> <short>__FREE` lines inside the parameters block.

    Returns the list of parameters that were actually added (the new ones).
    """
    lines = bngl_path.read_text().splitlines(keepends=True)
    existing = set(read_parameters(bngl_path))
    to_add = [p for p in params if p not in existing]
    if not to_add:
        return []

    out: list[str] = []
    for line in lines:
        if _PARAM_BLOCK_END.match(line.strip()):
            for p in to_add:
                out.append(f"{p} {p}__FREE\n")
        out.append(line)
    bngl_path.write_text("".join(out), newline="\n")
    return to_add


# ---------------------------------------------------------------------------
# beta() function
# ---------------------------------------------------------------------------
def build_piecewise_beta(n_steps: int) -> str:
    """Construct the nested-if BNGL expression for a K-step piecewise beta.

    For K = 1 (just b0):
        beta()=if(t>=t0,b0,\
            0)

    For K = 2 (b0 then b1):
        beta()=if(t>=t0 && t<t0+t1,b0,\
            if(t>=t0+t1,b1,\
            0))

    For K = 3:
        beta()=if(t>=t0 && t<t0+t1,b0,\
            if(t>=t0+t1 && t<t0+t1+t2,b1,\
            if(t>=t0+t1+t2,b2,\
            0)))
    """
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")
    parts: list[str] = []
    for k in range(n_steps):
        # Lower bound is the sum t0 + t1 + ... + t_k.
        lower = "+".join(f"t{i}" for i in range(k + 1))
        if k == n_steps - 1:
            parts.append(f"if(t>={lower},b{k},")
        else:
            upper = "+".join(f"t{i}" for i in range(k + 2))
            parts.append(f"if(t>={lower} && t<{upper},b{k},")
    closing = ")" * n_steps
    # BNGL needs a backslash at the end of every continued line inside the
    # if(...) — including the line *before* the trailing `0)...)`. Without
    # the backslash the parser hangs.
    sep = "\\\n\t"
    body = sep.join(parts) + sep + f"0{closing}\n"
    return "beta()=" + body


def build_logistic_beta(n_transitions: int) -> str:
    """Construct a smooth sum-of-logistics BNGL beta() on a SINGLE line.

        beta(t) = b0 + db1/(1+exp(-(t-tc1)/sw))
                     + db2/(1+exp(-(t-tc2)/sw)) + ...

    This is the smooth replacement for `build_piecewise_beta`'s hard nested-if
    step. `n_transitions` (>=1) is the transition count — the same integer the
    decision layer carries as `n_steps`. Each transition contributes ONE free
    amplitude `db_k`; the centers `tc_k` and shared width `sw` are FIXED
    parameters (declared in the SIRS template), so each extra transition costs
    one free parameter instead of three.

    Returned as a single balanced line so `set_beta_function` (which detects
    the beta block by paren-balance) replaces it cleanly, and so no helper
    sub-functions or expression-valued derived parameters are needed — both of
    which the materialization plumbing cannot emit.

    For n_transitions = 1:
        beta()=b0 + db1/(1+exp(-(t-tc1)/sw))
    For n_transitions = 2:
        beta()=b0 + db1/(1+exp(-(t-tc1)/sw)) + db2/(1+exp(-(t-tc2)/sw))
    """
    if n_transitions < 1:
        raise ValueError("n_transitions must be >= 1")
    terms = ["b0"]
    for k in range(1, n_transitions + 1):
        terms.append(f"db{k}/(1+exp(-(t-tc{k})/sw))")
    return "beta()=" + " + ".join(terms) + "\n"


_BETA_START_RE = re.compile(r"^\s*beta\(\)\s*=")


def set_beta_function(bngl_path: Path, beta_expr: str) -> None:
    """Replace the existing `beta()=...` block with `beta_expr`.

    The legacy BNGL `beta()` is written as a multi-line if(...) terminated by
    a line containing `0)...)`. We detect that by counting opening `if(` vs
    closing `)` until balanced inside the beta block.
    """
    lines = bngl_path.read_text().splitlines(keepends=True)
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        line = lines[i]
        if not replaced and _BETA_START_RE.match(line):
            # Consume until parentheses balance.
            depth = 0
            j = i
            while j < len(lines):
                depth += lines[j].count("(") - lines[j].count(")")
                j += 1
                if depth <= 0:
                    break
            new = beta_expr if beta_expr.endswith("\n") else beta_expr + "\n"
            out.append(new)
            i = j
            replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        raise ValueError(f"No beta() function found in {bngl_path}")
    bngl_path.write_text("".join(out), newline="\n")


# ---------------------------------------------------------------------------
# Simulation actions
# ---------------------------------------------------------------------------
def set_simulation_window(
    bngl_path: Path, t_start: float, t_end: float, n_steps: int,
) -> None:
    """Update t_start/t_end/n_steps inside `simulate({...})` in the actions
    block."""
    lines = bngl_path.read_text().splitlines(keepends=True)
    inside = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("begin actions"):
            inside = True
        elif stripped.startswith("end actions"):
            inside = False
        if inside and "simulate(" in line:
            line = re.sub(r"t_start=>[^,}\s]+", f"t_start=>{t_start}", line)
            line = re.sub(r"t_end=>[^,}\s]+", f"t_end=>{t_end}", line)
            line = re.sub(r"n_steps=>[^,}\s]+", f"n_steps=>{n_steps}", line)
        out.append(line)
    bngl_path.write_text("".join(out), newline="\n")
