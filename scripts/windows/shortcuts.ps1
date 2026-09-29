<#
  Put FluBNF where Windows finds it. The FluBNF folder sits in hidden
  AppData (%LOCALAPPDATA%\FluBNF\flubnf by default), so without this a
  student pastes that path into File Explorer to open it. This makes:

    * a Start menu shortcut named FluBNF: typing FluBNF in the Windows
      search box finds it, and right-click > Pin to taskbar (or Pin to
      Start) keeps it one click away;
    * once per Windows account, the same shortcut on the Desktop. Deleted,
      it stays deleted: the record lives outside the clone, so neither a
      reclone nor a rebuilt .venv brings it back. One that is still there
      is re-pointed with the Start menu one.

  Both run FluBNF.bat in THIS folder through cmd.exe (Windows will not pin
  a shortcut whose target is a .bat) with FluBNF's icon. FluBNF.bat runs
  this when the Start menu shortcut is missing or was made for another
  folder (a second clone, a moved one); running it by hand is fine too.
  It never fails a launch: any problem is one line of output, and exit 0.
  The parameters exist for the tests; FluBNF.bat passes none.
#>
param(
    [string]$StartMenu = [Environment]::GetFolderPath("Programs"),
    [string]$Desktop = [Environment]::GetFolderPath("Desktop"),
    [string]$RecordDir = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "FluBNF")
)
$ErrorActionPreference = "Stop"

try {
    $Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $Bat = Join-Path $Repo "FluBNF.bat"
    $Icon = Join-Path $Repo "scripts\windows\FluBNF.ico"
    $Cmd = Join-Path ([Environment]::SystemDirectory) "cmd.exe"
    $Shell = New-Object -ComObject WScript.Shell

    function Save-FluBNFShortcut([string]$Path) {
        $lnk = $Shell.CreateShortcut($Path)
        $lnk.TargetPath = $Cmd
        # cmd strips the outer pair of quotes; the inner pair keeps a path
        # with spaces (C:\Users\Jane Doe\...) in one piece
        $lnk.Arguments = '/c ""' + $Bat + '""'
        $lnk.WorkingDirectory = $Repo
        $lnk.IconLocation = $Icon + ",0"
        $lnk.Description = "FluBNF forecasting console"
        $lnk.Save()
    }

    foreach ($dir in @($StartMenu, $RecordDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Save-FluBNFShortcut (Join-Path $StartMenu "FluBNF.lnk")
    Write-Host "  FluBNF is in the Start menu: type FluBNF in the Windows search box to open it."

    $desktopLnk = Join-Path $Desktop "FluBNF.lnk"
    $offered = Join-Path $RecordDir "desktop-shortcut.txt"
    if ($Desktop -and (Test-Path -LiteralPath $Desktop)) {
        if (Test-Path -LiteralPath $desktopLnk) {
            Save-FluBNFShortcut $desktopLnk
        } elseif (-not (Test-Path -LiteralPath $offered)) {
            Save-FluBNFShortcut $desktopLnk
            Write-Host "  A FluBNF shortcut is on the Desktop too (delete it if you do not want it; it will not come back)."
        }
        Set-Content -LiteralPath $offered -Value "made once; FluBNF does not remake a deleted Desktop shortcut" -Encoding Ascii
    }

    # the folder the Start menu shortcut opens, one line, for FluBNF.bat's
    # quick check on later opens (Default = the ANSI code page cmd reads)
    Set-Content -LiteralPath (Join-Path $RecordDir "start-menu.txt") -Value $Repo -Encoding Default
} catch {
    Write-Host ("  could not add FluBNF to the Start menu: " + $_.Exception.Message)
}
exit 0
