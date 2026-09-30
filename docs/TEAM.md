# Working on FluBNF together

Several agents work on this project at once, each on one part of it: some
run in the cloud, some on the lab Mac. They cannot always reach each other
directly, so this repository is where they leave context for one another.
This page says who works on what, where to look before starting, and how to
hand work across.

## Start of every task

1. `git fetch origin` and read, on `origin/dev`:
   - this page;
   - every file in [team/](team/), newest entries first: what each lane is
     doing, what it decided, what it needs from others;
   - [FLUSIGHT-2026-27.md](FLUSIGHT-2026-27.md) for anything touching the
     weekly FluSight rounds.
2. Check the open pull requests on elyfmiller/flubnf, so you do not redo or
   undo work in flight.
3. If your task touches another lane's area (the table below), read that
   lane's notes first and leave a request there rather than changing its
   files on your own.

## Lanes

| Lane | Works on | Where | Notes |
|---|---|---|---|
| App | the console, launchers (FluBNF.command, FluBNF.app, FluBNF.bat, setup scripts), Windows, CI, docs | cloud; branch `dev` | [team/app.md](team/app.md) |
| Submission | the weekly FluSight run: data checks, validation, the hub pull requests, CDC rules | cloud | [team/submission.md](team/submission.md) |
| Engine | the private PyBNF fork, the Liu–West filter, its port to public PyBNF as `lwf` | lab Mac | [team/engine.md](team/engine.md) |
| Model | the Oracle SIHRS and Groundhog methods, replays and scores | lab Mac | [team/model.md](team/model.md) |

A new agent picks the lane closest to its task, or adds a row and a notes
file if none fits.

## Leaving context for the others

Each lane writes only its own file in `team/`, so edits never collide. Put
the newest entry at the top of its section and date it (YYYY-MM-DD).

- **Now**: what the lane is working on, its branch and pull request.
- **Decided**: decisions the other lanes must respect, with the reason (for
  example "rename nothing to `lwf_*` yet").
- **For other lanes**: requests and heads-ups, each starting with the lane
  it is for (`Submission:`, `App:` ...). The receiving lane answers in its
  own file and says it did.
- **Open**: questions waiting on Ely.

Keep entries short and factual: link a commit, a pull request or a doc
instead of repeating it. Remove what is no longer true.

Notes reach the others only once they are on `origin/dev`: commit a notes
change on its own (docs only, so it cannot break CI), rebase on
`origin/dev`, and push. An agent that cannot push to this repository (the
lab Mac lanes, whose work lives in other repositories) gives Ely its note to
paste, or has a lane that can push commit it.

## Messages between agents

- Agents running on the lab Mac can message other agents directly.
- Cloud agents can receive messages but cannot send them yet: they answer
  through their notes file, or through Ely.
- A message is not a record: anything another lane must keep knowing goes
  into a notes file as well.

## Ground rules for every lane

- Commits are authored as Ely F. Miller <efm46@nau.edu>, with no co-author
  trailers, attribution lines or session links, in commits and pull
  requests alike.
- Work lands through `dev`; pull requests go from `dev` to `main` and are
  opened only when Ely asks. Never rewrite history on a branch another lane
  owns.
- Never open a pull request to cdcepi/FluSight-forecast-hub or email CDC
  unless Ely asks.
- Say "Liu–West filter" for the filter and "forecasting sample" for its
  output, not "posterior"; the code keeps its `pf` names until the engine
  lane starts the `lwf` migration.
- Nothing reaches a student's machine until it is on `main`: the launchers
  update each copy from its own branch.
