# G29: compare (A)
Read B's proposal.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| ST-04 | `ledger_total` in the summary. | The same. | Equal. |
| ST-08 | Section heading tips go (Sandbox and Student experiments kept); Reclaim keeps its "?"; busy rows: Delete off, no "?", each distinct reason once in one notice above the sections; a report archive held only for the running run's own forecast date (display only). | All heading tips go (Sandbox and Student experiments too) and Reclaim's; busy rows: Delete off with the reason in its `title`; `_may_archive` holds report archives only while the run can write them (never a Groundhog-only, dataset, research, modified or vintage run), in the page and in the delete route. | Combine. B's `_may_archive` (criterion 1): A's held flag changes the page only, so the delete route would still refuse an archive the page shows deletable, and B's rule is the pipeline's own (a Groundhog-only run never archives). A's one notice for the reasons (criterion 1, the hint's "one heading notice"): a disabled button's `title` is not reachable by keyboard or touch, and some reasons are the only way to act ("stop it from its page in alice's console first"). B's dropped Reclaim "?" (its confirmation says it; criterion 5). A's kept Sandbox and Student experiments tips (criterion 2: "deleted in the Sandbox, not here" is said nowhere else; the report does not list them). |
| ST-10 | `storage._local_when` (route helper). | `retro_archive.stamp_local` (core). | Equal; A's narrower (no new core function). |
| ST-11 | "Delete the 1 / all N workroots not running (...)"; the Clear dialog without a list. | "Delete N workroots (...)", the dialog "not running"; the Clear button and dialog without "completed"; the bulk notices too. | B's: it also clears "completed" from the notices, and the button stays short (criteria 1, 5). |
| ST-12 | Template-level `st_listed`; "No runs in the ledger". | `inv["listed"]` from the route; "0 B in use"; "No runs recorded". | B's: one flag from the route rather than a long template expression (criterion 4); words equal. |
| ST-14 | "Delete the run <label>?", hint names the folder id, the report and submissions. | "Delete the <label> run?", hint names the files and the run id; an unrecorded workroot "the unrecorded run <id>". | B's: it also words the unrecorded case (criterion 1). |
| ST-15 | "Its 1 replay and 1 run workroot went with it; ..." | "With it went its 1 replay and its 2 run workroots; ..." | Equal; A's shorter. |
| ST-16 | No tip. | No tip. | Equal. |
| ST-17 | "failed" takes partial, stopped and interrupted; the date sliced from the id. | The button reads "not ok" (key unchanged); the day from `runs.run_id_time`. | B's: a stopped run is not "failed" (criterion 1), and the day comes from the one function that reads an id's time. |

Vote: combine: B's patch, with A's one busy notice (each distinct reason once, above the sections) in place of the `title`-only reason, A's kept Sandbox and Student experiments heading tips, A's `_local_when` (no new core function) and A's ST-15 sentence. Tests: B's test_storage_words for its parts, A's busy-notice and ST-10 assertions.
