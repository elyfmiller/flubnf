# The repository move of 2026-11-10

On 2026-11-10 FluBNF moved to a new public repository with the same name,
`elyfmiller/flubnf`. Clones, the install lines and the engine wheel's
release URL all keep working with the same address.

The old repository is kept, read-only, as
[`elyfmiller/flubnf-archive-2026-11`](https://github.com/elyfmiller/flubnf-archive-2026-11).

## What changed

- **Commit ids after 2026-10-09.** Eight commits' author or committer were
  corrected to Ely F. Miller. Their ids changed, and so did the ids of every
  commit after them. Every commit's files, dates and message are unchanged.
  [`commit-map-2026-11.txt`](commit-map-2026-11.txt) gives old id → new id for
  each of the 658 commits whose id changed.
- **Commits up to 2026-10-09 keep their ids**, including v1.0.0 and v1.1.0.
- **Pull request numbers start again at #1.** "#61", "#101" and the like in the
  docs written before the move mean the archive's pull requests. The four
  that were open moved:

  | Archive | New |
  |---|---|
  | #93 (usability and compute) | #1 |
  | #104 (review leftovers, decided) | #2 |
  | #105 (App final pass) | #3 |
  | #106 (report look) | #4 |

- **Links to a commit id after 2026-10-09** work in the archive only.
  Look the id up in the commit map for the new one.
- **Reviews and comments** on the old pull requests stay in the archive.

## A clone from before the move

`git pull` refuses the new history. Nothing is lost. If the clone has no
local edits:

```bash
git fetch origin
git reset --hard origin/main
```

Use `origin/dev`, or whichever branch the clone is on, instead of `origin/main`.
Local edits: commit them first, then `git rebase --onto` the new branch, using
the commit map for the old base id. Do not push from a clone that was not
reset: it would bring the old commits back.

The engine wheel was published again at the same release URL with the same
sha256, so `./setup_engine.sh` and `setup.ps1` install it as before.
