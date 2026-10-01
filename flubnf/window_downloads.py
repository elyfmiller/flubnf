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
enough. Off macOS, with FLUBNF_DOWNLOAD_REPLACE=off, or when pywebview's
internals are not the expected ones, pywebview is left as it is (the
Windows window saves through WebView2's own dialog, not this delegate).
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


def _quiet(msg: str) -> None:
    pass


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
                    target = clear_destination(str(chosen)) if chosen \
                        else None
                    if target is None:
                        trace(f"window: download not saved: {chosen} is a "
                              "folder or could not be removed")
                    else:
                        url = foundation.NSURL.fileURLWithPath_(target)
            except Exception as e:
                trace(f"window: download destination failed: "
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
        return "installed"
    except Exception as e:
        return f"not installed ({type(e).__name__}: {e})"
