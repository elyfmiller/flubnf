# Installing FluBNF

For lab members. Two files, two double clicks, no GitHub account needed.

You will be given one small file, `pybnf-pf-<something>.tar.gz`, about 130 KB.
That is the forecasting engine. Everything else downloads itself.

---

## Before you start

**macOS**: nothing. Git and Perl already ship with the system, and the setup
installs the rest.

**Windows**: install these two first, both are normal installers.

* Python 3.11 or newer, from <https://www.python.org/downloads/>. **Tick "Add
  python.exe to PATH"** on the first screen of the installer. It is easy to
  miss and everything afterwards depends on it.
* Git, from <https://git-scm.com/download/win>. The default options are fine.

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

## Step 2: put the engine file where FluBNF looks

Unpack the `.tar.gz` you were sent. macOS unpacks it by double clicking.
On Windows use 7-Zip or WinRAR, or right-click and Extract All if Windows
offers it (you may need to extract twice, once for `.gz` and once for `.tar`).

You will get a folder called **`PyBNF-Private`**. Move it so it ends up here:

| system | put the folder here | final path |
|---|---|---|
| macOS | `~/Documents/GitHub/` | `~/Documents/GitHub/PyBNF-Private` |
| Windows | `%LOCALAPPDATA%\FluBNF\` | `%LOCALAPPDATA%\FluBNF\PyBNF-Private` |

Paste `%LOCALAPPDATA%\FluBNF\` into the Explorer address bar to get there.

**Do not rename the folder.** The setup looks for that exact name.

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

While it sets up you should see lines like these:

```
+ unpacked copy present (no git): .../PyBNF-Private
+ version stamp: feature/particle-filter 3320d1f0
+ bngsim installed: 0.15.1
+ pybnf (fork) installed editable
+ pybnf with fit_type=pf, bngsim 0.15.1 -- engine ready
```

The line that matters is the last one. If you see **`engine ready`**, you are
done.

---

## If something goes wrong

**"It opened but says the engine is not installed."**
FluBNF still works, it just runs one of its two models instead of both, so you
are not stuck. To fix it, check that the folder is in exactly the place in the
table above and is named `PyBNF-Private`, then open FluBNF again.

If it still says that, open a terminal in the FluBNF folder and run
`./setup_engine.sh` (macOS) or `setup_engine.sh` from Git Bash (Windows). It
prints a section called **"what this machine can see"** that names the actual
cause instead of guessing. Send that block to Ely.

**It tried to log in to GitHub and asked for a password.**
That means it did not find your engine folder, so it fell back to downloading
the engine, which does need an account. Go back to step 2. Nothing you type at
that prompt will work: GitHub stopped accepting account passwords in 2021.

**Windows: a Defender pop-up mentioning FluBNF.**
Nothing is wrong and nothing is infected. That is Controlled Folder Access
noticing that Python wants to write inside a protected folder. It means
something ended up under `Documents`. See
[docs/WINDOWS.md](WINDOWS.md) for the full explanation.

**Windows: `python` or `git` is not recognised.**
Python was installed without "Add python.exe to PATH", or Git is not installed.
Re-run the installer from the top of this page, then close and reopen the
Command Prompt so it picks up the change.

---

## Notes

The engine folder you were sent is a **snapshot**, not a live checkout, so it
cannot update itself with `git pull`. When the engine changes you will be sent
a newer file; unpack it over the same folder, replacing what is there.

Each snapshot carries a `VERSION` file naming the exact commit it came from,
and FluBNF prints that on every setup. If two people's forecasts ever disagree,
that line is the first thing to compare.
