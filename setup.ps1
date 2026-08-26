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

# WHERE THE CHECKOUTS GO, AND WHY IT IS NO LONGER Documents.
#
# Controlled Folder Access, the ransomware protection built into Microsoft
# Defender, protects Documents, Pictures, Videos, Music and Favorites (and
# their C:\Users\Public counterparts) whenever it is switched on. A
# protected folder can be read by anything and written only by programs
# Defender trusts, and neither git.exe nor python.exe is trusted out of the
# box. Recorded on the corresponding author's Windows 11 machine on
# 2026-08-25, in the Defender operational log, verbatim:
#
#   Id 1123  git.exe has been blocked from modifying
#            %userprofile%\Documents\GitHub\FluSight-forecast-hub
#   Id 1123  python.exe has been blocked from modifying
#            %userprofile%\Documents\GitHub\PyBNF-pf\pybnf\__pycache__
#
# The message the USER sees in each case is an ordinary permission error
# that never mentions Defender, so the old defaults produced two failures
# that cannot be diagnosed from the failure.
#
# IT IS NOT ON BY DEFAULT, and an earlier draft of this file said it was.
# Microsoft documents the shipped state as Disabled: "CFA is turned off by
# default", with mode 0 marked "(default)". Get-MpPreference on the author's
# machine nonetheless reports EnableControlledFolderAccess = 1, so something
# turned it on there -- the author, the manufacturer's image, or IT policy
# on a managed machine. That is the point: it is ON for at least one real
# user of this project and may be ON for any student, so the defaults must
# not depend on it being off. Nothing in this script assumes either way; it
# asks the machine and reports what it is told.
#
# %LOCALAPPDATA% is the documented per-user location for application data
# (FOLDERID_LocalAppData). It is not in the protected set; it is per-user,
# so nothing here needs an administrator; and unlike %APPDATA% it does not
# roam and is not swept into OneDrive by Known Folder Move, which matters
# for a 150 MB clone made of tens of thousands of small files. C:\FluBNF was
# considered and rejected: creating a directory at the root of the system
# drive needs elevation on a default install.
#
# The engine venv default (~\.venvs) is deliberately unchanged. Controlled
# Folder Access protects named folders inside the profile, not the profile
# root, so ~\.venvs was never at risk.
#
# macOS and Linux are untouched by all of this; setup.sh keeps its
# ~/Documents/GitHub defaults, because those systems have no equivalent.
#
# ONE PROFILE ROOT, RESOLVED ONCE. FluBNF.bat reads %USERPROFILE% and
# flubnf/settings.py calls Path("~").expanduser(), which prefers
# %USERPROFILE% too. $HOME is a THIRD answer: the PowerShell 7 documentation
# says it takes %USERPROFILE% and warns that it "may not have the same value
# as $Env:HOMEDRIVE$Env:HOMEPATH", while the 5.1 documentation described it
# as the equivalent of %homedrive%%homepath%. We cannot run either from
# macOS to settle it, and on a university-managed machine with an Active
# Directory home directory the two are genuinely different (H:\, or a UNC
# path). So this script stops depending on the answer: it prefers
# %USERPROFILE%, exactly as the launcher and the Python side do, and where a
# LOOKUP rather than a default is at stake it probes $HOME as well, so a
# checkout made by an earlier release under either root is still found.
$ProfileRoot = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA }
                else { Join-Path $ProfileRoot "AppData\Local" }
$FluBnfRoot = Join-Path $LocalAppData "FluBNF"

function Get-ProfileRoots {
    <#
      Every plausible spelling of the user profile, most authoritative
      first, de-duplicated. One entry on an ordinary machine; two where
      $HOME and %USERPROFILE% disagree.
    #>
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
    <#
      FLUBNF_* wins; then an EXISTING checkout at the old Documents default,
      used exactly where it stands; then the new default under %LOCALAPPDATA%.

      NOTHING IS EVER MOVED OR COPIED. The author has 143 MB of PyBNF
      checkout and 150 MB of hub under Documents, and relocating a working
      tree is not a decision a setup script may take on a user's behalf. A
      machine that already works keeps working with no action at all; the
      reuse is announced in the plan block, and named again in the
      Controlled Folder Access warning below when that protection is on.
    #>
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
    <#
      A path under the user profile, for something this script did not
      necessarily create. Prefers %USERPROFILE%, but if an earlier release
      built it under a DIFFERENT profile root ($HOME on a machine where the
      two disagree) and that one exists while the preferred one does not,
      the existing one wins. Stranding a working install is the one outcome
      this whole file is written to avoid.
    #>
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
    <#
      Is $Child the same directory as $Parent, or somewhere beneath it?
      Purely lexical (GetFullPath does not touch the disk), which is what is
      wanted: the paths being tested may not exist yet.
    #>
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
    <#
      The folders Controlled Folder Access protects by default.

      Microsoft's documented default set is Documents, Favorites, Music,
      Pictures and Videos under each user profile, plus the C:\Users\Public
      counterparts of Documents, Music, Pictures and Videos, "for user
      accounts and system accounts". Desktop is NOT in that list, but the
      same page names Desktop when it describes OneDrive Known Folder Move
      redirection, other Microsoft pages have listed it, and the Windows
      Security app shows the live list. Desktop stays in here deliberately:
      this list only decides whether a WARNING is printed, so an entry too
      many costs a sentence and an entry too few costs the whole point.

      Read through GetFolderPath rather than assembled from a profile root,
      so that a Documents folder redirected into OneDrive by Known Folder
      Move is the one tested. The literal profile paths are added as well,
      because a redirected known folder leaves the plain one in place on
      some machines and both can hold a checkout, and every spelling of the
      profile root is used because $HOME and %USERPROFILE% can differ.

      The machine's OWN list, when Defender will tell us, is unioned in by
      the caller; see Get-CfaState. This function is the fallback for when
      it will not, which includes the documented case of CFA being off and
      the likely case of not running elevated.
    #>
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
    <#
      Controlled Folder Access state as @{ State; Why; Folders }, where
      State is "on", "audit", "off" or "unknown" and Folders is whatever
      list of protected folders the machine was willing to hand over.

      Get-MpPreference is the documented way to read it. It is NOT assumed to
      work: the Defender PowerShell module is absent on some images, a
      third-party antivirus can leave it present but non-functional, and an
      older build may not carry the property at all. Every one of those is
      "unknown" plus the reason, never a crash and never a guess.

      Documented mode values, all five of them:
        0 Disabled (the shipped default)
        1 Enabled -- untrusted apps blocked from protected folders
        2 AuditMode -- the same, logged instead of blocked
        3 BlockDiskModificationOnly
        4 AuditDiskModificationOnly
      3 and 4 act ONLY on writes to the disk sectors holding the boot
      record; Microsoft is explicit that they "don't affect files in
      protected folders". For this script's one question -- can git and
      python write into a checkout -- they are indistinguishable from off,
      and reporting them as "unknown" would have printed a page of alarming
      and irrelevant advice on a machine that was never going to block us.

      Both the number and the enumeration NAME are accepted, because
      Get-MpPreference returns a typed value whose rendering we cannot check
      from macOS, and a cast that guessed wrong would report "unknown" on a
      machine that answered perfectly well. Anything else is reported as the
      literal text it was, not folded into a verdict this cannot justify.
    #>
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
    # THE MACHINE'S OWN ANSWER, PREFERRED OVER OUR LIST OF DEFAULTS.
    # ControlledFolderAccessProtectedFolders holds folders an administrator
    # or the user ADDED; ...DefaultProtectedFolders holds the built-in set,
    # and Microsoft documents it as populated only when CFA is turned on and
    # read from an elevated session. Either may therefore be empty, which is
    # why Get-ProtectedFolders stays as the fallback rather than being
    # replaced. Anything we do get is strictly better than a guess: on a
    # managed image where IT protected an extra folder, this is the only way
    # to know.
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

$Hub = Resolve-Checkout $env:FLUBNF_HUB "FluSight-forecast-hub"
$PyBnf = Resolve-Checkout $env:FLUBNF_PYBNF "PyBNF-pf"
$EngineVenv = if ($env:FLUBNF_ENGINE_VENV) { $env:FLUBNF_ENGINE_VENV }
              # Resolve-ProfilePath, not a bare join: flubnf/settings.py
              # expands ~/.venvs/flubnf-engine through %USERPROFILE%, so
              # that is the spelling to prefer, and an engine venv an
              # earlier release built under the other profile root is still
              # found rather than silently rebuilt beside it.
              else { Resolve-ProfilePath ".venvs\flubnf-engine" }
$PyBnfRemote = if ($env:FLUBNF_PYBNF_REMOTE) { $env:FLUBNF_PYBNF_REMOTE }
               # HTTPS by default, not SSH. Students are onboarded through
               # GitHub Desktop, which installs Git Credential Manager and
               # caches an HTTPS credential, so a private clone just works
               # with no key to generate. Override with FLUBNF_PYBNF_REMOTE
               # if you prefer SSH.
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
# READ-ONLY, ALWAYS. This section asks Defender one question and prints
# advice. It never changes a Defender setting, never elevates, and never
# suggests switching Controlled Folder Access off: the protection is worth
# having, and a setup script is not the thing that gets to weaken it.
#
# It runs BEFORE anything is installed, because the failures it predicts are
# the ones that cannot be read off their own error messages, and a user who
# has been told what is coming can stop and fix it first.
$Cfa = Get-CfaState
$GitCmd = Get-Command git -ErrorAction SilentlyContinue
$GitExe = if ($GitCmd) { $GitCmd.Source }
          else { "C:\Program Files\Git\cmd\git.exe   (usual location; git is not on PATH here)" }
# Perl and run_network.exe are resolved HERE, before the perl section far
# below, because remedy 2 has to be able to name them. They are the writers
# behind the failure mode the other two miss: a fit materialises its BNGL
# model into app\state\workroots\<tag> INSIDE this repository and runs
# BNG2.pl there under perl, which writes m.net next to the model, and BNG's
# run_network.exe writes beside it. So a repository that sits in Documents
# breaks mid-fit even when the hub and the checkout are somewhere safe.
$PerlCmd = Get-Command perl -ErrorAction SilentlyContinue
$PerlExe = if ($PerlCmd) { $PerlCmd.Source }
           else { "C:\Strawberry\perl\bin\perl.exe   (usual location; perl is not on PATH here)" }
# bionetgen is a dependency of the CONSOLE venv, not the engine venv: see
# flubnf/settings.py::_bng_candidates, which looks under <repo>\.venv only.
$RunNetExe = Join-Path $VenvDir "Lib\site-packages\bionetgen\bng-win\run_network.exe"
# FromEnv records where the path CAME FROM, not just what it is. A recorded
# variable that names a protected folder which does not exist is a different
# problem from a default that happens to land in one, and it gets its own
# remedy below: it is a leftover from an earlier release rather than a choice.
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
# The documented defaults, plus whatever list this particular machine was
# willing to report. The union can only make the warning fire more often,
# never less, which is the right direction for a check whose false negative
# costs a day of misdiagnosis and whose false positive costs a paragraph.
# The inner parentheses are not decoration: they put the concatenation
# beyond any question about how much of the expression the pipeline claims.
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
# The console venv lives inside the repository, so listing both says the same
# thing twice; keep the repository line, which is the one a user can act on.
# @() around the pipeline: PowerShell unrolls a one-element result to a bare
# object, and .Count on that would be 1 for a string as readily as for a list.
if ((@($AtRisk | Where-Object { $_.Label -eq "repository" })).Count -gt 0) {
    $AtRisk = @($AtRisk | Where-Object { $_.Label -ne "console venv" })
}

if ($Cfa.State -eq "off") {
    # "will not block", not "is off": modes 3 and 4 also land here, and they
    # are switched ON -- they simply guard the boot sectors rather than any
    # folder, so for everything below they are indistinguishable from off.
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
            # quoted: setx takes the value as one argument, and a profile
            # directory with a space in it is common enough to plan for
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
    # THE STRANDED MACHINE. An earlier release of this script recorded the
    # Documents location in the User environment on every run, including
    # runs whose clone had just been blocked. That recorded value wins over
    # everything below it in Resolve-Checkout, so such a machine keeps
    # aiming at the folder it cannot write to and never reaches the new
    # default. It is not a user's choice and it should not be treated as
    # one, but it is also not this script's to silently overrule: naming it
    # and handing over the one-line fix is where the line is.
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

function Show-CfaHint {
    <#
      One line, at the moment a write actually fails, naming the protection
      that is the likely cause. The warning above is printed before the work
      and is therefore easy to scroll past; this fires next to the error the
      user is looking at, which is where it does the most good. Silent when
      the protection is off or the path is not protected.
    #>
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
# $VenvPy was resolved with the other paths at the top, so the Controlled
# Folder Access section could name it among the executables to allow.
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
# Set only where a clone was ATTEMPTED and did not produce a checkout. It
# gates the PERSISTENT record of FLUBNF_HUB at the end of this script: a
# location setup could not create is not a location to pin into the User
# environment for every future run, and pinning it is what stranded the
# machines this release exists to unstrand. Deliberately NOT set when the
# data fetch was merely skipped (FLUBNF_NO_DATA=1), where $Hub is still the
# right answer and simply has not been filled in yet.
$HubCloneFailed = $false
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
            Show-CfaHint $Hub
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
    # A winget install in THIS window updates the machine PATH but not the
    # PATH of an already-running process, so a perl installed a minute ago is
    # invisible to Get-Command until a new window opens. Look where Strawberry
    # actually puts it before declaring it missing, otherwise the script offers
    # to install something that is already there.
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
            # -1978335189 is APPINSTALLER_CLI_ERROR_UPDATE_NOT_APPLICABLE:
            # the package is already installed and no newer version exists.
            # winget reports that as a non-zero exit, but for our purposes it
            # is success, and reporting it as "declined UAC, no network" was
            # actively misleading on a machine where Perl was already present.
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
        # GIT_CONFIG_NOSYSTEM is deliberately NOT set. Git for Windows
        # configures Git Credential Manager in the SYSTEM gitconfig, so
        # hiding that file hides the helper, and the probe then reports "no
        # access" on every machine regardless of whether it has access. That
        # is what it did on 2026-08-25 to a machine signed in to GitHub
        # Desktop. credential.interactive=false plus the wall-clock timeout
        # below are what keep this from hanging, not the absence of a helper.
        # The helper list is deliberately NOT cleared. Clearing it stopped GCM
        # opening a GUI, but it also stopped GCM answering from its CACHE, so a
        # machine signed in to GitHub Desktop -- which is how this lab onboards
        # people -- was reported as having no access when it had access.
        # `credential.interactive=false` is the setting that forbids the
        # prompt while still allowing a stored credential to be returned, and
        # the hard wall-clock timeout below remains the backstop if some older
        # helper ignores it.
        $gitArgs = @("-c", "credential.interactive=false",
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
        # Keep git's own words. Deleting this unread was the same mistake this
        # script was rewritten to stop making everywhere else: "cannot read"
        # with no reason sends the reader guessing at credentials when the
        # answer may be a plain 404, a proxy, or a declined invitation.
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
    # Test the engine the way the ENGINE actually loads, not the way pip
    # would. app/core/engines/pf.py writes sys.path.insert(0, <checkout>) into
    # every generated runner, so the fork is imported from the checkout and a
    # pip install of it is not required to run a fit. Measured on Windows,
    # 2026-08-25: the editable install failed, this check reported "imports
    # fail", and fits ran perfectly anyway. A readiness check that disagrees
    # with the thing it is checking is worse than no check. Import
    # pybnf.pf.ParticleFilter specifically, since that class is the whole
    # reason the fork exists and a stock PyPI pybnf does not have it.
    $probe = "import sys; sys.path.insert(0, r'$PyBnf'); import bngsim; " +
             "from pybnf.pf import ParticleFilter; " +
             "print('pf ok, bngsim ' + bngsim.__version__)"
    $imp = Invoke-Captured $EnginePy @("-c", $probe)
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
        Warn "this machine cannot read $PyBnfRemote. git said:"
        if ($script:LastRemoteError) {
            foreach ($ln in ($script:LastRemoteError -split "`r?`n")) {
                if ($ln.Trim()) { Info "    $($ln.Trim())" }
            }
        } else {
            Info "    (git produced no error text)"
        }
        # Two very different problems produce "cannot read", and the advice
        # for each is the opposite of the other, so read git's own words
        # rather than guessing. Measured on Windows 11, 2026-08-25: being
        # signed in to GitHub Desktop does NOT populate the Windows Credential
        # Manager store that command-line git reads, so "just use GitHub
        # Desktop" was wrong advice and is not given any more.
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
    # numpy<2: the fork predates NumPy 2 and its historical fixes were
    # venv-local patches rather than commits, so the pin is the reproducible
    # answer. Same pin as setup_engine.sh on macOS and Linux.
    Info "  $PyExe $($PyArgs -join ' ') -m venv $EngineVenv"
    # Install the runtime set EXPLICITLY, then the fork with --no-deps.
    # PyBNF's setup.py pins msgpack==0.6.2, a 2019 release with no Windows
    # wheel for any modern Python, so letting pip resolve the fork's declared
    # dependencies makes it try to compile msgpack from source and fail on any
    # machine without MSVC build tools. Measured 2026-08-25: every package
    # below has a prebuilt win_amd64 wheel for Python 3.11, so no compiler is
    # needed. The list is what the PF path actually imports, traced rather
    # than guessed; PyBNF also declares nose and paramiko, which it never
    # imports.
    Info "  $EngineVenv\Scripts\pip install `"numpy<2`" scipy pandas `"bngsim==0.15.1`" `"dask==2022.12.1`" `"distributed==2022.12.1`" msgpack pyparsing tornado libroadrunner python-libsbml"
    Info "  $EngineVenv\Scripts\pip install -e $PyBnf --no-deps"
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
[Environment]::SetEnvironmentVariable("FLUBNF_PY_ENGINE", $EnginePy, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PYBNF", $PyBnf, "User")
# FLUBNF_HUB is the one that gets withheld after a failed clone. Writing it
# to the User environment PINS it: Resolve-Checkout returns an environment
# value ahead of everything else, so a run that recorded a location it could
# not create would send every later run back to the same place, past the
# legacy probe and past the current default. Leaving it unwritten costs
# nothing, because .flubnf.env.cmd below is rewritten on every run and
# FluBNF.bat and flubnf/settings.py resolve the identical default on their
# own; it simply lets the next run reconsider.
#
# It is SKIPPED, never cleared. Deleting the variable would also delete a
# value the user set deliberately -- FLUBNF_HUB=D:\... on a machine whose D:
# drive happened to be unplugged today -- and destroying a working
# configuration to fix a broken one is not a trade this script gets to make.
# A stale pin recorded by an earlier release is reported instead, by name
# and with its one-line fix, in the Controlled Folder Access section above.
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
