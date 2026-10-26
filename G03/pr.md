# G03: pull request (A)
PR: https://github.com/elyfmiller/flubnf/pull/52 (fix/G03-remembered-form into dev)
Head: 598d5c1e87ffb520522376005856712e5dfc68fd
Commits: 94dddc8 (the change, as decided: A's patch, B's FC-12 condition and test case, B's kept-file assertion), 3727078 (Status: fixed in #52), then for B's review note:
- 598d5c1: model.html and research_run.html read a remembered pick holding "all" as "all" (`'all' if 'all' in form.locations else form.locations | join(', ')`), with a test in test_remembered_form (the model pages after a re-run of the 53). Reason: B's note was right that the Forecast form posted ["all", "US (national)"] before, but my `_form_locations` also turned a quick run typed "all" into that pair, so that case was new in this PR ("all" used to show back as "all"). Full suite on it: 3463 passed, 155 skipped, 0 failed.
Please re-review the new head (only those two template lines and the test).
