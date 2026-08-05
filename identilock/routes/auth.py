"""First-run setup, unlocking, and locking."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from .. import db
from ..crypto import WrongPassphrase, passphrase_problems
from ..security import (
    clear_session_cookie,
    current_session,
    set_session_cookie,
    verify_csrf,
)
from ..seeds import seed_agencies
from ..web import get_conn, redirect, render

router = APIRouter()

AUTO_BACKUP_EVERY_DAYS = 7
AUTO_BACKUP_KEEP = 10


def _maybe_auto_backup(request: Request, conn: sqlite3.Connection) -> None:
    """A weekly backup that nobody has to remember.

    Runs at unlock because that is the one moment the app is certainly being
    used. Automatic copies are named identilock-auto-* and only those are
    pruned — backups the user made deliberately are never deleted. Any failure
    here is swallowed: a full disk must not stop the vault from opening.
    """
    settings = request.app.state.settings
    try:
        existing = list(settings.backup_dir.glob("identilock-*.db"))
        if existing:
            newest = max(p.stat().st_mtime for p in existing)
            if time.time() - newest < AUTO_BACKUP_EVERY_DAYS * 86400:
                return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        db.backup_to(conn, settings.backup_dir / f"identilock-auto-{stamp}.db")
        automatic = sorted(settings.backup_dir.glob("identilock-auto-*.db"))
        for old in automatic[:-AUTO_BACKUP_KEEP]:
            old.unlink()
    except OSError:
        pass


def _safe_next(target: str | None) -> str:
    """Only ever redirect within this app — never to an attacker-supplied host."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    if target.startswith("/unlock") or target.startswith("/setup"):
        return "/"
    return target


@router.get("/setup")
def setup_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_initialized(conn):
        return redirect("/unlock")
    return render(request, "setup.html", {"errors": []})


@router.post("/setup")
def setup_submit(
    request: Request,
    passphrase: str = Form(...),
    confirm: str = Form(...),
    acknowledged: str = Form(default=""),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if db.is_initialized(conn):
        return redirect("/unlock")

    errors = passphrase_problems(passphrase)
    if passphrase != confirm:
        errors.append("The two passphrases do not match.")
    if not acknowledged:
        errors.append(
            "Please confirm you understand the passphrase cannot be recovered."
        )
    if errors:
        return render(request, "setup.html", {"errors": errors})

    vault = db.initialize_vault(conn, passphrase)
    seed_agencies(conn)

    session = request.app.state.sessions.create(vault)
    session.pending_recovery_code = db.set_recovery(conn, vault.key)
    response = redirect("/recovery-code")
    set_session_cookie(response, session.token)
    return response


@router.get("/recovery-code")
def recovery_code_page(request: Request):
    session = current_session(request)
    if session is None:
        return redirect("/unlock")
    if not session.pending_recovery_code:
        return redirect("/")
    return render(
        request,
        "recovery_code.html",
        {"code": session.pending_recovery_code},
    )


@router.post("/recovery-code/save")
def recovery_code_save(request: Request, csrf_token: str = Form(default="")):
    """Write the code to a plain file so the user can drop it in their own
    cloud folder (iCloud Drive, Google Drive, OneDrive). Their account, their
    custody — nothing leaves this machine unless they move the file."""
    from pathlib import Path

    session = current_session(request)
    if session is None:
        return redirect("/unlock")
    verify_csrf(session, csrf_token)
    if not session.pending_recovery_code:
        return redirect("/")

    desktop = Path.home() / "Desktop"
    target_dir = desktop if desktop.is_dir() else Path.home()
    target = target_dir / "Identilock-Recovery-Code.txt"
    contents = (
        "Identilock Recovery Code\n"
        "========================\n\n"
        f"    {session.pending_recovery_code}\n\n"
        "If you ever forget your Identilock passphrase: open Identilock, click\n"
        '"Forgot your passphrase?" on the unlock screen, and enter this code.\n\n'
        "This code is replaced with a new one whenever the passphrase changes\n"
        "(including when you use this one), so keep this file up to date.\n\n"
        "Anyone with this code AND your Identilock data file can read your\n"
        "data. Keep it somewhere you trust — and not in the same place as a\n"
        "copy of the data file itself.\n"
    )
    try:
        target.write_text(contents, encoding="utf-8")
    except OSError as exc:
        return render(
            request,
            "recovery_code.html",
            {"code": session.pending_recovery_code,
             "save_message": f"Could not write the file: {exc}"},
        )
    return render(
        request,
        "recovery_code.html",
        {"code": session.pending_recovery_code,
         "save_message": (
             f"Saved to {target}. To keep an off-site copy, move that file "
             "into your iCloud Drive, Google Drive, or OneDrive folder — just "
             "don't keep a copy of your Identilock data file in the same "
             "account."
         )},
    )


@router.post("/recovery-code/ack")
def recovery_code_ack(request: Request, csrf_token: str = Form(default="")):
    session = current_session(request)
    if session is None:
        return redirect("/unlock")
    verify_csrf(session, csrf_token)
    session.pending_recovery_code = None
    return redirect("/")


@router.get("/recover")
def recover_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if not db.is_initialized(conn):
        return redirect("/setup")
    return render(
        request,
        "recover.html",
        {"error": None, "has_recovery": db.has_recovery(conn)},
    )


@router.post("/recover")
def recover_submit(
    request: Request,
    code: str = Form(...),
    new_passphrase: str = Form(...),
    confirm: str = Form(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if not db.is_initialized(conn):
        return redirect("/setup")

    def fail(message: str):
        return render(
            request,
            "recover.html",
            {"error": message, "has_recovery": db.has_recovery(conn)},
        )

    if not db.has_recovery(conn):
        return fail(
            "This vault has no recovery code — it was created before recovery "
            "codes existed, and one can only be issued while unlocked."
        )

    data_key = db.recover_data_key(conn, code)
    if data_key is None:
        return fail("That recovery code did not open the vault. Check it and try again.")

    errors = passphrase_problems(new_passphrase)
    if new_passphrase != confirm:
        errors.append("The two new passphrases do not match.")
    if errors:
        return fail(" ".join(errors))

    from ..crypto import Vault

    # Re-encrypt everything under the new passphrase, then burn the used code
    # by issuing a fresh one — a recovery code is single-use by design.
    new_vault = db.change_passphrase(conn, Vault(data_key), new_passphrase)
    session = request.app.state.sessions.create(new_vault)
    session.pending_recovery_code = db.set_recovery(conn, new_vault.key)
    response = redirect("/recovery-code")
    set_session_cookie(response, session.token)
    return response


@router.post("/setup/import")
async def setup_import(
    request: Request,
    upload: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Restore a move file on a fresh install, instead of starting over.

    Only possible while no vault exists here — once a passphrase has been set,
    this machine's data can no longer be silently replaced.
    """
    if db.is_initialized(conn):
        return redirect("/unlock")

    settings = request.app.state.settings
    data = await upload.read()

    # Validate the file as a real Identilock database before it replaces
    # anything, using a scratch path so a bad upload leaves no trace.
    scratch = settings.db_path.with_suffix(".import-tmp")
    scratch.write_bytes(data)
    try:
        check = db.connect(scratch)
        try:
            ok = db.is_initialized(check)
        finally:
            check.close()
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        scratch.unlink(missing_ok=True)
        return render(
            request,
            "setup.html",
            {
                "errors": [
                    "That file is not an Identilock move file. On the old "
                    "computer, use Settings → Moving to a New Computer to make "
                    "one, then load that file here."
                ]
            },
        )

    conn.close()
    scratch.replace(settings.db_path)
    return redirect("/unlock")


@router.get("/unlock")
def unlock_form(
    request: Request, next: str = "/", conn: sqlite3.Connection = Depends(get_conn)
):
    if not db.is_initialized(conn):
        return redirect("/setup")
    if current_session(request) is not None:
        return redirect(_safe_next(next))
    return render(request, "unlock.html", {"error": None, "next": _safe_next(next)})


@router.post("/unlock")
def unlock_submit(
    request: Request,
    passphrase: str = Form(...),
    next: str = Form(default="/"),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if not db.is_initialized(conn):
        return redirect("/setup")

    try:
        vault = db.unlock(conn, passphrase)
    except WrongPassphrase:
        # Argon2 already makes each attempt expensive; no extra lockout needed
        # for a service reachable only from this machine.
        return render(
            request,
            "unlock.html",
            {"error": "That passphrase did not open the vault.", "next": _safe_next(next)},
        )

    # Seal any pre-0.3 plaintext reminder/report fields now that we hold the key.
    try:
        db.migrate_plaintext_fields(conn, vault)
    except Exception:
        pass
    _maybe_auto_backup(request, conn)

    session = request.app.state.sessions.create(vault)
    response = redirect(_safe_next(next))
    set_session_cookie(response, session.token)
    return response


@router.post("/lock")
def lock(request: Request, csrf_token: str = Form(default="")):
    session = current_session(request)
    if session is not None:
        verify_csrf(session, csrf_token)
        request.app.state.sessions.drop(session.token)
    response = redirect("/unlock")
    clear_session_cookie(response)
    return response
