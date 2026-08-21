// Shared run quips: one list, two hosts. The forecast page and the
// retrospective page both draw from this file, so a quip added here appears
// in both places and neither list can drift from the other.
//
// House voice: lowercase, no exclamation marks, no emoji; flu, Bayesian
// inference, particle filtering, epidemiology; dry and playful. The last
// block speaks to the retrospective specifically -- a season replayed a week
// at a time, scored later against settled truth.
window.FLUBNF_QUIPS = [
  "teaching 10,000 particles to sneeze responsibly",
  "resampling the unlucky",
  "negotiating with a negative binomial",
  "asking last winter for advice",
  "herding susceptibles",
  "integrating quietly since 1927",
  "jittering, but only a little",
  "waiting for the posterior to settle down",
  "politely declining a degenerate proposal",
  "weighing particles by how well they coughed",
  "asking the prior to loosen its grip",
  "letting the likelihood do the talking",
  "quarantining a few outlier trajectories",
  "rewinding the epidemic to watch it again",
  "convincing beta to stay seasonal",
  "counting hospital beds twice, to be sure",
  "seeding infections at the solstice, as tradition demands",
  "drawing quantiles with a steady hand",
  "burning in, gently",
  "checking whether Rt has recovered",
  "wandering the parameter space, mostly on purpose",
  "shrinking toward the mean, emotionally as well",
  "giving every trajectory a fair cough",
  "propagating uncertainty with confidence",
  "consulting the negative binomial about its variance",
  "asking the particles to form an orderly quantile",
  "estimating how much winter is left",
  "keeping the ensemble members from agreeing too much",
  "resampling with all due ceremony",
  "checking the waning-immunity clock",
  "letting ten thousand epidemics bloom, then pruning",
  "holding the baseline to account",
  "measuring this season against its ancestors",
  "teaching beta to respect the calendar",
  "auditing the attack rate",
  "reweighting optimism by evidence",
  "keeping the vintage data honest",
  "asking each state how its winter is going",
  "updating priors, gently but firmly",
  "asking the effective sample size to stay effective",
  "walking the weekly data in, one saturday at a time",
  "smoothing the epidemic curve without flattering it",
  "granting each particle one more week of relevance",
  "comparing this week to every winter on record",
  "letting the evidence outvote the prior",
  "thinning the herd of implausible epidemics",
  "watching the credible interval breathe",
  "escorting stray trajectories back to the data",
  "renormalizing the weights, as one does",
  "budgeting uncertainty across four horizons",
  // ---- replay voice: the retrospective's own weather ----
  "replaying last winter at one week per breath",
  "marching the calendar forward, saturday by saturday",
  "pretending not to know how this season ended",
  "withholding hindsight from the particles",
  "handing each week only the data it was owed",
  "filing this forecast away to be graded later",
  "resisting the urge to peek at settled truth",
  "asking january what it was thinking",
  "keeping the vintage sealed until the deadline",
  "auditing a winter that has already happened",
  "explaining a plateau to an unconvinced filter",
  "putting the peak week back where it belongs",
  "reconstructing a winter from weekly fragments",
  "measuring regret one horizon at a time",
  "letting the season take its own sweet time",
  "declining to remember what happens in march",
  "scoring nothing yet, on principle"
];

// Rotate quips into an element. Returns a small controller so a paused run
// can hold its quip still: a rotating line beside a frozen bar would read as
// progress that is not happening.
window.flubnfQuips = function (target, ms) {
  var el = (typeof target === "string")
    ? document.getElementById(target) : target;
  var q = window.FLUBNF_QUIPS, i = 0, running = true;
  if (!el || !q || !q.length) return {pause: function () {}, resume: function () {}};
  setInterval(function () {
    if (running) el.textContent = q[i++ % q.length];
  }, ms || 2600);
  return {
    pause: function () { running = false; },
    resume: function () { running = true; }
  };
};
