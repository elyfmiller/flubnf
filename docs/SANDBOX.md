# The Sandbox: a model of your own, fitted

The Sandbox tab fits a model you write with the same particle filter the
console forecasts with, in its own folder (`sandbox/`, never under version
control). Nothing in it reaches the runs ledger, the retrospectives or a
submission. This page takes a new student from nothing to a fitted model
of their own; the page itself carries the short version under **How the
Sandbox works**.

## 1. Start from something that fits

New model, Start from:

| Start | What it is | Use it when |
|---|---|---|
| `seihr_template` | SEIR plus hospital admissions; every pathogen and population value marked `# EDIT` | a new respiratory pathogen (COVID-19, RSV, ...) |
| `sir_example`, `seir_example` | the smallest epidemics, counted as reported cases | learning the file format |
| `sihrs_example` | the production influenza model for one synthetic state, with seasonal forcing | seasonal influenza |
| `kinetics_example` | A to B, not an epidemic | any count that is the increment of something |
| Blank skeleton | one conversion, three fitted values | writing from scratch |
| Oracle SIHRS filter | the production model, priors and data for one jurisdiction and week | comparing with production |

Every example's `data.exp` was simulated from the model itself at the
values written in its `model.bngl`, with negative-binomial noise, and its
first comment says which values a fit should find. Run one unchanged
first: the fit should find those values.

## 2. The three files

**model.bngl** is the model in BNGL. Time is in weeks and every rate is
per week (a period of d days is the rate 7/d).

- A parameter whose name ends in `__FREE` is **fitted**. The filter draws
  it from its line in `priors.conf`; the value written in `model.bngl` is
  used only by Check and Simulate data. Every other parameter is fixed.
- The observed count must be the weekly **increment** of an accumulator:
  a species no rule consumes, added to by a rule such as
  `I() -> I() + Hadm()  rho*gamma` (it counts each admission without
  moving anyone). A function scales it to what is reported,
  `Hobs() = mult__FREE*H_Cum`. A reporting scale never enters a rule.
- The seed species are the population **one week before the first row of
  data.exp** (the engine starts at `pf_start_time = -1`). N and the
  starting infected set the size of the first weeks' counts.
- The simulate action must name a suffix (`suffix=>"seir"`); the engine
  matches the data file by it.

**data.exp** is a header line, then one row per week: the time in weeks
and the count for the week ending then. A missing week is a gap in the
time column, never a renumbered row.

**priors.conf** has one line per fitted parameter:
`uniform_var = Reff__FREE 0.8 3.0` draws evenly between the numbers,
`loguniform_var = mult__FREE 0.2 5.0` evenly on a log scale (for a value
that could be 0.2 or 5). `pf_cumulative_observable = Hobs` names the
output whose weekly increment is the count. Keep each range to values you
find plausible: particles drawn where the data rule them out are wasted.

## 3. Check, then run

**Check** reads the editor text without fitting. Problems are what would
stop a run; "Worth a look" lists what may run but not as meant. It also
runs the model once at its written values and sets its weekly counts
beside the data: if the two differ tenfold, N, the starting state or the
reporting scale is off, and the fit will start far from the data. No
problems means the model can run, not that it fits.

**Save and run** fits the saved files. The full fit (10,000 particles,
the production setting) gives the estimates, in seconds to minutes; a
quick check (200 particles) only shows that the model runs, and its
numbers are rough.

## 4. Read the result

The first line of Results says, in plain words, whether the fit is sound:

- **The fit looks healthy**: the particles stayed varied at every week.
- **The fit is rough**: they thinned out at some week; ranges may be too
  narrow.
- **The fit collapsed**: nearly every particle became a copy of one or a
  few parameter sets, so the table shows one value where a range should
  be (5%, median and 95% equal) and the band is not an estimate. Run the
  full fit; if it collapsed at the first data row, Check the scale; narrow
  a prior much wider than plausible; raise Jitter to 0.2 or 0.3.

The plot's band should cover most data points. A band that misses the
data is the model, not the filter: check the rates, the fixed values and
the observed output. The table gives each fitted value's median and 5 to
95% range. Engine messages keep the engine's own words.

## 5. Your own data

In the data.exp tab, **Load data** fills it from the FluSight hub (one
jurisdiction, settled or as a past date saw it), from a stored dataset, or
from a CSV you upload (`date,target_group,value[,population]`). Then set
N and the starting state to match the population and the first weeks.

**Simulate data from the model** replaces data.exp with counts drawn from
the model at its written values over the same weeks. Fitting those first
tests a new model and its priors on values you know, before real data.

## 6. Compare, keep, share

Edit and run again, or Duplicate the model under Manage to keep both
versions. Every run keeps its own copy of the three files. **Compare
with** draws another run's band dashed over this one, sets the parameter
tables side by side, and lists every change between the two. **Download
run** is a zip of the inputs, the engine's outputs and `summary.csv` (the
weekly quantiles); **Download model** zips the three files to share.
