"""Printable mailing packets for protected-consumer (minor) freezes.

Deliberately conservative: a packet is only offered for agencies whose mailing
address was confirmed at a primary source. Everything else sends you to the
agency's own page instead of guessing at an envelope.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response

from ..crypto import Vault
from ..repo import (
    get_agency,
    get_freeze_record,
    get_person,
    list_agencies,
    list_people,
    update_freeze_record,
)
from ..security import Session, verify_csrf
from ..seeds import FREEZE_CATEGORIES, STATUS_NOT_STARTED
from ..services import pdfletters
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()


def _long_date() -> str:
    # Built by hand rather than with %-d, which is not portable to Windows —
    # and coworkers will be running this on Windows.
    return f"{date.today():%B} {date.today().day}, {date.today():%Y}"


def _pick_guardian(request: Request, guardians: list) -> object | None:
    guardian_id = request.query_params.get("guardian")
    if guardian_id and guardian_id.isdigit():
        for adult in guardians:
            if adult.id == int(guardian_id):
                return adult
    return guardians[0] if guardians else None


def _mailable_agencies(conn: sqlite3.Connection) -> list:
    return [
        a
        for a in list_agencies(conn)
        if a.category in FREEZE_CATEGORIES and a.can_generate_letter
    ]


def _mark_mailed(
    conn: sqlite3.Connection, vault: Vault, person_id: int, agency_id: int
) -> None:
    """One-click bookkeeping for a packet that just went in an envelope.

    Fills only what mailing establishes — status, method, request date — and
    preserves anything already recorded by hand.
    """
    existing = get_freeze_record(conn, vault, person_id, agency_id)
    today = date.today().isoformat()
    update_freeze_record(
        conn,
        vault,
        person_id,
        agency_id,
        status=(
            "in_progress"
            if existing is None or existing.status == STATUS_NOT_STARTED
            else existing.status
        ),
        method="mail",
        date_requested=(existing.date_requested if existing else None) or today,
        date_confirmed=existing.date_confirmed if existing else None,
        expires_on=existing.expires_on if existing else None,
        last_verified=existing.last_verified if existing else None,
        confirmation=existing.confirmation if existing else None,
        pin=existing.pin if existing else None,
        notes=existing.notes if existing else None,
    )


@router.get("/letters")
def letters_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    minors = [p for p in people if p.is_minor]
    # Only reporting agencies belong here. Controls like the IRS IP PIN also
    # cover children, but they are enrollments rather than something you mail a
    # freeze request to, and listing them would just be confusing.
    agencies = [a for a in list_agencies(conn) if a.category in FREEZE_CATEGORIES]
    mailable = [a for a in agencies if a.can_generate_letter]
    blocked = [a for a in agencies if a.supports_minor and not a.can_generate_letter]
    return render(
        request,
        "letters_index.html",
        {
            "active": "letters",
            "minors": minors,
            "adults": [p for p in people if not p.is_minor],
            "mailable": mailable,
            "blocked": blocked,
        },
    )


# Registered before /letters/{person_id}/{agency_id} so the literal path wins.
@router.get("/letters/all")
def letters_print_all(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    minors = [p for p in people if p.is_minor]
    guardians = [p for p in people if not p.is_minor]
    agencies = _mailable_agencies(conn)
    packets = [(child, agency) for child in minors for agency in agencies]
    if not packets:
        return redirect("/letters")
    return render(
        request,
        "letters_print_all.html",
        {
            "active": "letters",
            "packets": packets,
            "guardian": _pick_guardian(request, guardians),
            "guardians": guardians,
            "today": _long_date(),
            "today_iso": date.today().isoformat(),
        },
    )


@router.get("/letters/all.zip")
def letters_download_zip(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    """Every packet as its own pre-named PDF, in one zip download."""
    people = list_people(conn, vault)
    minors = [p for p in people if p.is_minor]
    guardians = [p for p in people if not p.is_minor]
    agencies = _mailable_agencies(conn)
    packets = [(child, agency) for child in minors for agency in agencies]
    if not packets:
        return redirect("/letters")
    payload = pdfletters.build_zip(
        packets, _pick_guardian(request, guardians), _long_date()
    )
    filename = f"Freeze packets - {date.today().isoformat()}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/letters/all/mailed")
def letters_mark_all_mailed(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    minors = [p for p in list_people(conn, vault) if p.is_minor]
    for child in minors:
        for agency in _mailable_agencies(conn):
            _mark_mailed(conn, vault, child.id, agency.id)
    return redirect("/matrix")


@router.get("/letters/{person_id}/{agency_id}")
def letter_print(
    person_id: int,
    agency_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    person = get_person(conn, vault, person_id)
    agency = get_agency(conn, agency_id)
    if person is None or agency is None:
        raise HTTPException(status_code=404, detail="No such person or agency.")

    if not agency.can_generate_letter:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Identilock will not print a packet for {agency.name}: its mailing "
                "address was not confirmed at a primary source. Use the agency's "
                "own page instead — a packet containing a birth certificate should "
                "never go to an address nobody checked."
            ),
        )

    guardians = [p for p in list_people(conn, vault) if not p.is_minor]
    return render(
        request,
        "letter_print.html",
        {
            "active": "letters",
            "person": person,
            "agency": agency,
            "guardian": _pick_guardian(request, guardians),
            "guardians": guardians,
            "today": _long_date(),
        },
    )


@router.post("/letters/{person_id}/{agency_id}/mailed")
def letter_mark_mailed(
    person_id: int,
    agency_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    if get_person(conn, vault, person_id) is None or get_agency(conn, agency_id) is None:
        raise HTTPException(status_code=404, detail="No such person or agency.")
    _mark_mailed(conn, vault, person_id, agency_id)
    return redirect(f"/freeze/{person_id}/{agency_id}")
