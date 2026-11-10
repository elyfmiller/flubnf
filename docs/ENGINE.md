# Getting the engine

Everything in the README needs no GitHub login: this repository and the
FluSight hub are both public. The particle filter engine has two routes:

* **public, the default**: public PyBNF, where the Liu-West filter now
  lives (lanl/PyBNF, `job_type = lwf`), installed from this repository
  with no account and no file
  ([below](#the-public-engine-the-default)). The first open of FluBNF
  installs it.
* **private, the fallback**: the lab's PyBNF fork (`fit_type = pf`), which
  is not public. It runs only on a copy of FluBNF switched to it
  ([Choosing the engine](#choosing-the-engine)). It stays as the fallback
  for two rounds after the switch; then the private route goes (stage 4 in
  [team/engine.md](team/engine.md)). It is the one part of an install that
  can need a GitHub account, or a file from the lab.

The console runs without either, with analogue forecasts only, so this never
blocks an install.

<a id="the-public-engine-opt-in"></a>

## The public engine (the default)

The Liu-West filter is merged into public lanl/PyBNF as `job_type = lwf`
(merge commit `8410f794`, lanl/PyBNF#985). The public route installs that
commit with bngsim 0.15.1 on Python 3.12, and nothing else: both are held
for the whole season, and no installer takes a newer one.

It is the default by Ely's decision of 2026-11-09. The decision came
before stage 2 of the engine plan ran: there has been no full-grid
comparison through the console, no shadow Wednesday, no install by someone
outside the lab, and no fit on native Windows. The evidence for it is the
lab's own, in-house and retrospective (below). The private engine stays
installed as the fallback.

What gets installed, and how:

* One lock file, `engine-requirements.txt` in the FluBNF folder, lists
  every package with its SHA-256 hashes, plus one line for PyBNF itself: a
  wheel built from `8410f794` and attached to a release of this repository
  whose tag names the full commit. pip installs it with `--require-hashes`
  and `--only-binary :all:`, so a file that differs from the lock by one
  byte is refused and nothing is compiled. The wheel, not the commit's
  source archive: that archive holds over 500 paths longer than 150
  characters and breaks under the Windows path limit.
* A Python environment of its own: `~/.venvs/flubnf-public` on macOS and
  Linux, `%LOCALAPPDATA%\FluBNF\venv-public` on Windows
  (`FLUBNF_PUBLIC_VENV` moves it). It never shares one with the private
  engine (`~/.venvs/flubnf-engine`, and `~/.venvs/flubnf` on the lab Mac);
  setup refuses to install into either.
* Python 3.12 (on Windows, 64-bit x64 3.12). Setup finds one, or asks
  conda for one. An Intel Mac needs macOS 15 (libroadrunner's Intel
  wheel), and on Linux the lock has wheels for x86_64 only.
* On both routes: Perl, and BNG2.pl from the `bionetgen` package that
  setup puts in `.venv`. On macOS the engine also needs a C compiler,
  Apple's Command Line Tools (`xcode-select --install`), because bngsim
  compiles each model; the engine's own check says when it is missing. On
  Windows bngsim's code generation stays off (`BNGSIM_NO_CODEGEN=1`), as it
  is today, so no compiler is needed there.
* The network once: the PyBNF wheel comes from github.com, and the other
  packages from pypi.org.

On a copy that runs the public engine (every copy not switched to the
private one), the launchers (`FluBNF.command`, `FluBNF.app`,
`SetupEngine.command`, `FluBNF.bat`) check it on every open, and install
it when it is missing or no longer matches the lock. A copy switched to
the private engine checks that one instead, and leaves the public engine
as it is. On macOS and Linux, `./setup_engine.sh --public` does the same
install by hand.

Which one is installed: the lock is the reference. From the FluBNF folder,

    ~/.venvs/flubnf-public/bin/python scripts/engine_lock.py check

(on Windows, `"%LOCALAPPDATA%\FluBNF\venv-public\Scripts\python.exe"
scripts\engine_lock.py check`) prints `public engine ready: pybnf 1.8.1 from
pybnf-1.8.1-py3-none-any.whl, bngsim 0.15.1`, or what differs from the
lock. `pybnf.__version__` cannot tell: it reads 1.8.1 on the merge commit
and on the August release, which has no Liu-West filter.

Given the same random inputs, the two engines give the same forecast
draws, on 144 of 144 cells. Each with its own random numbers, the forecasts
differ draw by draw, and the public engine's total WIS is 1.0013 times the
private engine's (95% interval 0.986 to 1.016). Both results are the lab's
own, in-house and retrospective; neither is an acceptance result. A cell
takes 2.07 times as long on the public engine at the median, 2.21 at most,
so its time budgets are 2.4 times the private engine's. The measurements
are in [team/engine.md](team/engine.md). The output of either engine is a
forecasting sample.

The two-strain model, `sihrs-2strain`, runs on the private engine only:
the public engine has no counterpart for its typed-positives channel, so an
experiment of it is refused there before it starts, and the refusal names
the switch to the private engine. A model that calls BNGL's clock,
`time()`, is the private engine's only too: the public engine starts its
clock at 0 where the private one starts at -1, so the model would run a
week out of phase there, and each of its cells is refused; the Sandbox's
Check warns of it under the public engine. A counter species, as in
FluBNF's templates, keeps the clock on both engines. To run either one,
switch the copy to the private engine (next section).

### Choosing the engine

There is nothing to choose for the default. A copy of FluBNF that records
no engine runs the public one.

To switch a copy to the private engine, the fallback, run this on macOS or
Linux, from the FluBNF folder:

    ./setup_engine.sh --private

then open FluBNF again. On Windows, in Command Prompt, from the FluBNF
folder:

    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -Engine private

then open `FluBNF.bat` again. Either one records `FLUBNF_ENGINE=private`
for this copy of FluBNF alone (in `.flubnf.env`, or in `.flubnf.env.cmd`
on Windows), first, before it installs or fetches anything, so a run that
stops early (no network, say) still switches the copy. When the private
engine is already installed and works, that is all either one does: a few
seconds, no download, no network.

* On macOS and Linux, `./setup_engine.sh --private` tries the engine
  environment and checkout this copy records first, then the default
  ones, and records the pair that works. When a different engine archive
  is waiting for an unpacked private engine (below), it installs that in
  its place instead of stopping. Otherwise it installs the private engine
  as the rest of this page says.
* On Windows, `setup.ps1 -Engine private` tries the engine environment and
  folder `FluBNF.bat` would run, and stops there only on a copy whose
  console environment (`.venv`) is already made. Otherwise it goes on
  with the whole setup, which takes minutes and the network, and the next
  open of `FluBNF.bat` installs the private engine
  ([WINDOWS.md](WINDOWS.md#the-private-engine-the-fallback)).

`./setup_engine.sh --public` and `setup.ps1 -Engine public` record
`FLUBNF_ENGINE=public`: the default again. `./setup_engine.sh` or
`setup.ps1` with no option keeps whatever the copy records.

A `FLUBNF_ENGINE` that is neither `private` nor `public` runs the public
engine: the launchers say so in one line, and `flubnf doctor` shows a
warning. The installers (`setup_engine.sh` with no option, `install.sh`,
`reinstall.sh`) refuse such a value and install nothing; `setup.sh` and
`setup.ps1` say so in one line and go on with the public engine.

The record also reaches the `flubnf` commands started from a plain
Terminal (`flubnf app`, `retro`, `doctor`, `experiment`, `runner`): they
read it when the shell does not set `FLUBNF_ENGINE`. When the shell does
set it:

* `flubnf app`, `retro`, `doctor` and `experiment` follow the shell's
  value, for that shell; `flubnf doctor` warns when it names the other
  engine than the record.
* `flubnf runner` refuses to start when the shell's value names the other
  engine than the record, and says how to fix it: read the record into
  that Terminal first (`. ./.flubnf.env` in the FluBNF folder; on
  Windows, `call .flubnf.env.cmd`).
* The launchers (`FluBNF.command`, `FluBNF.app`, `FluBNF.bat`) follow the
  record over the shell. `setup_engine.sh` with no option, and
  `SetupEngine.command`, take the shell's value first.

Nothing switches engines by itself. When the public engine cannot install
(no network, no Python 3.12, an Intel Mac below macOS 15), the console
starts without it, with analogue forecasts only. When the private engine
is installed on that machine, the message names the one step that
switches to it.

A new machine starts on the default with the plain install line:

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash

A machine that must start on the fallback adds the variable:

    curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | FLUBNF_ENGINE=private bash

Pasted again on a copy that records the private engine, the plain line
keeps it and says so; `| FLUBNF_ENGINE=public bash` chooses the default
again.

`reinstall.sh` takes `FLUBNF_ENGINE=private` the same way, and then needs
the lab's engine file. Without it, it needs no engine file and leaves the
private engine where it is.

The rest of this page is the private engine, the fallback. Its archives,
bundles and checkouts are installed only on a copy switched to it: a copy
on the default leaves an engine file in Downloads alone.

## The shortest route: one small file, no account

The lab hands out `pybnf-pf-<sha>.tar.gz`, about 130 KB, cut with
`scripts/cut_engine_archive.sh`. Save it in your Downloads folder exactly
as it is, then switch the copy to the private engine as above; setup finds
the file, unpacks it where it belongs, installs the engine, and prints the
version stamp it carries. A git bundle of the fork (about 140 MB, made
with `git bundle create pybnf.bundle feature/particle-filter`) works the
same way for anyone who prefers a real clone. Both are found in any of
these places, on both platforms:

* the FluBNF folder itself, or the folder beside it,
* `~/Downloads`, `~/Desktop` or `~/Documents` (on Windows, the same three
  folders under your user profile, and their OneDrive copies).

Each folder itself is searched, not the folders inside it. On Windows only
the lab's name counts, `pybnf-pf-*.tar.gz`: PyPI's `pybnf-<version>.tar.gz`
and GitHub's `PyBNF-<version>.tar.gz` are not the engine and are passed
over.

On macOS and Linux, `./setup_engine.sh --private` installs it there and
then. On Windows, `setup.ps1 -Engine private` records the choice and names
the file, and the next open of `FluBNF.bat` installs it. On a copy that
already records the private engine, double clicking `FluBNF.command` or
`FluBNF.bat` does the same. The launcher says which file it used. When it
finds none, it lists the folders it looked in: `setup_engine.sh` on macOS
and Linux, and on Windows both `FluBNF.bat` and `setup.ps1`.
`FLUBNF_PYBNF_BUNDLE` points at one kept somewhere else. Because it is one
file on a shared drive or a USB stick, this route needs no GitHub account
and no administrator. It still needs the network once, for the engine's
Python packages (on Windows about 100 MB from pypi.org, and 31 MB for the
Perl that `FluBNF.bat` installs for FluBNF, again with no administrator).

On Windows the archive is unpacked into
`%LOCALAPPDATA%\FluBNF\PyBNF-Private`, and the engine's Python environment
is built at `%USERPROFILE%\.venvs\flubnf-engine` with 64-bit (x64) Python
3.12 or 3.11.
[WINDOWS.md](WINDOWS.md#the-particle-filter-engine-on-windows) has the
whole Windows story: where things go, updates, and what to do when the
install fails.

## Through GitHub instead

These routes too are for a copy switched to the private engine.

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
   collaborator on is usually missing from it. Set the local path to a
   folder setup looks in, then open FluBNF again:
   * macOS: `~/GitHub/PyBNF-Private`, then run `./setup_engine.sh
     --private` (or reopen `FluBNF.command` on a copy that already
     records the private engine);
   * Windows: `C:\Users\<you>\AppData\Local\FluBNF\PyBNF-Private` (that is
     `%LOCALAPPDATA%\FluBNF\PyBNF-Private`, which Controlled Folder Access
     never protects), or Desktop's own default,
     `C:\Users\<you>\Documents\GitHub\PyBNF-Private`, which is searched
     too; then open `FluBNF.bat` again. `%USERPROFILE%\GitHub` is not
     searched on Windows.

   Signing in to Desktop without cloning does not help, because Desktop
   does not share its login with terminal git.
2. GitHub CLI, two steps: `gh` is not installed by default.

       brew install gh && gh auth login

   Without Homebrew, download the macOS `.pkg` from
   <https://github.com/cli/cli/releases> (the file ending
   `_macOS_universal.pkg`) and double click it, then run `gh auth login`.
   Then run `./setup_engine.sh --private` again.

   On Windows, `winget install --id GitHub.cli -e --source winget`, then
   `gh auth login` in a new Command Prompt window. `FluBNF.bat` never
   clones from GitHub, so clone the fork yourself: `setup.ps1` prints the
   `git clone` line for this machine (into
   `%LOCALAPPDATA%\FluBNF\PyBNF-pf`). Then open `FluBNF.bat` again, which
   installs the engine from that clone.
3. An SSH key already registered with GitHub:

       FLUBNF_PYBNF_REMOTE=git@github.com:<owner>/<fork>.git ./setup_engine.sh --private

   On Windows, record the remote and open a new Command Prompt window, so
   the setting is visible there:

       setx FLUBNF_PYBNF_REMOTE "git@github.com:<owner>/<fork>.git"

   `setup.ps1` then checks access and prints its `git clone` line with that
   remote; clone, then open `FluBNF.bat` again.

Already tried and still stuck? git keeps using the credential it stored
first, so one wrong entry, or a login for another GitHub account, keeps
failing silently. Clear it, then use route 1 or 2. On macOS:

    printf 'protocol=https\nhost=github.com\n\n' | git credential-osxkeychain erase

On Windows, Git Credential Manager keeps it in Windows Credential Manager:
Control Panel, User Accounts, Credential Manager, Windows Credentials, then
remove the entry named `git:https://github.com`.

## Making and handing over the bundle

The bundle is around 140 MB, too large to email, so use a shared drive, a
USB stick, or a release asset on the fork. Nothing in it expires and
nothing in it is secret to the lab, but it is the fork's whole history, so
treat it the way you treat the fork.

Setup clones from it for you. By hand, on macOS:

    git clone -b feature/particle-filter pybnf.bundle ~/GitHub/PyBNF-Private

and on Windows, in Command Prompt, where `~` means nothing and a profile
path can hold a space:

    git clone -b feature/particle-filter "%USERPROFILE%\Downloads\pybnf.bundle" "%LOCALAPPDATA%\FluBNF\PyBNF-Private"

then open `FluBNF.bat` again, which installs the engine from that clone.

Two failures are worth knowing apart. A file that is not a bundle at all (a
browser that saved an error page under the name) is caught by
`git bundle verify`. A bundle whose copy did not finish is not: verify
accepts it and the clone then dies with `early EOF` or `index-pack died`.
Setup names both cases; the first needs a different file, the second needs
the same file copied again.

## Which engine am I running?

Each engine has one pinned build, its production build:

* the public engine, the default: lanl/PyBNF at `8410f794`, installed as
  the wheel `pybnf-1.8.1-py3-none-any.whl` from the release
  `pybnf-8410f794e3fa4817572fd07fceb043ddec39d77b` of this repository
  (sha256 `18a59bc24caa99ae1b4cc14518a4233cf17a0e4edac45d50d5e4189413ee21e5`),
  with bngsim 0.15.1, all from `engine-requirements.txt`;
* the private engine, the fallback: the fork's `feature/particle-filter`
  branch at commit `2fdadee0`, on bngsim 0.15.1 (docs/ORACLE-SIHRS.md,
  "Engine line-up"). It was production for the 2026-27 season until the
  switch to the public engine.

A run on either engine's pinned build carries no warning.

* In the app: the Home page's Setup card names the engine this copy runs,
  and its badge names the build: `PyBNF 8410f794` on the public engine,
  `PyBNF 2fdadee0, private engine` on the fallback. Any other build, or
  local edits, adds one warning line there and under the Forecast tab's
  Engine row; its "?" says how to switch. Every run records the engine and
  its build: the run page's "Produced by" list and the weekly report's
  settings show it ("8410f794 (lanl/PyBNF, bngsim 0.15.1)", or
  "2fdadee0 (feature/particle-filter)"), and a retrospective season
  records it for each week.
* `flubnf doctor` names the engine on its "engine" row, then prints the
  build as "PyBNF engine build", with a warning and the fix when it is not
  that engine's pinned build. It stays a warning: research runs may use
  another build on purpose.
* By hand, the public engine first: `engine_lock.py check`, as above. For
  the private engine, in its folder (`FLUBNF_PYBNF`, else `PyBNF-pf` or
  `PyBNF-Private` in the checkout folder; on Windows, the first engine in
  the list under [WINDOWS.md, "Where it goes"](WINDOWS.md#where-it-goes)),
  quoting the folder, since its path can hold a space:

      git -C "<engine folder>" rev-parse --short=8 HEAD
      git -C "<engine folder>" symbolic-ref --short HEAD
      git -C "<engine folder>" status --porcelain --untracked-files=no

  An empty status means no local edits. An archive install has no `.git`;
  its first `VERSION` line is `<branch> <commit>`.

Each time FluBNF opens, its launcher (`FluBNF.command`, `FluBNF.app`,
`FluBNF.bat`) runs `flubnf engine-update`, on either engine. It touches
only a private engine's checkout, and keeps the fallback at its pin when
that is safe: a git checkout on `feature/particle-filter` with no local
edits, behind `2fdadee0`, is fast-forwarded to exactly that commit (fetched
from GitHub first when it is not on disk, with no password prompt and a
30-second limit). Anything else is left as it is and the reason printed:
another branch, local edits, commits past the pin, no access to the fork.
The console's build warning repeats that reason. The public engine changes
only when the lock does. `FLUBNF_UPDATE=off` skips it along with the
launcher's own update, and `flubnf engine-update` runs it by hand (on
Windows, `.venv\Scripts\flubnf engine-update` in Command Prompt, from the
FluBNF folder).

To switch a private checkout by hand, stash any local edits first, then
check out the branch and pull (quote the folder if its path holds a
space), and open FluBNF again. The lines are the same in Terminal, Command
Prompt and PowerShell:

    git -C "<engine folder>" stash
    git -C "<engine folder>" checkout feature/particle-filter
    git -C "<engine folder>" pull

A private archive install is replaced by saving `pybnf-pf-2fdadee0.tar.gz`
in Downloads, then, on macOS and Linux, running `./setup_engine.sh
--private` (on macOS, double clicking `SetupEngine.command` on a copy that
records the private engine does the same). It installs an archive whose
version stamp differs from the unpacked copy's, and which is newer than
it, in that copy's place, even when the copy on disk works. On Windows,
opening `FluBNF.bat` again replaces the copy it unpacked into
`%LOCALAPPDATA%\FluBNF\PyBNF-Private` with the newer archive. Either way
the old copy is renamed, never deleted.

A retrospective season resumes only on the engine and the build its weeks
were fitted by. A season begun on the private engine is refused on the
public one, and the other way round. The refusal names the step that
switches back (for a private season, `./setup_engine.sh --private`, or
`setup.ps1 -Engine private`). Switch back to finish it there, or archive or discard it to
replay it on this one. A season from before builds were recorded was
fitted by the private engine: it resumes there as before, and is refused
on the public one. A season whose build could not be read when it began
records its engine alone, and resumes only on that engine.
