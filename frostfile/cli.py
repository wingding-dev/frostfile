"""Command line entry point: `frostfile`."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __version__
from .config import ensure_data_dir, load_settings


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host if host != "localhost" else "127.0.0.1", port))
        except OSError:
            return False
    return True


def _find_port(host: str, preferred: int) -> int:
    for candidate in range(preferred, preferred + 20):
        if _port_is_free(host, candidate):
            return candidate
    raise SystemExit(
        f"Could not find a free port near {preferred}. "
        "Pass --port to choose one yourself."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frostfile",
        description=(
            "Track credit freezes, identity controls, and breach exposure for "
            "your household. Runs entirely on this machine."
        ),
    )
    parser.add_argument("--version", action="version", version=f"frostfile {__version__}")
    parser.add_argument(
        "--port", type=int, default=None, help="Port to listen on (default 8731)."
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Interface to bind (default 127.0.0.1). Non-loopback needs FROSTFILE_ALLOW_REMOTE=1.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Where to keep the database. Defaults to your OS application data directory.",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open any window."
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the web browser instead of the app window.",
    )
    parser.add_argument(
        "--where", action="store_true", help="Print the data directory and exit."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = load_settings(
        data_dir=args.data_dir, host=args.host, port=args.port
    )
    ensure_data_dir(settings)

    if args.where:
        print(settings.data_dir)
        print(settings.db_path)
        return 0

    port = settings.port if _port_is_free(settings.host, settings.port) else _find_port(
        settings.host, settings.port
    )
    if port != settings.port:
        settings = load_settings(
            data_dir=settings.data_dir, host=settings.host, port=port
        )

    import uvicorn

    from .web import create_app

    app = create_app(settings)
    url = f"http://{'localhost' if settings.is_loopback else settings.host}:{port}/"

    print(f"FrostFile {__version__}")
    print(f"  data:  {settings.data_dir}")
    print(f"  open:  {url}")
    if not settings.is_loopback:
        print("  WARNING: bound to a non-loopback address. Anyone who can reach")
        print("           this port can reach your data. Stop unless you meant it.")
    print("  Press Ctrl+C to stop. Locking happens automatically after "
          f"{settings.lock_timeout_minutes} minutes idle.")

    config = uvicorn.Config(app, host=settings.host, port=port, log_level="warning")

    if not args.browser and not args.no_browser and _run_app_window(
        uvicorn.Server(config), url
    ):
        return 0

    # A stopped Server cannot be restarted, so the browser path gets its own.
    server = uvicorn.Server(config)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    return 0


def _gui_backend_available() -> bool:
    """Whether a usable native-window toolkit is present.

    Critically, the Qt backend calls abort() at the C level when it cannot load
    its platform plugin (e.g. libxcb-cursor0 missing on Linux) — a crash Python
    cannot catch, which would take the whole app down instead of falling back to
    the browser. So we probe Qt in a throwaway subprocess: if it aborts, only
    the probe dies and we return False.
    """
    import os

    if os.name != "nt" and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False  # headless: no window possible

    # GTK/WebKit backend — its failures are catchable Python ImportErrors.
    try:
        import gi  # noqa: F401

        gi.require_version("Gtk", "3.0")
        return True
    except Exception:
        pass

    # Qt backend — probe in isolation because it can hard-abort.
    import subprocess

    probe = "from PyQt6.QtWidgets import QApplication; QApplication([])"
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, timeout=20
        )
        return result.returncode == 0
    except Exception:
        return False


def _run_app_window(server, url: str) -> bool:
    """Open FrostFile in its own window instead of a browser tab.

    Uses pywebview, which wraps the operating system's built-in page renderer
    (WebView2 on Windows, WebKit on macOS) — the app looks and behaves like a
    normal program, and closing the window shuts the whole thing down. Returns
    False when that is not possible (no window toolkit, as on a bare Linux box),
    and the caller falls back to the browser.
    """
    try:
        import webview
    except ImportError:
        return False

    if not _gui_backend_available():
        return False

    # Without this, the "Download as Separate PDFs" zip silently no-ops in the
    # app window; downloads land in the OS's normal Downloads folder.
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except (AttributeError, TypeError, KeyError):
        pass

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)

    try:
        webview.create_window(
            "FrostFile", url, width=1160, height=820, min_size=(760, 520)
        )
        webview.start()
    except Exception:
        server.should_exit = True
        thread.join(timeout=5)
        return False

    server.should_exit = True
    thread.join(timeout=5)
    return True


if __name__ == "__main__":
    sys.exit(main())
