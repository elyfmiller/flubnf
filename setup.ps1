# flubnf one-command setup (Windows), twin of setup.sh. Idempotent.
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 [-NoPrompt] [-ShowDefenderExclusion]
# -NoProfile: a profile's $ErrorActionPreference = "Stop" makes git's stderr fatal.
# -NoPrompt: ask nothing (FluBNF.bat, CI); otherwise the only question is the
#   winget Strawberry Perl offer, and only in an interactive session.
# -ShowDefenderExclusion: print the scanning-exclusion detail; changes nothing.
#   A switch, never a prompt or default: someone has to ask for it.
param([switch]$NoPrompt, [switch]$ShowDefenderExclusion)

# "Continue" on purpose: under "Stop" any native stderr line (git progress) is
# terminating. So every native call reads its exit code on the NEXT statement;
# Invoke-Captured also reports "never ran" ($LASTEXITCODE is stale then).
$ErrorActionPreference = "Continue"

function Say($m)  { Write-Host "`n== $m ==" }
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Info($m) { Write-Host "  $m" }

function Invoke-Captured {
    <# Run a native command, capturing stdout+stderr: @{ Ran; Code; Output }.
       The caller prints Output only on failure. #>
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

# Checkouts default under %LOCALAPPDATA%\FluBNF, not Documents. Controlled
# Folder Access, when switched on, lets only trusted programs write to
# Documents (and Pictures, Videos, Music, Favorites), and git.exe/python.exe
# are not trusted: the user sees a plain permission error that never names
# Defender (event 1123; docs\WINDOWS.md has the log). Microsoft ships it off,
# but it is on for at least one machine here, so the defaults must not rely
# on it; this script asks the machine rather than assuming either way.
# %LOCALAPPDATA%: per-user, no admin, not roamed or synced by OneDrive. ~\.venvs
# is safe (CFA guards named folders, not the profile root). macOS/Linux keep
# ~/Documents/GitHub.
# Profile root: prefer %USERPROFILE%, as FluBNF.bat and settings.py do; $HOME
# can differ (AD home directories), so LOOKUPS of earlier installs probe both.
$ProfileRoot = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA }
                else { Join-Path $ProfileRoot "AppData\Local" }
$FluBnfRoot = Join-Path $LocalAppData "FluBNF"

function Get-ProfileRoots {
    <# Every spelling of the profile root, most authoritative first, deduplicated. #>
    $out = @()
    foreach ($r in @($ProfileRoot, $HOME, $env:USERPROFILE)) {
        if ($r -and ($out -notcontains $r)) { $out += $r }
    }
    return @($out)
}
$LegacyRoots = @(Get-ProfileRoots | ForEach-Object {
    Join-Path $_ "Documents\GitHub" })

$script:ReusedLegacy = @()
function Resolve-Checkout {
    <# FLUBNF_* wins; then an EXISTING checkout at the old Documents default,
       used where it stands (never moved or copied; announced in the plan);
       then the default under %LOCALAPPDATA%. #>
    param([string]$FromEnv, [string]$Name)
    if ($FromEnv) { return $FromEnv }
    foreach ($root in $LegacyRoots) {
        $legacy = Join-Path $root $Name
        if (Test-Path -LiteralPath $legacy) {
            $script:ReusedLegacy += $legacy
            return $legacy
        }
    }
    return (Join-Path $FluBnfRoot $Name)
}

function Resolve-ProfilePath {
    <# A profile-relative path: %USERPROFILE%'s, unless only another root's
       copy exists (an earlier install must not be stranded). #>
    param([string]$Relative)
    $preferred = Join-Path $ProfileRoot $Relative
    if (Test-Path -LiteralPath $preferred) { return $preferred }
    foreach ($root in (Get-ProfileRoots)) {
        $cand = Join-Path $root $Relative
        if (Test-Path -LiteralPath $cand) { return $cand }
    }
    return $preferred
}

function Test-PathInside {
    <# Is $Child $Parent or beneath it? Lexical only: paths may not exist yet. #>
    param([string]$Child, [string]$Parent)
    if (-not $Child -or -not $Parent) { return $false }
    try {
        $c = [IO.Path]::GetFullPath($Child).TrimEnd('\')
        $p = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
    } catch { return $false }
    if (-not $p) { return $false }
    if ($c -eq $p) { return $true }
    return $c.StartsWith(($p + '\'), [StringComparison]::OrdinalIgnoreCase)
}

function Get-ProtectedFolders {
    <# CFA's documented default folders (plus Public and Desktop: this only
       decides whether to WARN, so erring wide is cheap). GetFolderPath follows
       OneDrive KFM; literal paths under every profile root are added too. The
       caller unions in the machine's own list; this is the fallback when
       Defender will not say (CFA off, or not elevated). #>
    $out = @()
    foreach ($n in @("MyDocuments", "Desktop", "DesktopDirectory",
                     "MyPictures", "MyVideos", "MyMusic", "Favorites",
                     "CommonDocuments", "CommonDesktopDirectory",
                     "CommonPictures", "CommonVideos", "CommonMusic")) {
        try { $p = [Environment]::GetFolderPath($n) } catch { $p = $null }
        if ($p) { $out += $p }
    }
    foreach ($root in (Get-ProfileRoots)) {
        foreach ($n in @("Documents", "Desktop", "Pictures", "Videos",
                         "Music", "Favorites")) {
            $out += (Join-Path $root $n)
        }
    }
    return @($out | Where-Object { $_ } | Select-Object -Unique)
}

function Get-CfaState {
    <# @{ State; Why; Folders }, State "on"/"audit"/"off"/"unknown". Never
       assumes Get-MpPreference works (module missing, third-party AV, old
       build): "unknown" plus the reason. Modes: 0 off, 1 on, 2 audit, 3/4
       boot sectors only (= off for folders). The number or the enum name is
       accepted; anything else is reported verbatim. #>
    if (-not (Get-Command Get-MpPreference -ErrorAction SilentlyContinue)) {
        return @{ State = "unknown"; Folders = @()
                  Why = "Get-MpPreference is not available on this machine" }
    }
    try { $pref = Get-MpPreference -ErrorAction Stop }
    catch {
        return @{ State = "unknown"; Folders = @()
                  Why = "Get-MpPreference failed: $($_.Exception.Message)" }
    }
    if ($null -eq $pref) {
        return @{ State = "unknown"; Folders = @()
                  Why = "Get-MpPreference returned nothing" }
    }
    # The machine's own lists (added folders; the built-in set, populated only
    # when CFA is on and elevated) beat our defaults; either may be empty.
    $folders = @()
    foreach ($p in @("ControlledFolderAccessProtectedFolders",
                     "ControlledFolderAccessDefaultProtectedFolders")) {
        try { $v = $pref.$p } catch { $v = $null }
        if ($v) { $folders += @($v | ForEach-Object { "$_" }) }
    }
    $folders = @($folders | Where-Object { $_ } | Select-Object -Unique)
    $val = $null
    try { $val = $pref.EnableControlledFolderAccess } catch { }
    if ($null -eq $val) {
        return @{ State = "unknown"; Folders = $folders
                  Why = "this Defender build reports no EnableControlledFolderAccess setting" }
    }
    $s = ("$val").Trim()
    if ($s -eq "0" -or $s -eq "Disabled") {
        return @{ State = "off"; Folders = $folders
                  Why = "EnableControlledFolderAccess = $s" }
    }
    if ($s -eq "1" -or $s -eq "Enabled") {
        return @{ State = "on"; Folders = $folders
                  Why = "EnableControlledFolderAccess = $s" }
    }
    if ($s -eq "2" -or $s -eq "AuditMode") {
        return @{ State = "audit"; Folders = $folders
                  Why = "EnableControlledFolderAccess = $s" }
    }
    if ($s -eq "3" -or $s -eq "BlockDiskModificationOnly" -or
        $s -eq "4" -or $s -eq "AuditDiskModificationOnly") {
        return @{ State = "off"; Folders = $folders
                  Why = "EnableControlledFolderAccess = $s, which guards the boot sectors only and leaves protected folders alone" }
    }
    return @{ State = "unknown"; Folders = $folders
              Why = "EnableControlledFolderAccess = $s, which this script does not recognise" }
}

function Get-RealtimeState {
    <# Defender real-time scanning (slows writes, never blocks them):
       @{ State; Why; Paths; Processes }, State "on"/"off"/"unknown", lists =
       existing exclusions. Guarded like Get-CfaState. Get-MpComputerStatus
       (what RUNS) wins over Get-MpPreference (what is configured, plus the
       exclusion lists). #>
    $paths = @()
    $procs = @()
    $pref = $null
    if (Get-Command Get-MpPreference -ErrorAction SilentlyContinue) {
        try { $pref = Get-MpPreference -ErrorAction Stop } catch { $pref = $null }
    }
    if ($pref) {
        try { $paths = @($pref.ExclusionPath | ForEach-Object { "$_" }) } catch { $paths = @() }
        try { $procs = @($pref.ExclusionProcess | ForEach-Object { "$_" }) } catch { $procs = @() }
    }
    $paths = @($paths | Where-Object { $_ })
    $procs = @($procs | Where-Object { $_ })
    if (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue) {
        $st = $null
        try { $st = Get-MpComputerStatus -ErrorAction Stop } catch { $st = $null }
        if ($st) {
            $rt = $null
            try { $rt = $st.RealTimeProtectionEnabled } catch { }
            if ($null -ne $rt) {
                if ($rt) {
                    return @{ State = "on"; Paths = $paths; Processes = $procs
                              Why = "RealTimeProtectionEnabled = True" }
                }
                return @{ State = "off"; Paths = $paths; Processes = $procs
                          Why = "RealTimeProtectionEnabled = False" }
            }
        }
    }
    if ($pref) {
        $dis = $null
        try { $dis = $pref.DisableRealtimeMonitoring } catch { }
        if ($null -ne $dis) {
            $d = ("$dis").Trim()
            if ($d -eq "True") {
                return @{ State = "off"; Paths = $paths; Processes = $procs
                          Why = "DisableRealtimeMonitoring = True" }
            }
            if ($d -eq "False") {
                return @{ State = "on"; Paths = $paths; Processes = $procs
                          Why = "DisableRealtimeMonitoring = False" }
            }
        }
    }
    return @{ State = "unknown"; Paths = $paths; Processes = $procs
              Why = "neither Get-MpComputerStatus nor Get-MpPreference would say" }
}

$Hub = Resolve-Checkout $env:FLUBNF_HUB "FluSight-forecast-hub"
$PyBnf = Resolve-Checkout $env:FLUBNF_PYBNF "PyBNF-pf"
# No PyBNF-pf (the dev host's name): an existing PyBNF-Private (the repo's
# real name) wins over cloning fresh. Mirrors flubnf/settings.py.
if (-not $env:FLUBNF_PYBNF -and -not (Test-Path -LiteralPath $PyBnf)) {
    $alt = Resolve-Checkout $null "PyBNF-Private"
    if (Test-Path -LiteralPath $alt) { $PyBnf = $alt }
}
$EngineVenv = if ($env:FLUBNF_ENGINE_VENV) { $env:FLUBNF_ENGINE_VENV }
              # Resolve-ProfilePath: settings.py uses %USERPROFILE%, and a
              # venv built under the other root is still found.
              else { Resolve-ProfilePath ".venvs\flubnf-engine" }
$PyBnfRemote = if ($env:FLUBNF_PYBNF_REMOTE) { $env:FLUBNF_PYBNF_REMOTE }
               # HTTPS: GitHub Desktop's Git Credential Manager caches it.
               else { "https://github.com/elyfmiller/PyBNF-Private.git" }
$EnginePy = Join-Path $EngineVenv "Scripts\python.exe"
$VenvDir = Join-Path $Here ".venv"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

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
if ($script:ReusedLegacy.Count -gt 0) {
    Info ""
    Info "Reusing folders that are already on this machine, rather than the"
    Info "current default under $FluBnfRoot"
    foreach ($p in $script:ReusedLegacy) { Info "  $p" }
    Info "Nothing has been moved or copied, and nothing needs to be: a machine"
    Info "set up before the default changed keeps working exactly as it is."
    Info "Do note that these sit under Documents, which Controlled Folder"
    Info "Access protects by default; the next section says what that means."
}
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

Say "controlled folder access (Defender ransomware protection)"
# Read-only: never changes Defender, never elevates, never suggests turning
# CFA off. Runs before any install: these failures cannot be read off their errors.
$Cfa = Get-CfaState
$GitCmd = Get-Command git -ErrorAction SilentlyContinue
$GitExe = if ($GitCmd) { $GitCmd.Source }
          else { "C:\Program Files\Git\cmd\git.exe   (usual location; git is not on PATH here)" }
# perl.exe and run_network.exe are resolved here so remedy 2 can name them:
# a fit writes inside the repo (BNG2.pl in app\state\workroots), so a repo in
# Documents breaks mid-fit even with the hub and checkout elsewhere.
$PerlCmd = Get-Command perl -ErrorAction SilentlyContinue
$PerlExe = if ($PerlCmd) { $PerlCmd.Source }
           else { "C:\Strawberry\perl\bin\perl.exe   (usual location; perl is not on PATH here)" }
# bionetgen lives in the CONSOLE venv (settings.py::_bng_candidates). Newer
# wheels moved run_network.exe from bng-win\ to bng-win\bin\: probe both so
# the allow-list names the real binary.
$RunNetCandidates = @(
    (Join-Path $VenvDir "Lib\site-packages\bionetgen\bng-win\bin\run_network.exe"),
    (Join-Path $VenvDir "Lib\site-packages\bionetgen\bng-win\run_network.exe"))
$RunNetExe = $RunNetCandidates | Where-Object { Test-Path -LiteralPath $_ } |
             Select-Object -First 1
if (-not $RunNetExe) { $RunNetExe = $RunNetCandidates[0] }
# FromEnv: a recorded variable naming a missing protected path is a leftover
# from an earlier release, not a choice; it gets its own remedy below.
$Resolved = @(
    @{ Label = "repository";     Path = $Here;       Var = $null; FromEnv = $false },
    @{ Label = "console venv";   Path = $VenvDir;    Var = $null; FromEnv = $false },
    @{ Label = "FluSight data";  Path = $Hub;        Var = "FLUBNF_HUB"
       FromEnv = [bool]$env:FLUBNF_HUB },
    @{ Label = "engine venv";    Path = $EngineVenv; Var = "FLUBNF_ENGINE_VENV"
       FromEnv = [bool]$env:FLUBNF_ENGINE_VENV },
    @{ Label = "PyBNF checkout"; Path = $PyBnf;      Var = "FLUBNF_PYBNF"
       FromEnv = [bool]$env:FLUBNF_PYBNF }
)
# Defaults UNION the machine's list: a false warning costs a paragraph, a
# missed one a day. The inner parentheses bound what the pipeline claims.
$Protected = @((@(Get-ProtectedFolders) + @($Cfa.Folders)) |
               Where-Object { $_ } | Select-Object -Unique)
$AtRisk = @()
foreach ($e in $Resolved) {
    $hit = $null
    foreach ($pf in $Protected) {
        if (Test-PathInside $e.Path $pf) { $hit = $pf; break }
    }
    if ($hit) {
        $AtRisk += @{ Label = $e.Label; Path = $e.Path; Var = $e.Var
                      FromEnv = $e.FromEnv; Folder = $hit }
    }
}
# The console venv is inside the repository: keep only the repository line.
# @(): PowerShell unrolls a one-element result, so .Count needs the wrapper.
if ((@($AtRisk | Where-Object { $_.Label -eq "repository" })).Count -gt 0) {
    $AtRisk = @($AtRisk | Where-Object { $_.Label -ne "console venv" })
}

if ($Cfa.State -eq "off") {
    # "will not block", not "is off": modes 3/4 land here too.
    Ok "Controlled Folder Access will not block anything here"
    Ok "  ($($Cfa.Why))"
} elseif ($AtRisk.Count -eq 0) {
    if ($Cfa.State -eq "unknown") {
        Info "the Controlled Folder Access setting could not be read:"
        Info "  $($Cfa.Why)"
        Ok "It does not matter here: none of the paths above is inside a folder"
        Ok "it protects, whatever it is set to."
    } else {
        Ok "Controlled Folder Access is on ($($Cfa.Why)), and none of the paths"
        Ok "above is inside a folder it protects"
    }
} else {
    if ($Cfa.State -eq "on") {
        Warn "Controlled Folder Access is ON ($($Cfa.Why)) and these paths are"
        Warn "inside folders it protects:"
    } elseif ($Cfa.State -eq "audit") {
        Warn "Controlled Folder Access is in AUDIT mode ($($Cfa.Why)): it logs"
        Warn "what it would block instead of blocking it. Nothing below is"
        Warn "failing yet, and all of it starts failing the day it is enabled."
        Warn "These paths are inside folders it protects:"
    } else {
        Warn "the Controlled Folder Access setting could not be read:"
        Warn "  $($Cfa.Why)"
        Warn "Microsoft ships it OFF, so it is probably off here. It is on for"
        Warn "at least one machine this project runs on, though, and if it is on"
        Warn "here then these paths are inside folders it protects:"
    }
    foreach ($e in $AtRisk) {
        Warn ("  {0,-16} {1}" -f ($e.Label + ":"), $e.Path)
    }
    Warn ""
    Warn "WHAT THAT DOES. A protected folder can be read by anything and"
    Warn "written only by programs Defender trusts. git.exe and python.exe are"
    Warn "not trusted by default, and neither is perl.exe, so:"
    Warn "  * git may fail to clone or to pull the FluSight hub,"
    Warn "  * python may fail to write __pycache__ inside a checkout, and"
    Warn "  * a fit may fail partway through, because it writes its model and"
    Warn "    the generated network into app\state\workroots INSIDE this"
    Warn "    repository, through perl.exe and BioNetGen's run_network.exe."
    Warn "ALL of those arrive as ordinary permission errors that never mention"
    Warn "Defender. That is what makes this worth a warning: the failure"
    Warn "cannot be diagnosed from the failure. The block is recorded only in"
    Warn "the Defender log, as event 1123."
    Info ""
    Info "Remedies, best first."
    Info ""
    Info "  1. PREFERRED: put the folder where Controlled Folder Access does"
    Info "     not reach. No administrator, and Defender is not touched."
    $hasVar = $false
    foreach ($e in $AtRisk) {
        if ($e.Var) {
            $hasVar = $true
            $leaf = Split-Path -Leaf $e.Path
            # quoted: the profile path may contain spaces
            Info "       setx $($e.Var) `"$(Join-Path $FluBnfRoot $leaf)`""
        }
    }
    if ($hasVar) {
        Info "     Then close this window, open a NEW one, and re-run this"
        Info "     script. Nothing is moved for you: the old folder is left"
        Info "     exactly where it is and the new location is fetched from"
        Info "     scratch, so if you would rather not download it again, move"
        Info "     the folder there yourself first and then run the setx line."
    }
    foreach ($e in $AtRisk) {
        if (-not $e.Var) {
            Info "     The repository itself has no variable: move this whole"
            Info "     folder to $FluBnfRoot\flubnf (or anywhere outside the"
            Info "     folders listed above) and run FluBNF.bat from its new"
            Info "     home. This one matters even if setup succeeds, because"
            Info "     a fit writes into app\state\workroots inside it."
        }
    }
    Info ""
    Info "  2. Allow the specific programs through Controlled Folder Access."
    Info "     This needs an ADMINISTRATOR. This script will not do it: it"
    Info "     never elevates and never changes a Defender setting. Windows"
    Info "     Security > Virus & threat protection > Ransomware protection >"
    Info "     Manage ransomware protection > Allow an app through Controlled"
    Info "     folder access > Add an allowed app, and add:"
    Info "       $GitExe"
    Info "       $EnginePy"
    Info "       $VenvPy"
    Info "       $PerlExe"
    Info "       $RunNetExe"
    Info "     git.exe and python.exe are the two Defender actually logged as"
    Info "     blocked on the machine this was diagnosed on. perl.exe and"
    Info "     run_network.exe are on the list because they write inside this"
    Info "     repository during a fit; leave them out and setup will look"
    Info "     fine and the first fit will not."
    Info "     If those Windows Security controls are greyed out, or the page"
    Info "     says the setting is managed by your organisation, then IT set"
    Info "     it by policy and remedy 2 is not available to you even as an"
    Info "     administrator. Use remedy 1."
    Info ""
    Info "  3. LAST RESORT, and it REDUCES PROTECTION: a folder exclusion."
    Info "     Microsoft documents the default protected folders as ones you"
    Info "     cannot modify or remove -- 'You can't modify the list of"
    Info "     default protected folders' -- so the only folder-level lever is"
    Info "     a Defender exclusion path, which weakens antivirus coverage of"
    Info "     that folder for everything, not just for FluBNF -- and we have"
    Info "     not been able to confirm that it exempts Controlled Folder"
    Info "     Access at all."
    Info "     Prefer 1 or 2. Do not switch Controlled Folder Access off."
    # An earlier release recorded the Documents location even after a blocked
    # clone, and a recorded value wins in Resolve-Checkout. Name it and give
    # the one-line fix; do not silently overrule it.
    $Stale = @($AtRisk | Where-Object {
        $_.FromEnv -and $_.Var -and -not (Test-Path -LiteralPath $_.Path) })
    if ($Stale.Count -gt 0) {
        Info ""
        Info "  A NOTE ON WHAT IS ALREADY RECORDED ON THIS MACHINE."
        foreach ($e in $Stale) {
            Info "     $($e.Var) is recorded in your environment as"
            Info "       $($e.Path)"
            Info "     which is inside a protected folder AND is not there at"
            Info "     all. An earlier version of this setup recorded that"
            Info "     location by default, even on a run whose clone had just"
            Info "     been blocked, so a blocked machine keeps aiming at the"
            Info "     folder it cannot write to. Nothing is lost by moving it:"
            $leaf = Split-Path -Leaf $e.Path
            Info "       setx $($e.Var) `"$(Join-Path $FluBnfRoot $leaf)`""
            Info "     then close this window, open a NEW one, and re-run this"
            Info "     script."
        }
    }
    Info ""
    Info "To read the evidence yourself, in an ordinary PowerShell window:"
    Info "  Get-MpPreference | Select-Object EnableControlledFolderAccess"
    Info '  Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" |'
    Info '    Where-Object { $_.Id -eq 1123 } | Select-Object -First 20 TimeCreated, Message'
    Info ""
    Info "docs\WINDOWS.md has the whole story, with the log lines this came"
    Info "from. Setup continues; nothing above has been changed."
}

Say "defender real-time scanning (speed, not failure)"
# Read-only like the section above: never adds an exclusion (it reduces
# protection, needs an admin, is often forbidden on managed laptops); the
# detail prints only with -ShowDefenderExclusion. Scanning slows writes
# without failing them, so nothing points at it. That it explains the slow
# Windows CI is a hypothesis, not a measurement (docs\WINDOWS.md).
$Rt = Get-RealtimeState
# Paths this project writes constantly (the repo: venv, __pycache__, workroots).
$ScanPaths = @($Here, $Hub, $PyBnf, $EngineVenv) |
             Where-Object { $_ } | Select-Object -Unique
$AlreadyExcluded = @()
$NotExcluded = @()
foreach ($p in $ScanPaths) {
    $covered = $false
    foreach ($x in $Rt.Paths) {
        if (Test-PathInside $p $x) { $covered = $true; break }
    }
    if ($covered) { $AlreadyExcluded += $p } else { $NotExcluded += $p }
}

if ($Rt.State -eq "off") {
    Ok "Defender real-time scanning is off here ($($Rt.Why)), so it is not"
    Ok "  what is slowing anything down. Nothing to consider."
    # The switch must answer even here, or it reads as broken.
    if ($ShowDefenderExclusion) {
        Info "  You asked for the exclusion detail: there is nothing to"
        Info "  exclude from, so an exclusion would buy you nothing here."
    }
# "on", not "not off": "unknown" (exclusions readable, state not) falls
# through to the generic branch below.
} elseif ($Rt.State -eq "on" -and $AlreadyExcluded.Count -gt 0 -and $NotExcluded.Count -eq 0) {
    Ok "Defender real-time scanning is on ($($Rt.Why)), and every path this"
    Ok "  project works in is already covered by an exclusion on this machine."
    foreach ($p in $AlreadyExcluded) { Info "    $p" }
    if ($ShowDefenderExclusion) {
        Info "  You asked for the exclusion detail: it is already in place."
        Info "  docs\WINDOWS.md, section 'Defender real-time scanning', has"
        Info "  the line that lists these and the line that removes one."
    }
} else {
    if ($Rt.State -eq "on") {
        Info "Defender real-time scanning is on ($($Rt.Why))."
    } else {
        Info "Defender real-time scanning could not be read: $($Rt.Why)"
        Info "Microsoft ships it switched on, so assume it is on here."
    }
    # Four lines by default; a wall of antivirus text reads as an instruction.
    Info "Nothing is wrong and nothing needs doing: every part of FluBNF works"
    Info "with scanning on. It can just be slower, and a long fit is where you"
    Info "would notice, because this project writes constantly into folders"
    Info "Defender is inspecting."
    if (-not $ShowDefenderExclusion) {
        Info ""
        Info "Excluding those folders from scanning is the ordinary developer"
        Info "remedy. It needs an administrator, it reduces protection for"
        Info "those folders, and it is often blocked on a managed laptop. This"
        Info "script will not do it. To see what it would involve, with the"
        Info "folders that resolved on THIS machine, and change nothing:"
        Info "  powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -ShowDefenderExclusion"
    } else {
        # Opt-in only (the switch): prints the trade and the route, changes nothing.
        Info ""
        Info "You asked for the detail. This script is still not going to do"
        Info "any of it; what follows is for you or your IT department."
        Info ""
        if ($AlreadyExcluded.Count -gt 0) {
            Info "  Already excluded on this machine:"
            foreach ($p in $AlreadyExcluded) { Info "      $p" }
            Info ""
        }
        Info "  Scanned, and written into constantly by this project:"
        foreach ($p in $NotExcluded) { Info "      $p" }
        Info ""
        # Existing process exclusions (docs\WINDOWS.md suggests one) may
        # already cover the folders above.
        if (@($Rt.Processes).Count -gt 0) {
            Info "  Process exclusions this machine already has. These cover"
            Info "  what the named program reads and writes ANYWHERE, so one"
            Info "  of them may already cover the folders listed above:"
            foreach ($x in $Rt.Processes) { Info "      $x" }
            Info ""
        }
        Info "  THE TRADE, both halves."
        Info "  It WOULD stop Defender inspecting every file this project"
        Info "  writes, which is the thing that would make runs faster."
        Info "  It WOULD NOT make FluBNF safer, easier to install, or better"
        Info "  in any other way, and it does NOT reliably affect Controlled"
        Info "  Folder Access, the separate setting reported above. If your"
        Info "  problem is a write that FAILS, this is the wrong remedy."
        Info "  It WOULD leave those folders unscanned for EVERYTHING on this"
        Info "  machine, not just for FluBNF, until it is removed."
        Info "  It NEEDS AN ADMINISTRATOR, and on a university-managed laptop"
        Info "  it is often blocked by policy. That answer is fine. Nothing"
        Info "  here depends on it and the only difference is speed."
        Info ""
        Info "  THE ROUTE THAT NEEDS NO COMMAND LINE. Windows Security >"
        Info "  Virus & threat protection > Virus & threat protection"
        Info "  settings > Manage settings > Exclusions > Add or remove"
        Info "  exclusions > Add an exclusion > Folder, and add each of the"
        Info "  folders listed above. The same page removes one again."
        Info ""
        Info "  THE COMMAND FORM, for an administrator window or for IT, is"
        Info "  in docs\WINDOWS.md under 'Defender real-time scanning',"
        Info "  together with the line that undoes it. It is quoted there"
        Info "  rather than printed here so that the command a person runs"
        Info "  arrives with the paragraph about what it costs attached to"
        Info "  it, instead of on its own in a setup transcript."
    }
    Info ""
    Info "docs\WINDOWS.md, section 'Defender real-time scanning', has the"
    Info "measurements this note rests on and what is still unmeasured."
}

function Show-CfaHint {
    <# At a failed write, name CFA next to the error (the early warning is easy
       to scroll past). Silent when CFA is off or the path is unprotected. #>
    param([string]$Path)
    if ($Cfa.State -eq "off") { return }
    foreach ($pf in $Protected) {
        if (Test-PathInside $Path $pf) {
            Warn "  Note: $Path is inside"
            Warn "  $pf, which Controlled Folder Access protects. If the words"
            Warn "  above read as a permission problem, that is the first thing"
            Warn "  to rule out; see the section near the top of this run."
            return
        }
    }
}

Say "python"
$PyExe = $null
$PyArgs = @()
# PATH launchers first, then Anaconda/Miniconda's default folders (their
# installer leaves PATH alone). Mirrors FluBNF.bat's CONDAPY probe.
$Cands = @(
    @{ exe = "py"; args = @("-3.12") },
    @{ exe = "py"; args = @("-3.11") },
    @{ exe = "py"; args = @("-3") },
    @{ exe = "python"; args = @() }
)
foreach ($condaPy in @("$env:USERPROFILE\anaconda3\python.exe",
                       "$env:USERPROFILE\miniconda3\python.exe",
                       "$env:LOCALAPPDATA\anaconda3\python.exe",
                       "C:\ProgramData\anaconda3\python.exe")) {
    if (Test-Path $condaPy) { $Cands += @{ exe = $condaPy; args = @() } }
}
foreach ($c in $Cands) {
    # 2>$null is fine: absence is what is tested. Splat through a variable
    # (@probe): an inline empty array reaches a native command as a stray "".
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
    Warn "python >= 3.11 required. The easy route is Anaconda"
    Warn "(anaconda.com/download, defaults are fine: this script finds it with"
    Warn "nothing added to PATH). Or python.org, then re-run this script."
    Warn "If 'python' opens the Microsoft Store instead of running, that is the"
    Warn "App Installer stub: install real Python from the link above."
    exit 1
}
Ok "Python $v via $(@($PyExe) + $PyArgs -join ' ')"

Say "analysis venv (.venv) + package"
# $VenvPy was resolved at the top so the CFA section could name it.
if (-not (Test-Path $VenvPy)) {
    Info "creating $VenvDir"
    $mk = Invoke-Captured $PyExe (@($PyArgs) + @("-m", "venv", $VenvDir))
    if (-not (Test-Path $VenvPy)) {
        Warn "venv creation failed ($(CodeStr $mk)). The command said:"
        Show-Output $mk
        Warn "Usual causes: a policy on this machine blocks writing here, or the"
        Warn "Python install is missing 'ensurepip'."
        Show-CfaHint $VenvDir
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

# The directories the app reads, for both the fresh clone and the repair.
# Forward slashes for git; Test-Path gets the native form.
$HubDirs = @("auxiliary-data", "target-data",
             "model-output/FluSight-baseline",
             "model-output/FluSight-ensemble")

function Get-MissingHubDirs {
    param([string]$Hub, [string[]]$Dirs)
    @($Dirs | Where-Object {
        # native separator, so printed paths do not mix them
        $native = $_.Replace('/', '\')
        -not (Test-Path -LiteralPath (Join-Path $Hub $native))
    })
}

function Repair-HubCone {
    <# Widen an existing sparse clone's cone to $Dirs. A by-hand
       `clone --sparse` holds only the root, and reapply cannot add what the
       cone never held; `add` does, idempotently. ADD, NEVER SET: on a full
       clone `set` deletes every unnamed dir, while `add` fails harmlessly
       (exit 128). Measured on git 2.39.5. #>
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
# Set only when a clone was ATTEMPTED and failed (not for FLUBNF_NO_DATA=1):
# it withholds the persistent FLUBNF_HUB record at the end.
$HubCloneFailed = $false
$HubGit = Join-Path $Hub ".git"
$GitPresent = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($env:FLUBNF_NO_DATA -eq "1") {
    Warn "data skipped (FLUBNF_NO_DATA=1) -- set FLUBNF_HUB later"
} elseif (Test-Path $HubGit) {
    Ok "hub present: $Hub"
    if (-not $GitPresent) {
        Warn "git is not on PATH, so the hub was left exactly as it is on disk"
        # @(): PowerShell unrolls 0/1-element results; .Count needs the wrapper.
        if ((@(Get-MissingHubDirs $Hub $HubDirs)).Count -gt 0) {
            Warn "and it holds none of the data directories the app reads, so"
            Warn "the console will open on 'Latest vintage: none'. Install Git"
            Warn "from https://git-scm.com/download/win, open a NEW window, and"
            Warn "re-run this script; it will widen the checkout for you."
        }
    } else {
        # Small (shallow stays shallow); --ff-only refuses over local edits.
        # Verified on a shallow blobless sparse clone, git 2.39.5.
        $pull = Invoke-Captured "git" @("-C", $Hub, "pull", "--ff-only", "--quiet")
        if ($pull.Code -eq 0) {
            Ok "hub updated (git pull --ff-only)"
        } else {
            Warn "hub update skipped ($(CodeStr $pull)); the data already on disk is"
            Warn "still used. git said:"
            Show-Output $pull 10
            Show-CfaHint $Hub
        }
        # Repair runs even if the pull failed, and BEFORE reapply (which cannot
        # add). A full clone leaves core.sparseCheckout unset (exit 1).
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
            # Full clone: reapply would fail (exit 128), so skip it.
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
    # Sparse: only the directories the app reads (~10x smaller than the hub).
    $ParentOk = $true
    $HubParent = Split-Path -Parent $Hub
    if ($HubParent -and -not (Test-Path $HubParent)) {
        # Create the parent first: an unwritable or missing one fails early, by name.
        try {
            New-Item -ItemType Directory -Force -Path $HubParent -ErrorAction Stop | Out-Null
            Ok "created $HubParent"
        } catch {
            $ParentOk = $false
            $HubCloneFailed = $true
            Warn "cannot create $HubParent"
            Warn "  $($_.Exception.Message)"
            Show-CfaHint $HubParent
        }
    }
    if ($ParentOk) {
        Info "fetching FluSight data (sparse, about 150 MB); a few minutes..."
        $clone = Invoke-Captured "git" @("clone", "--filter=blob:none", "--sparse",
            "--depth", "1", "https://github.com/cdcepi/FluSight-forecast-hub", $Hub)
        # Check the exit code AND the result on disk.
        if ($clone.Code -eq 0 -and (Test-Path $HubGit)) {
            # `set` only here: this clone was made a statement ago, so its cone
            # is empty and nothing can be pruned. Elsewhere, `add`.
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
            $HubCloneFailed = $true
            Warn "git clone failed ($(CodeStr $clone)). git said:"
            Show-Output $clone 20
            Show-CfaHint $Hub
            Warn "Nothing else was changed; re-run this script once that is fixed."
        }
    }
}

Say "perl (engine network generation)"
$Perl = Get-Command perl -ErrorAction SilentlyContinue
$PerlOffPath = $false
if (-not $Perl) {
    # A fresh winget install is not on this process's PATH: look in
    # Strawberry's folders before offering to install it again.
    foreach ($cand in @("$env:SystemDrive\Strawberry\perl\bin\perl.exe",
                        "$env:ProgramFiles\Strawberry\perl\bin\perl.exe",
                        "C:\Strawberry\perl\bin\perl.exe")) {
        if (Test-Path $cand) {
            $Perl = [pscustomobject]@{ Source = $cand }
            $PerlOffPath = $true
            break
        }
    }
}
if ($Perl) {
    Ok "perl found: $($Perl.Source)"
    if ($PerlOffPath) {
        Warn "It is installed but not on THIS window's PATH. Open a new window"
        Warn "before running the engine, or BNG2.pl will not find it."
    }
} else {
    Warn "perl not found. BioNetGen's BNG2.pl needs Perl for the one-time"
    Warn "network-generation step of the PF engine; Strawberry Perl"
    Warn "(https://strawberryperl.com) is the standard choice on Windows."
    Warn "The console, analogue engine, and reports do not need it."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    # Package id unverified on Windows (a wrong one just exits non-zero; the
    # link stands). winget is absent on some Enterprise/LTSC images.
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
            # -1978335189 = APPINSTALLER_CLI_ERROR_UPDATE_NOT_APPLICABLE:
            # already installed, which is success here.
            if ($wcode -eq 0 -or $wcode -eq -1978335189) {
                if ($wcode -eq 0) { Ok "Strawberry Perl installed." }
                else { Ok "Strawberry Perl was already installed." }
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
    <# Can this machine read $Remote now? "yes", "no" or "unknown". Never
       clones, writes, prompts or hangs: GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=echo
       and credential.interactive=false forbid prompts while GCM can still
       answer from its cache; ssh BatchMode + ConnectTimeout bound ssh; a
       wall-clock timeout kills the tree with taskkill /T (PS 5.1 has no
       Kill($true); untested on Windows). #>
    param([string]$Remote, [int]$TimeoutMs = 15000)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return "unknown" }
    $o = Join-Path ([IO.Path]::GetTempPath()) "flubnf-lsremote.out"
    $e = Join-Path ([IO.Path]::GetTempPath()) "flubnf-lsremote.err"
    $saved = @{}
    foreach ($k in @("GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "GIT_SSH_COMMAND")) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
    }
    try {
        $env:GIT_TERMINAL_PROMPT = "0"
        $env:GIT_ASKPASS = "echo"
        $env:GIT_SSH_COMMAND = "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
        # Keep the system gitconfig (GIT_CONFIG_NOSYSTEM unset) and the
        # credential helpers: GCM's cache is how Desktop-onboarded machines
        # authenticate, and hiding it reported false "no access" (2026-08-25).
        $gitArgs = @("-c", "credential.interactive=false",
                     "ls-remote", "--heads", $Remote, "feature/particle-filter")
        # splatted, not backtick-continued (fragile under CRLF/trailing space)
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
        # Keep git's stderr: it tells auth failure from 404, proxy or no invitation.
        try {
            $script:LastRemoteError = (Get-Content $e -Raw -ErrorAction SilentlyContinue)
        } catch { $script:LastRemoteError = $null }
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
    # Probe as runners load the fork (checkout on sys.path, see
    # app/core/engines/pf.py), not pip's view: the editable install can fail
    # on Windows while fits work. ParticleFilter is what stock pybnf lacks.
    $probe = "import sys; sys.path.insert(0, r'$PyBnf'); import bngsim; " +
             "from pybnf.pf import ParticleFilter; " +
             "print('pf ok, bngsim ' + bngsim.__version__)"
    $imp = Invoke-Captured $EnginePy @("-c", $probe)
    if ($imp.Code -eq 0) {
        $EngineReady = $true
    } else {
        # A venv that imports badly (e.g. NumPy 2) is not "no access".
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
        Warn "this machine cannot read $PyBnfRemote. git said:"
        if ($script:LastRemoteError) {
            foreach ($ln in ($script:LastRemoteError -split "`r?`n")) {
                if ($ln.Trim()) { Info "    $($ln.Trim())" }
            }
        } else {
            Info "    (git produced no error text)"
        }
        # Read git's words: "no credential cached" and "no access" need
        # opposite advice. (Desktop sign-in does not give command-line git a
        # credential, so "use GitHub Desktop" is not offered.)
        $errText = [string]$script:LastRemoteError
        if ($errText -match "Authentication failed|Invalid username or token|could not read Username|Cannot prompt") {
            Warn "  DIAGNOSIS: no credential for github.com is cached on this"
            Warn "  machine. This is not a permissions problem, and nothing"
            Warn "  above needs changing. Run the clone below ONCE by hand:"
            Warn "  Git Credential Manager will open a browser window, you"
            Warn "  authenticate once, and every later run is silent."
        } elseif ($errText -match "not found|does not exist|403|Forbidden") {
            Warn "  DIAGNOSIS: the credential worked but the account it belongs"
            Warn "  to cannot see this repository. Either the invitation was"
            Warn "  never accepted (check github.com/notifications) or the"
            Warn "  signed-in account is not the one that was invited."
        } else {
            Warn "  1) ask Ely for a collaborator invitation to PyBNF-Private,"
            Warn "     and accept it at github.com/notifications"
            Warn "  2) run the clone below once by hand so the credential"
            Warn "     manager can authenticate you interactively"
        }
        Warn "  Prefer SSH? setx FLUBNF_PYBNF_REMOTE git@github.com:elyfmiller/PyBNF-Private.git"
        Info "With access, the remaining steps are:"
        Info "  git clone -b feature/particle-filter $PyBnfRemote $PyBnf"
    } else {
        Warn "access to the fork was not checked, or could not be determined:"
        Warn "no git, no network, the probe was skipped, or it timed out."
        Info "If you do have access:"
        Info "  git clone -b feature/particle-filter $PyBnfRemote $PyBnf"
    }
    # Engine venv needs Python 3.11/3.12 (numpy<2 wheels stop at cp312; a
    # source build dies on MAX_PATH): print a suitable interpreter, else conda.
    $EngineBootCmd = $null
    foreach ($c in @(@{exe="py"; args=@("-3.12")}, @{exe="py"; args=@("-3.11")})) {
        try { $vv = & $c.exe @($c.args + @("-c", "import sys; print(sys.version_info[1])")) 2>$null }
        catch { $vv = $null }
        if ($vv) { $EngineBootCmd = "$($c.exe) $($c.args -join ' ')"; break }
    }
    if (-not $EngineBootCmd -and $v) {
        try { if ([version]"$v" -lt [version]"3.13") { $EngineBootCmd = "$PyExe $($PyArgs -join ' ')".Trim() } } catch { }
    }
    if ($EngineBootCmd) {
        Info "  $EngineBootCmd -m venv $EngineVenv"
    } else {
        Info "  (your Python is newer than the engine's numpy pin supports; make a 3.12 first)"
        Info "  conda create -y -p $env:USERPROFILE\.venvs\flubnf-engine-py312 python=3.12"
        Info "  $env:USERPROFILE\.venvs\flubnf-engine-py312\python.exe -m venv $EngineVenv"
    }
    # Same pins as setup_engine.sh: the runtime set explicitly (all have
    # win_amd64 wheels), then the fork --no-deps (its msgpack==0.6.2 pin has
    # no Windows wheel and needs MSVC).
    Info "  $EngineVenv\Scripts\pip install `"numpy<2`" scipy pandas `"bngsim==0.15.1`" `"dask==2022.12.1`" `"distributed==2022.12.1`" msgpack pyparsing tornado libroadrunner python-libsbml"
    Info "  $EngineVenv\Scripts\pip install -e $PyBnf --no-deps"
    Info "  then re-run this script"
    Warn "Without the engine: the console, analogue engine, and reports all work."
}

Say "environment"
# Twin of .flubnf.env: User env vars (future processes only) plus
# .flubnf.env.cmd, which FluBNF.bat reads on every launch.
# PYTHONUTF8: Windows defaults text I/O to cp1252, breaking the UTF-8 assets.
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PY_ENGINE", $EnginePy, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PYBNF", $PyBnf, "User")
# No FLUBNF_HUB after a failed clone: a User value wins every later
# Resolve-Checkout and would pin the unwritable path (the launcher and
# settings.py resolve the same default without it). Skipped, never cleared:
# a deliberate value (say, an unplugged D:) must survive. Stale pins are
# reported in the CFA section.
if ($HubCloneFailed) {
    Warn "FLUBNF_HUB was left alone rather than set to"
    Warn "  $Hub"
    Warn "The clone into it did not produce a checkout, and recording a location"
    Warn "setup could not create would send every future run straight back to"
    Warn "it. Whatever FLUBNF_HUB was before this run, it still is. Fix the"
    Warn "cause above and re-run; nothing else was left half-done."
    Ok "user environment recorded (FLUBNF_PY_ENGINE, FLUBNF_PYBNF)"
} else {
    [Environment]::SetEnvironmentVariable("FLUBNF_HUB", $Hub, "User")
    Ok "user environment recorded (FLUBNF_HUB, FLUBNF_PY_ENGINE, FLUBNF_PYBNF)"
}

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
    # cmd reads batch files in the OEM code page (not Set-Content's ANSI; only
    # accented paths differ, untested). No BOM: it breaks "@echo off".
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

# exit 0 = setup finished (fatal cases exited 1 above). "Some externals
# missing" is a normal end state, so the doctor's $LASTEXITCODE must not
# reach FluBNF.bat as "setup.ps1 reported a problem".
exit 0
