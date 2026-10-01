"""CONSOLE (`flubnf window` on macOS): a saved download replaces the file
the user chose to replace.

pywebview 6.2.1's Cocoa DownloadDelegate (webview/platforms/cocoa.py)
shows a save panel and hands its path to WebKit. When a file of that name
exists, the panel asks to replace it, but its Replace only answers yes:
it deletes nothing. WebKit then finds the destination taken and drops the
download (WKDownload.mm: an existing destination is never overwritten),
with no error shown. The old file stays, byte for byte, and every
re-download of a name that repeats (a hub CSV, the weekly report of an
as-of) silently keeps the first copy.

install() swaps in a subclass of pywebview's delegate whose one method is
the same save panel followed by clear_destination(): the file the user
agreed to replace is removed before WebKit is given the path. It overrides
only the method pywebview already defines, so PyObjC reuses that
selector's signature, and BrowserView.DownloadDelegate is looked up per
download (webView_navigationAction_didBecomeDownload_), so the rebind is
enough. The method copies pywebview 6's own body, so install() runs only
under pywebview 6 (another major version may have changed what that body
does) and only when pywebview will use Cocoa. Off macOS, with
FLUBNF_DOWNLOAD_REPLACE=off, under another pywebview or GUI, or when the
delegate is not the expected one, pywebview is left as it is (the Windows
window saves through WebView2's own dialog, not this delegate).

Removing the old file before WebKit writes is what WebKit itself does when
it is allowed to overwrite. A download that then fails midway leaves no
copy: the user asked for this one to replace it. An HTTP error (a 404
notice) never removes anything: WebKit gets the path as pywebview would
give it, and keeps the old file if one is there.
"""
from __future__ import annotations

import os
import stat
import sys

#: FLUBNF_DOWNLOAD_REPLACE=off keeps pywebview's own delegate
ENV = "FLUBNF_DOWNLOAD_REPLACE"
#: the one delegate method pywebview defines and this module overrides
METHOD = ("download_decideDestinationUsingResponse_"
          "suggestedFilename_completionHandler_")
#: the Objective-C name of the subclass (class names are process-wide)
CLASS_NAME = "FluBNFReplacingDownloadDelegate"
#: the pywebview major version whose delegate body the override copies
CHECKED_MAJOR = "6"


def _quiet(msg: str) -> None:
    pass


def pywebview_version() -> str | None:
    """The installed pywebview's version, or None when it cannot be read."""
    try:
        from importlib.metadata import version
        return version("pywebview")
    except Exception:
        return None


def http_error(response) -> bool:
    """True when WebKit's response is an HTTP error (status 400 or more);
    False for a success, a response without a status, or one that cannot
    be read."""
    try:
        return int(response.statusCode()) >= 400
    except Exception:
        return False


def clear_destination(path) -> str | None:
    """The path WebKit may save to: `path` itself, after removing what
    holds that name. The save panel returns an existing name only once the
    user has confirmed Replace, so a regular file (or a link, which is
    removed, not its target) goes. None, which cancels the download, for a
    folder or a link to one, anything else that is not a file, a relative
    path (the panel's never is) and a removal that fails. Never raises."""
    try:
        p = os.fspath(path)
        if not p or not os.path.isabs(p):
            return None
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            return p                                    # free
        if os.path.isdir(p):
            return None             # a folder, or a link to one: never
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)):
            return None             # a pipe, socket or device
        os.unlink(p)
        return p
    except Exception:
        return None


def replacing_delegate(base, appkit, foundation, trace=_quiet):
    """A subclass of `base` (pywebview's DownloadDelegate) whose download
    destination method is pywebview's own (the save panel in Downloads,
    named as WebKit suggests) plus clear_destination() before WebKit gets
    the path. `appkit` and `foundation` are the PyObjC modules (stand-ins
    in the tests). Nothing else is defined on the class: every method of
    an NSObject subclass becomes a selector."""

    def say(msg):
        # a trace that fails (stderr closed) must not keep WebKit waiting
        try:
            trace(msg)
        except Exception:
            pass

    class FluBNFReplacingDownloadDelegate(base):
        def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
                self, download, response, suggested, handler):
            url = None
            try:
                panel = appkit.NSSavePanel.savePanel()
                directory = foundation.NSSearchPathForDirectoriesInDomains(
                    foundation.NSDownloadsDirectory,
                    foundation.NSUserDomainMask, True)[0]
                panel.setDirectoryURL_(
                    foundation.NSURL.fileURLWithPath_(directory))
                panel.setNameFieldStringValue_(suggested)
                if panel.runModal() == appkit.NSFileHandlingPanelOKButton:
                    chosen = panel.filename()
                    if chosen and http_error(response):
                        # an error page replaces nothing: pywebview's path
                        say("window: download is an HTTP error; nothing "
                            "removed")
                        url = foundation.NSURL.fileURLWithPath_(chosen)
                    else:
                        target = clear_destination(str(chosen)) if chosen \
                            else None
                        if target is None:
                            say(f"window: download not saved: {chosen} is "
                                "a folder or could not be removed")
                        else:
                            url = foundation.NSURL.fileURLWithPath_(target)
            except Exception as e:
                say(f"window: download destination failed: "
                    f"{type(e).__name__}: {e}")
                url = None
            # exactly once, as pywebview does: a URL saves, None cancels
            handler(url)

    return FluBNFReplacingDownloadDelegate


def install(webview_module=None, trace=_quiet, platform=None) -> str:
    """Rebind pywebview's BrowserView.DownloadDelegate to
    replacing_delegate()'s subclass, on macOS only. Returns what it did in
    a few words, for the window's startup trace; never raises, and on any
    failure pywebview keeps its own delegate. `webview_module` is the
    imported pywebview (its Cocoa module is imported from it); `platform`
    is sys.platform by default; tests pass one."""
    if (platform or sys.platform) != "darwin":
        return "skipped (not macOS)"
    if os.environ.get(ENV, "").strip().lower() == "off":
        return f"skipped ({ENV}=off)"
    gui = os.environ.get("PYWEBVIEW_GUI", "").strip().lower()
    if gui not in ("", "cocoa"):
        return f"skipped (PYWEBVIEW_GUI={gui})"
    ver = pywebview_version()
    if not ver or ver.split(".")[0] != CHECKED_MAJOR:
        return f"skipped (pywebview {ver or 'version unknown'} not checked)"
    try:
        import importlib
        pkg = getattr(webview_module, "__name__", None) or "webview"
        cocoa = importlib.import_module(pkg + ".platforms.cocoa")
        view = cocoa.BrowserView
        base = getattr(view, "DownloadDelegate", None)
        if base is None or not callable(getattr(base, METHOD, None)):
            return "skipped (this pywebview has no such delegate)"
        if base.__name__ == CLASS_NAME:
            return "already installed"
        import AppKit
        import Foundation
        view.DownloadDelegate = replacing_delegate(base, AppKit, Foundation,
                                                   trace=trace)
        return f"installed (pywebview {ver})"
    except Exception as e:
        return f"not installed ({type(e).__name__}: {e})"
