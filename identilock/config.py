"""Filesystem locations and runtime settings.

Everything Identilock persists lives in one directory so that "back up your
data" is a single instruction you can give a non-technical coworker.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Identilock"

# How long the vault stays unlocked without interaction. The decryption key is
# held only in memory, so locking genuinely drops it.
DEFAULT_LOCK_TIMEOUT_MINUTES = 15

# Non-secret preferences changed from the Settings page. Kept as plain JSON
# (not in the encrypted database) because they must be readable before the
# vault is unlocked — the lock timeout and the data location are needed at
# startup, when no passphrase has been entered yet.
PREFS_FILE = "prefs.json"


def read_prefs(directory: Path) -> dict:
    try:
        raw = json.loads((directory / PREFS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def write_prefs(directory: Path, **updates) -> None:
    # First parameter deliberately not named data_dir: "data_dir" is itself a
    # storable preference (the moved-data pointer) passed via **updates.
    directory.mkdir(parents=True, exist_ok=True)
    prefs = read_prefs(directory)
    prefs.update(updates)
    prefs = {k: v for k, v in prefs.items() if v is not None}
    data = json.dumps(prefs, indent=2)
    # Atomic write: a crash mid-write must not truncate the file and silently
    # drop the moved-data pointer, which would send the next launch to a stale
    # copy. Write a temp file, fsync, then rename over the target.
    tmp = directory / (PREFS_FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, directory / PREFS_FILE)


def default_data_dir() -> Path:
    """Per-platform application data directory."""
    override = os.environ.get("IDENTILOCK_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "identilock"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    lock_timeout_minutes: int
    # True when a moved-data pointer led to a folder that has no database (an
    # unplugged drive, a deleted/renamed folder). The app must warn rather than
    # silently offer a fresh setup screen over the user's real, absent data.
    data_unreachable: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "identilock.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def is_loopback(self) -> bool:
        return self.host in {"127.0.0.1", "::1", "localhost"}


def load_settings(
    *,
    data_dir: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> Settings:
    resolved_dir = data_dir or default_data_dir()
    prefs = read_prefs(resolved_dir)

    # "Move my data" from the Settings page leaves a pointer behind in the old
    # folder. Followed hop by hop so moving twice still resolves; an explicit
    # --data-dir or env override always wins and skips pointers entirely.
    followed_pointer = False
    if data_dir is None and not os.environ.get("IDENTILOCK_DATA_DIR"):
        seen = {resolved_dir}
        while True:
            moved = prefs.get("data_dir")
            candidate = Path(moved).expanduser() if moved else None
            if candidate is None or candidate in seen:
                break
            seen.add(candidate)
            resolved_dir = candidate
            followed_pointer = True
            prefs = {**prefs, **read_prefs(candidate)}

    # A pointer that leads to a folder with no database means the real data is
    # unreachable (unplugged drive, deleted folder) — flag it so the app warns
    # instead of quietly recreating an empty vault at the dangling location.
    data_unreachable = followed_pointer and not (
        resolved_dir / "identilock.db"
    ).exists()

    resolved_host = host or os.environ.get("IDENTILOCK_HOST", "127.0.0.1")
    resolved_port = port or int(os.environ.get("IDENTILOCK_PORT", "8731"))
    try:
        timeout = int(
            os.environ.get("IDENTILOCK_LOCK_MINUTES")
            or prefs.get("lock_minutes")
            or DEFAULT_LOCK_TIMEOUT_MINUTES
        )
    except (TypeError, ValueError):
        timeout = DEFAULT_LOCK_TIMEOUT_MINUTES

    settings = Settings(
        data_dir=resolved_dir,
        host=resolved_host,
        port=resolved_port,
        lock_timeout_minutes=max(1, timeout),
        data_unreachable=data_unreachable,
    )

    # Binding to anything but loopback would expose SSNs and freeze PINs to the
    # local network. Refuse unless the user has very deliberately opted in.
    if not settings.is_loopback and os.environ.get("IDENTILOCK_ALLOW_REMOTE") != "1":
        raise SystemExit(
            f"Refusing to bind to {settings.host!r}.\n"
            "Identilock holds Social Security numbers and freeze PINs, and has no\n"
            "transport encryption or multi-user access control. It is meant to be\n"
            "reachable only from the machine it runs on.\n"
            "If you truly need this, set IDENTILOCK_ALLOW_REMOTE=1 and put it behind\n"
            "a TLS-terminating reverse proxy you control."
        )

    return settings


def ensure_data_dir(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    # Best effort on POSIX; Windows inherits the user profile's ACL.
    if os.name != "nt":
        os.chmod(settings.data_dir, 0o700)
        os.chmod(settings.backup_dir, 0o700)
