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
    set_freeze_status,
    update_freeze_record,
)
from ..security import Session, verify_csrf
from ..seeds import STATUS_ORDER
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

    return render(
        request,
        "matrix.html",
        {
            "active": "matrix",
            "people": people,
            "grouped": grouped,
            "matrix": matrix,
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
    return render(
        request,
        "freeze_detail.html",
        {
            "active": "matrix",
            "person": person,
            "agency": agency,
            "record": record,
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
