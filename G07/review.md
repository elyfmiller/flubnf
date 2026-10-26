# G07: review (B)
PR #56, head 1b5a4ca (8b0bdd4 the change, 1b5a4ca the Status cell).

Approve.

What I checked
- The diff against dev b8bf2b2 is A's prototype plus the decided
  `choices()` line, with the Retrospective's note flashed before its
  redirect and `retro_context` listing whole datasets; the DA-12 test
  asserts the pickers and the "Your data" tabs. Author and committer Ely F.
  Miller; no attribution lines or forbidden words in the messages, the
  diff or the PR body; no footer; Status cell `fixed in #56`; the body in
  the repo's style.
- On the head: the 8 new tests and the dataset tests (19 files): 565
  passed; `ruff check --select F821,F823,F811,F401 app/ui` clean.
- B's reproduction script against the head: the thin file's run closes
  partial with "Too few donors" and no zero-week row on its page, the
  Forecast tab's badge warn, the replay "No scored cells" with the
  abstentions; the one-row file "1 problem to fix" and 422; a lone week
  reads "1 week"; the three pages of a dataset without its vintages 200
  (and /data, /retro?tab=own, /forecast?tab=own); garbage and 25-field
  posts 400 with the message; the second name's upload opens the first
  dataset and says "This file is already stored as 流感 data: 1 group,
  10 weeks."
