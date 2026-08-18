"""The freeze matrix and per-cell detail editing."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from ..crypto import Vault
from ..repo import (
    freeze_matrix,
    get_agency,
    get_freeze_record,
    get_person,
    list_agencies,
    list_people,
    pending_claim_first,
    set_freeze_status,
    update_freeze_record,
)
from ..security import Session, verify_csrf
from ..seeds import (
    FREEZE_CATEGORIES,
    STATUS_ACTIVE,
    STATUS_NO_FILE,
    STATUS_NOT_APPLICABLE,
    STATUS_ORDER,
)
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()


@router.get("/matrix")
def matrix_view(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    agencies = list_agencies(conn)
    matrix = freeze_matrix(conn, vault)

    # FYI-only entries have no status a person could truthfully set, so they
    # are listed below the grid instead of getting a row of dropdowns.
    grouped: dict[str, list] = {}
    for agency in agencies:
        if agency.is_fyi:
            continue
        grouped.setdefault(agency.category, []).append(agency)

    # A row settled for every person frosts as a whole line. "Settled" per
    # cell means frozen/enrolled or confirmed no-file; "not applicable" cells
    # don't break the line but can't carry it alone — a row the household
    # opted out of entirely is shelved, not done.
    done = {STATUS_ACTIVE, STATUS_NO_FILE}
    settled_rows = set()
    if people:
        for agency in agencies:
            if agency.is_fyi:
                continue
            statuses = [
                record.status
                for person in people
                if (record := matrix.get(person.id, {}).get(agency.id))
            ]
            if (
                len(statuses) == len(people)
                and all(s in done | {STATUS_NOT_APPLICABLE} for s in statuses)
                and any(s in done for s in statuses)
            ):
                settled_rows.add(agency.id)

    return render(
        request,
        "matrix.html",
        {
            "active": "matrix",
            "people": people,
            "grouped": grouped,
            "matrix": matrix,
            "settled_rows": settled_rows,
            "fyi_agencies": [a for a in agencies if a.is_fyi],
        },
    )


@router.post("/matrix/quick")
def matrix_quick_update(
    person_id: int = Form(...),
    agency_id: int = Form(...),
    status: str = Form(...),
    back: str = Form("/matrix"),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
):
    verify_csrf(session, csrf_token)
    if status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail="Unrecognized status.")
    set_freeze_status(conn, person_id, agency_id, status)
    target = back if back.startswith("/") and not back.startswith("//") else "/matrix"
    return redirect(target)


@router.get("/freeze/{person_id}/{agency_id}")
def freeze_detail(
    person_id: int,
    agency_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    person = get_person(conn, vault, person_id)
    agency = get_agency(conn, agency_id)
    if person is None or agency is None:
        raise HTTPException(status_code=404, detail="No such freeze record.")
    record = get_freeze_record(conn, vault, person_id, agency_id)
    # Warn on freeze pages while claim-first accounts are still open: those
    # sign-ups run an identity check a freeze can break, so the order matters.
    # Once the accounts are claimed the warning has nothing to say and hides.
    claim_first_pending = (
        pending_claim_first(conn, person_id)
        if agency.category in FREEZE_CATEGORIES and agency.action_kind == "act"
        else []
    )
    return render(
        request,
        "freeze_detail.html",
        {
            "active": "matrix",
            "person": person,
            "agency": agency,
            "record": record,
            "claim_first_pending": claim_first_pending,
        },
    )


@router.post("/freeze/{person_id}/{agency_id}")
def freeze_save(
    person_id: int,
    agency_id: int,
    status: str = Form("not_started"),
    method: str = Form(""),
    date_requested: str = Form(""),
    date_confirmed: str = Form(""),
    expires_on: str = Form(""),
    last_verified: str = Form(""),
    confirmation: str = Form(""),
    pin: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    if status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail="Unrecognized status.")
    # A stale or forged id would otherwise hit a FOREIGN KEY violation and 500;
    # reject it cleanly as a 404 instead.
    if get_person(conn, vault, person_id) is None or get_agency(conn, agency_id) is None:
        raise HTTPException(status_code=404, detail="No such person or agency.")
    update_freeze_record(
        conn,
        vault,
        person_id,
        agency_id,
        status=status,
        method=method.strip(),
        date_requested=date_requested.strip(),
        date_confirmed=date_confirmed.strip(),
        expires_on=expires_on.strip(),
        last_verified=last_verified.strip(),
        confirmation=confirmation.strip() or None,
        pin=pin.strip() or None,
        notes=notes.strip() or None,
    )
    return redirect(f"/freeze/{person_id}/{agency_id}")
