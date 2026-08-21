"""Reduced-priority process helpers (app/core/proc.py) on both platforms.

POSIX lowers priority with a `nice` command prefix; Windows has no `nice`
and uses a process creation flag instead. Exactly one of the two forms is
active per platform, and both decline to {} / [] rather than fail: lower
priority is an optimization, never a precondition.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import proc                                  # noqa: E402


def test_posix_uses_a_nice_prefix_and_no_popen_kwargs():
    if os.name != "posix":
        return
    prefix = proc.low_priority_prefix()
    # [] when `nice` is genuinely absent; otherwise the documented form
    assert prefix == [] or prefix[1:] == ["-n", str(proc.NICENESS)]
    assert proc.low_priority_popen_kwargs() == {}


def test_windows_uses_creationflags_not_a_prefix(monkeypatch):
    flag = 0x00004000                     # BELOW_NORMAL_PRIORITY_CLASS
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", flag,
                        raising=False)
    assert proc.low_priority_prefix() == []
    assert proc.low_priority_popen_kwargs() == {"creationflags": flag}


def test_zero_niceness_disables_both_forms(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert proc.low_priority_cmd(["x"], niceness=0) == ["x"]
    assert proc.low_priority_popen_kwargs(niceness=0) == {}
