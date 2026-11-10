# Installing FluBNF

For lab members. One line or one clone, then one double click. No GitHub
account is needed, and nothing has to be sent to you: the forecasting
engine downloads itself with everything else.

---

## Before you start

**macOS**: install Anaconda from <https://www.anaconda.com/download>,
defaults are fine; setup finds it with nothing added to PATH, and asks it
for the Python 3.12 the engine needs. If macOS offers to install "command
line developer tools" along the way, click Install: the engine needs them.
Git and Perl already ship with the system. An Intel Mac needs macOS 15 or
newer for the engine.

**Windows**: install these two first, both are normal installers with
defaults that are fine as they are.

* Anaconda, from <https://www.anaconda.com/download> (the lab's standard
  Python). No settings to change: FluBNF finds it where it installs. If
  your Windows user name has a space and the installer will not use the
  folder it suggests, install it in `C:\anaconda3`, which FluBNF also
  finds. FluBNF asks it for the 64-bit (x64) Python 3.12 the engine needs.
  On a laptop with an ARM processor (Snapdragon), Anaconda is the one to
  use.
* Git, from <https://git-scm.com/download/win>.

---

## Step 1: get FluBNF

**macOS**, paste this one line into Terminal:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
```

It puts FluBNF in `~/GitHub/flubnf`: the `GitHub` folder in your home
folder, then `flubnf`. To find it in Finder, choose **Go > Go to Folder**
and paste `~/GitHub/flubnf`.

**Windows**, open Command Prompt and run:

```
git clone https://github.com/elyfmiller/flubnf "%LOCALAPPDATA%\FluBNF\flubnf"
```

Put it there and not in `Documents`. Windows Defender has a feature called
Controlled Folder Access that protects `Documents`, and when it is switched on
it silently stops Git and Python from writing there. Nothing warns you; things
just fail for reasons that look unrelated.

---

## Step 2: open FluBNF

* **macOS**: double-click `FluBNF.command` in `~/GitHub/flubnf`. The first
  time only, right-click it and choose **Open**, because the app is not
  signed by Apple.
* **Windows**: double-click `FluBNF.bat` (in File Explorer, paste
  `%LOCALAPPDATA%\FluBNF\flubnf` into the address bar to get there). You
  only do this once: the first open adds **FluBNF to the Start menu**, so from
  then on you press the Windows key, type `FluBNF` and press Enter. Right-click
  it there and choose **Pin to taskbar** to keep it one click away. A FluBNF
  shortcut also appears on your Desktop; delete it if you do not want it,
  and it will not come back.

That is the whole install. The first launch sets everything up, the engine
included, which takes a few minutes, then the console opens in a window of
its own (or a browser tab, where that cannot be shown). **You do not need
to run `SetupEngine` separately**; opening the app does it. The engine
needs the network once: its PyBNF comes from github.com, and its other
packages from pypi.org.

**Windows: the first launch installs Perl too.** Fits need Perl, and
FluBNF installs its own when the PC has none: the window says "installing
Perl for FluBNF: a 31 MB download, no administrator needed", then "Perl
for FluBNF is ready". Nothing to click, and no administrator. Only when
that fails (no network, say) does FluBNF offer Strawberry Perl instead,
once: Windows then asks permission and you click **Yes**, or, on an
account that is not an administrator, an administrator types their
password. The next open tries FluBNF's own Perl again.

**macOS, keep it in the Dock**: while the console window is open,
right-click FluBNF in the Dock and choose **Options > Keep in Dock**. That
icon opens FluBNF from then on, with no Terminal window unless there is
something to show you (setup work, an engine install, an error). Keep the
FluBNF folder out of Documents, Desktop and Downloads (`~/GitHub` is where
it goes): macOS does not let FluBNF.app open anything there. An older copy
in Documents moves itself the next time it opens. Leave `FluBNF.app` in the
FluBNF folder: a copy dragged to Applications cannot start.

---

## How to tell it worked

The lines differ a little by platform; the one that matters is the same
on both.

macOS (in the Terminal window the install runs in):

```
== public PyBNF (the Liu-West filter, job_type = lwf), the default ==
...
== verify ==
  + public engine ready: pybnf 1.8.1 from pybnf-1.8.1-py3-none-any.whl, bngsim 0.15.1
```

Windows:

```
Installing the public engine (public PyBNF, with the Liu-West filter).
One time, a few minutes.
looking for a Python for the engine, 64-bit (x64) 3.12:
  downloading the public engine's packages and installing them, usually
  2 to 5 minutes; leave this window open
  + public engine ready: pybnf 1.8.1 from pybnf-1.8.1-py3-none-any.whl, bngsim 0.15.1
```

Under "looking for a Python" comes a line for each Python it tried, and
under "downloading", pip's own lines.

If you see **`public engine ready`**, you are done. On Windows, also check
that no line says Perl is still missing: the Sandbox needs Perl too.

---

## First forecast

With the console open:

1. **Data** tab: "check for new data", then "Update data", so the FluSight
   data is this week's.
2. **Forecast** tab: leave the date at the newest Saturday in the data,
   read the Data issues box, and run both models.
3. **Output** tab: open the weekly report and look through "All locations"
   before anything else.

That is the start of the weekly routine. The whole of it, from Sunday to
the Wednesday deadline, including how the files reach the hub, is
[Weekly routine](FLUSIGHT-2026-27.md#weekly-routine-sunday-to-wednesday)
in the season guide. FluBNF only writes the files; nothing is submitted
until someone uploads them.

To fit a model of your own instead, the Sandbox tab starts from an example
or a template: [SANDBOX.md](SANDBOX.md) walks through it. The Sandbox fits
with the engine, so it needs the engine installed, which the first open
does, and on Windows Perl too, which FluBNF installs; when something is
missing, a model's page says "This computer cannot fit yet" and its "?"
says what to do, and lists anything else missing. A model that calls
`time()`, and the two-strain model, run on the private engine only
([ENGINE.md](ENGINE.md#choosing-the-engine)).

---

## If something goes wrong

**"It opened but says the engine is not installed."**
FluBNF still works, it just runs one of its two models instead of both, so you
are not stuck. The Sandbox cannot fit until the engine is installed. Right
after an update this is expected once: the engine is public PyBNF since
the switch to the public engine, and the next open installs it. So open
FluBNF again first.

If it still says that, the install needs, once:

* a network that reaches github.com and pypi.org (the engine's PyBNF comes
  from a GitHub release, its other packages from pypi.org); a network that
  blocks either stops it, so try home Wi-Fi or a phone's hotspot;
* Python 3.12, 64-bit (x64) on Windows: Anaconda, from "Before you start",
  makes one;
* on macOS, Apple's Command Line Tools (`xcode-select --install` in
  Terminal);
* on a Mac with an Intel processor, macOS 15 or newer.

On macOS, double-click **`SetupEngine.command`** in the FluBNF folder. It
does only the engine step and names the actual cause. When a Mac cannot
run the engine at all (no Python 3.12 and no Anaconda to make one, an
Intel Mac below macOS 15), FluBNF says so and stops trying the install on
every open, until FluBNF's engine files or the Mac's system change. When
Anaconda is there but could not make a Python 3.12, that is usually the
network, and the next open tries again.

On Windows, read the `FluBNF.bat` window: the lines above
`The public engine did not install` name the cause and what to do. Every
open tries again by itself, so do what it says and open FluBNF again.
[docs/WINDOWS.md](WINDOWS.md#if-the-install-fails) lists the usual causes.
To see what the machine itself can see, run these two lines in Command
Prompt (the first is your FluBNF folder):

```
cd /d "%LOCALAPPDATA%\FluBNF\flubnf"
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

Either way, if it does not finish, send Ely what it prints.

**The lab asks you to use the private engine.** The lab's own PyBNF fork
is kept as the fallback for two rounds after the switch. For it you are
sent one small file, `pybnf-pf-<something>.tar.gz`, about 130 KB. Save it
in your **Downloads** folder as it is (do not unzip, move or rename it),
then switch this copy of FluBNF to it. On macOS, in Terminal:

```bash
cd ~/GitHub/flubnf && ./setup_engine.sh --private
```

On Windows, in Command Prompt:

```
cd /d "%LOCALAPPDATA%\FluBNF\flubnf"
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -Engine private
```

On macOS the line installs it from the file there and then; on Windows,
open FluBNF again, which installs it from the file. When FluBNF already
says the private engine is installed here, the same line switches to it in
seconds, with no file and no network. Either way the line records the
choice first, so it holds even when the rest cannot finish (no network,
say). `./setup_engine.sh --public` (on Windows, the same `powershell` line
with `-Engine public`) goes back to the default.

**It tried to log in to GitHub and asked for a password.**
This happens only on the private engine. It means it did not find the
engine file, so it fell back to downloading the engine, which does need an
account. Check the file is in Downloads with its original name. Nothing you
type at that prompt will work: GitHub stopped accepting account passwords
in 2021.

**Windows: the window says Perl is still missing.**
FluBNF could not install its own Perl: the window said why just above
(no network, or the package did not arrive whole), and every open tries
again, so opening FluBNF once the network is back is usually enough. A
school or work PC that blocks programs under AppData stops it too. Then
install Strawberry Perl from <https://strawberryperl.com>, which needs an
administrator, or delete `.venv\perl-offer.txt` in the FluBNF folder and
open FluBNF again to be offered it again. The next fit finds it, with no
restart. A perl that "is not a Windows Perl" (the one that comes with
Git's Unix tools) does not count: FluBNF installs its own all the same.

**Windows: a Defender pop-up mentioning FluBNF.**
Nothing is wrong and nothing is infected. That is Controlled Folder Access
noticing a program writing inside a protected folder. Send Ely a note; the
full explanation is in [docs/WINDOWS.md](WINDOWS.md).

**Windows: `git` is not recognised.**
Git is not installed yet, or the Command Prompt was open before you installed
it. Install it from the link at the top, then close and reopen the window.

---

## If it still does not work (Windows)

When FluBNF closes by itself, or still cannot fit after you did what it
said, these lines collect what Ely needs, in about five minutes. Close
FluBNF, open Command Prompt (Start, type `cmd`) and paste them; if
Windows asks whether to paste several lines, paste anyway. The first is
your FluBNF folder; change it if yours is somewhere else.

```
cd /d "%LOCALAPPDATA%\FluBNF\flubnf"
echo %USERPROFILE% & echo BNGPATH=%BNGPATH%
whoami /groups | findstr /c:"S-1-5-32-544" >nul && echo admin || echo standard
where perl & perl -e "print $^O"
dir /b "%SystemDrive%\Strawberry\perl\bin\perl.exe" "%USERPROFILE%\Downloads\pybnf*.tar.gz"
type .flubnf.env.cmd .venv\engine-attempt.txt .venv\perl-offer.txt "%LOCALAPPDATA%\FluBNF\perl\flubnf-perl.ok"
"%LOCALAPPDATA%\FluBNF\venv-public\Scripts\python.exe" scripts\engine_lock.py check
"%USERPROFILE%\.venvs\flubnf-engine\Scripts\python.exe" -c "import sys, sysconfig; print(sysconfig.get_platform()); sys.path.insert(0, sys.argv[1]); import bngsim, pybnf.pf; print('engine imports')" "%LOCALAPPDATA%\FluBNF\PyBNF-Private"
FluBNF.bat
```

The line with `engine_lock.py check` checks the public engine, and the
line after it the private one, the fallback; on a PC without one of them,
that line says it cannot be found. The last line opens FluBNF in this
window, so if it crashes, the reason
stays on screen ("The syntax of the command is incorrect.") instead of
the window closing. Copy everything the window shows, or take screenshots
of it, and send that to Ely. Lines that say a file or program cannot be
found are answers too: leave them in.

---

## Reinstalling from scratch (macOS)

If your copy is out of date or broken, or Ely asks everyone to reinstall,
do this instead of the steps above. Restart your Mac first, so no old
FluBNF is still running. Then paste this one line into Terminal:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash
```

It needs no engine file. It checks first and changes nothing until the
checks pass: git, a Python the engine can use (Anaconda from "Before you
start", or Python 3.12), no FluBNF running, GitHub reachable. Then it
renames your old FluBNF folder with `-old-` and the date and time (nothing
is deleted; your old runs stay inside the renamed folder, and the new
console starts without them), installs FluBNF fresh, installs the public
engine (or checks the one already installed against its lock), and opens
the console. If the install stops before a new console exists, it puts the
old folder back. The private engine, the fallback, its Python environment
and any engine files are left where they are.

Once the new console works, the `-old-` folder can go in the Trash. If
FluBNF was in your Dock, that icon now points at the renamed copy and will
not open; drag it off and drag `FluBNF.app` from the new folder on
instead.

Pasting the line again on a machine that is already current changes
nothing; it just opens the console. If it says `already current` but the
console is still broken, paste this instead:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | FLUBNF_REINSTALL_FORCE=1 bash
```

Only when the lab asks you to reinstall on the private engine: save the
engine file you were sent in Downloads, delete any older
`pybnf-pf-….tar.gz` files from Downloads and the Desktop, and paste:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | FLUBNF_ENGINE=private bash
```

That also renames the private engine's Python environment and any unpacked engine copy, moves
every other engine file (`pybnf….tar.gz`, `pybnf….bundle`) into
`Downloads/old-engine-files`, and installs the private engine from the
file it found. Setup takes the newest engine file it finds, so old ones
left in Downloads are how a machine ends up with the wrong engine.

---

## Resetting or reinstalling (Windows)

The line above is for macOS and Linux only. On Windows there are two
routes; try the first, which keeps your runs.

**Reset in place.** This makes your FluBNF folder match the lab's copy
exactly. Close FluBNF first (close its window). Open Command Prompt (Start,
type `cmd`) and run these three lines, one at a time:

```
cd /d "%LOCALAPPDATA%\FluBNF\flubnf"
git fetch origin
git reset --hard origin/main
```

If your FluBNF folder is somewhere else, for example
`Documents\GitHub\flubnf`, put that folder in the first line instead and keep
the quotation marks. Then double-click `FluBNF.bat`.

The reset throws away edits to FluBNF's own files and any commits made in the
folder. It keeps everything git does not track: `app\state` (your runs,
uploaded datasets and retrospective seasons), `.venv`, the engine and the
FluSight data. If FluBNF said `origin/<branch> no longer exists`, the folder
is on a branch other than `main`: run `git checkout -f main` before the
reset line.

This is the fix when FluBNF says it cannot fast-forward and you never
committed anything yourself (the usual cause is in
[the appendix](#appendix-the-september-2026-history-rewrite)). Do not
delete the folder and clone again instead: that loses `app\state`, and
leaves the old engine, which lives outside the folder, exactly where it
was.

**Reinstalling from scratch.** For when the reset is not enough, or Ely asks
everyone to reinstall. Nothing is deleted until you choose to delete it.

1. Close FluBNF.
2. Rename your FluBNF folder, both engines' Python environments and every
   private engine folder with `-old` on the end. In Command Prompt:

   ```
   ren "%LOCALAPPDATA%\FluBNF\flubnf" flubnf-old
   ren "%LOCALAPPDATA%\FluBNF\venv-public" venv-public-old
   ren "%LOCALAPPDATA%\FluBNF\PyBNF-Private" PyBNF-Private-old
   ren "%LOCALAPPDATA%\FluBNF\PyBNF-pf" PyBNF-pf-old
   ren "%USERPROFILE%\Documents\GitHub\PyBNF-Private" PyBNF-Private-old
   ren "%USERPROFILE%\Documents\GitHub\PyBNF-pf" PyBNF-pf-old
   ren "%USERPROFILE%\.venvs\flubnf-engine" flubnf-engine-old
   ```

   The first line is your FluBNF folder (change it if yours is elsewhere),
   and the second is the public engine's Python environment. The other
   five also set aside the private engine (the fallback): the next four
   are the places it can be, and the last is its Python environment. If
   you ever pointed `FLUBNF_PYBNF` at a folder of your own, rename that one
   too. A line for a folder you do not have says
   `The system cannot find the file specified`, which is fine. If one says
   `A duplicate file name exists`, an `-old` copy is there from before: add
   the date, as in `flubnf-old-2026-09-29`. `Access is denied` means
   something still has the folder open; close FluBNF and any window inside
   that folder.
3. Get FluBNF again, in Command Prompt:

   ```
   git clone https://github.com/elyfmiller/flubnf "%LOCALAPPDATA%\FluBNF\flubnf"
   ```

4. Double-click `FluBNF.bat` in the new folder. The first run sets
   everything up again and installs the public engine; the window ends as
   in "How to tell it worked".

Your old runs stay in `flubnf-old`, and the new console starts without them.
To bring your uploaded datasets across, close FluBNF and copy the folder
`app\state\datasets` from `flubnf-old` to the same place in `flubnf`. Once
the new console works, the `-old` folders can go in the Recycle Bin.

Only when the lab asks you to reinstall on the private engine: before
step 4, delete older `pybnf-pf-….tar.gz` and `pybnf….bundle` files from
Downloads, Desktop and Documents, save the engine file you were sent in
Downloads, and switch the new copy to it as under "The lab asks you to use
the private engine" above. Then double-click `FluBNF.bat`.

---

## Notes

The engine is public PyBNF since the switch to the public engine, and
FluBNF installs it itself, with no file to save
([ENGINE.md](ENGINE.md#the-public-engine-the-default)). It changes only
when FluBNF's lock file does, and the next open then installs the new one.
The engine file the lab used to send, `pybnf-pf-….tar.gz`, is now only for
the private engine, the fallback, and only on a copy switched to it; a
copy on the default leaves it alone in Downloads.

The private engine's file is a **snapshot**, so it does not update itself
from GitHub. When the lab changes it you are sent a newer file: save it in
Downloads, delete the old `pybnf-pf-….tar.gz` from Downloads so there is
no doubt which one was installed, and open FluBNF again. Setup takes the
newest archive it can find,
and since 2026-09-09 a newer one also replaces an engine that is already
unpacked (the old copy is moved aside, never deleted). Before that it did
not, and a laptop kept a three week old engine through a clean reinstall
with the current file sitting in Downloads.

The console itself does update, every time you open it, as long as the
update can fast-forward. When it cannot, the launcher now says which of the
two reasons it is instead of naming both. Offline means it will catch up on
its own next time. Local edits to tracked files are set aside into
`git stash` and the update goes through; `git stash list` in the FluBNF
folder shows them and `git stash pop` puts them back. Local commits are left
alone, and the launcher prints the command that would discard them rather
than running it. Commits the launcher counts as this folder's own may not
be ([the appendix](#appendix-the-september-2026-history-rewrite) says
when). To make a machine match the lab
whatever is on it, from Terminal in the FluBNF folder:

    git fetch origin && git reset --hard origin/main

(On Windows, the Command Prompt lines are under "Resetting or reinstalling
(Windows)" above.) That throws away local edits and local commits in the
clone. It touches nothing outside it: the virtual environment, the engine,
`app/state` and the data clone are all untracked and stay exactly as they
are.

If two people's forecasts ever disagree, compare the engines first. The
Home page's Setup card names the engine and its build (`PyBNF 8410f794`
for the public engine). For the public engine, this line in the FluBNF
folder prints what is installed, the same on every machine that matches
the lock:

    ~/.venvs/flubnf-public/bin/python scripts/engine_lock.py check

(on Windows, the `engine_lock.py check` line under "If it still does not
work (Windows)"). For the private engine, each snapshot carries a `VERSION`
file naming the exact commit it came from, and FluBNF prints that on every
setup.

---

## Appendix: the September 2026 history rewrite

Main's history was rewritten once, in September 2026: the commits made from
early September up to the rewrite were given new ids. A FluBNF folder that
updated itself in between cannot fast-forward past that, and on every open
it says `this clone has N commit(s) origin does not` ("throw this clone's
work away"), or just `offline or local changes - running as-is`, and keeps
running the old console. Nothing of yours is lost: those commits are the
lab's own under their old ids. The fix is the reset: on Windows, "Reset in
place" under "Resetting or reinstalling (Windows)" above; on macOS, the
`git fetch origin && git reset --hard origin/main` line under Notes. If you
did commit something of your own in the folder, ask Ely before resetting.
