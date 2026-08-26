# flubnf one-command setup (Windows). Idempotent: re-running fixes what is
# missing. PowerShell twin of setup.sh. Run with:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
#
# -NoProfile matters: a user profile that sets $ErrorActionPreference = "Stop"
# would otherwise turn every line git writes to stderr into a script-ending
# error (see the comment on $ErrorActionPreference below).
#
# -NoPrompt makes this script ask nothing at all, for unattended runs and CI.
# Without it the only question ever asked is whether to let winget install
# Strawberry Perl, and even that is skipped in a non-interactive session.
param([switch]$NoPrompt)

# "Continue" is deliberate. In Windows PowerShell every line a native command
# writes to stderr comes back as an ErrorRecord, so under "Stop" an entirely
# healthy `git clone` would end this script the moment git printed its first
# status line. The price of Continue is that a failing command does not stop
# the script by itself, so EVERY native call below reads its own exit code on
# the very next statement and decides what to do with it.
#
# Never test $LASTEXITCODE two statements later. It is global, so the next
# native call overwrites it, and -- the defect that produced the misleading
# "data fetch failed (offline? git missing?)" report from the field -- it is
# left completely untouched when a command could not be found at all, so it
# still holds the exit code of whatever ran before. Invoke-Captured below
# reports "did it even run" separately from "what did it exit with".
$ErrorActionPreference = "Continue"

function Say($m)  { Write-Host "`n== $m ==" }
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Info($m) { Write-Host "  $m" }

function Invoke-Captured {
    <#
      Run a native command with stdout and stderr captured, and return
      @{ Ran; Code; Output }. Output is held rather than printed so a normal
      run stays quiet, and is printed by the caller when something failed --
      the diagnostic that `2>$null` used to throw away.
    #>
    param([string]$Exe, [string[]]$Arguments = @())
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) {
        return @{ Ran = $false; Code = $null
                  Output = @("$Exe was not found on PATH, so it never ran") }
    }
    $out = & $Exe @Arguments 2>&1
    $code = $LASTEXITCODE          # read HERE, on the next statement, always
    return @{ Ran = $true; Code = $code
              Output = @($out | ForEach-Object { "$_" }) }
}

function CodeStr($res) {
    if ($res.Ran) { "exit code $($res.Code)" } else { "never started" }
}

function Show-Output($res, [int]$Max = 20) {
    $lines = @($res.Output)
    if ($lines.Count -eq 0) { return }
    foreach ($l in ($lines | Select-Object -Last $Max)) { Write-Host "      $l" }
}

$Interactive = ((-not $NoPrompt) -and (-not $env:CI) -and
                [Environment]::UserInteractive)

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Hub = if ($env:FLUBNF_HUB) { $env:FLUBNF_HUB }
       else { Join-Path $HOME "Documents\GitHub\FluSight-forecast-hub" }
$EngineVenv = if ($env:FLUBNF_ENGINE_VENV) { $env:FLUBNF_ENGINE_VENV }
              else { Join-Path $HOME ".venvs\flubnf-engine" }
$PyBnf = if ($env:FLUBNF_PYBNF) { $env:FLUBNF_PYBNF }
         else { Join-Path $HOME "Documents\GitHub\PyBNF-pf" }
$PyBnfRemote = if ($env:FLUBNF_PYBNF_REMOTE) { $env:FLUBNF_PYBNF_REMOTE }
               else { "git@github.com:elyfmiller/PyBNF-Private.git" }
$EnginePy = Join-Path $EngineVenv "Scripts\python.exe"
$VenvDir = Join-Path $Here ".venv"

Say "plan (nothing has been installed yet)"
function Plan($label, $path) {
    $mark = if (Test-Path -LiteralPath $path) { "present" }
            else { "will be created" }
    Write-Host ("  {0,-18} {1}   [{2}]" -f ($label + ":"), $path, $mark)
}
Plan "repository"      $Here
Plan "console venv"    $VenvDir
Plan "FluSight data"   $Hub
Plan "engine venv"     $EngineVenv
Plan "PyBNF checkout"  $PyBnf
Info ""
Info "To put any of these somewhere else, set the variable first, open a NEW"
Info "window so the setting is visible, then re-run this script:"
Info "  setx FLUBNF_HUB D:\FluSight-forecast-hub"
Info "  setx FLUBNF_ENGINE_VENV D:\venvs\flubnf-engine"
Info "  setx FLUBNF_PYBNF D:\Projects\PyBNF-pf"
if ($Hub -like "*OneDrive*") {
    Warn "the data path is inside OneDrive. A git clone of this size in a"
    Warn "synced folder syncs tens of thousands of small files; putting it"
    Warn "outside OneDrive with setx FLUBNF_HUB is strongly preferable."
}

Say "python"
$PyExe = $null
$PyArgs = @()
$Cands = @(
    @{ exe = "py"; args = @("-3.12") },
    @{ exe = "py"; args = @("-3.11") },
    @{ exe = "py"; args = @("-3") },
    @{ exe = "python"; args = @() }
)
foreach ($c in $Cands) {
    # 2>$null here is the acceptable case: absence IS the thing being tested,
    # and each candidate is expected to fail until one does not.
    # $probe is built first and splatted with @probe (a variable, so real
    # splatting). Passing @($c.args) inline is an array-valued ARGUMENT, and
    # an empty one reaches a native command as a stray empty string, which
    # would have broken the bare-"python" candidate on a machine without the
    # py launcher.
    $probe = @($c.args) + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
    try { $v = & $c.exe @probe 2>$null }
    catch { $v = $null }
    if ($v) {
        try {
            if ([version]"$v" -ge [version]"3.11") { $PyExe = $c.exe; $PyArgs = $c.args; break }
        } catch { }
    }
}
if (-not $PyExe) {
    Warn "python >= 3.11 required. Install it from https://www.python.org/downloads/"
    Warn "and tick 'Add python.exe to PATH', then re-run this script."
    Warn "If 'python' opens the Microsoft Store instead of running, that is the"
    Warn "App Installer stub: install real Python from the link above."
    exit 1
}
Ok "Python $v via $(@($PyExe) + $PyArgs -join ' ')"

Say "analysis venv (.venv) + package"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Info "creating $VenvDir"
    $mk = Invoke-Captured $PyExe (@($PyArgs) + @("-m", "venv", $VenvDir))
    if (-not (Test-Path $VenvPy)) {
        Warn "venv creation failed ($(CodeStr $mk)). The command said:"
        Show-Output $mk
        Warn "Usual causes: a policy on this machine blocks writing here, or the"
        Warn "Python install is missing 'ensurepip'."
        exit 1
    }
}
Ok "venv: $VenvDir"
$pipUp = Invoke-Captured $VenvPy @("-m", "pip", "install", "-q", "--upgrade", "pip")
if ($pipUp.Code -ne 0) {
    Warn "pip self-upgrade failed ($(CodeStr $pipUp)); continuing, it is not fatal. pip said:"
    Show-Output $pipUp 10
}
$inst = Invoke-Captured $VenvPy @("-m", "pip", "install", "-q", "-e", "$Here[app,dev]")
if ($inst.Code -eq 0) {
    Ok "flubnf installed editable"
} else {
    Warn "pip install failed ($(CodeStr $inst)). pip said:"
    Show-Output $inst 40
    exit 1
}
$bng = Invoke-Captured $VenvPy @("-m", "pip", "install", "-q", "bionetgen")
if ($bng.Code -eq 0) {
    Ok "bionetgen (BNG2.pl + Windows binaries) installed"
} else {
    Warn "bionetgen install failed ($(CodeStr $bng)). The PF engine needs it; the"
    Warn "console, the analogue engine and the reports do not. pip said:"
    Show-Output $bng 10
}

# The directories the app actually reads, named once and used by both the
# fresh clone below and the repair of an existing one. Forward slashes are
# git's own path separator on every platform, Windows included, so this is
# the form handed to git; Test-Path is given the native form instead.
$HubDirs = @("auxiliary-data", "target-data",
             "model-output/FluSight-baseline",
             "model-output/FluSight-ensemble")

function Get-MissingHubDirs {
    param([string]$Hub, [string[]]$Dirs)
    @($Dirs | Where-Object {
        # $Dirs holds git's separator; Test-Path is given the native one.
        # (Windows accepts either, but mixing them in a printed path is the
        # kind of detail that makes a report harder to read than it need be.)
        $native = $_.Replace('/', '\')
        -not (Test-Path -LiteralPath (Join-Path $Hub $native))
    })
}

function Repair-HubCone {
    <#
      Widen an existing sparse clone's cone to the directories the app reads.

      WHY THIS EXISTS. `git clone --sparse` is documented to check out only
      the files in the repository ROOT. A hub cloned by hand with the command
      in the field report is therefore a perfectly healthy clone that holds
      none of the app's data, and the console opens on "Latest vintage: none"
      exactly as if nothing had been cloned at all. `sparse-checkout reapply`,
      which this script used to be alone in running here, cannot repair that:
      reapply re-applies the cone already recorded, and that cone is empty.

      Measured on git 2.39.5 against a local fixture shaped like the hub
      (macOS; sparse-checkout is git behaviour, not platform behaviour):
        * after clone --filter=blob:none --sparse --depth 1, the working tree
          holds the root file only and `sparse-checkout list` prints nothing
        * `reapply` on that clone exits 0 and adds nothing
        * `sparse-checkout add <the four dirs>` brings them all in, exit 0,
          and repeating it is a no-op

      ADD, NEVER SET. Both were measured on the same fixture. Against a full
      non-sparse clone, `set` exits 0 and DELETES every directory not named
      (it pruned model-output/OtherTeam), which would silently gut the
      checkout of anyone who deliberately cloned the whole hub. `add` against
      a full clone fails with "no sparse-checkout to add to", exit 128, and
      changes nothing on disk. This function is only called for a clone that
      reports core.sparseCheckout=true, so that is a backstop, not the path.
    #>
    param([string]$Hub, [string[]]$Dirs)
    $absent = @(Get-MissingHubDirs $Hub $Dirs)
    if ($absent.Count -eq 0) { return }
    Warn "this clone does not contain $($absent -join ', ')."
    Info "A clone made with --sparse checks out the top level and nothing"
    Info "else, so the data directories have to be asked for. Widening the"
    Info "sparse checkout now; this is where the download happens..."
    $add = Invoke-Captured "git" (@("-C", $Hub, "sparse-checkout", "add") + $Dirs)
    $still = @(Get-MissingHubDirs $Hub $Dirs)
    if ($add.Code -eq 0 -and $still.Count -eq 0) {
        Ok "sparse checkout widened: the data directories are present now"
    } else {
        Warn "could not widen the sparse checkout ($(CodeStr $add)). git said:"
        Show-Output $add 20
        if ($still.Count -gt 0) {
            Warn "still absent: $($still -join ', ')"
            Warn "The console will still open on 'Latest vintage: none'. Usual"
            Warn "causes: no network, or the hub no longer has that directory."
        }
    }
}

Say "FluSight hub data"
Info "target: $Hub"
$HubGit = Join-Path $Hub ".git"
$GitPresent = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($env:FLUBNF_NO_DATA -eq "1") {
    Warn "data skipped (FLUBNF_NO_DATA=1) -- set FLUBNF_HUB later"
} elseif (Test-Path $HubGit) {
    Ok "hub present: $Hub"
    if (-not $GitPresent) {
        Warn "git is not on PATH, so the hub was left exactly as it is on disk"
        # @() around every call: PowerShell unrolls a returned array, so an
        # empty result comes back as $null and a one-element result as a bare
        # string. Wrapping makes .Count mean what it reads as in all three
        # cases, without depending on the scalar .Count that 5.1 also has.
        if ((@(Get-MissingHubDirs $Hub $HubDirs)).Count -gt 0) {
            Warn "and it holds none of the data directories the app reads, so"
            Warn "the console will open on 'Latest vintage: none'. Install Git"
            Warn "from https://git-scm.com/download/win, open a NEW window, and"
            Warn "re-run this script; it will widen the checkout for you."
        }
    } else {
        # A shallow clone stays shallow across a fetch, so this is a small
        # update, and --ff-only correctly refuses if the tree has local edits.
        # Verified against a shallow blobless sparse clone on git 2.39.5: it
        # fast-forwards cleanly. (That was previously an untested claim.)
        $pull = Invoke-Captured "git" @("-C", $Hub, "pull", "--ff-only", "--quiet")
        if ($pull.Code -eq 0) {
            Ok "hub updated (git pull --ff-only)"
        } else {
            Warn "hub update skipped ($(CodeStr $pull)); the data already on disk is"
            Warn "still used. git said:"
            Show-Output $pull 10
        }
        # The cone repair runs whether or not the pull worked, and BEFORE
        # reapply, because reapply cannot add what the cone never held. The
        # config read tells the two kinds of clone apart: `git config --get`
        # exits 1 when the key is unset, which is what a full clone gives.
        $cfg = Invoke-Captured "git" @("-C", $Hub, "config", "--get",
                                       "core.sparseCheckout")
        $IsSparse = ($cfg.Code -eq 0 -and
                     ((@($cfg.Output) -join "").Trim() -eq "true"))
        if ($IsSparse) {
            Repair-HubCone $Hub $HubDirs
            # A sparse cone changed by a newer release only takes effect on
            # reapply; a no-op when nothing changed.
            $re = Invoke-Captured "git" @("-C", $Hub, "sparse-checkout", "reapply")
            if ($re.Code -ne 0) {
                Warn "sparse-checkout reapply failed ($(CodeStr $re)); not fatal. git said:"
                Show-Output $re 10
            }
        } else {
            # A full clone already holds everything, and reapply FAILS on one
            # ("must be in a sparse-checkout to reapply sparsity patterns",
            # exit 128, measured), so the old unconditional call reported a
            # problem on a checkout that was entirely correct.
            Info "full (non-sparse) clone: nothing to widen"
            $absent = @(Get-MissingHubDirs $Hub $HubDirs)
            if ($absent.Count -gt 0) {
                Warn "but it does not contain $($absent -join ', '), which the app reads"
            }
        }
    }
} elseif (Test-Path $Hub) {
    Warn "$Hub exists but is not a git clone, so it cannot be updated and a"
    Warn "clone into it would fail. Move or delete it, or point FLUBNF_HUB at"
    Warn "another path, then re-run this script."
} elseif (-not $GitPresent) {
    Warn "git is not on PATH, so the FluSight data cannot be fetched."
    Warn "Install Git from https://git-scm.com/download/win, open a NEW window"
    Warn "so PATH is picked up, and re-run this script."
} else {
    # Sparse checkout pulls ONLY the data directories the app reads (about
    # 10x smaller than the full hub, which is mostly other teams' forecasts).
    $ParentOk = $true
    $HubParent = Split-Path -Parent $Hub
    if ($HubParent -and -not (Test-Path $HubParent)) {
        # git clone creates missing parents itself; doing it here first turns
        # an unwritable or unreachable parent (a redirected Documents folder,
        # a D: drive that is not there) into an early, named failure.
        try {
            New-Item -ItemType Directory -Force -Path $HubParent -ErrorAction Stop | Out-Null
            Ok "created $HubParent"
        } catch {
            $ParentOk = $false
            Warn "cannot create $HubParent"
            Warn "  $($_.Exception.Message)"
        }
    }
    if ($ParentOk) {
        Info "fetching FluSight data (sparse, about 150 MB); a few minutes..."
        $clone = Invoke-Captured "git" @("clone", "--filter=blob:none", "--sparse",
            "--depth", "1", "https://github.com/cdcepi/FluSight-forecast-hub", $Hub)
        # Belt and braces: the exit code AND the result on disk, because a
        # stale $LASTEXITCODE is exactly the trap this rewrite exists to close.
        if ($clone.Code -eq 0 -and (Test-Path $HubGit)) {
            # `set` is right HERE and only here: this clone was made one
            # statement ago with --sparse, so its cone is empty and there is
            # nothing of the user's for `set` to prune. Everywhere else the
            # cone is widened with `add`; see Repair-HubCone.
            $sp = Invoke-Captured "git" (@("-C", $Hub, "sparse-checkout", "set") +
                                         $HubDirs)
            if ($sp.Code -eq 0) {
                Ok "hub data ready (sparse): $Hub"
            } else {
                Warn "cloned, but sparse-checkout failed ($(CodeStr $sp)), so the"
                Warn "clone may hold more or less than the app expects. git said:"
                Show-Output $sp 10
            }
        } else {
            Warn "git clone failed ($(CodeStr $clone)). git said:"
            Show-Output $clone 20
            Warn "Nothing else was changed; re-run this script once that is fixed."
        }
    }
}

Say "perl (engine network generation)"
$Perl = Get-Command perl -ErrorAction SilentlyContinue
if ($Perl) {
    Ok "perl found: $($Perl.Source)"
} else {
    Warn "perl not found. BioNetGen's BNG2.pl needs Perl for the one-time"
    Warn "network-generation step of the PF engine; Strawberry Perl"
    Warn "(https://strawberryperl.com) is the standard choice on Windows."
    Warn "The console, analogue engine, and reports do not need it."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    # NOTE (unverified from macOS): the package id below is the one commonly
    # documented for Strawberry Perl. Confirm with `winget search perl` before
    # relying on it; if it is wrong, winget simply exits non-zero and the
    # manual link above still stands. winget itself ships in App Installer,
    # which is absent on some Enterprise and LTSC images.
    if (-not $winget) {
        Info "winget is not available here, so install it from the link above."
    } elseif (-not $Interactive) {
        Info "winget is available. In an interactive window this script offers:"
        Info "  winget install --id StrawberryPerl.StrawberryPerl -e"
    } else {
        Info ""
        Info "winget can install it for you:"
        Info "  winget install --id StrawberryPerl.StrawberryPerl -e"
        Info "Strawberry Perl is a machine-wide install, so Windows will raise a"
        Info "UAC consent dialog that you have to accept yourself. This script"
        Info "never elevates anything on its own, and declining changes nothing."
        $ans = Read-Host "  Run it now? [y/N]"
        if ($ans -match '^\s*(y|yes)\s*$') {
            & winget install --id StrawberryPerl.StrawberryPerl -e --source winget --accept-source-agreements --accept-package-agreements
            $wcode = $LASTEXITCODE
            if ($wcode -eq 0) {
                Ok "Strawberry Perl installed."
                Warn "Its PATH entry reaches only NEW processes: close this window,"
                Warn "open a new one, and re-run this script to confirm."
            } else {
                Warn "winget exited $wcode. Declined UAC, no network, or a different"
                Warn "package id: install by hand from https://strawberryperl.com"
            }
        } else {
            Info "skipped; install later from https://strawberryperl.com"
        }
    }
}

function Test-RemoteAccess {
    <#
      Can this machine read $Remote right now? Returns "yes", "no" or
      "unknown". It never clones, never writes, and must never hang:

        * GIT_TERMINAL_PROMPT=0 stops git's own username/password prompt, but
          NOT a credential helper. Git for Windows installs Git Credential
          Manager as the default helper, and GCM opens a GUI window -- the
          hang we must avoid -- so the helper list is cleared for this one
          call and GCM's interactive mode is turned off by name as well.
        * GIT_ASKPASS=echo makes any remaining password request return empty
          instead of waiting.
        * ssh -o BatchMode=yes fails instead of asking for a passphrase, and
          ConnectTimeout bounds a black-holed TCP connect.
        * GIT_CONFIG_NOSYSTEM=1 stops a system gitconfig re-adding a helper.
        * and a hard wall-clock timeout backs all of that up.

      UNVERIFIED FROM macOS: $p.Kill() ends git but not necessarily a child
      ssh.exe, because Windows has no POSIX process groups, and Kill($true)
      (kill the tree) is .NET 5+, which Windows PowerShell 5.1 does not have.
      taskkill /T /F is the documented stand-in and is used here; it has not
      been exercised on a Windows box.
    #>
    param([string]$Remote, [int]$TimeoutMs = 15000)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return "unknown" }
    $o = Join-Path ([IO.Path]::GetTempPath()) "flubnf-lsremote.out"
    $e = Join-Path ([IO.Path]::GetTempPath()) "flubnf-lsremote.err"
    $saved = @{}
    foreach ($k in @("GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "GIT_SSH_COMMAND",
                     "GIT_CONFIG_NOSYSTEM")) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
    }
    try {
        $env:GIT_TERMINAL_PROMPT = "0"
        $env:GIT_ASKPASS = "echo"
        $env:GIT_SSH_COMMAND = "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
        $env:GIT_CONFIG_NOSYSTEM = "1"
        $gitArgs = @("-c", "credential.helper=", "-c", "credential.interactive=false",
                     "ls-remote", "--heads", $Remote, "feature/particle-filter")
        # splatted rather than continued with backticks: one less thing that a
        # CRLF checkout or a stray trailing space could break
        $spArgs = @{
            FilePath = "git"; ArgumentList = $gitArgs; NoNewWindow = $true
            PassThru = $true; RedirectStandardOutput = $o
            RedirectStandardError = $e; ErrorAction = "SilentlyContinue"
        }
        $p = Start-Process @spArgs
        if (-not $p) { return "unknown" }
        try { $null = $p.Handle } catch { }   # cache the handle so ExitCode
                                              # is still readable after exit
        if (-not $p.WaitForExit($TimeoutMs)) {
            try { & taskkill /T /F /PID $p.Id 2>&1 | Out-Null } catch { }
            return "unknown"
        }
        if ($p.ExitCode -eq 0) { return "yes" }
        return "no"
    } catch {
        return "unknown"
    } finally {
        foreach ($k in @($saved.Keys)) {
            [Environment]::SetEnvironmentVariable($k, $saved[$k], "Process")
        }
        Remove-Item $o, $e -Force -ErrorAction SilentlyContinue
    }
}

Say "engine venv (pybnf + bngsim)"
$EngineReady = $false
if (Test-Path $EnginePy) {
    $imp = Invoke-Captured $EnginePy @("-c", "import pybnf, bngsim")
    if ($imp.Code -eq 0) {
        $EngineReady = $true
    } else {
        # Not the same thing as "you have no access": an engine venv that
        # exists but imports badly (NumPy 2 against a fork that predates it is
        # the one seen in the lab) used to be reported as a missing fork.
        Warn "engine venv exists at $EngineVenv but its imports fail. Python said:"
        Show-Output $imp 10
    }
}
if ($EngineReady) {
    Ok "engine venv ready: $EngineVenv"
} else {
    Warn "engine venv not ready. The PF engine (fit_type=pf) needs the PyBNF"
    Warn "fork with fit_type=pf, which is a PRIVATE repository."
    $access = "unknown"
    if (Test-Path (Join-Path $PyBnf ".git")) {
        $access = "local"
    } elseif ($env:FLUBNF_NO_PROBE -eq "1") {
        Info "access probe skipped (FLUBNF_NO_PROBE=1)"
    } else {
        Info "checking whether this machine can already reach it (up to 15 s;"
        Info "read-only, and it cannot ask you for a password)..."
        $access = Test-RemoteAccess $PyBnfRemote 15000
    }
    if ($access -eq "local") {
        Ok "a PyBNF checkout is already on disk: $PyBnf"
        Info "Finish with:"
    } elseif ($access -eq "yes") {
        Ok "this machine can read $PyBnfRemote -- no invitation needed."
        Info "Run these four commands:"
        Info "  git clone -b feature/particle-filter $PyBnfRemote $PyBnf"
    } elseif ($access -eq "no") {
        Warn "this machine cannot read $PyBnfRemote."
        Warn "  1) ask Ely for a collaborator invitation to PyBNF-Private"
        Warn "  2) add an SSH key: ssh-keygen -t ed25519, then paste"
        Warn "     %USERPROFILE%\.ssh\id_ed25519.pub at github.com ->"
        Warn "     Settings -> SSH and GPG keys -> New SSH key"
        Warn "  3) re-run this script"
        Info "With access, the remaining steps are:"
        Info "  git clone -b feature/particle-filter $PyBnfRemote $PyBnf"
    } else {
        Warn "access to the fork was not checked, or could not be determined:"
        Warn "no git, no network, the probe was skipped, or it timed out."
        Info "If you do have access:"
        Info "  git clone -b feature/particle-filter $PyBnfRemote $PyBnf"
    }
    # numpy<2: the fork predates NumPy 2 and its historical fixes were
    # venv-local patches rather than commits, so the pin is the reproducible
    # answer. Same pin as setup_engine.sh on macOS and Linux.
    Info "  $PyExe $($PyArgs -join ' ') -m venv $EngineVenv"
    Info "  $EngineVenv\Scripts\pip install `"numpy<2`" scipy pandas `"bngsim==0.15.1`""
    Info "  $EngineVenv\Scripts\pip install -e $PyBnf"
    Info "  then re-run this script"
    Warn "Without the engine: the console, analogue engine, and reports all work."
}

Say "environment"
# The Windows analogue of setup.sh's .flubnf.env, in two halves. User-level
# environment variables are read by every future process on this account, and
# .flubnf.env.cmd is read by FluBNF.bat on every launch -- which is what makes
# this configuration visible to the very next double-click. User-scope
# variables reach only processes started AFTER this moment, so without the
# file a console launched from a window that was already open would still see
# nothing at all.
# UTF-8 mode: Windows defaults text I/O to cp1252, which breaks reads of the
# app's UTF-8 assets. This makes every Python launch behave like macOS/Linux.
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
[Environment]::SetEnvironmentVariable("FLUBNF_HUB", $Hub, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PY_ENGINE", $EnginePy, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PYBNF", $PyBnf, "User")
Ok "user environment recorded (FLUBNF_HUB, FLUBNF_PY_ENGINE, FLUBNF_PYBNF)"

$EnvCmd = Join-Path $Here ".flubnf.env.cmd"
$EnvLines = @(
    "@echo off",
    "rem Written by setup.ps1; FluBNF.bat calls this on every launch.",
    "rem Delete it and re-run setup.ps1 to regenerate.",
    "set `"PYTHONUTF8=1`"",
    "set `"FLUBNF_HUB=$Hub`"",
    "set `"FLUBNF_PY_ENGINE=$EnginePy`"",
    "set `"FLUBNF_PYBNF=$PyBnf`""
)
try {
    # cmd.exe reads a batch file in the console code page, which is the OEM
    # page (437 on a US install), not the ANSI page Set-Content would use.
    # The two agree for an all-ASCII path and differ only for a profile name
    # with accented characters -- UNVERIFIED, we cannot test it from macOS.
    # GetEncoding(65001) carries a BOM preamble, and a BOM in front of
    # "@echo off" is a cmd syntax error, hence the explicit no-BOM UTF-8.
    $cp = [int](Get-Culture).TextInfo.OEMCodePage
    $enc = if ($cp -eq 65001) { New-Object System.Text.UTF8Encoding($false) }
           else { [Text.Encoding]::GetEncoding($cp) }
    [IO.File]::WriteAllText($EnvCmd, (($EnvLines -join "`r`n") + "`r`n"), $enc)
    Ok "wrote $EnvCmd (read by FluBNF.bat on every launch)"
} catch {
    Warn "could not write $EnvCmd"
    Warn "  $($_.Exception.Message)"
    Warn "FluBNF.bat will fall back to the default data location."
}

Say "doctor"
$env:FLUBNF_HUB = $Hub
$env:FLUBNF_PY_ENGINE = $EnginePy
$env:FLUBNF_PYBNF = $PyBnf
& $VenvPy -c "from flubnf.settings import check; import sys; sys.exit(1 if check() else 0)"
$DoctorCode = $LASTEXITCODE
if ($DoctorCode -eq 0) {
    Ok "all externals present -- you are ready: double-click FluBNF.bat"
} else {
    Warn "some externals missing (listed above) -- console still runs: double-click FluBNF.bat"
}

# THE EXIT CODE IS A STATEMENT ABOUT SETUP, NOT ABOUT THE EXTERNALS.
# Reaching this line means setup finished its work; every condition that
# should stop a user has already exited 1 above (no Python >= 3.11, the venv
# could not be created, the package would not install). The doctor's verdict
# is reported in the text above and deliberately does NOT become this
# script's exit code: on a machine without access to the private PyBNF fork,
# "some externals missing" is the normal and expected end state, and a
# caller must be able to tell that apart from "setup broke".
#
# Without this line the exit status was whatever the doctor happened to
# leave in $LASTEXITCODE, so an ordinary successful run on a machine with no
# engine would have made FluBNF.bat print "setup.ps1 reported a problem" --
# the same family of misreport as the bug this rewrite exists to fix.
# (Whether Windows PowerShell 5.1 propagates a trailing $LASTEXITCODE
# through -File at all is disputed and we cannot test it from macOS; this
# line makes the question moot in both directions.)
exit 0
