# Installing FluBNF

For lab members. Two files, two double clicks, no GitHub account needed.

You will be given one small file, `pybnf-pf-<something>.tar.gz`, about 130 KB.
That is the forecasting engine. Everything else downloads itself.

---

## Before you start

**macOS**: install Anaconda from <https://www.anaconda.com/download>,
defaults are fine; setup finds it with nothing added to PATH. If macOS offers
to install "command line developer tools" along the way, click Install. Git
and Perl already ship with the system.

**Windows**: install these two first, both are normal installers with
defaults that are fine as they are.

* Anaconda, from <https://www.anaconda.com/download> (the lab's standard
  Python). No settings to change: FluBNF finds it where it installs.
* Git, from <https://git-scm.com/download/win>.

---

## Step 1: get FluBNF

**macOS**, paste this one line into Terminal:

```bash
curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/install.sh | bash
```

**Windows**, open Command Prompt and run:

```
git clone https://github.com/elyfmiller/flubnf %LOCALAPPDATA%\FluBNF\flubnf
```

Put it there and not in `Documents`. Windows Defender has a feature called
Controlled Folder Access that protects `Documents`, and when it is switched on
it silently stops Git and Python from writing there. Nothing warns you; things
just fail for reasons that look unrelated.

---

## Step 2: save the engine file to Downloads

Save the `pybnf-pf-...tar.gz` you were sent into your **Downloads** folder.

That is the whole step. Do not unzip it, do not move it, do not rename it.
The setup finds it there on both platforms, unpacks it to the right place
itself, and tells you which file it used.

(It is also found on your Desktop, in Documents, or next to the FluBNF
folder, if that is where it ended up.)

---

## Step 3: open FluBNF

* **macOS**: double-click `FluBNF.command`. The first time only, right-click it
  and choose **Open**, because the app is not signed by Apple.
* **Windows**: double-click `FluBNF.bat`.

That is the whole install. The first launch sets everything up, which takes a
few minutes, then the console opens in your browser. **You do not need to run
`SetupEngine` separately**; opening the app does it.

---

## How to tell it worked

The lines differ a little by platform; the one that matters ends the same
way on both.

macOS:

```
+ engine unpacked from pybnf-pf-XXXX.tar.gz into .../PyBNF-Private
+ version stamp: feature/particle-filter XXXX
+ bngsim installed: 0.15.1
+ pybnf (fork) installed editable
+ pybnf with fit_type=pf, bngsim 0.15.1 -- engine ready
```

Windows:

```
unpacking the engine from "...\Downloads\pybnf-pf-XXXX.tar.gz" - no GitHub account needed
version stamp: feature/particle-filter XXXX
Installing the particle filter engine. One time, a few minutes.
PF engine ready, bngsim 0.15.1 -- engine ready
```

If you see **`engine ready`**, you are done.

---

## If something goes wrong

**"It opened but says the engine is not installed."**
FluBNF still works, it just runs one of its two models instead of both, so you
are not stuck. Check the engine file is in your Downloads folder with its
original name, then open FluBNF again.

If it still says that: on macOS, open Terminal in the FluBNF folder and run
`./setup_engine.sh`, which prints a section called **"what this machine can
see"** naming the actual cause. On Windows, run this in Command Prompt from
the FluBNF folder:

```
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

Either way, send Ely what it prints.

**It tried to log in to GitHub and asked for a password.**
That means it did not find the engine file, so it fell back to downloading
the engine, which does need an account. Check the file is in Downloads with
its original name. Nothing you type at that prompt will work: GitHub stopped
accepting account passwords in 2021.

**Windows: a Defender pop-up mentioning FluBNF.**
Nothing is wrong and nothing is infected. That is Controlled Folder Access
noticing a program writing inside a protected folder. Send Ely a note; the
full explanation is in [docs/WINDOWS.md](WINDOWS.md).

**Windows: `git` is not recognised.**
Git is not installed yet, or the Command Prompt was open before you installed
it. Install it from the link at the top, then close and reopen the window.

---

## Notes

The engine you were sent is a **snapshot**, so it does not update itself.
When the engine changes you will be sent a newer file, with the one extra
instruction that goes with it.

Each snapshot carries a `VERSION` file naming the exact commit it came from,
and FluBNF prints that on every setup. If two people's forecasts ever disagree,
that line is the first thing to compare.
