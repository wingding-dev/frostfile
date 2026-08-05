"""Breach exposure checks against Have I Been Pwned."""

from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, Depends, Form, Request

from ..crypto import Vault
from ..repo import get_setting, list_breach_checks, list_people, save_breach_check
from ..security import Session, verify_csrf
from ..services import hibp
from ..web import get_conn, get_session, get_vault, render

router = APIRouter()

HIBP_KEY_SETTING = "hibp_api_key"


def _page(
    request: Request,
    conn: sqlite3.Connection,
    vault: Vault,
    *,
    error: str = "",
    message: str = "",
    password_result: dict | None = None,
):
    return render(
        request,
        "breaches.html",
        {
            "active": "breaches",
            "people": list_people(conn, vault),
            "checks": list_breach_checks(conn, vault),
            "has_key": bool(get_setting(conn, vault, HIBP_KEY_SETTING)),
            "subscription_url": hibp.SUBSCRIPTION_URL,
            "error": error,
            "message": message,
            "password_result": password_result,
        },
    )


@router.get("/breaches")
def breaches_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    return _page(request, conn, vault)


@router.post("/breaches/email")
def breaches_check_email(
    request: Request,
    email: str = Form(...),
    person_id: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    api_key = get_setting(conn, vault, HIBP_KEY_SETTING) or ""

    try:
        breaches = hibp.check_email(email.strip(), api_key)
    except hibp.HibpError as exc:
        return _page(request, conn, vault, error=str(exc))

    save_breach_check(
        conn,
        vault,
        person_id=int(person_id) if person_id.isdigit() else None,
        email=email.strip(),
        source="hibp",
        result={"breaches": [b.as_dict() for b in breaches]},
    )
    if breaches:
        message = f"{len(breaches)} breach(es) found for that address."
    else:
        message = "No known breaches for that address."
    return _page(request, conn, vault, message=message)


@router.post("/breaches/email-all")
def breaches_check_everyone(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    api_key = get_setting(conn, vault, HIBP_KEY_SETTING) or ""

    # One lookup per distinct address; two people sharing an email get one call.
    targets: list[tuple[str, int]] = []
    seen: set[str] = set()
    for person in list_people(conn, vault):
        email = (person.email or "").strip().lower()
        if email and email not in seen:
            seen.add(email)
            targets.append((person.email.strip(), person.id))
    if not targets:
        return _page(
            request,
            conn,
            vault,
            error="Nobody has an email address on file. Add them under Family first.",
        )

    checked = found = 0
    problems: list[str] = []
    for index, (email, person_id) in enumerate(targets):
        if index:
            # The cheapest HIBP plan allows 10 lookups a minute; pausing
            # between calls keeps a large family under that without failing.
            time.sleep(6.5)
        try:
            breaches = hibp.check_email(email, api_key)
        except hibp.HibpError as exc:
            problems.append(f"{email}: {exc}")
            continue
        save_breach_check(
            conn,
            vault,
            person_id=person_id,
            email=email,
            source="hibp",
            result={"breaches": [b.as_dict() for b in breaches]},
        )
        checked += 1
        found += len(breaches)

    summary = f"Checked {checked} address{'' if checked == 1 else 'es'}; {found} breach entr{'y' if found == 1 else 'ies'} found. Details below."
    if problems:
        return _page(
            request, conn, vault, error=f"{summary} Problems: " + " · ".join(problems)
        )
    return _page(request, conn, vault, message=summary)


@router.post("/breaches/password")
def breaches_check_password(
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    try:
        count = hibp.check_password(password)
    except hibp.HibpError as exc:
        return _page(request, conn, vault, error=str(exc))

    # The password is not stored, not logged, and not echoed back.
    return _page(request, conn, vault, password_result={"count": count})
