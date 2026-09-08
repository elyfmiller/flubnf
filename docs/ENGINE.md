# Getting the particle filter engine

Everything in the README needs no GitHub login: this repository and the
FluSight hub are both public. The particle filter engine is the one
exception, because it needs a PyBNF fork that is not yet public. The
console runs without it, with analogue forecasts only, so this never
blocks an install.

## The shortest route: one small file, no account

The lab hands out `pybnf-pf-<sha>.tar.gz`, about 130 KB, cut with
`scripts/cut_engine_archive.sh`. Save it in your Downloads folder exactly
as it is and open the app; setup finds it, unpacks it where it belongs,
installs the engine, and prints the version stamp it carries. A git bundle
of the fork (about 140 MB, made with `git bundle create pybnf.bundle
feature/particle-filter`) works the same way for anyone who prefers a real
clone. Both are found in any of these places, on both platforms:

* the FluBNF folder itself, or the folder beside it,
* `~/Downloads`, `~/Desktop` or `~/Documents` (on Windows, the same three
  folders under your user profile).

Then double click `FluBNF.command` (macOS) or `FluBNF.bat` (Windows), or run
`./setup_engine.sh`. The console says which file it used and, when it finds
none, exactly which folders it looked in. `FLUBNF_PYBNF_BUNDLE` points at
one kept somewhere else. Because it is one file on a shared drive or a USB
stick, this is also the only route that works with no administrator rights
or no network at all.

## Through GitHub instead

A GitHub account password will not work at a git prompt: GitHub retired
password authentication in 2021, so being a collaborator on the fork is not
by itself enough to clone it in a terminal.

Before any of the routes below, check that the collaborator invitation was
accepted. Until then the repository is invisible everywhere, in Desktop's
repository list, in search, and to git, which is indistinguishable from
having no access. The invitee accepts from their email or from
<https://github.com/notifications>.

1. GitHub Desktop, no terminal and nothing to install beyond Desktop
   itself: File, Clone repository, then the URL tab, and paste the fork's
   `owner/name`. Use the URL tab: the GitHub.com tab lists repositories
   you own plus your organisations', so a private repository you are only a
   collaborator on is usually missing from it. Set the local path to
   `~/Documents/GitHub/PyBNF-Private`, where setup looks, then reopen
   `FluBNF.command`. Signing in to Desktop without cloning does not help,
   because Desktop does not share its login with terminal git.
2. GitHub CLI, two steps: `gh` is not installed by default.

       brew install gh && gh auth login

   Without Homebrew, download the macOS `.pkg` from
   <https://github.com/cli/cli/releases> (the file ending
   `_macOS_universal.pkg`) and double click it, then run `gh auth login`.
   On Windows, `winget install --id GitHub.cli`. Then re-run
   `./setup_engine.sh`.
3. An SSH key already registered with GitHub:

       FLUBNF_PYBNF_REMOTE=git@github.com:<owner>/<fork>.git ./setup_engine.sh

Already tried and still stuck? macOS caches the first answer it gets, so one
wrong entry keeps failing silently. Clear it, then use route 1 or 2:

    printf 'protocol=https\nhost=github.com\n\n' | git credential-osxkeychain erase

## Making and handing over the bundle

The bundle is around 140 MB, too large to email, so use a shared drive, a
USB stick, or a release asset on the fork. Nothing in it expires and
nothing in it is secret to the lab, but it is the fork's whole history, so
treat it the way you treat the fork.

Setup clones from it for you. By hand:

    git clone -b feature/particle-filter pybnf.bundle ~/Documents/GitHub/PyBNF-Private

Two failures are worth knowing apart. A file that is not a bundle at all (a
browser that saved an error page under the name) is caught by
`git bundle verify`. A bundle whose copy did not finish is not: verify
accepts it and the clone then dies with `early EOF` or `index-pack died`.
Setup names both cases; the first needs a different file, the second needs
the same file copied again.
