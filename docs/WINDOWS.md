# FluBNF on Windows

Native Windows support is in active bring-up. The console, the analogue
engine, data fetching, scoring, and reports are expected to work; the PF
fitting engine has additional requirements listed under Limitations.

## Supported path (lab laptops)

Install once:

1. A Python. Anaconda from https://www.anaconda.com/download is the lab's
   standard and needs no settings changed: `FluBNF.bat` and `setup.ps1`
   probe the folders it installs into, so nothing is added to PATH.
   Python 3.11 or newer from https://www.python.org/downloads/ works too
   (tick "Add python.exe to PATH" in the installer).
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
protected folder is one `git.exe` is not allowed to write into. The next
section is the whole story; if you already have a clone under `Documents`
it keeps working and nothing needs moving.

Double-click `FluBNF.bat` in that folder. The first run creates the
virtual environment and installs dependencies (a few minutes); every later
run self-updates with a fast-forward `git pull` and starts the console.

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
   administrator, and Defender is not touched at all. Move the folder
   yourself first if you would rather not download 150 MB again, then:

   ```
   setx FLUBNF_HUB "%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub"
   setx FLUBNF_PYBNF "%LOCALAPPDATA%\FluBNF\PyBNF-pf"
   ```

   Open a **new** window afterwards, so the setting is visible, and re-run
   `setup.ps1`. For the repository itself there is no variable: move the
   whole folder out of `Documents` and run `FluBNF.bat` from its new home.

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
| PyBNF checkout (`FLUBNF_PYBNF`) | `%LOCALAPPDATA%\FluBNF\PyBNF-pf` | no |
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
this change keeps working with no action. Nothing is ever moved or copied
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
same suite on `windows-latest`. In run 33200477476:

| job | time |
|---|---|
| ubuntu, python 3.11 and 3.12 | about 5 minutes |
| windows, python 3.11 | 62 minutes |
| windows, python 3.12 | 71 minutes |
| `windows-setup-script`, same runner image | about 3 minutes |

Six tests failed on Windows, which is nowhere near an hour of work, so the
failures are not where the time goes. The setup-script job runs on the same
image and finishes in three minutes, so the runner hardware is not where it
goes either. What is left is the shape of the workload: this suite creates
many temporary directories and spawns many subprocesses, which is exactly
what real-time scanning is most expensive against. The corresponding author
also sees live Defender notifications while running this project on his own
Windows machine.

That is a strong hypothesis and it is deliberately still labelled one. Two
things were added so the next CI run answers it with numbers instead:

- both the ubuntu and the windows jobs now run pytest with
  `--durations=25 --durations-min=1.0`, and each writes its table into the
  job summary. Read side by side, a flat ratio across every test reads as an
  environment cost, and a handful of tests carrying the whole hour reads as
  a specific defect;
- the windows job excludes its own workspace from Defender on the **3.12 leg
  only**, so one run carries its own control. The legs differ in Python
  version as well, which is a confound, but it runs against the hypothesis:
  3.12 is currently the slower leg, so a 3.12 run that lands below 3.11
  cannot be explained by the version.

Doing that to a GitHub-hosted runner is a much smaller thing than doing it
to a laptop. The runner is an ephemeral virtual machine that exists for the
length of the job, holds no credentials, and is destroyed afterwards, so
nothing is left less protected than it was. That is why the CI job may do it
and `setup.ps1` may not.

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
therefore the only CI exercise of it. The test job is the exception and is
worth being plain about: its `MEASUREMENT` step really does call
`Add-MpPreference -ExclusionPath` and `-ExclusionProcess`, so a CI run does
exercise the write path, on a throwaway runner and nowhere else. If those
lines turn out to be wrong they will be wrong there first, which is the
point of putting them there and not on a laptop. `Remove-MpPreference` is
run nowhere: the runner is discarded instead.

And the causal claim itself is unmeasured until a CI run comes back with the
duration tables. Until then this section says that Defender real-time
scanning is the leading explanation for a 12x gap, not that it is the cause.

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
| `-NoPrompt` | ask nothing at all. `FluBNF.bat` always passes it; the one question it suppresses is `setup.ps1`'s own offer to let winget install Strawberry Perl, which is then printed as a command to run later. The double-click path is not left without the offer: `FluBNF.bat` asks its own time-bounded Perl question during engine install. Run `setup.ps1` by hand to be asked here too. |
| `-ShowDefenderExclusion` | print the antivirus-exclusion instructions in full, with the folders that resolved on this machine. Changes nothing, needs no administrator, and is never implied by any other run. See "Defender real-time scanning" above. |
| `FLUBNF_HUB` | put the FluSight data somewhere else, e.g. `setx FLUBNF_HUB D:\FluSight-forecast-hub`, then open a new window. Default: `%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub`, or an existing clone at the old `%USERPROFILE%\Documents\GitHub\FluSight-forecast-hub` if one is there |
| `FLUBNF_PYBNF` | the PyBNF fork checkout. Same resolution order; default `%LOCALAPPDATA%\FluBNF\PyBNF-pf` |
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

- **Fit scheduling priority.** On macOS and Linux, fitting subprocesses
  start under `nice` so the console stays responsive during long runs. The
  Windows equivalent (`BELOW_NORMAL_PRIORITY_CLASS`, provided by
  `app/core/proc.py:low_priority_popen_kwargs`) is not yet wired into the
  engine call sites, so fits run at normal priority and the console may
  feel sluggish during a run.
- **PF engine.** The particle-filter engine needs three externals on
  Windows:
  - the private PyBNF fork (pure Python; clones and installs normally),
  - `bngsim` (official Windows wheels exist on PyPI for Python 3.10-3.13,
    so `pip install bngsim` works without a compiler),
  - Perl, for the one-time BNG2.pl network-generation step at fit prep.
    The `bionetgen` pip package ships the Windows BNG binaries
    (`bng-win`, including `run_network.exe`), but not a Perl interpreter;
    `FluBNF.bat` offers to install Strawberry Perl via winget when it
    installs the engine (time-bounded like the data offer, default yes),
    or install it yourself from https://strawberryperl.com.
  The PF engine has not yet been validated end to end on native Windows;
  until it is, machines without the engine automatically run the analogue
  engine only, exactly as on a Tier-A Mac.
- **Windows CI is experimental.** Two jobs in
  `.github/workflows/tests.yml` run on `windows-latest`, both with
  `continue-on-error`, so a red Windows run does not fail the checks while
  the port stabilizes. `test-windows (experimental)` runs the test suite.
  `windows-setup-script (experimental)` is the only automated exercise of
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
  path. Both jobs will be promoted to required checks once they have been
  green for a few consecutive weeks.

  Every job in that workflow now carries a `timeout-minutes`, because none
  of the test jobs did and a hang would therefore have run to GitHub's
  6 hour default while `continue-on-error` kept anyone from being told. The
  budgets are fuses, not targets: 20 minutes on ubuntu, which finishes in
  about 5, and 90 on windows, which took 71 at its worst. The windows number
  should come down a long way once the hour is accounted for, because a fuse
  sized far above the load never blows. `windows-setup-script` already had
  its own 60.
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
