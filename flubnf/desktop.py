"""Desktop wrapper for the FluBNF Streamlit app.

Runs Streamlit on a private localhost port and renders the UI inside a
native window (PyWebView on macOS/Linux/Windows). The user never sees
"localhost:8501" or a browser — it looks and feels like a regular
desktop app.

Run with:
    flubnf-desktop
or:
    python -m flubnf.desktop

Implementation notes:
  * We don't kill the Streamlit subprocess by name — we keep a Popen
    handle and terminate on window close.
  * Picks a free ephemeral port so it never clashes with anything else.
  * Window is sized to a sensible default and remembers the user's
    resize for the session.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Bind to port 0 and return whatever the kernel assigned."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_streamlit(port: int, timeout: float = 30.0) -> bool:
    """Poll the Streamlit health endpoint until it responds (or timeout)."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.4)
    return False


def _start_streamlit(port: int) -> subprocess.Popen:
    """Start the Streamlit server as a subprocess."""
    ui_module = Path(__file__).resolve().parent / "ui.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(ui_module),
        "--server.headless", "true",
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--browser.gatherUsageStats", "false",
        "--server.runOnSave", "false",
    ]
    log.info("launching streamlit: %s", " ".join(cmd))
    # We capture stderr to surface bootstrap failures; stdout we don't care about.
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        # New process group so we can clean up the entire tree on quit.
        start_new_session=True,
    )


def _open_window(port: int, title: str = "FluBNF Forecasting") -> None:
    """Open the native window pointing at the running Streamlit server."""
    try:
        import webview  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "pywebview is not installed. Install with:\n"
            "    pip install -e '.[desktop]'\n"
            "or:\n"
            "    pip install pywebview"
        ) from e

    webview.create_window(
        title,
        f"http://127.0.0.1:{port}",
        width=1400,
        height=900,
        min_size=(1100, 720),
        confirm_close=False,
        background_color="#f4f7fb",
    )
    # pywebview on macOS uses the WKWebView Cocoa backend; gui=None auto-picks.
    webview.start(debug=False)


def _terminate_process(proc: subprocess.Popen) -> None:
    """Politely kill the Streamlit subprocess + any children."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flubnf-desktop",
        description="Launch the FluBNF Streamlit UI as a native desktop window.",
    )
    parser.add_argument(
        "--port", type=int, default=0,
        help="Localhost port to use (0 = pick a free one).",
    )
    parser.add_argument(
        "--no-window", action="store_true",
        help="Start Streamlit but skip opening the native window "
             "(prints the URL instead). Useful for headless debugging.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug-level logging.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    port = args.port or _find_free_port()
    proc = _start_streamlit(port)
    try:
        if not _wait_for_streamlit(port):
            stderr = proc.stderr.read().decode(errors="replace") \
                if proc.stderr else "(no stderr)"
            print(f"Streamlit did not become healthy in 30s. stderr:\n{stderr}",
                  file=sys.stderr)
            return 2

        if args.no_window:
            print(f"FluBNF UI is running at http://127.0.0.1:{port}")
            print("Press Ctrl+C to stop.")
            try:
                proc.wait()
            except KeyboardInterrupt:
                pass
            return 0

        _open_window(port)
        return 0
    finally:
        _terminate_process(proc)


if __name__ == "__main__":
    sys.exit(main())
