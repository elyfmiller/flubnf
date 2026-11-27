# The weight screen's replays on Ely's Windows PC: the engine named, the hub
# clone at the 10-24 screen's commit, a temporary state folder, below-normal
# priority, logged. Arguments go to replay.py after <out>.
#   replay.ps1 -Out <folder> [-Extra '--weeks','2024-12-07','--locations','Arizona,Ohio']
param([Parameter(Mandatory = $true)][string]$Out, [string[]]$Extra = @())
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$Hub = 'C:\Users\efinn\GitHub\FluSight-forecast-hub-model'
$want = '09c96ec8'
$head = (git -C $Hub rev-parse --short=8 HEAD).Trim()
if ($head -ne $want) { throw "hub clone at $head, not $want" }
# the User values, not a stale shell's
foreach ($n in 'FLUBNF_PYBNF', 'FLUBNF_PY_ENGINE', 'FLUBNF_PY_ENGINE_PUBLIC') {
    Set-Item "env:$n" ([Environment]::GetEnvironmentVariable($n, 'User'))
}
$env:FLUBNF_ENGINE = 'public'
$env:FLUBNF_HUB = $Hub
$env:FLUBNF_STATE_DIR = "$env:TEMP\flubnf-model-state"
$env:FLUBNF_SHORTCUTS = 'off'
$env:FLUBNF_UPDATE = 'off'
$env:PYTHONPATH = $Repo
New-Item -ItemType Directory -Force "$Out\logs" | Out-Null
$log = "$Out\logs\replay-$(Get-Date -Format yyyyMMdd-HHmmss).log"
"start $((Get-Date).ToUniversalTime().ToString('s'))Z repo $((git -C $Repo rev-parse --short=8 HEAD).Trim()) hub $head engine public" | Out-File $log -Encoding utf8
$p = Start-Process -FilePath "$Repo\.venv\Scripts\python.exe" -ArgumentList (@("`"$PSScriptRoot\replay.py`"", "`"$Out`"") + $Extra) `
    -WorkingDirectory $Repo -NoNewWindow -PassThru -RedirectStandardOutput "$log.out" -RedirectStandardError "$log.err"
$null = $p.Handle   # held, so ExitCode is readable after the exit
try { $p.PriorityClass = 'BelowNormal' } catch {}
"pid $($p.Id)" | Out-File $log -Append -Encoding utf8
$p.WaitForExit()
"exit $($p.ExitCode) $((Get-Date).ToUniversalTime().ToString('s'))Z" | Out-File $log -Append -Encoding utf8
exit $p.ExitCode
