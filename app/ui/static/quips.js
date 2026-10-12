// Run quips. FLUBNF_QUIPS is shared by the forecast and retrospective
// pages; FLUBNF_RETRO_QUIPS (replays of past seasons) joins them on the
// retrospective pages only. House voice: lowercase, no exclamation marks,
// no emoji; flu, Bayesian inference, particle filtering, epidemiology;
// dry and playful.
window.FLUBNF_QUIPS = [
  "teaching 10,000 particles to sneeze responsibly",
  "resampling the unlucky",
  "negotiating with a negative binomial",
  "asking last winter for advice",
  "herding susceptibles",
  "integrating quietly since 1927",
  "jittering, but only a little",
  "waiting for the particles to settle down",
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
  "warming up the filter, gently",
  "checking whether Rt has recovered",
  "wandering the parameter space, mostly on purpose",
  "shrinking toward the mean, emotionally as well",
  "giving every trajectory a fair cough",
  "propagating uncertainty with confidence",
  "consulting the negative binomial about its variance",
  "asking the particles to form an orderly quantile",
  "estimating how much winter is left",
  "asking the Groundhog what it saw last year",
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
  "asking the dispersion parameter to commit",
  "checking the serial interval against its alibi",
  "refusing to extrapolate past the data's patience",
  "letting the weights fall where the evidence puts them",
  "calibrating the 95% interval to mean 95%",
  "trimming the tails, but only the implausible ones",
  "asking each replicate for an independent opinion",
  "averaging replicates so no one seed gets the last word",
  "reminding the particles that hospitals report on saturdays",
  "reading the reporting delay between the lines",
  "nowcasting the weeks that have not finished arriving",
  "keeping the pinball loss small and the ego smaller",
  "cross-checking the peak against every donor season",
  "sorting quantiles into ascending order, as the hub requires",
  "filling 23 quantiles, one careful step at a time",
  "estimating the effective reproduction number, effectively",
  "weighing the prior against a very persuasive week",
  "testing whether the curve has turned or merely paused",
  "tracking susceptibles as they quietly run out",
  "letting seasonality do its annual thing",
  "interviewing the log-likelihood about its maximum",
  "rounding nothing until the very end",
  "propagating exactly the noise the data deserves",
  "checking the denominator before trusting the rate",
  "separating signal from reporting artifact",
  "allowing for the holiday reporting dip",
  "accepting that some weeks are just noisy",
  "drawing samples at a respectful pace",
  "folding four horizons into one honest fan",
  "giving each jurisdiction an epidemic of its own",
  "keeping the variance where the data can see it",
  "asking the growth rate what it has been up to",
  "measuring the forecast against the baseline's modest ambitions",
  "inflating nothing but the uncertainty, and only honestly",
  "treating every reported zero with polite suspicion",
  "reading the curve's second derivative for hints",
  "reserving judgment until the weights are in",
  "converging at a pace the filter finds comfortable",
  "letting the observation model take the blame for noise",
  "weighting the recent weeks, without forgetting the old ones",
  "counting admissions, not headlines",
  "checking that the fan widens as the horizon does",
  "consulting the population denominator, state by state",
  "keeping the median modest and the tails honest"
];

// the retrospective's own weather: replaying seasons that already ended
window.FLUBNF_RETRO_QUIPS = [
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

// Rotate quips into an element (the shared lines, plus `extra` when given:
// the retrospective pages pass FLUBNF_RETRO_QUIPS); returns {pause, resume} so a paused run
// holds still. WCAG 2.2.2: prefers-reduced-motion shows one static quip,
// and a click, or Enter or Space on the focused line (a toggle button for
// assistive tech, pressed while held), toggles rotation in every mode.
window.flubnfQuips = function (target, ms, extra) {
  var el = (typeof target === "string")
    ? document.getElementById(target) : target;
  var q = (window.FLUBNF_QUIPS || []).concat(extra || []), i = 0, running = true, held = false;
  if (!el || !q || !q.length) return {pause: function () {}, resume: function () {}};
  i = Math.floor(Math.random() * q.length);   // a fresh line each visit
  el.textContent = q[i++ % q.length];   // paint at once, not after a delay
  el.title = "Click to pause or resume this line";
  el.style.cursor = "pointer";
  el.setAttribute("role", "button");
  el.setAttribute("tabindex", "0");
  el.setAttribute("aria-label", "Hold the rotating line");
  el.setAttribute("aria-pressed", "false");
  function toggle() {
    held = !held;
    el.setAttribute("aria-pressed", held ? "true" : "false");
  }
  el.addEventListener("click", toggle);
  el.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
  });
  var reduce = typeof matchMedia === "function"
    && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce) {
    setInterval(function () {
      if (running && !held) el.textContent = q[i++ % q.length];
    }, ms || 2600);
  }
  return {
    pause: function () { running = false; },
    resume: function () { running = true; }
  };
};
