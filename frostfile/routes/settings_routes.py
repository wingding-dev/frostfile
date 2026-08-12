"""Settings: passphrase changes, backups, and preferences."""

from __future__ import annotations

import dataclasses
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request

from .. import db
from ..config import (
    default_mirror_dir,
    ensure_data_dir,
    mirror_backups,
    write_prefs,
)
from ..crypto import Vault, WrongPassphrase, passphrase_problems
from ..security import Session, set_session_cookie, verify_csrf
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()


def _page(
    request: Request,
    conn: sqlite3.Connection,
    vault: Vault,
    **flash,
):
    settings = request.app.state.settings
    # When the mirror is off by choice, still show where copies WOULD go so
    # the page can offer to turn it back on. None in both slots means the
    # mirror is not available here at all (explicit --data-dir, no Documents
    # folder) and the section is hidden entirely.
    mirror_display = settings.mirror_dir
    if mirror_display is None and settings.mirror_off_by_pref:
        mirror_display = default_mirror_dir()
    return render(
        request,
        "settings.html",
        {
            "active": "settings",
            "data_dir": str(settings.data_dir),
            "db_path": str(settings.db_path),
            "mirror_dir": str(mirror_display) if mirror_display else "",
            "mirror_on": settings.mirror_dir is not None,
            "lock_minutes": settings.lock_timeout_minutes,
            "has_recovery": db.has_recovery(conn),
            **flash,
        },
    )


@router.get("/settings")
def settings_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    return _page(request, conn, vault)


@router.post("/settings/lock")
def save_lock_timeout(
    request: Request,
    minutes: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    try:
        value = int(minutes)
    except ValueError:
        return _page(request, conn, vault, error="Enter a number of minutes.")
    if not 1 <= value <= 240:
        return _page(
            request, conn, vault, error="Pick between 1 and 240 minutes."
        )

    settings = request.app.state.settings
    write_prefs(settings.data_dir, lock_minutes=value)
    request.app.state.sessions.set_timeout(value)
    request.app.state.settings = dataclasses.replace(
        settings, lock_timeout_minutes=value
    )
    return _page(
        request,
        conn,
        vault,
        message=f"Done — FrostFile now locks itself after {value} minutes idle.",
    )


@router.post("/settings/mirror")
def toggle_backup_mirror(
    request: Request,
    enable: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    settings = request.app.state.settings
    turn_on = enable == "1"
    mirror = default_mirror_dir() if turn_on else None
    if turn_on and mirror is None:
        return _page(
            request,
            conn,
            vault,
            error="No Documents folder was found on this computer, so there "
            "is nowhere to keep the spare copies.",
        )

    write_prefs(settings.data_dir, mirror_backups=turn_on)
    new_settings = dataclasses.replace(
        settings, mirror_dir=mirror, mirror_off_by_pref=not turn_on
    )
    request.app.state.settings = new_settings
    if turn_on:
        # Catch the mirror up right away so the user sees the files appear
        # instead of waiting for the next weekly backup.
        mirror_backups(new_settings)
        message = f"Done — spare copies of your backups now go to {mirror}."
    else:
        message = (
            "Done — no new spare copies will be made. The ones already in "
            "the folder stay until you delete them."
        )
    return _page(request, conn, vault, message=message)


@router.post("/settings/data-dir")
def move_data_dir(
    request: Request,
    folder: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    settings = request.app.state.settings
    raw = folder.strip()
    if not raw:
        return _page(request, conn, vault, error="Enter a folder path.")
    target = Path(raw).expanduser()
    if not target.is_absolute():
        return _page(
            request,
            conn,
            vault,
            error="Enter the full path to the folder (starting from the drive or your home folder).",
        )
    if target == settings.data_dir:
        return _page(request, conn, vault, message="Already using that folder.")

    new_db = target / "frostfile.db"
    if new_db.exists():
        return _page(
            request,
            conn,
            vault,
            error=(
                f"{target} already contains an FrostFile database. Pick an "
                "empty folder, or move that file out of the way first."
            ),
        )
    old_dir = settings.data_dir
    try:
        target.mkdir(parents=True, exist_ok=True)
        db.backup_to(conn, new_db)
    except (OSError, sqlite3.Error) as exc:
        # Leave no half-written database behind for a later launch to open.
        new_db.unlink(missing_ok=True)
        return _page(
            request, conn, vault, error=f"Could not write to that folder: {exc}"
        )

    new_settings = dataclasses.replace(settings, data_dir=target)
    ensure_data_dir(new_settings)  # applies the 0700 mode to the new folders

    # The new folder keeps the current preferences and carries NO onward pointer
    # (clear any stale one so resolution never bounces back out of it), and the
    # folder this instance was running from gets a pointer so a future launch
    # that starts there follows the move. Never touch the machine-wide default:
    # a --data-dir or test instance must not redirect someone else's data.
    write_prefs(target, lock_minutes=settings.lock_timeout_minutes, data_dir=None)
    write_prefs(old_dir, data_dir=str(target))

    # Switch the LIVE app to the new folder so every subsequent request in this
    # session writes there — otherwise edits made after the move would land in
    # the old database and vanish at next launch.
    request.app.state.settings = new_settings

    return _page(
        request,
        conn,
        vault,
        message=(
            f"Done — your data now lives in {target}, and FrostFile is already "
            "using it (anything you change from here on is saved there). The old "
            f"copy at {old_dir} is now a stale snapshot; delete it once you have "
            "confirmed everything looks right in the new location."
        ),
    )


@router.post("/settings/passphrase")
def change_passphrase(
    request: Request,
    current: str = Form(...),
    new_passphrase: str = Form(...),
    confirm: str = Form(...),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)

    try:
        db.unlock(conn, current)
    except WrongPassphrase:
        return _page(request, conn, vault, error="The current passphrase is wrong.")

    errors = passphrase_problems(new_passphrase)
    if new_passphrase != confirm:
        errors.append("The two new passphrases do not match.")
    if errors:
        return _page(request, conn, vault, error=" ".join(errors))

    # Re-wraps every encrypted field AND issues a fresh recovery code in one
    # transaction, so the old code stops working and the new one is guaranteed
    # to match the new key.
    new_vault, recovery_code = db.change_passphrase(conn, vault, new_passphrase)
    new_session = request.app.state.sessions.create(new_vault)
    new_session.pending_recovery_code = recovery_code

    response = redirect("/recovery-code")
    set_session_cookie(response, new_session.token)
    return response


@router.post("/settings/recovery")
def reissue_recovery_code(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    session.pending_recovery_code = db.set_recovery(conn, vault.key)
    return redirect("/recovery-code")


@router.post("/settings/move-kit")
def make_move_kit(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    desktop = Path.home() / "Desktop"
    target_dir = desktop if desktop.is_dir() else Path.home()
    stamp = datetime.now().strftime("%Y-%m-%d")
    target = target_dir / f"FrostFile-move-{stamp}.db"
    try:
        db.backup_to(conn, target)
        os.chmod(target, 0o600)
    except (OSError, sqlite3.Error) as exc:
        return _page(request, conn, vault, error=f"Could not write the move file: {exc}")
    return _page(
        request,
        conn,
        vault,
        message=(
            f"Done — everything is packaged into one file: {target}. Copy it to "
            "the new computer any way you like (USB stick, shared drive), "
            "install FrostFile there, and choose “Moving from another "
            "computer?” on its first screen. Your passphrase stays the "
            "same. The file is scrambled like everything else, so it is safe "
            "in transit — and useless without the passphrase."
        ),
    )


@router.post("/settings/backup")
def make_backup(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    settings = request.app.state.settings
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = settings.backup_dir / f"frostfile-{stamp}.db"
    try:
        db.backup_to(conn, target)
    except (OSError, sqlite3.Error) as exc:
        return _page(
            request,
            conn,
            vault,
            error=(
                "Could not write the backup — the disk may be full or the "
                f"folder unwritable. Nothing was changed. ({exc})"
            ),
        )
    return _page(
        request,
        conn,
        vault,
        message=(
            f"Backup written to {target}. It is encrypted with the same "
            "passphrase, so it is safe to copy elsewhere — and useless without it."
        ),
    )
