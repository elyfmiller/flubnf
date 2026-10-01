"""A download saved over an existing file replaces it in the macOS window
(flubnf/window_downloads.py).

pywebview's save panel only asks about Replace; WebKit then refuses the
taken name and drops the download without a word, so the old file stays.
The window's delegate removes what the user agreed to replace before
WebKit gets the path. Headless: the helper on real files, and the delegate
swap against a stand-in pywebview Cocoa module, AppKit and Foundation (no
PyObjC here). One check needs a Mac: download a CSV, change the saved copy,
download again and choose Replace; the copy must match the server's file.
"""
import os
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import cli                                    # noqa: E402
from flubnf import window_downloads as wd                 # noqa: E402

COCOA = "webview.platforms.cocoa"


# ------------------------------------------------- the destination helper

def test_a_free_path_is_handed_back_as_it_is(tmp_path):
    p = tmp_path / "2026-10-03-NAU_PyBNF-OracleSIHRS.csv"
    assert wd.clear_destination(str(p)) == str(p)
    assert not p.exists()


def test_the_file_the_user_agreed_to_replace_is_removed(tmp_path):
    p = tmp_path / "FluBNF-weekly-report-2026-09-26.html"
    p.write_text("yesterday's report")
    assert wd.clear_destination(p) == str(p)
    assert not p.exists()


def test_a_folder_is_never_removed_and_cancels_the_download(tmp_path):
    d = tmp_path / "reports"
    (d / "inside").mkdir(parents=True)
    assert wd.clear_destination(str(d)) is None
    assert (d / "inside").is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX links and pipes")
def test_links_and_odd_files(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    to_folder = tmp_path / "to-folder"
    to_folder.symlink_to(folder)
    assert wd.clear_destination(str(to_folder)) is None
    assert to_folder.is_symlink() and folder.is_dir()
    # a link to a file: the link goes, never its target
    target = tmp_path / "target.csv"
    target.write_text("keep")
    link = tmp_path / "link.csv"
    link.symlink_to(target)
    assert wd.clear_destination(str(link)) == str(link)
    assert not os.path.lexists(link) and target.read_text() == "keep"
    dangling = tmp_path / "dangling.csv"
    dangling.symlink_to(tmp_path / "gone.csv")
    assert wd.clear_destination(str(dangling)) == str(dangling)
    assert not os.path.lexists(dangling)
    # a pipe is not a file to replace
    fifo = tmp_path / "pipe.csv"
    os.mkfifo(fifo)
    assert wd.clear_destination(str(fifo)) is None
    assert fifo.exists()


def test_a_removal_that_fails_cancels_and_never_raises(tmp_path, monkeypatch):
    p = tmp_path / "locked.csv"
    p.write_text("old")

    def refuse(path):
        raise PermissionError(13, "Operation not permitted", str(path))
    monkeypatch.setattr(wd.os, "unlink", refuse)
    assert wd.clear_destination(str(p)) is None
    assert p.read_text() == "old"
    # nor for a path that is no path at all, or a relative one
    assert wd.clear_destination("bad\0name") is None
    assert wd.clear_destination("") is None
    assert wd.clear_destination("relative.csv") is None
    assert wd.clear_destination(None) is None


# ------------------------------------------- stand-ins for pywebview/PyObjC

class _Panel:
    """NSSavePanel as pywebview drives it."""
    def __init__(self, answer, chosen):
        self.answer, self.chosen, self.calls = answer, chosen, []

    def setDirectoryURL_(self, url):
        self.calls.append(("directory", url))

    def setNameFieldStringValue_(self, name):
        self.calls.append(("name", name))

    def runModal(self):
        return self.answer

    def filename(self):
        return self.chosen


OK, CANCEL = 1, 0


def _stand_ins(monkeypatch, downloads, answer=OK, chosen=None):
    """A Cocoa module whose BrowserView carries pywebview's stock delegate
    (the panel's path straight to WebKit), and the AppKit and Foundation
    the swapped delegate reads. Returns (BrowserView, the stock delegate,
    the panel)."""
    panel = _Panel(answer, chosen)
    appkit = types.ModuleType("AppKit")
    appkit.NSSavePanel = types.SimpleNamespace(savePanel=lambda: panel)
    appkit.NSFileHandlingPanelOKButton = OK
    foundation = types.ModuleType("Foundation")
    foundation.NSDownloadsDirectory, foundation.NSUserDomainMask = 15, 1
    foundation.NSSearchPathForDirectoriesInDomains = \
        lambda d, m, expand: [str(downloads)]
    foundation.NSURL = types.SimpleNamespace(
        fileURLWithPath_=lambda p: ("file-url", str(p)))

    class DownloadDelegate:
        def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
                self, download, response, suggested, handler):
            panel = appkit.NSSavePanel.savePanel()
            if panel.runModal() == appkit.NSFileHandlingPanelOKButton:
                handler(foundation.NSURL.fileURLWithPath_(panel.filename()))
            else:
                handler(None)

    class BrowserView:
        pass
    BrowserView.DownloadDelegate = DownloadDelegate
    cocoa = types.ModuleType(COCOA)
    cocoa.BrowserView = BrowserView
    monkeypatch.setitem(sys.modules, COCOA, cocoa)
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "Foundation", foundation)
    monkeypatch.delenv(wd.ENV, raising=False)
    monkeypatch.delenv("PYWEBVIEW_GUI", raising=False)
    monkeypatch.setattr(wd, "pywebview_version", lambda: "6.2.1")
    return BrowserView, DownloadDelegate, panel


WEBVIEW = types.ModuleType("webview")


INSTALLED = "installed (pywebview 6.2.1)"


def _decide(delegate_cls, suggested="2026-10-03-NAU_PyBNF-OracleSIHRS.csv",
            response=None):
    """WebKit asking the delegate where to save: what the completion
    handler got, each call."""
    got = []
    getattr(delegate_cls(), wd.METHOD)(object(), response or object(),
                                       suggested, got.append)
    return got


# --------------------------------------------------------- the swap itself

def test_on_macos_the_delegate_is_swapped_for_one_that_replaces(
        tmp_path, monkeypatch):
    chosen = tmp_path / "2026-10-03-NAU_PyBNF-OracleSIHRS.csv"
    chosen.write_text("yesterday's file")
    view, stock, panel = _stand_ins(monkeypatch, tmp_path, chosen=str(chosen))
    # the stock delegate hands WebKit a taken name (WebKit then drops it)
    assert _decide(stock) == [("file-url", str(chosen))] and chosen.exists()
    assert wd.install(WEBVIEW, platform="darwin") == INSTALLED
    new = view.DownloadDelegate
    assert new is not stock and issubclass(new, stock)
    assert new.__name__ == wd.CLASS_NAME
    # one override of the method pywebview defines, no new selector
    assert [k for k in vars(new) if not k.startswith("__")] == [wd.METHOD]
    panel.calls.clear()
    assert _decide(new) == [("file-url", str(chosen))]
    assert not chosen.exists()            # WebKit now writes a fresh file
    # pywebview's panel: in Downloads, named as WebKit suggests
    assert panel.calls == [("directory", ("file-url", str(tmp_path))),
                           ("name", "2026-10-03-NAU_PyBNF-OracleSIHRS.csv")]
    # a second install keeps the one swap
    assert wd.install(WEBVIEW, platform="darwin") == "already installed"
    assert view.DownloadDelegate is new


def test_cancel_and_a_folder_both_cancel_the_download(tmp_path, monkeypatch):
    kept = tmp_path / "kept.csv"
    kept.write_text("old")
    view, _stock, panel = _stand_ins(monkeypatch, tmp_path, answer=CANCEL,
                                     chosen=str(kept))
    assert wd.install(WEBVIEW, platform="darwin") == INSTALLED
    assert _decide(view.DownloadDelegate) == [None]
    assert kept.read_text() == "old"
    panel.answer, panel.chosen = OK, str(tmp_path)
    assert _decide(view.DownloadDelegate) == [None]
    assert tmp_path.is_dir()


def test_a_failing_panel_still_answers_webkit_once(tmp_path, monkeypatch):
    view, _stock, _panel = _stand_ins(monkeypatch, tmp_path)
    sys.modules["AppKit"].NSSavePanel = types.SimpleNamespace()
    lines = []
    assert wd.install(WEBVIEW, trace=lines.append,
                      platform="darwin") == INSTALLED
    assert _decide(view.DownloadDelegate) == [None]
    assert len(lines) == 1 and "download destination failed" in lines[0]


def test_a_failing_trace_never_keeps_webkit_waiting(tmp_path, monkeypatch):
    """A trace that raises (stderr closed under a Dock launch) in the
    folder branch and again in the except branch: WebKit still gets its
    one answer."""
    view, _stock, panel = _stand_ins(monkeypatch, tmp_path, chosen=str(tmp_path))

    def broken(msg):
        raise BrokenPipeError(32, "Broken pipe")
    assert wd.install(WEBVIEW, trace=broken, platform="darwin") == INSTALLED
    assert _decide(view.DownloadDelegate) == [None]          # a folder
    sys.modules["AppKit"].NSSavePanel = types.SimpleNamespace()
    assert _decide(view.DownloadDelegate) == [None]          # a failing panel


class _Response:
    def __init__(self, code):
        self.code = code

    def statusCode(self):
        return self.code


def test_an_http_error_replaces_nothing(tmp_path, monkeypatch):
    """A 404 notice downloaded under a CSV's name: WebKit gets the path as
    pywebview gives it (so it keeps the old file), nothing is removed."""
    kept = tmp_path / "2026-10-03-NAU_PyBNF-OracleSIHRS.csv"
    kept.write_text("the saved copy")
    view, _stock, _panel = _stand_ins(monkeypatch, tmp_path, chosen=str(kept))
    lines = []
    assert wd.install(WEBVIEW, trace=lines.append, platform="darwin") == \
        INSTALLED
    got = _decide(view.DownloadDelegate, response=_Response(404))
    assert got == [("file-url", str(kept))] and kept.read_text() == \
        "the saved copy"
    assert lines and "HTTP error" in lines[0]
    assert _decide(view.DownloadDelegate, response=_Response(200)) == \
        [("file-url", str(kept))]
    assert not kept.exists()                     # a success replaces it
    assert wd.http_error(_Response(500)) and not wd.http_error(_Response(304))
    assert not wd.http_error(object()) and not wd.http_error(None)


def test_another_pywebview_major_or_gui_is_left_alone(tmp_path, monkeypatch):
    """The override copies pywebview 6's body: another major version, an
    unreadable version, or a GUI other than Cocoa keeps pywebview's own."""
    view, stock, _panel = _stand_ins(monkeypatch, tmp_path)
    for ver in ("7.0.0", "5.4", None):
        monkeypatch.setattr(wd, "pywebview_version", lambda v=ver: v)
        said = wd.install(WEBVIEW, platform="darwin")
        assert said.startswith("skipped (pywebview ") and "not checked" in said
        assert view.DownloadDelegate is stock
    monkeypatch.setattr(wd, "pywebview_version", lambda: "6.3.0")
    monkeypatch.setenv("PYWEBVIEW_GUI", "qt")
    assert wd.install(WEBVIEW, platform="darwin") == \
        "skipped (PYWEBVIEW_GUI=qt)"
    assert view.DownloadDelegate is stock
    monkeypatch.setenv("PYWEBVIEW_GUI", "Cocoa")
    assert wd.install(WEBVIEW, platform="darwin") == \
        "installed (pywebview 6.3.0)"


def test_off_macos_or_switched_off_nothing_changes(tmp_path, monkeypatch):
    view, stock, _panel = _stand_ins(monkeypatch, tmp_path)
    for plat in ("linux", "win32"):
        assert wd.install(WEBVIEW, platform=plat) == "skipped (not macOS)"
        assert view.DownloadDelegate is stock
    monkeypatch.setenv(wd.ENV, "off")
    assert wd.install(WEBVIEW, platform="darwin") == \
        "skipped (FLUBNF_DOWNLOAD_REPLACE=off)"
    assert view.DownloadDelegate is stock
    # sys.platform by default: this suite's machine is not a Mac's window
    monkeypatch.delenv(wd.ENV)
    if sys.platform != "darwin":
        assert wd.install(WEBVIEW) == "skipped (not macOS)"
        assert view.DownloadDelegate is stock


def test_another_pywebview_keeps_its_own_delegate(tmp_path, monkeypatch):
    view, stock, _panel = _stand_ins(monkeypatch, tmp_path)
    # the method renamed in some other version: nothing to override
    delattr(stock, wd.METHOD)
    assert wd.install(WEBVIEW, platform="darwin").startswith("skipped")
    assert view.DownloadDelegate is stock
    del view.DownloadDelegate
    assert wd.install(WEBVIEW, platform="darwin").startswith("skipped")
    assert not hasattr(view, "DownloadDelegate")


def test_any_failure_leaves_pywebview_untouched(tmp_path, monkeypatch):
    view, stock, _panel = _stand_ins(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "AppKit", None)     # import fails
    said = wd.install(WEBVIEW, platform="darwin")
    assert said.startswith("not installed (ModuleNotFoundError")
    assert view.DownloadDelegate is stock
    monkeypatch.setitem(sys.modules, COCOA, None)       # nor this one
    assert wd.install(WEBVIEW, platform="darwin").startswith("not installed")


# ----------------------------------------------- where the window installs it

def test_the_window_installs_it_before_the_main_loop(monkeypatch):
    """app_window hands the imported pywebview to install() once, after
    ALLOW_DOWNLOADS and before webview.start; what it did goes to the
    startup trace."""
    seen, traced = [], []

    class Event:
        def __iadd__(self, handler):
            return self
    window = types.SimpleNamespace(events=types.SimpleNamespace(
        closed=Event(), shown=Event(), loaded=Event()))
    fake = types.SimpleNamespace(settings={},
                                 create_window=lambda *a, **k: window)

    def install(webview_module, trace=None):
        seen.append(("install", webview_module,
                     fake.settings.get("ALLOW_DOWNLOADS")))
        return "installed"

    def start(func):
        seen.append(("start",))
        t = threading.Thread(target=func)
        t.start()
        t.join()
    fake.start = start
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(wd, "install", install)
    for name, stand_in in {
            "_windows_mshtml_only": lambda: False,
            "_name_mac_process": lambda: None,
            "_terminate_predecessor": lambda: False,
            "_write_pidfile": lambda: (lambda: None),
            "_bind_app_socket": lambda port, settle=0.0: (None, port),
            "_start_window_server": lambda sock, port: (lambda: None),
            "_window_watchdog": lambda *a, **k: "loaded",
            "_bring_window_forward": lambda *a, **k: False,
            "_allow_pinch_zoom": lambda window: None,
            "_trace": traced.append,
            "_exit_now": lambda *cleanups: None}.items():
        monkeypatch.setattr(cli, name, stand_in)
    cli.app_window(port=8710)
    assert seen == [("install", fake, True), ("start",)]
    assert "window: save over an existing file: installed" in traced
