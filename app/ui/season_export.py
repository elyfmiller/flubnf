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
season's weeks.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


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


def render_season_report(root: Path, season: str, archive: str = "") -> str:
    """The season page in export mode, as one self-contained HTML string."""
    from app.core import playback
    from app.ui.routes.retro import season_page_context
    from app.ui.templating import templates
    root = Path(root)
    score_error = _settle_scores(root, season)
    ctx = season_page_context(root, season, archive, score_error=score_error)
    # the facts and settings of THIS tree (the page's live lookup goes by
    # the season's name), frozen as a snapshot: never a live replay
    from app.ui.retro_seasons import _archive_progress
    ctx["prog"] = _archive_progress(root, season)
    stored = list(ctx["weeks"])
    embed = {"payloads": {w: playback.build_week(root, season, w)
                          for w in stored},
             # the models alone: the API's extra `states` repeats the first
             "maps": {w: {"models": season_map_swap(root, w)["models"]}
                      for w in stored}}
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    ctx.update(export=True,
               embed_json=json.dumps(embed, separators=(",", ":"))
               .replace("</", "<\\/"),
               exported_at=time.strftime("%Y-%m-%d %H:%M"))
    return templates.env.get_template("retro_season.html").render(ctx)
