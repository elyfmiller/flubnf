# G24: compare (A)

B's patch applied to b4b176b on a scratch worktree, served on 8813 with
the same private hub copy as mine (the live file one week past the
archive's 2026-10-17); the same browser script on both.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| DA-04 | both redirects name `#main` | both redirects drop the fragment | **A.** The upload form posts to `/data/datasets#datasets`, and a redirect with no fragment keeps the request's (the Fetch rule). On 8813, the form's Save only: location `#datasets`, scrollY 581, the notice at top **-499** px, unseen (B measured Delete, whose form has no fragment). A's: `#main`, the notice at 18 px. Criterion 1 |
| DA-05 | the remedy inside the badge; a separate `comparators_missing` flag in the check's JSON (test_pull_hub's pin updated) | a hint beside the badge; the same condition folded into the JSON's `behind` | Equal on the symptom. B's needs no change to the JSON's keys (criterion 4). B's |
| DA-07 | `data.LIVE_VINTAGE` read by load_vintage; "2026-10-24 (live file)"; the title "in the live file" | the readers take an optional `path`; "2026-10-24 (target-data, not archived)", the Source tile and the title in the hub card's own words | **B.** Same mechanism in effect; B's words are the hub card's ("not archived · target-data"), so the page names the file one way (criterion 5) |
| DA-19 | one map by season label over the strip's seasons and the chart's (`_season_vars`) | the strip follows the chart's rule, newest-first from its own newest | **A.** The chart ranks the seasons of the chosen vintage's series, the strip those of the archive. With an older vintage they part: on 8813, /data?loc=Arizona&vintage=2024-03-02, strip 2023-24 rgb(43,157,43), chart 2023-24 **#0173A9** (gold, the newest the series has). A's on the same page: strip and chart 2023-24 both #2B9D2B. Criterion 1 ("a season keeps one colour on the page") |
| DA-23 | " · as of <snapshot>" on both titles | the same (", as of" on the season title) | Equal |

Vote: combine: A's DA-04 (`#main` on both redirects) and DA-19 (one map
by label); B's DA-05, DA-07 and DA-23.
