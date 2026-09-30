"""Runs compared, downloaded and given the Oracle step: run_files,
diff_runs, model_zip, run_zip, and the Oracle step on an unedited Oracle
SIHRS start. app/core/sandbox.py is the facade; every name here imports
from it too.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import zipfile
from pathlib import Path

import numpy as np

from app.core import sandbox as _sb  # TRAJ_ZIP_MAX: patched there
from app.core.engines import pf as pf_engine
from app.core.sandbox import (
    MODEL_FILE,
    NAME_RE,
    REQUIRED,
    SHIPPED,
    SHIPPED_DATASET,
    SOURCE_FILE,
    SandboxError,
    _stamp,
    model_dir,
    read_info,
    run_dir,
    shipped_state,
)
from app.core.sandbox_results import results, summary_rows

# ------------------------------------------------ compare, export, clean up
# A run's three files are its own copies in the cell folder (m.bngl, the
# <suffix>.exp and priors.conf; runs made before priors.conf was copied
# fall back to pf.conf's prior lines). Downloads are built in memory and
# carry no absolute path: pf.conf's paths are rewritten relative to the
# cell, as the zip lays it out.


TRAJ_ZIP_MAX = 2 * 1024 * 1024
#: settings a comparison lists when they differ
RUN_SETTINGS = ("particles", "jitter", "forecast_weeks", "seed", "cumulative",
                "suffix", "obs_col", "n_obs")


def _run_meta(run_id: str) -> tuple:
    d = run_dir(run_id)
    return d, json.loads((d / "meta.json").read_text(encoding="utf-8"))


def run_files(run_id: str) -> dict:
    """The three files as the run used them: {"model.bngl", "data.exp",
    "priors.conf"} (a missing one reads '')."""
    d, meta = _run_meta(run_id)
    cell = d / f"{meta['model']}_r0"

    def read(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    priors = read(cell / "priors.conf")
    if not priors:
        conf = read(cell / "pf.conf").splitlines()
        priors = "".join(l + "\n" for l in conf
                         if l.split("=", 1)[0].strip().endswith("_var"))
    return {"model.bngl": read(cell / "m.bngl"),
            "data.exp": read(cell / f"{meta.get('suffix', '')}.exp"),
            "priors.conf": priors}


def diff_runs(a: str, b: str, max_lines: int = 400) -> dict:
    """What changed from run a to run b: a unified diff of each of the
    three files (empty when identical) and the run settings that differ,
    as {"files": [{"name", "diff", "same"}], "settings": [{"key", "a",
    "b"}], "data_source": {"a", "b"} when the data came from elsewhere}."""
    fa, fb = run_files(a), run_files(b)
    _, ma = _run_meta(a)
    _, mb = _run_meta(b)
    files = []
    for f in REQUIRED:
        lines = list(difflib.unified_diff(
            fa[f].splitlines(), fb[f].splitlines(), fromfile=f"{a}/{f}",
            tofile=f"{b}/{f}", n=2, lineterm=""))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... {len(lines) - max_lines} more lines"]
        files.append({"name": f, "diff": "\n".join(lines),
                      "same": fa[f] == fb[f]})
    settings = [{"key": k, "a": ma.get(k), "b": mb.get(k)} for k in RUN_SETTINGS
                if ma.get(k) != mb.get(k)]
    out = {"a": a, "b": b, "files": files, "settings": settings}

    def src(m):
        s = m.get("source") or {}
        return {k: s.get(k) for k in ("location", "asof", "start", "end")} if s else {}
    if src(ma) != src(mb):
        out["data_source"] = {"a": src(ma), "b": src(mb)}
    return out


def _zip(entries: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in entries:
            info = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data if isinstance(data, bytes)
                       else str(data).encode("utf-8"))
    return buf.getvalue()


def model_zip(name: str) -> bytes:
    """The model folder as a zip: its three files and the model.json and
    data.source.json sidecars, under <name>/."""
    d = model_dir(name)
    return _zip([(f"{name}/{f}", (d / f).read_bytes())
                 for f in REQUIRED + (MODEL_FILE, SOURCE_FILE)
                 if (d / f).is_file()])


def _relative_conf(text: str, cell: Path) -> str:
    """pf.conf with the cell's and BNG2.pl's absolute paths removed."""
    out = []
    for line in text.splitlines():
        if line.split("=", 1)[0].strip() == "bng_command":
            line = "bng_command = BNG2.pl"
        else:
            for p in sorted({pf_engine.conf_safe_path(cell), str(cell)},
                            key=len, reverse=True):
                line = line.replace(p + "/", "").replace(p, ".")
        out.append(line)
    return "\n".join(out) + "\n"


def run_zip(run_id: str) -> bytes:
    """A run as a zip under <run_id>/: meta.json, pf.conf (paths made
    relative), the three files, the engine's parameter sample and ESS
    record, summary.csv (the 10/50/90% trajectory per week beside the
    observed count), the Oracle step's summary when one was made, and the
    raw trajectory only when it is small (TRAJ_ZIP_MAX)."""
    d, meta = _run_meta(run_id)
    cell = d / f"{meta['model']}_r0"
    files = run_files(run_id)
    entries = [(f"{run_id}/meta.json", (d / "meta.json").read_bytes())]
    if (cell / "pf.conf").is_file():
        entries.append((f"{run_id}/pf.conf", _relative_conf(
            (cell / "pf.conf").read_text(encoding="utf-8", errors="replace"),
            cell)))
    entries += [(f"{run_id}/m.bngl", files["model.bngl"]),
                (f"{run_id}/{meta.get('suffix') or 'data'}.exp", files["data.exp"]),
                (f"{run_id}/priors.conf", files["priors.conf"])]
    pf_out = cell / "out" / "Results" / "PF"
    runs = pf_out / "Runs"
    for p in sorted(runs.glob("params_*.txt")) if runs.is_dir() else []:
        entries.append((f"{run_id}/{p.name}", p.read_bytes()))
    if (pf_out / "ess_0.txt").is_file():
        entries.append((f"{run_id}/ess_0.txt", (pf_out / "ess_0.txt").read_bytes()))
    res = results(d)
    if res.get("traj"):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["column", "t", "date", "q10", "q50", "q90",
                    meta.get("obs_col") or "observed"])
        w.writerows(summary_rows(res))
        entries.append((f"{run_id}/summary.csv", buf.getvalue()))
    for p in sorted(runs.glob("*traj_noise*")) if runs.is_dir() else []:
        if p.stat().st_size <= _sb.TRAJ_ZIP_MAX:
            entries.append((f"{run_id}/{p.name}", p.read_bytes()))
    if (d / ORACLE_FILE).is_file():
        entries.append((f"{run_id}/{ORACLE_FILE}", (d / ORACLE_FILE).read_bytes()))
    return _zip(entries)



# ------------------------------------------- the Oracle step (sandbox only)
# On a finished run of an unedited Oracle SIHRS start (hub origin, four
# forecast weeks), the production Oracle step (app/core/oracle.apply_week
# on pf_engine.collect's samples) is applied inside the run folder and its
# quantiles shown beside the plain filter's. It writes only under the run
# folder: never the ledger, the site, the archive or model-output.

ORACLE_FILE = "oracle_step.json"
ORACLE_DIR = "oracle"
#: the quantile levels the page shows (of the 23 FluSight levels)
ORACLE_LEVELS = (0.025, 0.25, 0.5, 0.75, 0.975)


def oracle_default_w() -> float:
    """The production blend weight (flubnf.oracle.W_PRODUCTION)."""
    from flubnf import oracle as OR
    return float(OR.W_PRODUCTION)


def oracle_gate(run_id: str) -> dict:
    """Whether the Oracle step may run on this run: {"ok", "reason"}.
    It may when the run finished, has four forecast weeks, is of a model
    started from the hub's Oracle SIHRS filter, and neither the run's
    files nor the model's differ from the creation digests."""
    try:
        _, meta = _run_meta(run_id)
    except SandboxError as e:
        return {"ok": False, "reason": str(e)}
    name = str(meta.get("model", ""))
    info = read_info(name) if NAME_RE.match(name) else {}
    origin = meta.get("origin") or info.get("origin")
    if SHIPPED_DATASET in (origin, info.get("origin")):
        return {"ok": False, "reason": "The Oracle step reads the hub's vintage "
                "and donor bank; this model starts from a dataset."}
    if origin != SHIPPED or info.get("origin") != SHIPPED:
        return {"ok": False, "reason": "Only runs of a model started from the "
                "Oracle SIHRS filter can take the Oracle step."}
    if meta.get("status") != "ok":
        return {"ok": False, "reason": "The run has not finished cleanly."}
    if int(meta.get("forecast_weeks", 0) or 0) != 4:
        return {"ok": False, "reason": "The Oracle step needs a run with 4 "
                "forecast weeks, as production makes."}
    dig = info.get("digests") or {}
    ran = meta.get("digests") or {}
    edited = [f for f in REQUIRED if ran.get(f) != dig.get(f)]
    if edited:
        return {"ok": False, "reason": "This run's " + ", ".join(edited)
                + (" differs" if len(edited) == 1 else " differ")
                + " from the Oracle SIHRS start as created."}
    st = shipped_state(name)
    if not st["intact"]:
        return {"ok": False, "reason": "The model was edited after it was "
                "created (" + ", ".join(st["changed"]) + "), so it is no "
                "longer the Oracle SIHRS start."}
    if not (info.get("location") and info.get("forecast_date")):
        return {"ok": False, "reason": "model.json does not record the "
                "location and forecast date."}
    return {"ok": True, "reason": ""}


def _levels(xs) -> list | None:
    v = np.asarray(xs, float)
    v = v[np.isfinite(v)]
    if not v.size:
        return None
    return [float(q) for q in np.quantile(v, ORACLE_LEVELS)]


def oracle_step(run_id: str, w: float | None = None) -> dict:
    """Apply the production Oracle step to one run's forecast samples;
    the summary is written to <run>/oracle_step.json (apply_week's own
    oracle.json and donor bank go to <run>/oracle/). Refused in words
    when oracle_gate refuses or w is outside 0..1."""
    from app.core import horizons as hz
    from app.core import oracle as oracle_mod
    gate = oracle_gate(run_id)
    if not gate["ok"]:
        raise SandboxError(gate["reason"])
    w = oracle_default_w() if w is None else float(w)
    if not (0.0 <= w <= 1.0):
        raise SandboxError(f"the blend weight w must be between 0 and 1, "
                           f"not {w:g}")
    d, meta = _run_meta(run_id)
    info = read_info(meta["model"])
    loc, fd = str(info["location"]), str(info["forecast_date"])
    samples = pf_engine.collect(d)
    if loc not in samples:
        raise SandboxError(f"the fit left no forecast samples for {loc}")
    samples = {loc: samples[loc]}
    member, prov = oracle_mod.apply_week(samples, fd, d / ORACLE_DIR, w=w)
    table = {r["canonical"]: r["target_end_date"]
             for r in prov["quantiles"]["horizons"]["table"]}
    ent = prov["locations"].get(loc, {})
    rows = [{"horizon": h, "target_end_date": table.get(h, ""),
             "filter": _levels(samples[loc][h]),
             "oracle": _levels(member[loc][h])} for h in hz.HORIZONS]
    out = {"run_id": run_id, "location": loc, "forecast_date": fd,
           "w": w, "w_production": oracle_default_w(),
           "levels": list(ORACLE_LEVELS), "rows": rows,
           "state": ent.get("state", ""), "active": ent.get("active"),
           "reason": ent.get("reason", ""), "bank": prov["bank"]["label"],
           "reference_date": prov["quantiles"]["horizons"]["reference_date"],
           "label": "sandbox, not a submission", "utc": _stamp()}
    tmp = d / (ORACLE_FILE + ".tmp")
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(d / ORACLE_FILE)
    return out


def read_oracle(run_id: str) -> dict | None:
    """The run's Oracle step summary, or None."""
    try:
        return json.loads(
            (run_dir(run_id) / ORACLE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return None
