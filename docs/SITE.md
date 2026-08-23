# The public site

The site at `site/` is generated from the lab's own state by
`flubnf site build`. It is not written by hand and it is not built in CI.

## Why it is committed

Everything the page shows comes from `app/state/` and the FluSight hub
clone, both of which are gitignored and far too large to track. CI has none
of that data and never will. So the generated page **is** the published
evidence: it is built on the machine that holds the retrospectives,
reviewed as a diff, committed, and pushed. GitHub Actions only takes what
was reviewed and puts it online.

That has one consequence worth remembering: **a push that changes only
source code does not change the site.** Rebuild and commit `site/` to move
the published page.

## The loop

1. **Run a retrospective.** Retrospective tab in the console, or
   `flubnf retro <season>`. Weeks land under `app/state/retro/<season>/`.
   The build discovers seasons by looking for stored weeks, so a new season
   needs no code change. When both `app/state/retro/` and
   `app/state/retro_seal/` hold the same season, the more complete one wins
   and your own run breaks the tie.

2. **Build.**

   ```
   .venv/bin/flubnf site build
   ```

   Takes about twenty seconds against the three sealed seasons, most of
   it scoring. It prints what it wrote, the outlook week it chose, the pooled
   relWIS, and whether the computed scores still match the figures the
   console publishes.

   Useful flags:

   - `--check` — exit non-zero if any computed score disagrees with the
     console. Worth using before you commit.
   - `--season` / `--asof` — pin the home outlook to a specific stored week
     instead of the newest forecast. The default is deliberately *not*
     photogenic: in July the newest week is a quiet summer map, and picking
     a January peak because it looks better is cherry-picking. The override
     exists so that choice, when you make it, is recorded in the payload as
     `outlook.source.pinned`.
   - `--out` — write somewhere other than `site/`.

3. **Review.** Open `site/index.html` — it works from disk, no server
   needed — and read the diff of `site/site.json`. The payload is
   pretty-printed with sorted keys precisely so this diff is readable: it
   shows which numbers moved. `site/index.html` changes with it; the large
   diff there is the same payload embedded so the page works offline.

4. **Commit and push.** `site/plotly.min.js` only changes when the library
   is upgraded. Pushing `main` with anything under `site/` changed triggers
   the `pages` workflow, which re-checks that the payload beside the page
   matches the payload inside it, refuses to publish if any consistency
   check failed, and deploys.

Lab members do not push; the site changes when you push.

## What the build reads

| On the page | Read from |
| --- | --- |
| Outlook map, per-model cards | the newest run bundle covering ≥40 jurisdictions, else the newest stored retrospective week |
| Forecast fans, settled overlays | the same week's playback payload (or the run's `results.json`), with truth after the forecast date |
| Season table, per-member scores | every stored week of every discovered season, rescored here |
| FluSight placements | the `<table class="perf">` in `app/ui/templates/home.html` |
| Methods prose and diagrams | `app/ui/templates/methods.html`, rendered through the console's own Jinja environment |
| Model source | `flubnf/templates/SIHRS_pop_min.bngl` |
| Bibliography | the DOIs in `flubnf/sihrs_priors.py` |

Three of those deserve a note.

**The ensemble score is the shipped one.** A season's `scores.json` is
written by `retro.score_season`, whose `ensemble` column blends with the
frozen LOSO weights — a configuration the lab evaluated and rejected, and
which scores worse (pooled 0.710 against 0.704). Reading it here would put
the rejected ensemble on the page under the shipped ensemble's name, and
nothing would look wrong. The build instead rescores every season from each
week's playback payload, whose `ensemble` block is the equal-weight 50/50
blend. That path reproduces the published record exactly (0.848 / 0.651 /
0.691, pooled 0.704) and `app/tests/test_site_build.py` pins it.

**Placements are harvested, not recomputed.** Ranking against the whole
FluSight field means scoring every submitting team on identical cells —
around 1.6 GB of hub CSVs across three seasons, and a field definition
(which hub-run models count as competitors) that is a lab decision, not a
formula. Those standings live in `home.html` and the build reads them from
there, so you edit one place. A season the table does not cover renders as
"not yet scored against the field" rather than with an invented rank.

**Observations are vintage-true; only the overlay is hindsight.** A
replayed week's playback payload carries settled truth, because the
console's replay viewer exists to show what happened. The site's observed
line and the map's "current" anchor instead come from the vintage archived
on the forecast date, because they describe what the forecast saw. This is
not pedantry: NHSN revises the freshest week upward by a median 4-5%, and
when the vintage rule was applied here it moved one state across a category
cutpoint. Settled values appear on the page as the settled overlay, which
is where hindsight belongs.

## The drift alarm

The console states its performance in prose on several pages. The site
computes it. After every build the payload carries a `consistency` block
comparing the two, season by season, and the page prints the result. If
they ever disagree, the build says so, `--check` fails, the workflow
refuses to deploy, and the page shows the computed figure with a warning.
Nothing silently reshapes itself: a mismatch means either the console's
text or the retrospective on disk has moved, and a human decides which.

## Adding to the page

`app/core/site_build.py` decides what is true; `app/core/site_page.py`
decides how it looks and holds all the markup, CSS and behaviour. Numbers
that change every rebuild belong in the payload; static content belongs in
the page. Anything the state cannot fund must be omitted with a stated
reason — never an empty cell, a dash, or a number the build invented.

## Enabling Pages the first time

In the repository settings, under Pages, set the source to **GitHub
Actions**. The `pages` workflow does the rest.
