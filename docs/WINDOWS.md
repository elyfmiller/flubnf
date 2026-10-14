# FluBNF on Windows

Native Windows support is in active bring-up. The console, the analogue
engine, data fetching, scoring, and reports are expected to work. The PF
fitting engine is installed separately, from one small file (see
[The particle-filter engine on Windows](#the-particle-filter-engine-on-windows)),
and its externals are listed under Limitations.

## Supported path (lab laptops)

Install once:

1. A Python. Anaconda from https://www.anaconda.com/download is the lab's
   standard and needs no settings changed: `FluBNF.bat` and `setup.ps1`
   probe the folders it installs into, so nothing is added to PATH.
   Python 3.11 or newer from https://www.python.org/downloads/ works too
   (tick "Add python.exe to PATH" in the installer). The particle-filter
   engine needs 64-bit (x64) Python 3.12 or 3.11; with Anaconda, FluBNF
   makes one itself.
2. Git from https://git-scm.com/download/win (defaults are fine).

Then get the code and launch:

```
git clone https://github.com/elyfmiller/flubnf "%LOCALAPPDATA%\FluBNF\flubnf"
```

The quotation marks matter. `%LOCALAPPDATA%` expands to
`C:\Users\<you>\AppData\Local`, and if your account name contains a space
then an unquoted destination reaches `git` as two arguments and the clone
stops with `fatal: Too many arguments.` -- which says nothing about spaces.

Not `Documents`. Whenever Controlled Folder Access is switched on it
protects `Documents`, `Pictures`, `Music`, `Videos` and `Favorites`, and a
protected folder is one `git.exe` is not allowed to write into. The
[Controlled Folder Access](#controlled-folder-access) section is the whole
story; if you already have a clone under `Documents` it keeps working and
nothing needs moving.

Double-click `FluBNF.bat` in that folder. The first run creates the
virtual environment and installs dependencies (a few minutes); every later
run self-updates with a fast-forward `git pull`, brings a clean PyBNF
engine checkout up to the production build the same way, and starts the
console. When it cannot update, it says why and prints the commands that
would do it; see
[When FluBNF.bat cannot update itself](#when-flubnfbat-cannot-update-itself).

The first open also puts FluBNF where Windows finds it, since the folder
sits in hidden AppData: a Start menu entry named FluBNF (press the Windows
key and type `FluBNF`; right-click it to pin it to the taskbar or to
Start) and, once per Windows account, the same shortcut on the Desktop.
A deleted Desktop shortcut is not made again. Both run `FluBNF.bat` in
this folder; open FluBNF from a second clone, or after moving this one,
and the Start menu entry follows it. `scripts\windows\shortcuts.ps1`
makes them, and `set FLUBNF_SHORTCUTS=off` before launching skips it.

For the particle-filter engine, save the lab's `pybnf-pf-<sha>.tar.gz` in
your Downloads folder before that double-click, or before any later one:
`FluBNF.bat` installs it. The next section has the details.

If the FluSight data is not on the machine yet, `FluBNF.bat` says so and
offers to run `setup.ps1` for you. Answering N starts the console anyway
with data browsing empty, and the offer comes back on the next launch;
walking away lets the offer answer itself with Y after twenty seconds, so
an unattended first double-click still ends at a console with data. The
offer disappears for good once the data is there.

That offer is judged on the data, not on the folder: the launcher looks for
`auxiliary-data\locations.csv` inside the hub, and setup runs with
`-NoPrompt`, so a double-click can never end at a question with no timeout.
Nothing on the double-click path waits on input without a deadline.

## The particle-filter engine on Windows

The console, the Groundhog and the reports need nothing more. Fits by the
particle filter need the engine: a copy of the lab's private PyBNF fork and
a Python environment of its own. `FluBNF.bat` installs both, and needs no
GitHub account and no administrator to do it. Fits also need Perl, which
`FluBNF.bat` installs for FluBNF with no administrator either (below).
Without the engine the console runs analogue forecasts only.

### Installing it from the lab's file

The lab hands out `pybnf-pf-<sha>.tar.gz`, about 130 KB. Save it in your
Downloads folder exactly as it is (do not unzip it, do not rename it) and
double-click `FluBNF.bat`. The window shows

```
unpacking the engine from "...\Downloads\pybnf-pf-XXXX.tar.gz" - no GitHub account needed
version stamp: feature/particle-filter XXXX
Installing the particle filter engine. One time, a few minutes.
looking for a Python for the engine, 64-bit (x64) 3.12 or 3.11:
downloading about 100 MB of packages and installing them, usually 2 to
5 minutes; leave this window open
PF engine ready, bngsim 0.15.1 -- engine ready
```

with a line under "looking for a Python" for each Python it tried, and
pip's own lines under "downloading"; the console then starts with both
models.

The file is found in the FluBNF folder, the folder above it, and your
Downloads, Desktop and Documents folders, OneDrive's copies of those three
included: each folder itself, not the folders inside it. When none is
found, the window lists every folder it looked in. Only the lab's name
counts, `pybnf-pf-*.tar.gz`: PyPI's `pybnf-<version>.tar.gz` and GitHub's
`PyBNF-<version>.tar.gz` are not the engine and are passed over. When there
is more than one `pybnf-pf-*.tar.gz`, the newest wins and the window says
so, so delete the old ones when a new one arrives.
`FLUBNF_PYBNF_BUNDLE` names a file kept anywhere else. The lab's other
format, `pybnf.bundle` (a git bundle of the fork, about 140 MB), is
installed the same way but becomes a git clone, so it needs Git on PATH.

### Perl

Every fit, and the Sandbox's Check, runs BioNetGen's `BNG2.pl`, a Perl
program, so `FluBNF.bat` checks for Perl on every open, engine or not.
Only a Windows Perl counts: the perl in Git's Unix tools, MSYS2 or Cygwin
cannot load BNG2.pl's own modules, and the window names it when that is
the one on PATH. A Strawberry Perl in `%SystemDrive%\Strawberry` that is
not on this window's PATH (a Command Prompt opened before the install) is
put first on it for the console.

Without one, `FluBNF.bat` installs FluBNF's own Perl: conda-forge's
repack of Strawberry Perl 5.32.1.1 (`perl-5.32.1.1-2_h57928b3_strawberry`,
a 31 MB download, 145 MB unpacked), in `%LOCALAPPDATA%\FluBNF\perl`. No
administrator, no installer, no question. The console's Python downloads
it (the proxy and certificates pip used) and refuses anything but the
pinned size and SHA-256; Windows' own `tar.exe` unpacks it; every one of
its 7,728 files is checked against the package's own list, and `perl.exe`
must start, before `flubnf-perl.ok` is written. An unpack without that
marker, or with another package's, is removed and done again. Perl works
out where its modules are from where it sits, so nothing is relocated.
From then on every open finds it first and puts `Library\bin` first on
PATH; the console looks there first too. Delete the folder to have it
installed again. It has no C compiler (Strawberry's own `c\bin` is not in
the package), which fits on Windows do not use (see bngsim below).

Only when that fails (no network, a PC that blocks programs under
AppData) does `FluBNF.bat` offer Strawberry Perl with winget, once; the
next open tries FluBNF's own again first. Left alone, the question
answers itself with yes after twenty seconds. It is a machine-wide
install (about 210 MB), so the window first says Windows will ask
permission, and Windows does: click Yes, or the flashing shield on the
taskbar if nothing appears. An account that is not an administrator
needs an administrator's password. The install is judged by Strawberry's
`perl.exe` on disk, not by winget's exit code, and a failure says why: the
prompt declined or not answered in time (or no administrator), a policy
blocking it, another install running. The outcome goes in
`.venv\perl-offer.txt`; from then on every open prints a two-line
reminder with the link until Perl is there, and deleting the file brings
the offer back. Another install running records nothing, so the next
open asks again. Without winget, the window names
https://strawberryperl.com instead.

The console looks for a Windows Perl the same way at every fit: FluBNF's
own first, then on its PATH, then on the Path Windows holds now, then in
Strawberry Perl's folders. A Perl installed while the console is open is used by the next
fit, with no restart, and `flubnf doctor` names the one it finds.

### Where it goes

| what | where |
|---|---|
| the engine, from `pybnf-pf-<sha>.tar.gz` | `%LOCALAPPDATA%\FluBNF\PyBNF-Private` (unpacked, no `.git`) |
| the engine, from `pybnf.bundle` | `%LOCALAPPDATA%\FluBNF\PyBNF-pf` (a git clone) |
| its Python environment | `%USERPROFILE%\.venvs\flubnf-engine` (`FLUBNF_ENGINE_VENV` puts it elsewhere) |
| an unpacked engine a newer file replaced | `%LOCALAPPDATA%\FluBNF\PyBNF-Private.replaced-<date and time>` |
| the record of a failed install | `.venv\engine-attempt.txt` in the FluBNF folder |
| FluBNF's own Perl | `%LOCALAPPDATA%\FluBNF\perl` (`flubnf-perl.ok` marks it whole) |
| the record of the Perl offer | `.venv\perl-offer.txt` in the FluBNF folder |

None of these is in a folder Controlled Folder Access protects.

The environment is built with 64-bit (x64) Python 3.12 or 3.11 and no
other: the engine pins `numpy<2`, which has no Windows wheels past Python
3.12, and `numpy<2`, bngsim and libroadrunner have Windows wheels for x64
only. An environment whose Python is another version or build, no longer
starts, or has no pip is rebuilt. `FluBNF.bat` tries `py -3.12`,
`py -3.11`, a `python` on PATH, then Anaconda's own Python, with one line
each saying what it found. When none fits and Anaconda is there, it asks
conda for an x64 Python 3.12 in `%USERPROFILE%\.venvs\flubnf-engine-py312` and builds the
environment from that. Anaconda (or Miniconda, Miniforge) is found
through `CONDA_EXE`, which Anaconda Prompt sets, then the folder its
installer records in `%USERPROFILE%\.conda\environments.txt`, then the
installers' usual folders, `C:\anaconda3` and `C:\anaconda` among them
(the installer will not use a profile folder whose name has a space).
Before it installs the packages, `FluBNF.bat` checks for five seconds
that this network reaches pypi.org, where they come from.

When more than one engine folder exists, the first of these that holds an
engine (a `.git` folder or `pybnf\pf.py`) is used:

1. the folder `FLUBNF_PYBNF` names, if it holds one,
2. `%USERPROFILE%\Documents\GitHub\PyBNF-pf`,
3. `%LOCALAPPDATA%\FluBNF\PyBNF-pf`,
4. `%USERPROFILE%\Documents\GitHub\PyBNF-Private`,
5. `%LOCALAPPDATA%\FluBNF\PyBNF-Private`.

`setup.ps1` searches the same list the same way, and `flubnf/settings.py`
the same folders in the same order; the console `FluBNF.bat` starts is told
which one it found. `%USERPROFILE%\GitHub` is where the macOS setup puts
things and is not searched on Windows. While a folder higher in the list
holds an engine, a new engine file is not unpacked at all, so an old clone
under `Documents\GitHub` keeps winning. Renaming it (to `PyBNF-pf-old`, say)
takes it out of the search.

### Updates

FluBNF updates itself each time `FluBNF.bat` opens. The engine is a
separate folder, and what happens to it depends on how it was installed.

- **From `pybnf-pf-<sha>.tar.gz`.** The unpacked copy has no git history,
  so nothing can update it in place. When the lab sends a newer file, save
  it in Downloads and open `FluBNF.bat` again. A file whose version stamp
  differs, and which is newer than the copy on disk, replaces it; an older
  one never does. The copy it replaces is renamed to
  `PyBNF-Private.replaced-<date and time>`, never deleted, and is put back
  if the new file does not unpack.
- **A git clone** (from `pybnf.bundle`, GitHub Desktop or `git clone`).
  After its own update, `FluBNF.bat` runs `flubnf engine-update`. A clone
  on `feature/particle-filter` with no edits to its tracked files, behind
  the production build, is fast-forwarded to exactly that commit. When the
  commit is not on disk yet it is fetched from GitHub first, with no
  password prompt and a 30-second limit. Anything else is left as it is,
  and the reason is printed in the window on a line starting `engine:`.

To skip both updates for one open, for example while trying another build,
open Command Prompt in the FluBNF folder and run
`set FLUBNF_UPDATE=off`, then `FluBNF.bat`, in that window.

### "not the production build"

When the engine is any build other than the production one (`2fdadee0` on
`feature/particle-filter` for the 2026-27 season), or has local edits, the
Home page's Setup card and the Forecast tab's Engine row carry a warning:

```
The engine is feature/particle-filter at 1a2b3c4d, not the production build 2fdadee0 on feature/particle-filter.
```

For a clone the update left alone, it goes on with
`FluBNF tried to update it when it opened:` and the reason, and its "?"
gives the fix for this machine. By what it says:

| the warning says | what to do |
|---|---|
| installed from an archive | Save `pybnf-pf-2fdadee0.tar.gz` in Downloads and open `FluBNF.bat` again. |
| tracked files have local edits | `git -C "<engine folder>" stash`, then open `FluBNF.bat` again. `git -C "<engine folder>" stash pop` brings the edits back. |
| it is on another branch, or on a detached HEAD | `git -C "<engine folder>" checkout feature/particle-filter`, then open `FluBNF.bat` again. |
| could not fetch it from GitHub | This machine cannot read the private fork. Give it access ([ENGINE.md](ENGINE.md), "Through GitHub instead"), or change to the lab's file: rename the engine folder (add `-old`), save the file in Downloads and open `FluBNF.bat`. |
| it has newer commits, or its history does not lead to the production build | A research build, which may be on purpose. To go back, rename the folder and install from the lab's file as in the row above. |

`<engine folder>` is the folder the warning names; keep the quotation
marks, since a profile path can hold a space. The lines work from any
folder, in Command Prompt or PowerShell. [ENGINE.md](ENGINE.md), "Which
engine am I running?", shows how to read the build by hand.

### If the install fails

The console starts anyway, with analogue forecasts only, and the window
says

```
Engine setup did not finish (see above). The console still runs,
analogue forecasts only. With the engine file still in your Downloads
folder, or the engine folder still in place, the next open tries again.
```

The lines above it name the cause and one step that works on this PC.
The usual ones, by what the window says:

- `This network does not reach the Python package index (pypi.org)`: the
  engine's packages come from there, once. Open `FluBNF.bat` on another
  network, such as home Wi-Fi or a phone's hotspot.
- `pip could not install the engine's packages`: pip's error is above it.
  If the connection dropped, open `FluBNF.bat` again; pip reuses what it
  already downloaded.
- `No Python on this PC can run the engine`: none is 64-bit (x64) 3.12
  or 3.11, and there is no Anaconda to make one. Where the Python install
  manager is installed, the window says to run `py install 3.12`;
  otherwise, and on a PC with an ARM processor, it says to install
  Anaconda. An Anaconda installed in a folder FluBNF does not know is
  found when `FluBNF.bat` runs from Anaconda Prompt.
- `conda did not make a Python the engine can use`: conda's own messages
  are above it. When they name a command to run (`conda tos accept ...`),
  run it in Anaconda Prompt.
- `The engine's packages are installed, but the engine does not load`:
  when `msvcp140.dll` is missing from `Windows\System32`, the window says
  to install the Visual C++ Redistributable for x64 from
  https://aka.ms/vc14/vc_redist.x64.exe, which asks for an administrator.
  Otherwise it prints a `ren` line that sets the engine's Python
  environment aside, so the next open builds a fresh one.
- the engine venv `could not be deleted` for a rebuild: a program still
  has a file in it open. Close every other FluBNF window, or restart
  Windows.
- Python could not make the engine venv, or pip would not go into it: a
  full disk (free about 1 GB) or antivirus holding pip's files.
- the archive did not unpack: the download did not finish, so fetch the
  file again. Windows 10 before version 1803 has no `tar.exe` at all;
  update Windows, or ask for `pybnf.bundle`.
- `git is not on PATH`, for a bundle: install Git for Windows, or use the
  `.tar.gz`, which needs no git.

Apart from that `ren` line, nothing needs resetting between tries: every
open tries again for as long as the engine file or folder is there.
`.venv\engine-attempt.txt` records the failed attempt and stops the
retries only when there is nothing left to install from (no engine file,
no engine folder); the window then says `PF engine still not installed`,
asks for the file and lists the folders it looked in.

For a fuller account of what this machine can see, run `setup.ps1` in
Command Prompt:

```
cd /d "%LOCALAPPDATA%\FluBNF\flubnf"
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

(with your own FluBNF folder in the first line, if it is elsewhere). It
reports on the engine environment and names the engine file `FluBNF.bat`
would install from, in which case it does not check GitHub at all, since
the file needs no account. With no file, it says where it looked and
whether this machine can reach the private fork. For the GitHub routes
(GitHub Desktop, the GitHub CLI, SSH) see [ENGINE.md](ENGINE.md).

## When FluBNF.bat cannot update itself

The update is a fast-forward and nothing else, so it never overwrites
anything. When it cannot go through, `FluBNF.bat` runs the copy on disk and
says why:

- `offline (origin unreachable)`: it catches up on the next open.
- `local edits are blocking the update`: it sets them aside with
  `git stash` and updates anyway, and prints the commands that list them
  and put them back.
- `origin rewrote its history`: every commit here is upstream already,
  under a new id, so nothing unique would be lost by taking origin's copy.
- `this clone has N commit(s) origin does not`: work committed in this
  folder. It prints the reset that would discard it and leaves the choice
  to you.
- `origin/<branch> no longer exists`: the branch this folder follows was
  deleted or renamed upstream. FluBNF ships from `main`, and it prints the
  `checkout` line that moves the folder there.

The commands it prints name the FluBNF folder (`git -C "<folder>" ...`)
and stand one to a line, because the console holds that window: open a new
Command Prompt or PowerShell window and paste them one at a time.

Main's history was rewritten once, in September 2026: the commits made
from early September up to the rewrite were given new ids. A clone that
updated itself in between cannot fast-forward past it, and its
`FluBNF.bat`, the old one, which cannot update either, says
`offline or local changes - running as-is` or
`this clone has N commit(s) origin does not ... throw this clone's work away`
on every open. If you never committed anything in that folder, those
commits are the lab's own under their old ids, and nothing of yours is lost
by the reset. The reset in place, which keeps `app\state`, and a
reinstall from scratch are in
[INSTALL-STUDENTS.md, "Resetting or reinstalling (Windows)"](INSTALL-STUDENTS.md#resetting-or-reinstalling-windows).
Deleting the folder and cloning again is not the fix: it loses your runs
and leaves the old engine, which lives outside the folder, where it was.

## Controlled Folder Access

**Read this section first if any of these happened: a `git clone` or a
`git pull` failed with a permission error that makes no sense; a Python
import failed to write its cache; a fit stopped partway through; or Windows
showed you a Defender pop-up naming this project.**

**Nothing is wrong with your computer and nothing is infected.** A Defender
pop-up about FluBNF is not a virus alert and not damage. Controlled Folder
Access stopped one program from writing to one folder because it did not
recognise the program. Nothing was deleted, encrypted or changed, no data
was lost, and every one of these situations is fixed by the remedies below.
If a fit stopped, it stopped because of the block; re-run it once the block
is dealt with.

Controlled Folder Access is the ransomware protection built into Microsoft
Defender. **Microsoft ships it turned off** -- "CFA is turned off by
default", with mode `0`, Disabled, marked as the default. It was
nevertheless **on** on the corresponding author's Windows 11 machine, and
something had to turn it on: the user, the manufacturer's image, or IT
policy on a managed machine. University-managed machines are exactly where
that last one is likely, which is to say exactly the machines the
undergraduates use. So this is neither universal nor rare, and the project's
defaults are chosen so that it does not matter which you have.

When it is on, it protects these folders for every user account and system
account on the machine:

`Documents`, `Favorites`, `Music`, `Pictures` and `Videos` under each user
profile, plus `C:\Users\Public\Documents`, `\Music`, `\Pictures` and
`\Videos`. Microsoft's page describes `Desktop` as protected when it is
redirected by OneDrive Known Folder Move but does not list it among the
defaults; this project treats it as protected anyway, because a warning too
many costs a paragraph and a warning too few costs a day. An administrator
can add further folders, and `setup.ps1` asks the machine for its own list
rather than relying on any of the above.

A protected folder can be read by anything and written only by programs
Defender trusts. `git.exe`, `python.exe` and `perl.exe` are not trusted out
of the box.

FluBNF is unusually good at tripping it. The project writes into checkouts
constantly rather than only reading from them:

- the FluSight hub is a git clone that is pulled on every setup run, so
  `git.exe` writes into it every time;
- the PyBNF engine is imported straight from its checkout (the generated
  runners do `sys.path.insert(0, <checkout>)`), so `python.exe` writes
  `__pycache__` directories inside it on first import;
- fits materialize BNGL models at runtime and hand them to BioNetGen, which
  runs `BNG2.pl` under a Perl interpreter that writes generated network
  files next to the model. Those live in `app\state\workroots\<tag>`
  **inside the repository**, so a repository cloned into `Documents` -- the
  GitHub Desktop default -- breaks partway through a fit even when the hub
  and the PyBNF checkout are somewhere safe. For that one, remedy 1 means
  moving the whole repository.

Every one of those is a write, by an untrusted executable, into a folder the
old defaults put inside `Documents`.

### What it looks like when it happens

The failure text never mentions Defender. `git` reports an ordinary
permission or "unable to create file" error; Python reports an import or
cache-write failure. The block is recorded only in Defender's own log.

This is the field case, from the corresponding author's Windows 11 machine
on 2026-08-25, verbatim from **Applications and Services Logs > Microsoft >
Windows > Windows Defender > Operational**:

```
5:49:52 PM  Id 1123: git.exe has been blocked from modifying
            %userprofile%\Documents\GitHub\FluSight-forecast-hub
5:50:12 PM  Id 5007: ...AllowedApplications\git.exe = 0x0
8:46:37 PM  Id 1123: python.exe has been blocked from modifying
            %userprofile%\Documents\GitHub\PyBNF-pf\pybnf\__pycache__
8:46:57 PM  Id 5007: ...AllowedApplications\python.exe = 0x0
```

Event **1123** is the block itself. Event **1124** is the same thing in
audit mode, where Defender logs what it would have blocked and blocks
nothing. Event **5007** is a settings change: the two above are the moment
each executable was added to the allow-list, which is what the Windows
pop-up does when a user clicks through it. That pairing is why the problem
was so hard to see the first time: the initial attempt failed invisibly, the
user clicked "Allow" on a prompt, and the retry then worked, so the failure
looked intermittent rather than caused.

### The two commands that reveal it

```powershell
Get-MpPreference | Select-Object EnableControlledFolderAccess
Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" |
  Where-Object { $_.Id -eq 1123 } |
  Select-Object -First 20 TimeCreated, Message
```

`EnableControlledFolderAccess` has five documented values: `0` disabled (the
shipped default), `1` enabled, `2` audit mode, `3` block disk modification
only and `4` audit disk modification only. Modes `3` and `4` act only on the
disk sectors holding the boot record and, in Microsoft's words, "don't
affect files in protected folders", so for this project they are equivalent
to off and `setup.ps1` reports them that way.

On the machine above it reads `1`. Since Microsoft ships `0`, that reading
means the setting was turned on there -- by the author, by the machine's
image, or by policy. Which of those it was, we cannot tell from the value.

### What setup.ps1 does about it

`setup.ps1` runs both queries for you, before it installs anything, and
handles the cases where the Defender module is absent or the cmdlet errors
by saying so rather than by assuming an answer. It also asks Defender for
the machine's own protected-folder list, so a folder your IT department
added is covered too, and falls back to the documented defaults when the
machine will not answer. If Controlled Folder Access is on (or in audit
mode, or unreadable) **and** one of the paths it is about to use lies inside
a protected folder, it prints the risk and the remedies and then carries on.
It never changes a Defender setting, never elevates, and never suggests
switching the protection off.

It also declines to record `FLUBNF_HUB` after a clone that failed. An
earlier release recorded it unconditionally, which pinned the failing
location into the user environment and sent every later run straight back to
it; if your machine is in that state, `setup.ps1` now names the stale
variable and prints the one `setx` line that clears it.

### Remedies, best first

1. **Put the folder where Controlled Folder Access does not reach.** No
   administrator, and Defender is not touched at all. Move the FluSight
   data folder yourself first if you would rather not download 150 MB
   again. Move an engine folder first in any case, because setup never
   fetches the engine. Then:

   ```
   setx FLUBNF_HUB "%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub"
   setx FLUBNF_PYBNF "%LOCALAPPDATA%\FluBNF\PyBNF-Private"
   ```

   Give the engine line your engine folder's own name: `PyBNF-Private`
   (GitHub Desktop's name for it) or `PyBNF-pf`. An engine installed from
   the lab's file is under `%LOCALAPPDATA%` already and needs neither the
   move nor the line.

   Open a **new** window afterwards, so the setting is visible, and re-run
   `setup.ps1`. For the repository itself there is no variable: move the
   whole folder out of `Documents` and run `FluBNF.bat` from its new home.
   Its `.venv` does not survive a move, because the programs in it still
   name the old folder. `FluBNF.bat` notices on the next open, renames it to
   `.venv.moved-<date and time>` and builds a new one, which takes a few
   minutes; deleting `.venv` yourself before that open does the same.
   Everything else moves with the folder, `app\state` included. GitHub
   Desktop then lists the repository as missing, and **Locate...** points
   it at the new folder.

2. **Allow the specific executables through.** This needs an administrator.
   Windows Security > Virus & threat protection > Ransomware protection >
   Manage ransomware protection > Allow an app through Controlled folder
   access > Add an allowed app. Five are worth adding, and `setup.ps1`
   prints the full path of each:

   | executable | usual location | what it writes |
   |---|---|---|
   | `git.exe` | `C:\Program Files\Git\cmd\git.exe` | the FluSight hub clone and every later pull |
   | `python.exe` (console venv) | `<repo>\.venv\Scripts\python.exe` | the app itself, and `__pycache__` |
   | `python.exe` (engine venv) | `%USERPROFILE%\.venvs\flubnf-engine\Scripts\python.exe` | `__pycache__` inside the PyBNF checkout |
   | `perl.exe` | `C:\Strawberry\perl\bin\perl.exe` | `m.net`, from `BNG2.pl`, during a fit |
   | `run_network.exe` | `<repo>\.venv\Lib\site-packages\bionetgen\bng-win\bin\run_network.exe` (older wheels omit the `bin\`; setup.ps1 prints the path that actually exists on your machine) | simulation output, during a fit |

   `git.exe` and `python.exe` are the two Defender actually logged as
   blocked above. `perl.exe` and `run_network.exe` are on the list because
   they write during a fit rather than during setup: leave them out and
   setup will look perfect and the first fit will not.

   **If those controls are greyed out**, or Windows Security says the
   setting is managed by your organisation, then Controlled Folder Access
   was set by Group Policy or Intune. Remedy 2 is then unavailable to you
   even as a local administrator, and remedy 1 is the route that works.

3. **Last resort, and it reduces protection: a folder exclusion.** Microsoft
   is explicit that "You can't modify the list of default protected
   folders", so the only folder-level lever is a Microsoft Defender
   exclusion path, which weakens antivirus coverage of that folder for
   everything on the machine rather than for FluBNF alone -- and we have not
   been able to confirm that it exempts Controlled Folder Access at all.
   Prefer 1 or 2, and do not switch Controlled Folder Access off.

### Where things go by default now

| what | default | protected? |
|---|---|---|
| FluSight hub (`FLUBNF_HUB`) | `%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub` | no |
| PyBNF engine (`FLUBNF_PYBNF`) | `%LOCALAPPDATA%\FluBNF\PyBNF-Private` from the lab's file, `%LOCALAPPDATA%\FluBNF\PyBNF-pf` for a clone | no |
| engine venv (`FLUBNF_ENGINE_VENV`) | `%USERPROFILE%\.venvs\flubnf-engine` | no; the profile **root** is not protected, only the named folders inside it |
| the repository itself | wherever you cloned it | `Documents` is, `%LOCALAPPDATA%` is not |

`%LOCALAPPDATA%` was chosen over the alternatives because it is the
documented per-user application data location (`FOLDERID_LocalAppData`), it
is not in the protected set, it needs no administrator, and -- unlike
`%APPDATA%` -- it neither roams nor gets swept into OneDrive by Known Folder
Move, which matters for a 150 MB clone made of tens of thousands of small
files. `C:\FluBNF` was rejected: creating a directory at the root of the
system drive requires elevation on a default install.

**An existing checkout under `Documents` is reused exactly where it is.**
`setup.ps1`, `FluBNF.bat` and `flubnf/settings.py` all resolve in the same
order -- the `FLUBNF_*` variable, then an existing directory at the old
`Documents\GitHub` path, then the new default -- so a machine set up before
this change keeps working with no action. The engine follows the same rule
with two names and one more condition, a folder counting only when an
engine is in it; the full list is under
[Where it goes](#where-it-goes). Nothing is ever moved or copied
for you: the author's own machine has 143 MB of PyBNF checkout and 150 MB of
hub under `Documents`, and relocating a working tree is not a decision a
setup script gets to take. The reuse is announced in the plan block, and
named again in the warning when the protection is on.

All three resolvers anchor on `%USERPROFILE%`. That is what `FluBNF.bat`
reads and what Python's `expanduser` prefers, and `setup.ps1` prefers it
too rather than using PowerShell's `$HOME`, which the PowerShell 5.1
documentation described as `%HOMEDRIVE%%HOMEPATH%` and which can therefore
be a mapped `H:\` or a UNC path on a domain-managed machine with an Active
Directory home directory. When the two disagree, `setup.ps1` looks under
both before falling back to the new default, so a checkout an earlier
release made under either one is still found rather than silently
re-cloned.

## Defender real-time scanning

This is a **different setting from Controlled Folder Access**, with a
different symptom, and the two are easy to confuse because both are
Microsoft Defender and both can put a notification on your screen.

| | Controlled Folder Access | real-time scanning |
|---|---|---|
| what it does | refuses a write | allows the write and inspects it |
| what you see | a permission error, and the run stops | nothing, and the run takes longer |
| shipped state | off (mode `0`) | on |
| section | the one above | this one |

Because nothing fails, there is no error message to search for and nothing
to diagnose from. The only symptom is that a thing that should take a minute
takes ten.

### The evidence, and what is still a guess

`.github/workflows/tests.yml` runs one test suite on `ubuntu-latest` and the
same suite on `windows-latest`. On CI the ubuntu legs take about 5 minutes,
the windows legs 60 to 70, and the `windows-setup-script` job on the same
runner image about 3. The few Windows failures are nowhere near an hour of
work, and the setup-script job rules out the runner hardware. What is left is
the shape of the workload: this suite creates many temporary directories and
spawns many subprocesses, which is exactly what real-time scanning is most
expensive against. The corresponding author also sees live Defender
notifications while running this project on his own Windows machine.

That is a strong hypothesis and it is still labelled one. Both the ubuntu and
the windows jobs run pytest with `--durations=25 --durations-min=1.0` and
write the table into the job summary: a flat ratio across every test reads as
an environment cost, a handful of tests carrying the whole hour as a specific
defect. An earlier CI step that excluded the windows workspace from Defender
on one leg, as a control, has since been removed; CI no longer changes
Defender at all.

### What setup.ps1 does about it

It reads two Defender properties and prints what it was told, before it
installs anything:

```powershell
Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled, AntivirusEnabled
Get-MpPreference | Select-Object ExclusionPath, ExclusionProcess
```

and reports whether real-time protection is on, and whether the folders this
project works in are already covered by an exclusion somebody added
earlier. If scanning is off, or everything is already excluded, it says so
in one line and moves on.

It **never adds an exclusion, never changes a Defender setting, and never
elevates.** The reason is not caution for its own sake. An exclusion is a
genuine reduction in protection for a real folder on a machine somebody else
owns, it needs an administrator, and on a managed university laptop it is
frequently forbidden by policy. A setup script that quietly weakened
antivirus coverage as part of "installing FluBNF" would be doing something
nobody agreed to.

To see the full instructions, run it once with the switch:

```
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -ShowDefenderExclusion
```

That switch prints and changes nothing. It exists as a switch rather than a
question because `FluBNF.bat` runs `setup.ps1` with `-NoPrompt` on the
double-click path, so a prompt would be invisible exactly where it matters,
and a default would be a change nobody asked for.

### The exclusion, if you decide you want it

Read this whole subsection before running anything in it.

**What it would do.** Stop Defender inspecting every file this project
writes, which is the thing that would make runs faster.

**What it would not do.** It would not make FluBNF safer, easier to install,
or better in any other way, and it does not reliably exempt Controlled
Folder Access, which is the separate setting in the section above. If your
problem is a `git` or `python` write that FAILS, this is not the remedy;
go back to that section.

**What it costs.** Those folders stop being scanned for **everything** on
the machine, not just for FluBNF, until the exclusion is removed. It needs
an administrator. On a managed laptop the option is often greyed out or
blocked by policy, and **that answer is fine**: nothing in this project
depends on it, and the only difference is speed.

The route that needs no command line is Windows Security > Virus & threat
protection > Virus & threat protection settings > Manage settings >
Exclusions > Add or remove exclusions > Add an exclusion > Folder.

The equivalent commands, in a PowerShell window opened with **Run as
administrator**. Run `setup.ps1 -ShowDefenderExclusion` first: it prints the
folders that actually resolved on your machine, which is what belongs in
these lines.

```powershell
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\FluBNF"
Add-MpPreference -ExclusionPath "<the folder holding FluBNF.bat>"
```

To see what is excluded now, and to undo it:

```powershell
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
Remove-MpPreference -ExclusionPath "$env:LOCALAPPDATA\FluBNF"
```

Removing it is exactly as easy as adding it, which is most of why this is
worth offering at all rather than hiding.

Two paths are enough for the common install: `%LOCALAPPDATA%\FluBNF` covers
the hub clone and the PyBNF checkout, and the repository folder covers the
console virtual environment, every `__pycache__`, and `app\state\workroots`,
where a fit writes its model and its generated network. If you moved
anything with `FLUBNF_HUB`, `FLUBNF_PYBNF` or `FLUBNF_ENGINE_VENV`, the
switch above prints where they went.

A narrower alternative, if excluding a folder is more than you want: exclude
the process instead of the path, with `-ExclusionProcess "python.exe"`. It
is narrower in one sense and broader in another, since it stops scanning
that executable's file activity everywhere rather than in one folder, so it
is offered as a choice and not as a recommendation.

### What is unverified here

Everything in this section about the Defender cmdlets was written on macOS
from Microsoft's documentation; since then `setup.ps1`'s read path has run
on real Windows (the 2026-08-25 field tests) as well as in CI. Still taken
from documentation rather than measured here: that `Get-MpComputerStatus`
exposes
`RealTimeProtectionEnabled` in the form `setup.ps1` matches, that
`Get-MpPreference` carries `ExclusionPath` and `ExclusionProcess` as lists,
and that the `Add-MpPreference` and `Remove-MpPreference` lines above run as
written in an elevated Windows PowerShell 5.1 window.

`setup.ps1` takes the read path only, and the `windows-setup-script` job is
the only CI exercise of it. Nothing runs the write path
(`Add-MpPreference`, `Remove-MpPreference`): the CI measurement step that
once called `Add-MpPreference` on a throwaway runner was removed.

The causal claim itself is unmeasured. This section says that Defender
real-time scanning is the leading explanation for the gap, not that it is
the cause.

## A hub cloned by hand

`git clone --sparse` is documented to check out **only the files in the
repository root**. A hub cloned by hand with

```
git clone --filter=blob:none --sparse --depth 1 https://github.com/cdcepi/FluSight-forecast-hub "%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub"
```

therefore succeeds, prints no error, and contains no `auxiliary-data`, no
`target-data` and no `model-output`. The console opens on "Latest vintage:
none" exactly as if nothing had been cloned. This happened in the field on
2026-08-25, and it was invisible because every gate tested for the clone
rather than for its contents.

`setup.ps1` now widens an existing sparse checkout with `git sparse-checkout
add` before it reapplies anything, because `reapply` re-applies the cone
already recorded and that cone is empty. It uses `add` rather than `set`:
`add` extends a cone and fails harmlessly on a full clone, whereas `set`
would delete every directory it is not given, gutting the checkout of
anyone who deliberately cloned the whole hub. `setup.sh` does the same on
macOS and Linux, and `flubnf doctor` now tests for the data directories, so
it can no longer report "you are ready" over an empty clone.

Re-running `setup.ps1` is the repair. Nothing has to be deleted or
re-cloned.

To run the full first-time setup yourself, from the repository folder:

```
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

It prints where everything will be installed before installing anything,
fetches the sparse FluSight hub clone (about 150 MB), records the
environment, and reports what is still missing. It is idempotent:
re-running it updates an existing hub clone and fixes whatever is absent.

`-NoProfile` is not decoration. A PowerShell profile that sets
`$ErrorActionPreference = "Stop"` turns every line git writes to stderr
into a script-ending error, because Windows PowerShell surfaces native
stderr as error records.

Useful switches and variables:

| what | effect |
|---|---|
| `-NoPrompt` | ask nothing at all. `FluBNF.bat` always passes it; the one question it suppresses is `setup.ps1`'s own offer to let winget install Strawberry Perl, which is then printed as a command to run later. The double-click path is not left without Perl: `FluBNF.bat` checks for a Windows Perl on every open, installs FluBNF's own when there is none (no administrator), and asks its own time-bounded winget question once only when that fails (see [Perl](#perl)). Run `setup.ps1` by hand to be asked here too. |
| `-ShowDefenderExclusion` | print the antivirus-exclusion instructions in full, with the folders that resolved on this machine. Changes nothing, needs no administrator, and is never implied by any other run. See "Defender real-time scanning" above. |
| `FLUBNF_HUB` | put the FluSight data somewhere else, e.g. `setx FLUBNF_HUB D:\FluSight-forecast-hub`, then open a new window. Default: `%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub`, or an existing clone at the old `%USERPROFILE%\Documents\GitHub\FluSight-forecast-hub` if one is there |
| `FLUBNF_PYBNF` | the PyBNF engine folder, used only when an engine is in it (a `.git` folder or `pybnf\pf.py`); otherwise the first engine in the list under [Where it goes](#where-it-goes). A clone made by hand defaults to `%LOCALAPPDATA%\FluBNF\PyBNF-pf` |
| `FLUBNF_PYBNF_BUNDLE` | an engine file (`pybnf-pf-<sha>.tar.gz` or `pybnf.bundle`) kept outside the folders searched; `FluBNF.bat` installs from it and `setup.ps1` names it |
| `FLUBNF_ENGINE_VENV` | the engine virtual environment. Default `%USERPROFILE%\.venvs\flubnf-engine` |
| `FLUBNF_NO_DATA=1` | skip the data clone entirely |
| `FLUBNF_NO_PROBE=1` | skip the read-only check for access to the private PyBNF fork |

The exit code is a statement about setup, not about the externals.
`setup.ps1` exits 0 whenever it finished its work, including on the ordinary
machine that has no access to the private PyBNF fork and therefore ends with
"some externals missing". It exits non-zero only when setup itself could not
proceed: no Python 3.11 or newer, the virtual environment could not be
created, or the package would not install. That distinction is what lets
`FluBNF.bat` report a real problem without crying wolf on every healthy
first run, and the Windows CI job asserts it on all three of its runs.

`setup.ps1` writes `.flubnf.env.cmd` in the repository folder, the Windows
twin of the `.flubnf.env` that `FluBNF.command` sources on macOS.
`FluBNF.bat` calls it on every launch. It matters because the User-scope
environment variables `setup.ps1` also records reach only processes started
afterwards, so without the file a console launched from an already-open
window would still see nothing.

## WSL2 alternative

FluBNF runs unmodified under WSL2 (Ubuntu): install WSL, then follow the
standard `setup.sh` instructions inside the Linux environment.

## Limitations (current)

- **Fit scheduling priority.** Fit runners start below normal priority
  on Windows (`BELOW_NORMAL_PRIORITY_CLASS`, from
  `app/core/proc.py:low_priority_popen_kwargs`), as they start under `nice`
  on macOS and Linux, so the console stays responsive during long runs.
  That holds for forecasts, retrospective weeks and Sandbox fits alike,
  and what a runner starts, Perl included, inherits it. FluBNF's own
  BNG2.pl runs (network generation at preparation, the Sandbox's Check)
  run at normal priority, as they do on macOS and Linux.
- **PF engine.** The particle-filter engine needs three externals on
  Windows (`FluBNF.bat` installs the first two from the lab's engine file;
  see [The particle-filter engine on Windows](#the-particle-filter-engine-on-windows)):
  - the private PyBNF fork (pure Python; clones and installs normally),
  - `bngsim` (official Windows wheels exist on PyPI for Python 3.10-3.13,
    so `pip install bngsim` works without a compiler). Windows fits run
    with its code generation off (`BNGSIM_NO_CODEGEN=1`, set for every
    engine runner): bngsim would otherwise compile each model with a C
    compiler found on PATH, and a student's PC has none (bngsim's fallback
    then tells them to install Visual Studio Build Tools) or a gcc from
    another program whose library can compile and then not load, which
    fails every fit of that model from bngsim's cache. The interpreted
    right-hand side gives the same fit to about 1e-12 (same ESS, evidence
    and forecast quantiles on all five shipped examples, measured on
    Linux); quick checks take the same time and full fits about 15%
    longer. macOS and Linux keep code generation.
  - a Windows Perl, for BNG2.pl's network generation at fit prep. The
    `bionetgen` pip package ships the Windows BNG binaries (`bng-win`,
    including `run_network.exe`), but not a Perl interpreter.
    `FluBNF.bat` installs FluBNF's own, with no administrator (see
    [Perl](#perl)), or uses a Strawberry Perl already there.

  The Sandbox's `pf.conf` names no folder, so the engine reads it whatever
  the profile folder is called. The Forecast tab's still writes full
  paths, which the engine cannot read under a profile folder with a letter
  outside ASCII (José) or with `.con`, `.exp` or `.xml` in its name
  (m.contreras), so Forecast-tab fits fail for such an account. Perl reads
  its command line in the ANSI code page, so a FluBNF folder whose path
  holds letters outside it (Łukasz, 李明 on an English Windows) can stop
  BNG2.pl: move the folder to `C:\Users\Public\FluBNF\flubnf`, which needs
  no administrator. When such a path has no short (8.3) name, the Sandbox
  refuses before a run and says the same.

  What has run on native Windows, as recorded (add each new record here,
  with its date, machine and engine build):
  - 2026-09-01, in the Windows Sandbox VM: one console full grid of 159
    PF fits, 4 of which failed and were never diagnosed; 2 submissions
    were written and the report built (commit d461782). Perl was
    installed by hand, since that VM has no winget.
  - Nothing has been recorded since: no fit on the production engine
    `2fdadee0` (pinned 2026-09-25) or on the current launcher and runner
    code, no Sandbox-tab fit (the tab came on 2026-09-04), and no run of
    `FluBNF.bat`'s winget Perl install.

  Machines without the engine run the analogue engine only, exactly as on
  a Tier-A Mac.
- **Windows CI is required.** Three jobs in
  `.github/workflows/tests.yml` run on `windows-latest`, and a red Windows
  run fails the checks as a red Ubuntu one does. `test-windows` runs the
  test suite, which runs `FluBNF.bat`'s blocks in cmd.exe with stand-in
  programs (the update, a moved `.venv`, the engine file, `:sync`, the
  Perl offer with a stand-in winget, the engine venv;
  `tests/test_windows_launcher.py`). Then, in PowerShell, it runs the real
  BNG2.pl with the Strawberry Perl FluBNF resolves, on every shipped
  example and under folders named like awkward profile folders
  (`Jane Doe`, `O'Brien`, `José`; `app/tests/test_real_bng.py`), and stops
  first if that Perl is not Strawberry's. On the 3.12 leg a last step records
  whether bngsim opens a network file in a folder whose name is outside
  ASCII: a record in the run's summary, never a failure.
  `windows-own-perl` hides Strawberry, runs `FluBNF.bat`'s Perl block for
  real (the download, Windows' `tar.exe`, a profile folder named
  `Jane O'Brien (Lab)`; `tests/test_windows_own_perl.py`), then runs the
  real BNG2.pl under that Perl, and bngsim through a fit's calls with code
  generation off and no compiler on PATH
  (`app/tests/test_bngsim_no_codegen.py`). No job runs a real winget, a
  real engine venv build or a real fit.
  `windows-setup-script` is the only automated exercise of
  the first-run path: it parses `setup.ps1` under Windows PowerShell 5.1,
  then runs it five times through the command line `FluBNF.bat` uses --
  once with the data fetch skipped, once performing the real sparse
  FluSight clone, once more over the machine the second run configured,
  once against a hub cloned **by hand** with `--sparse`, which is the state
  the field report came from and the only one that can show whether the
  repair above works, and once against a machine that already holds a
  checkout at the old `Documents` location, which must be reused where it
  stands -- checking each transcript against what the script
  promised to say. It holds no credentials, so the engine is always missing
  there and the degraded path is what gets tested. It does not cover
  `FluBNF.bat` itself, the Perl/winget branch, or any non-ASCII profile
  path.

  Every job in that workflow carries a `timeout-minutes`, so a hang fails
  its job rather than running to GitHub's 6 hour default. The budgets are
  fuses, not targets: 20 minutes on ubuntu, which finishes in about 5, 90
  on windows, which took 71 at its worst, 30 for `windows-own-perl` (a
  31 MB download and a few BNG2.pl runs), and 60 for
  `windows-setup-script`. The windows number should come down a long way
  once the hour is accounted for, because a fuse sized far above the load
  never blows.
- **The windows suite takes an hour and nobody yet knows on what.** 62 and
  71 minutes against ubuntu's 5, with only 6 failures, so the failures are
  not the hour. Defender real-time scanning is the leading explanation and
  the section above says why, what was added to measure it, and what a
  student can do about it on their own machine if they want to. Nothing in
  the project depends on their doing anything.
- **The PowerShell is not run on the development host.** The lab develops
  on macOS, so `setup.ps1` was written from the language rules. The git
  behaviour it depends on (`--sparse` checking out the root only, `reapply`
  adding nothing, `add` being idempotent, `set` pruning a full clone,
  `pull --ff-only` succeeding against a shallow blobless sparse clone) was
  measured locally on git 2.39.5, because that is git behaviour rather than
  platform behaviour, and the equivalent bash in `setup.sh` was executed
  against five clone states. The script itself has since run on real
  Windows (field tests, 2026-08-25; a Windows Sandbox first run,
  2026-09-01) as well as in CI, which remains the routine check of every
  change.
- **The Controlled Folder Access detection is unverified against a machine
  that has it on.** The GitHub runner is not such a machine, so what CI
  can show is that `Get-MpPreference` is queried without crashing and that
  the section prints. These things behind it are read from Microsoft's
  documentation rather than measured here:
  - that Controlled Folder Access is **off** in the shipped state
    (Microsoft's own page says "CFA is turned off by default"), so a
    machine that has it on was configured that way by its user, its image,
    or policy;
  - that `EnableControlledFolderAccess` reports `0` through `4` in the form
    this script matches (both the number and the enumeration name are
    accepted, so either rendering is handled), and that modes `3` and `4`
    leave protected folders alone;
  - that the default protected set is `Documents`, `Favorites`, `Music`,
    `Pictures` and `Videos` under each profile plus the `C:\Users\Public`
    counterparts, and cannot have its defaults removed. `Desktop` is
    treated as protected here even though the current page omits it from
    that list;
  - that a policy-managed machine greys out the Windows Security ransomware
    controls, which is why remedy 2 carries a caveat. Microsoft documents
    Group Policy and Intune as configuration methods; that the local UI is
    then unavailable is the standard Windows behaviour for a managed
    setting, and is not something this lab can demonstrate;
  - and that a Microsoft Defender exclusion path does **not** reliably
    exempt Controlled Folder Access, which is why remedy 3 is marked as
    unconfirmed as well as last.

  The event IDs, the block text and the `EnableControlledFolderAccess = 1`
  reading are not from documentation: they were taken off the corresponding
  author's own machine.
- **`$HOME` versus `%USERPROFILE%` in PowerShell is unsettled here.** The
  PowerShell 7 documentation says `$HOME` takes `%USERPROFILE%` and warns it
  "may not have the same value as `$Env:HOMEDRIVE$Env:HOMEPATH`"; the 5.1
  documentation described it as the equivalent of `%homedrive%%homepath%`.
  We cannot run 5.1 here to settle which applies, so `setup.ps1` no longer
  depends on the answer: it anchors on `%USERPROFILE%`, matching
  `FluBNF.bat` and `flubnf/settings.py`, and probes both spellings when
  looking for something that already exists.
