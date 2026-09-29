"""The season report download: the season page, as one file.

render_season_report renders retro_season.html (and base.html) in export
mode from the same context the console's page uses (routes/retro.py
season_page_context), with every stored week's playback payload and map
embedded, so the file shows what the Retrospective tab shows: the season
scores, the season player with its forecast detail (open first) and
categorical map, the cumulative chart and the per-state table. It needs
no server and no network (templating.inline_static writes every
stylesheet, script, font and mark into the page).

app/core/report_season.build_season_report caches the result beside the
season's weeks. A build can take a while (the season scored first, then
every week), so the page's Download report and Show in folder run it as
a background job (report_job) and show its progress; the download itself
then serves the finished file.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

#: progress(phase, done, total): what a build is doing; done and total are
#: None while it has no honest denominator
_NOOP = lambda phase, done=None, total=None: None   # noqa: E731


def season_map_swap(root: Path, asof: str) -> dict:
    """One stored week's map as the swap payload the page applies per frame
    ({default, models: {model: {states}}, states}), as
    /api/retro/{season}/mapswap/{asof} serves it."""
    from app.core.usmap import state_swap_payload
    from app.ui.routes.retro import (_retro_map_models,
                                     _week_map_cards_by_model)
    by_model = _week_map_cards_by_model(root, asof)
    order = _retro_map_models(by_model)
    models = {m: {"states": state_swap_payload(by_model[m])} for m in order}
    default = order[0] if order else ""
    return {"default": default, "models": models,
            "states": (models[default]["states"] if default
                       else state_swap_payload({}))}


def _settle_scores(root: Path, season: str) -> str:
    """Score the season first when the page would wait for it (the job the
    page starts, run to the end here); the failure, else ""."""
    from app.ui import retro_prep
    if retro_prep._results_pending(root):
        job = retro_prep._ensure_results_job(root, season)
        job["done"].wait()
        return str(job.get("error") or "")
    covered = retro_prep._job_covered(root)
    if (covered and covered.get("error")
            and not retro_prep._scores_scoreable_fast(root)):
        return str(covered["error"])
    return ""


def render_season_report(root: Path, season: str, archive: str = "",
                         progress=None) -> str:
    """The season page in export mode, as one self-contained HTML string.
    `progress(phase, done, total)` hears each step."""
    from app.core import playback
    from app.ui.routes.retro import season_page_context
    from app.ui.templating import templates
    progress = progress or _NOOP
    root = Path(root)
    progress("Scoring the season")
    score_error = _settle_scores(root, season)
    progress("Reading the season")
    ctx = season_page_context(root, season, archive, score_error=score_error)
    # the facts and settings of THIS tree (the page's live lookup goes by
    # the season's name), frozen as a snapshot: never a live replay
    from app.ui.retro_seasons import _archive_progress
    ctx["prog"] = _archive_progress(root, season)
    stored = list(ctx["weeks"])
    embed = {"payloads": {}, "maps": {}}
    for i, w in enumerate(stored):
        progress("Adding the weeks", i, len(stored))
        embed["payloads"][w] = playback.build_week(root, season, w)
        # the models alone: the API's extra `states` repeats the first
        embed["maps"][w] = {"models": season_map_swap(root, w)["models"]}
    progress("Writing the file")
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    ctx.update(export=True,
               embed_json=json.dumps(embed, separators=(",", ":"))
               .replace("</", "<\\/"),
               exported_at=time.strftime("%Y-%m-%d %H:%M"))
    return templates.env.get_template("retro_season.html").render(ctx)


# ------------------------------------------------ the page's build job
#: one build job per season tree: {root: job}; a click while one runs joins
#: it
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()


def _size_h(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{max(1, round(n / 1e3))} kB"


def job_status(root: Path) -> dict:
    """The build job of this tree as the page polls it: state (idle,
    running, done, error), phase, done/total (weeks, when counted), and
    when done the file's name and size; when failed, why."""
    with _JOBS_LOCK:
        job = _JOBS.get(str(root))
        if not job:
            return {"state": "idle"}
        return {k: v for k, v in job.items() if k != "thread"}


def report_job(root: Path, season: str, archive: str = "", build: str = "",
               versions: dict | None = None) -> dict:
    """Start (or join) the build of this tree's season report in the
    background; its status (job_status). A fresh cached report finishes at
    once."""
    from app.core import report_season
    root = Path(root)
    key = str(root)
    with _JOBS_LOCK:
        job = _JOBS.get(key)
        if job and job["state"] == "running":
            return {k: v for k, v in job.items() if k != "thread"}
        job = {"state": "running", "phase": "Starting", "done": None,
               "total": None, "error": "", "name": "", "size_h": "",
               "t0": time.time()}
        _JOBS[key] = job

    def progress(phase, done=None, total=None):
        job.update(phase=phase, done=done, total=total)

    def _run():
        try:
            p = report_season.build_season_report(
                root, season, archive=archive, build=build,
                versions=versions, progress=progress)
            job.update(state="done", phase="Ready", name=p.name,
                       size_h=_size_h(p.stat().st_size),
                       done=None, total=None)
        except Exception as e:
            # the page shows why; the console's log keeps the trace
            traceback.print_exc()
            job.update(state="error", done=None, total=None,
                       error=f"{type(e).__name__}: {str(e)[:300]}")

    threading.Thread(target=_run, daemon=True,
                     name=f"flubnf-report-{season}").start()
    return job_status(root)
