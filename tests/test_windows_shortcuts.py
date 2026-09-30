"""FluBNF is findable on Windows without its path.

The clone sits in hidden AppData (%LOCALAPPDATA%\\FluBNF\\flubnf), so
FluBNF.bat runs scripts/windows/shortcuts.ps1 when the Start menu shortcut
is missing or opens another folder: a Start menu entry (type FluBNF in the
search box) and, once per account, a Desktop shortcut. The text checks run
everywhere; the shortcut files are made for real on Windows."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BAT = (REPO / "FluBNF.bat").read_bytes().decode("ascii")
PS1 = (REPO / "scripts" / "windows" / "shortcuts.ps1").read_text(
    encoding="ascii")
ICON = REPO / "scripts" / "windows" / "FluBNF.ico"

windows_only = pytest.mark.skipif(os.name != "nt",
                                  reason="makes real Windows shortcuts")


def _hook() -> str:
    i = BAT.index("\r\n:startconsole\r\n")
    return BAT[i:BAT.index("\r\n:shortcutsdone\r\n", i)]


# ------------------------------------------------------------- FluBNF.bat
def test_the_launcher_makes_the_shortcuts_before_the_console_starts():
    hook = _hook()
    assert ('powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass '
            '-File "%CD%\\scripts\\windows\\shortcuts.ps1" <nul') in hook
    start = BAT.index('".venv\\Scripts\\flubnf" app')
    assert BAT.index("\r\n:shortcutsdone\r\n") < start
    # every path to the console passes through it
    assert BAT.count("\r\n:startconsole\r\n") == 1


def test_a_normal_open_costs_two_file_tests_not_a_powershell():
    """PowerShell starts only when the Start menu shortcut is missing or
    was made for another folder (a second clone, a moved one)."""
    hook = _hook()
    lines = hook.split("\r\n")
    call = next(i for i, ln in enumerate(lines) if ln.startswith("powershell"))
    skip = next(i for i, ln in enumerate(lines)
                if ln == 'if /I "%SHORTCUTFOR%"=="%CD%" goto :shortcutsdone')
    assert skip < call
    assert ('if not exist "%APPDATA%\\Microsoft\\Windows\\Start Menu\\'
            'Programs\\FluBNF.lnk" goto :shortcutsmake') in lines
    assert ('if exist "%LOCALAPPDATA%\\FluBNF\\start-menu.txt" set /p '
            'SHORTCUTFOR=<"%LOCALAPPDATA%\\FluBNF\\start-menu.txt"') in lines
    assert 'if /I "%FLUBNF_SHORTCUTS%"=="off" goto :shortcutsdone' in lines


def test_the_hook_leaves_the_self_updates_bytes_alone():
    """cmd.exe resumes a rewritten FluBNF.bat at the old byte offset; the
    hook sits far below the frozen head (tests/test_windows_launcher.py)."""
    assert BAT.index("\r\n:startconsole\r\n") > 3317


# --------------------------------------------------------- shortcuts.ps1
def test_the_shortcut_runs_this_folders_launcher_through_cmd():
    """cmd.exe, not the .bat, so Windows offers Pin to taskbar; the inner
    quotes keep a profile path with a space in one piece."""
    assert 'Join-Path ([Environment]::SystemDirectory) "cmd.exe"' in PS1
    assert "$lnk.TargetPath = $Cmd" in PS1
    assert "$lnk.Arguments = '/c \"\"' + $Bat + '\"\"'" in PS1
    assert '$Bat = Join-Path $Repo "FluBNF.bat"' in PS1
    assert '$lnk.IconLocation = $Icon + ",0"' in PS1


def test_the_start_menu_and_desktop_come_from_windows_not_from_guesses():
    """Known folders, so OneDrive's Desktop redirection is followed."""
    assert '[Environment]::GetFolderPath("Programs")' in PS1
    assert '[Environment]::GetFolderPath("Desktop")' in PS1
    assert 'GetFolderPath("LocalApplicationData")) "FluBNF"' in PS1


def test_cmd_writes_the_record_it_reads_so_an_accented_path_matches():
    """PowerShell's Default encoding is the ANSI code page, cmd reads the
    OEM one: for C:\\Users\\José a record PowerShell wrote never matched,
    and every open ran PowerShell again. cmd writes it, after the call."""
    lines = _hook().split("\r\n")
    call = next(i for i, ln in enumerate(lines) if ln.startswith("powershell"))
    write = lines.index('if exist "%APPDATA%\\Microsoft\\Windows\\Start Menu\\'
                        'Programs\\FluBNF.lnk" cd >"%LOCALAPPDATA%\\FluBNF\\'
                        'start-menu.txt"')
    assert call < write
    assert "start-menu.txt" not in PS1.split("#>", 1)[1].replace(
        "# start-menu.txt", "")


def test_it_never_fails_a_launch():
    body = PS1[PS1.index("try {"):]
    assert "} catch {" in body and body.rstrip().endswith("exit 0")


def test_the_icon_is_a_windows_icon_with_the_sizes_explorer_asks_for():
    data = ICON.read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00", "not an ICO file"
    count = int.from_bytes(data[4:6], "little")
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert {16, 32, 48, 256} <= sizes, sizes


def test_it_is_ascii_with_crlf_like_the_other_windows_scripts():
    raw = (REPO / "scripts" / "windows" / "shortcuts.ps1").read_bytes()
    raw.decode("ascii")
    if os.name != "nt" and b"\r\n" not in raw:
        pytest.skip("checked out with LF; git writes CRLF on Windows")
    assert raw.count(b"\n") == raw.count(b"\r\n")


@pytest.mark.skipif(shutil.which("pwsh") is None,
                    reason="PowerShell is not installed")
def test_it_parses():
    script = REPO / "scripts" / "windows" / "shortcuts.ps1"
    r = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command",
         "$e=$null;$t=$null;[void][System.Management.Automation.Language."
         f"Parser]::ParseFile('{script}',[ref]$t,[ref]$e);$e.Count"],
        capture_output=True, text=True, timeout=120)
    assert r.stdout.strip() == "0", r.stdout + r.stderr


# ------------------------------------------------------ on Windows, for real
def _run(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(REPO / "scripts" / "windows" / "shortcuts.ps1"),
         "-StartMenu", str(tmp_path / "Start Menu" / "Programs"),
         "-Desktop", str(tmp_path / "Desktop"),
         "-RecordDir", str(tmp_path / "FluBNF")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)


def _read_lnk(path: Path) -> dict:
    ps = ("$l=(New-Object -ComObject WScript.Shell).CreateShortcut("
          f"'{path}'); $l.TargetPath; $l.Arguments; $l.WorkingDirectory; "
          "$l.IconLocation")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, timeout=60)
    target, args, cwd, icon = (r.stdout.splitlines() + [""] * 4)[:4]
    return {"target": target, "args": args, "cwd": cwd, "icon": icon}


def _same(a: str, b: Path) -> bool:
    return Path(a).resolve() == b.resolve()


@windows_only
def test_a_first_run_puts_it_in_the_start_menu_and_on_the_desktop(tmp_path):
    (tmp_path / "Desktop").mkdir()
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "could not" not in r.stdout, r.stdout
    assert "type FluBNF in the Windows search box" in r.stdout
    start = tmp_path / "Start Menu" / "Programs" / "FluBNF.lnk"
    lnk = _read_lnk(start)
    assert lnk["target"].lower().endswith("\\cmd.exe"), lnk
    assert str(REPO / "FluBNF.bat").lower() in lnk["args"].lower(), lnk
    assert _same(lnk["cwd"], REPO), lnk
    assert "flubnf.ico" in lnk["icon"].lower(), lnk
    assert (tmp_path / "Desktop" / "FluBNF.lnk").is_file()


@windows_only
def test_a_deleted_desktop_shortcut_stays_deleted(tmp_path):
    (tmp_path / "Desktop").mkdir()
    assert _run(tmp_path).returncode == 0
    (tmp_path / "Desktop" / "FluBNF.lnk").unlink()
    (tmp_path / "Start Menu" / "Programs" / "FluBNF.lnk").unlink()
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "Start Menu" / "Programs" / "FluBNF.lnk").is_file()
    assert not (tmp_path / "Desktop" / "FluBNF.lnk").exists()
    assert "Desktop" not in r.stdout


@windows_only
def test_a_problem_is_one_line_and_never_a_failed_launch(tmp_path):
    """A Start menu folder that cannot be made (a file in its place)."""
    (tmp_path / "Start Menu").write_text("in the way")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "could not add FluBNF to the Start menu" in r.stdout
