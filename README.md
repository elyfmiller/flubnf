# FluBNF

[![tests](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml/badge.svg)](https://github.com/elyfmiller/flubnf/actions/workflows/tests.yml)

FluBNF is an operations console for forecasting weekly influenza hospital
admissions in all 52 US jurisdictions, in the
[CDC FluSight](https://github.com/cdcepi/FluSight-forecast-hub) format. It
runs the models, scores them against the official baseline, replays whole
seasons on point-in-time data, and writes the submission files and reports
for a FluSight week.

## The models

The shipped forecast is an equal-weight, never-fitted 50/50 blend of two
members that fail in different regimes:

* **PF-SIHRS**, the mechanistic member: an SIHRS compartmental model
  (susceptible, infected, hospitalized, recovered, with waning immunity and
  seasonal transmission) written in [BNGL](https://bionetgen.org). A
  sequential particle filter carries 10,000 candidate epidemics per state,
  reweighting them each week against the newest admissions data; fitting a
  state-season takes seconds, via a fork of
  [PyBNF](https://github.com/lanl/PyBNF) with
  [bngsim](https://github.com/lanl/bngsim) integrating the model in-process.
* **The calendar analogue**, the empirical member: it scales each state's
  latest observation by growth ratios drawn from prior seasons at the same
  point in the calendar, pooled across states. No epidemiology, no fitted
  parameters, and hard to beat when a season behaves like past seasons.

The mechanistic member can respond to turning points the analogue
structurally cannot anticipate (it carried the clean 2024-25 A-wave),
though turn-week interval coverage remains the system's stated weakness;
the analogue holds the middle horizons and stays anchored when
a season behaves unusually. Forecasts are full predictive distributions at
the 23 FluSight quantile levels, horizons 0-3 weeks.

## Performance

Three seasons replayed at full grid (52 jurisdictions, 3 replicates),
strictly on vintage data: the models see only the hub's archived data
snapshot for each forecast date. (For seven of the 76 replayed weeks that
snapshot diverges from what was public by the submission deadline, and the
replay scores the members' internal forecasts rather than the floored,
rounded submission files the live console writes; both effects are
measured and recorded in the seal caveats of
[docs/RELEASE-1.0.md](docs/RELEASE-1.0.md).) Scores are weighted interval score relative to the CDC
FluSight-baseline (below 1.000 beats the baseline), computed as a ratio of
WIS sums over the cells the model and the baseline share; the CDC dashboard
reports a different, pairwise scaled relative WIS, so figures here are not
comparable with figures there. The analogue member's donor pool excludes
season 2021-22 (the shipped configuration). The comparator column
is the official FluSight multi-team ensemble, scored on exactly the same
cells through the same scorer.

| season | FluBNF ensemble | FluSight ensemble | scored cells |
|---|---|---|---|
| 2023-24 | 0.813 | 0.741 | 6,063 |
| 2024-25 | 0.618 | 0.663 | 4,922 |
| 2025-26 | 0.683 | 0.684 | 4,475 |
| pooled | **0.678** | 0.685 | 15,460 |

The ensemble beat the baseline in every season, and is level with the
official FluSight ensemble overall; the pooled gap is not statistically
separable from zero. These are
self-computed retrospective replays, not real-time submissions, and three
seasons is every vintage-true season the hub's archive can support.

One reproduction caveat: an analogue calendar fix committed after the
seal (commit `52cc22f`, 2026-08-26) changes exactly one replayed week, so
a replay on current code reproduces the 2023-24 and 2024-25 rows exactly
but yields 0.681 / 0.677 for the 2025-26 and pooled figures rather than
the sealed 0.683 / 0.678; reproducing the printed values bit-exactly
requires the pre-fix code state (commit `9b0ef26`). The measured deltas
are in the replication note of the same record.

A second, larger caveat, recorded 2026-09-06: the sealed fits ran a
particle-filter kernel whose parameter jitter acted in raw parameter space
on log-uniform priors, an undeclared behaviour that widened the forecast
bands and happened to score. The production engine now runs the
contract-correct kernel, with its scale chosen by a pre-registered sweep
(jitter 0.15). Replayed on the identical 15,460 cells it scores 0.723
pooled (0.835 / 0.716 / 0.661 by season) against the sealed 0.678; the
corrected kernel at the sealed scale scored 0.735. The gap is disclosed
here rather than hidden by keeping the accidental behaviour, and the
sealed table stands as the record of the sealed engine until the three
seasons are resealed on the production engine. The
full validation record - methodology, pre-registered gates, the
independent replication, and everything that was tested and did not ship -
is in [docs/RELEASE-1.0.md](docs/RELEASE-1.0.md) and on the console's
Methods page.

## The app

The console (`flubnf app`) is organized around the FluSight week:

* **Data** - pull the hub, confirm the NHSN feed is current, and pass the
  integrity audit (vintage gaps, NaN policy, join checks).
* **Forecast** - pick the forecast date and run the members; the full
  52-jurisdiction grid with 3 replicates completes well inside a working
  day on a laptop.
* **Output** - the validated hubverse submission CSVs and a weekly HTML
  report: a US map with per-state quantile-fan drill-downs.

Beyond the weekly loop:

* **Retrospectives** replay a whole season on vintage data, with pause and
  resume; an interrupted replay refits only the cells that never ran.
* The **season playback player** steps through any stored retrospective
  week by week - member fans, the ensemble, settled truth, the CDC's own
  submitted comparators, running relWIS - and exports as one
  self-contained HTML file.
* **Reproducibility is structural**: every run derives its RNG seeds from
  `(location, date, replicate)`, leases an exclusive workroot, and is
  recorded in a ledger with the spec and versions needed to re-execute it.
* Four color themes with high-contrast and red-green-safe modifiers.

## Install

A source clone is the supported installation (the console needs a FluSight
hub clone, BioNetGen, and an engine venv, not just a wheel; `pip install .`
works for using `flubnf` as a library).

**macOS** - one line, or double-click `FluBNF.app` / `FluBNF.command` from
a clone; the first run sets everything up and opens the console (the
bundle is unsigned: first launch is right-click, then Open):

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
```

**Linux**:

```bash
git clone https://github.com/elyfmiller/flubnf && cd flubnf
./setup.sh
.venv/bin/flubnf app
```

**Windows (experimental)** - install Git and a Python (Anaconda with
untouched defaults is found automatically, nothing added to PATH;
python.org 3.11+ with "Add python.exe to PATH" ticked also works), clone
outside `Documents` (`%LOCALAPPDATA%\FluBNF\flubnf` is the suggested
spot), and double-click `FluBNF.bat`, which offers the full first-time
setup. Cloning
outside `Documents` avoids Microsoft Defender's Controlled Folder Access
(shipped off, but common on managed machines), which silently blocks git,
python, and perl there. Details: [docs/WINDOWS.md](docs/WINDOWS.md).

External components resolve via `flubnf/settings.py`, each overridable by
environment variable; check any machine with
`python -c "from flubnf.settings import check; check()"`:

| variable | points at |
|---|---|
| `FLUBNF_HUB` | a clone of `cdcepi/FluSight-forecast-hub` |
| `FLUBNF_BNG` | BioNetGen's `BNG2.pl` |
| `FLUBNF_PY_ENGINE` | python of the engine venv (`pybnf` + `bngsim`) |
| `FLUBNF_PYBNF` | a PyBNF checkout providing `fit_type = pf` |

### Getting the particle filter engine

Everything above needs no GitHub login: this repository and the FluSight hub
are both public. The particle filter engine is the one exception, because it
needs a PyBNF fork that is private. **The console runs without it**, analogue
forecasts only, so this never blocks an install.

**The shortest route needs no GitHub account at all: one small file.** The
lab hands out `pybnf-pf-<sha>.tar.gz`, about 130 KB, cut with
`scripts/cut_engine_archive.sh`. Save it in your Downloads folder exactly as
it is and open the app; setup finds it, unpacks it where it belongs, and
installs the engine, printing the version stamp it carries. A `git bundle`
of the fork (about 140 MB, made with
`git bundle create pybnf.bundle feature/particle-filter`) works the same way
for anyone who prefers a real clone. Both are found in any of these places,
on both platforms:

* the FluBNF folder itself, or the folder beside it,
* `~/Downloads`, `~/Desktop` or `~/Documents` (on Windows, the same three
  folders under your user profile).

Then double-click `FluBNF.command` (macOS) or `FluBNF.bat` (Windows), or run
`./setup_engine.sh`. The console says which file it used and, when it finds
none, exactly which folders it looked in. `FLUBNF_PYBNF_BUNDLE` points at one
kept somewhere else. Because it is one file on a shared drive or a USB stick,
this is also the only route that works with no administrator rights or no
network at all.

**A GitHub account password will not work at a git prompt.** If you would
rather go through GitHub than use a bundle: GitHub retired password
authentication in 2021, so being a collaborator on the fork is not by itself
enough to clone it in a terminal. Pick one of these instead, in increasing
order of effort:

**Before any of them, check the invitation was accepted.** A collaborator
invitation has to be accepted before the repository exists for you at all.
Until then it is invisible everywhere, in Desktop's repository list, in search,
and to git, which is indistinguishable from having no access. Signing in with
the right account is not the same as having accepted. The owner sees pending
invites at `.../PyBNF-Private/settings/access` with an **Invited** badge; the
invitee accepts from their email or from <https://github.com/notifications>.

1. **GitHub Desktop. No terminal, no Homebrew, nothing to install beyond
   Desktop itself.** File > Clone repository, then **the URL tab**, and paste
   `elyfmiller/PyBNF-Private`. Use the URL tab even though the GitHub.com tab
   looks like the right one: that list shows repositories you *own* plus your
   organisations', so a private repo you are only a **collaborator** on is
   usually missing from it. Not finding it in the list does not mean you lack
   access. Set the local path to `~/Documents/GitHub/PyBNF-Private`, which is
   where setup looks, then reopen `FluBNF.command`. Signing in to Desktop
   *without* cloning does not help, because Desktop does not share its login
   with terminal git.
2. **GitHub CLI.** Two steps, not one: `gh` is not installed by default, so
   `gh auth login` on a fresh machine returns `command not found`.
   ```bash
   brew install gh && gh auth login
   ```
   **No Homebrew?** You do not need it, and you do not need to install it.
   Download the macOS `.pkg` from <https://github.com/cli/cli/releases> (under
   Assets, the file ending `_macOS_universal.pkg`) and double-click it; it is a
   normal installer. Then run `gh auth login`. On Windows,
   `winget install --id GitHub.cli`. Then re-run `./setup_engine.sh`.
   If installing anything at all is a problem on a managed laptop, use option 1
   or the offline bundle below, neither of which needs admin rights.
3. **SSH key**, if you already have one registered with GitHub:
   ```bash
   FLUBNF_PYBNF_REMOTE=git@github.com:elyfmiller/PyBNF-Private.git ./setup_engine.sh
   ```

Already tried and still stuck? macOS caches the first answer it gets, so one
wrong entry keeps failing silently. Clear it, then use option 1 or 2:

```bash
printf 'protocol=https\nhost=github.com\n\n' | git credential-osxkeychain erase
```

**Making and handing over the bundle.** The bundle is around 140 MB, too large
to email, so use a shared drive, a USB stick, or a release asset on the fork.
Nothing about it expires and nothing in it is secret to the lab, but it is the
private fork's whole history, so treat it the way you treat the fork.

Setup clones from it for you. To do it by hand instead:

```bash
git clone -b feature/particle-filter pybnf.bundle ~/Documents/GitHub/PyBNF-Private
```

Two failures are worth knowing apart. A file that is not a bundle at all (a
browser that saved an error page under the name) is caught by
`git bundle verify`. A bundle whose copy did not finish is **not**: verify
accepts it and the clone then dies with `early EOF` or `index-pack died`.
Setup names both cases; the first needs a different file, the second needs the
same file copied again.

## Layout

```
flubnf/          the science package: model templates, data resolution,
                 fitting, quantiles, WIS, baseline construction, priors
app/             the console: FastAPI UI, run ledger, engines, ensemble,
                 submissions, reports; app/tests/ is its suite
scripts/         operational runners (not packaged into the wheel)
docs/            release record, model provenance, the student install
                 guide, site and Windows notes
tests/           the science-package suite
data/            small tracked inputs
model-metadata/  the hubverse model card
```

Generated and local-only, never in the repository: `app/state/` (ledger,
retrospectives, the sealed three-season record), `site/`, `workspaces/`,
`research/`.

## Citing

See [CITATION.cff](CITATION.cff), and cite the version (v1.0.0) so the
claim cited is the claim that was validated.

## License

MIT, see [LICENSE](LICENSE).
