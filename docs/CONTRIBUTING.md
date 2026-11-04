# Contributing: from a terminal to a pull request

For a student, or anyone working for one, at a terminal: the Sandbox's model
and experiment actions as `flubnf` commands, and how a model variant comes back
to FluBNF as a pull request. What each choice means is in
[SANDBOX.md](SANDBOX.md); this page does not repeat it. [TEAM.md](TEAM.md) and
[team/](team/) are the maintainers' working notes, not instructions for
contributors.

- Fork elyfmiller/flubnf, branch from `dev`, and open the pull request against
  `dev`. Only Ely merges.
- Everything here is written and committed by people, under their own name:
  no co-author lines, and no line saying a change was generated, in commits
  and in the pull request's title and description. A check on every pull
  request from a fork refuses them.
- A model comes in as one folder, `proposals/<name>/` (section 6). Review runs
  it again on the lab's runner, where its fingerprints must match yours; it
  becomes a shipped model only through Ely's own work.
- Changes to the launchers, the installers, CI (`.github/` and
  `scripts/make_test_lock.py`) or the engine updater are flagged and read
  line by line. Any other change, a doc fix say, comes
  the same way, with the reason in the description.

## 1. A clone of your own

**On your computer**, install FluBNF as
[INSTALL-STUDENTS.md](INSTALL-STUDENTS.md) says, Steps 1 to 3. The
commands on this page are that clone's own `flubnf`:
`~/GitHub/flubnf/.venv/bin/flubnf` on macOS,
`"%LOCALAPPDATA%\FluBNF\flubnf\.venv\Scripts\flubnf"` on Windows, in
Command Prompt.

**On the students' Mac Studio**, your clone goes in `~/Students/<you>`:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | FLUBNF_DIR="$HOME/Students/<you>" bash
```

`<you>` is your name in letters, digits, `_` and `-` only, not `review`,
and not another student's in other letter case: the runner queues only
for such a folder, and in any other a start runs outside the queue. The
variable goes to `bash`, and is written with `$HOME`: `~` does not
expand inside quotes. There, always run
`~/Students/<you>/.venv/bin/flubnf`, never `~/GitHub/flubnf`'s: that is
the lab's runner, and its Sandbox is not yours. The account is shared:
keep no GitHub login on it, and do not commit or push from it
(section 6).

**Your name on your commits.** On your own computer, once per clone:

```bash
git -C <clone> config user.name "<Your Name>"
git -C <clone> config user.email "<your address>"
```

The address is one of your own, or GitHub's private noreply address for
your account. Keep every clone on `main` except while you make a pull
request: the launchers update a clone from its own branch.

## 2. The commands

A command takes what its page asks and nothing more, and answers in the
page's words:

| On the page | Command |
|---|---|
| New model, **Oracle SIHRS template, for replays** | `flubnf model new NAME --location LOCATION --forecast-date DATE [--season-start DATE]` |
| **Check** | `flubnf model check NAME` |
| **Register** | `flubnf model register NAME` |
| The Experiments card's models | `flubnf model list` |
| **Start**, **Resume** | `flubnf experiment start MODEL SEASON [--size SIZE] [--oracle/--no-oracle]` |
| An experiment's page | `flubnf experiment show ID` |
| The Experiments card's rows | `flubnf experiment list` |
| **Stop** | `flubnf experiment stop ID` |
| **Delete** | `flubnf experiment delete ID [--yes]` |
| Storage: the Sandbox line, and Student experiments | `flubnf storage` |

Every command takes `--json`: it prints one JSON document on stdout, the
console's own JSON where the page has one, and the words go to stderr.

| Exit | Meaning |
|---|---|
| 0 | done, or answered in words (a start that finished or was stopped included) |
| 1 | refused or failed: the model, the settings or the request |
| 2 | usage: an unknown option or a missing argument |
| 3 | this computer: a `MACHINE` finding (the console open, another replay, no engine, the 20 GB floor), or interrupted |

**On your computer**, `experiment start` replays in the terminal until it
ends. It is refused while this clone's console is open (use the page
then) or another replay runs here. If you open the console meanwhile,
the run stops before its next week; Start on the page resumes it. Ctrl-C
once stops it after the fits in flight, twice stops it now. To keep it
going after the terminal closes:

```bash
nohup <clone>/.venv/bin/flubnf experiment start beta2@1 2024-25 --size pilot > experiment.log 2>&1 &
```

and stop it with `flubnf experiment stop <id>`. On macOS the command keeps
the computer awake; on Windows nothing does from a terminal.

**On the students' Mac Studio**, `start` queues the experiment for the
runner, as the page's Start does there. Its JSON has `started: false`,
the `plan` when it queues, and `queued`, which `show --json` has too: its
place, the wait, about how long it runs, the disk it needs and keeps, why
it waits, and whether the runner is running (null while it replays).

**Scripts against an open console** can call its routes instead, with
`Accept: application/json`: `POST /sandbox/experiments`,
`GET /api/sandbox/experiments/<id>`, `POST /sandbox/stop`
(`experiment=<id>`) and `POST /sandbox/experiments/<id>/delete`
(`confirm=<id>`).

## 3. A model for replays

```bash
flubnf model new beta2 --location California --forecast-date 2024-12-28
# edit sandbox/models/beta2/model.bngl and priors.conf (SANDBOX.md sections 1-3)
flubnf model check beta2        # until "Ready for replays"
flubnf model register beta2     # beta2@1; edit the model and it registers as beta2@2
flubnf model list
```

Check prints each finding with its tier and code; the codes are in
`app/core/problem_codes.py`. Register takes the name exactly as its
folder spells it.

## 4. Experiments

```bash
flubnf experiment start beta2@1 2024-25 --size pilot
flubnf experiment list
flubnf experiment show beta2-v1_2024-25_pilot
flubnf experiment stop beta2-v1_2024-25_pilot      # from another terminal
flubnf experiment delete beta2-v1_2024-25_pilot    # asks first
flubnf storage
```

The same `start` resumes a stopped experiment. `delete` asks only in a
terminal; with `--json`, give `--yes`. Sizes, the id, the Oracle step's
default, Stop, Resume and Delete: [SANDBOX.md section 7](SANDBOX.md#7-experiments).
The queue, its limits and the 20 GB floor:
[On the students' Mac Studio](SANDBOX.md#on-the-students-mac-studio).

## 5. Reading the results

`show` prints the page's figures. `show --json` has `summary`
(`summary.json` as stored: sums only) and `figures` (the ratios worked
out):

| Key | Holds |
|---|---|
| `id`, `model`, `season`, `size`, `oracle`, `complete` | the experiment |
| `experiment`, `model_fingerprint` | the two fingerprints review matches |
| `cells` | `compared`, `model_only`, `shipped_only` |
| `overall`, `us`, `by_location`, `by_week`, `by_horizon` | sums: `n`, `base_wis`, `base_log_wis`, and under `model` and `shipped`: `wis`, `log_wis`, `cov50`, `cov80`, `cov95` |
| `ran`, `shipped`, `scored`, `failures` | what ran; the shipped replay compared with; the truth and its sha256; the fits with no forecast |

relWIS is `wis / base_wis`, log relWIS `log_wis / base_log_wis`, a
coverage `covXX / n`, and vs shipped this model's `wis` over the shipped
replay's. With the Oracle step off, both sides are the Liu-West filter's
alone (SANDBOX.md section 7).

**Before you commit `summary.json`**, read its `failures` texts and
`shipped.root`: they can name folders on your computer.

## 6. Making a proposal

A proposal is one folder, `proposals/<name>/`: the registered model's
name, never a shipped model's, and no other proposal's in other letter
case. It holds these six files and nothing else, each a plain file of at
most 256 KB:

| File | From |
|---|---|
| `model.bngl`, `priors.conf`, `model.json` | `sandbox/library/<name>/<n>/`, as Register wrote them |
| `experiment.json`, `summary.json` | `sandbox/experiments/<id>/`, as the experiment wrote them |
| `README.md` | you: what you changed, why, and what the figures say |

**On the computer that ran the experiment**, from its clone:

```bash
mkdir -p ~/proposal-beta2
cp sandbox/library/beta2/1/{model.bngl,priors.conf,model.json} ~/proposal-beta2/
cp sandbox/experiments/beta2-v1_2024-25_pilot/{experiment.json,summary.json} ~/proposal-beta2/
# write ~/proposal-beta2/README.md yourself: what you changed, why, what the figures say
```

Copy `model.json` from the library, not the Sandbox model's file of that
name. On the Mac Studio, whose account is shared, name the folder
`~/proposal-<you>-beta2` instead, and bring it to your own computer as
`~/proposal-beta2` with your remote session's file transfer, or
`scp -r`. On Windows, run this block and the next in Git Bash, which
comes with Git; the `flubnf` commands stay in Command Prompt.

**On your own computer**, in your clone:

```bash
git remote add fork https://github.com/<you>/flubnf.git   # once, after forking on GitHub
git fetch origin
git switch -c beta2 origin/dev
mkdir -p proposals/beta2 && cp ~/proposal-beta2/* proposals/beta2/
git add proposals/beta2 && git commit
git push -u fork beta2
git switch main
```

The first push asks you to sign in to GitHub: Git for Windows opens a
sign-in window; on macOS, `gh auth login` once sets git up, or give a
personal access token as the password.

Branch from `origin/dev`, never `main`, so the pull request carries your
commits only; to update the branch, merge `origin/dev`, never `main`.
Back on `main`, the launchers keep your clone current: a clone left on a
branch stops updating, and an untracked copy of a merged proposal would
stop the update, which is why the folder is put together outside the
clone.

## 7. The pull request

Open it against `dev`: the website offers `main` first, so change it. Use
`https://github.com/elyfmiller/flubnf/compare/dev...<you>:beta2`, or on
your own computer
`gh pr create --repo elyfmiller/flubnf --base dev --head <you>:beta2`,
and fill in the template.

**Written by people, under their own name**, in full:

- your own name and address on every commit, never Ely's account or address;
- no co-author line, and no line saying the change was generated;
- the title and the description are held to the same rule;
- do not apply a suggested change on the website: it adds a co-author line.

**The contributor check** reads every pull request from a fork. It
refuses, each error saying what to do:

- a base branch other than `dev`: change it to `dev`;
- more than 250 commits or 3,000 changed files, or a tree too large to
  read: open a smaller one;
- a co-author or generated-by line in a commit message, the title or the
  description, however it is dressed (a quote mark, bold, a tag or an
  emoji in front changes nothing): remove or reword it;
- a commit authored or committed under Ely's account or address that is
  not already on `main`: commit under your own name and address;
- a path under `proposals/` that breaks section 6's rules, each named
  with what is wrong.

It flags, as a warning that leaves it green, a change to the launchers,
the installers, CI (`.github/` and `scripts/make_test_lock.py`) or the
engine updater, and a commit linked to another GitHub account than yours
(the website's `web-flow` may commit).

To fix a commit: `git commit --amend` (`--reset-author` takes your name
and address), or `git rebase -i` for an older one, then
`git push --force-with-lease fork <branch>`. The check runs again on
every push, and when the title, the description or the base changes.

The tests wait for Ely's approval. Review reruns the proposal on the Mac
Studio, where its fingerprints must equal your `summary.json`'s. Only Ely
merges.
