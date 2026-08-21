# flubnf one-command setup (Windows). Idempotent: re-running fixes what is
# missing. PowerShell twin of setup.sh. Run with:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Continue"
function Say($m)  { Write-Host "`n== $m ==" }
function Ok($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Hub = if ($env:FLUBNF_HUB) { $env:FLUBNF_HUB }
       else { Join-Path $HOME "Documents\GitHub\FluSight-forecast-hub" }
$EngineVenv = if ($env:FLUBNF_ENGINE_VENV) { $env:FLUBNF_ENGINE_VENV }
              else { Join-Path $HOME ".venvs\flubnf-engine" }
$PyBnf = if ($env:FLUBNF_PYBNF) { $env:FLUBNF_PYBNF }
         else { Join-Path $HOME "Documents\GitHub\PyBNF-pf" }
$EnginePy = Join-Path $EngineVenv "Scripts\python.exe"

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
    try { $v = & $c.exe @($c.args) "-c" "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null }
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
    exit 1
}
Ok "Python $v via $(@($PyExe) + $PyArgs -join ' ')"

Say "analysis venv (.venv) + package"
$VenvPy = Join-Path $Here ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) { & $PyExe @($PyArgs) "-m" "venv" (Join-Path $Here ".venv") }
if (-not (Test-Path $VenvPy)) { Warn "venv creation failed"; exit 1 }
& $VenvPy -m pip install -q --upgrade pip
& $VenvPy -m pip install -q -e "$Here[app,dev]"
if ($LASTEXITCODE -eq 0) { Ok "flubnf installed editable" } else { Warn "pip install failed"; exit 1 }
& $VenvPy -m pip install -q bionetgen
if ($LASTEXITCODE -eq 0) { Ok "bionetgen (BNG2.pl + Windows binaries) installed" }

Say "FluSight hub data"
if (Test-Path (Join-Path $Hub ".git")) {
    Ok "hub present: $Hub"
} elseif ($env:FLUBNF_NO_DATA -eq "1") {
    Warn "data skipped (FLUBNF_NO_DATA=1) -- set FLUBNF_HUB later"
} else {
    # No questions: sparse checkout pulls ONLY the data directories the app
    # reads (about 10x smaller than the full hub, which is mostly other
    # teams' forecast files).
    Write-Host "  fetching FluSight data (sparse, about 150 MB)..."
    git clone --filter=blob:none --sparse --depth 1 `
        https://github.com/cdcepi/FluSight-forecast-hub $Hub 2>$null
    if ($LASTEXITCODE -eq 0) {
        Push-Location $Hub
        git sparse-checkout set auxiliary-data target-data `
            model-output/FluSight-baseline model-output/FluSight-ensemble
        Pop-Location
        Ok "hub data ready (sparse): $Hub"
    } else {
        Warn "data fetch failed (offline? git missing?) -- rerun setup.ps1 when connected"
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
}

Say "engine venv (pybnf + bngsim)"
$EngineReady = $false
if (Test-Path $EnginePy) {
    & $EnginePy -c "import pybnf, bngsim" 2>$null
    if ($LASTEXITCODE -eq 0) { $EngineReady = $true }
}
if ($EngineReady) {
    Ok "engine venv ready: $EngineVenv"
} else {
    Warn "engine venv not ready. The PF engine (fit_type=pf) needs a PyBNF fork"
    Warn "that is not yet public. If you have access:"
    Warn "  git clone -b feature/particle-filter <your PyBNF fork> $PyBnf"
    Warn "  $PyExe $($PyArgs -join ' ') -m venv $EngineVenv"
    Warn "  $EngineVenv\Scripts\pip install `"numpy<2`" scipy pandas bngsim"
    Warn "  $EngineVenv\Scripts\pip install -e $PyBnf"
    Warn "Without it: the console, analogue engine, and reports still work."
}

Say "environment"
# The Windows analogue of setup.sh's .flubnf.env: user-level environment
# variables, read by every future FluBNF.bat launch without any sourcing.
# UTF-8 mode: Windows defaults text I/O to cp1252, which breaks reads of
# the app's UTF-8 assets. This makes every Python launch behave like
# macOS/Linux.
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
[Environment]::SetEnvironmentVariable("FLUBNF_HUB", $Hub, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PY_ENGINE", $EnginePy, "User")
[Environment]::SetEnvironmentVariable("FLUBNF_PYBNF", $PyBnf, "User")
Ok "user environment recorded (FLUBNF_HUB, FLUBNF_PY_ENGINE, FLUBNF_PYBNF)"

Say "doctor"
$env:FLUBNF_HUB = $Hub
$env:FLUBNF_PY_ENGINE = $EnginePy
$env:FLUBNF_PYBNF = $PyBnf
& $VenvPy -c "from flubnf.settings import check; import sys; sys.exit(1 if check() else 0)"
if ($LASTEXITCODE -eq 0) {
    Ok "all externals present -- you are ready: double-click FluBNF.bat"
} else {
    Warn "some externals missing (listed above) -- console still runs: double-click FluBNF.bat"
}
