"""Dashboard, agency directory, the sources index, and help."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from .. import sources as source_registry
from ..crypto import Vault
from ..repo import (
    freeze_matrix,
    get_agency,
    get_setting,
    household_progress,
    list_agencies,
    list_people,
    list_reminders,
    set_setting,
)
from ..security import Session, verify_csrf
from ..seeds import STATUS_NOT_APPLICABLE
from ..services import linkcheck
from ..web import get_conn, get_session, get_vault, render

LINK_CHECK_SETTING = "link_check"

router = APIRouter()

# How many "do this next" items to surface before it stops feeling actionable.
NEXT_ACTION_LIMIT = 8


@router.get("/")
def dashboard(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    agencies = list_agencies(conn)
    matrix = freeze_matrix(conn, vault)
    progress = household_progress(conn, people, agencies, matrix)

    # Highest-value outstanding work first: the directory's sort order already
    # puts the nationwide bureaus above the long tail.
    next_actions = []
    for agency in agencies:
        if agency.is_fyi:
            continue
        for person in people:
            record = matrix.get(person.id, {}).get(agency.id)
            if record and (record.is_done or record.status == STATUS_NOT_APPLICABLE):
                continue
            next_actions.append({"person": person, "agency": agency, "record": record})
    next_actions = next_actions[:NEXT_ACTION_LIMIT]

    reminders = list_reminders(conn, vault)
    overdue = [r for r in reminders if r.is_overdue]
    upcoming = [r for r in reminders if not r.is_overdue and r.is_soon]

    expiring = []
    for person in people:
        for agency in agencies:
            record = matrix.get(person.id, {}).get(agency.id)
            if record and record.is_expiring:
                expiring.append({"person": person, "agency": agency, "record": record})

    minors_without_bureau_freeze = []
    bureau_ids = [a.id for a in agencies if a.category == "credit_bureau"]
    for person in people:
        if not person.is_minor:
            continue
        cells = matrix.get(person.id, {})
        if any(
            not (cells.get(aid) and cells[aid].is_done) for aid in bureau_ids
        ):
            minors_without_bureau_freeze.append(person)

    return render(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "people": people,
            "agencies": agencies,
            "progress": progress,
            "next_actions": next_actions,
            "overdue": overdue,
            "upcoming": upcoming,
            "expiring": expiring,
            "minors_at_risk": minors_without_bureau_freeze,
        },
    )


@router.get("/agencies")
def agency_directory(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    agencies = list_agencies(conn, include_hidden=True)
    grouped: dict[str, list] = {}
    for agency in agencies:
        grouped.setdefault(agency.category, []).append(agency)
    return render(
        request,
        "agencies.html",
        {"active": "agencies", "grouped": grouped},
    )


@router.get("/agencies/{agency_id}")
def agency_detail(
    agency_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    agency = get_agency(conn, agency_id)
    if agency is None:
        raise HTTPException(status_code=404, detail="No such agency.")
    people = list_people(conn, vault)
    matrix = freeze_matrix(conn, vault)
    rows = [
        {"person": p, "record": matrix.get(p.id, {}).get(agency.id)} for p in people
    ]
    return render(
        request,
        "agency_detail.html",
        {"active": "agencies", "agency": agency, "rows": rows},
    )


def _stored_link_check(conn: sqlite3.Connection, vault: Vault) -> dict:
    raw = get_setting(conn, vault, LINK_CHECK_SETTING)
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


@router.get("/sources")
def sources_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    return render(
        request,
        "sources.html",
        {
            "active": "agencies",
            "all_sources": source_registry.all_sources(),
            "compiled_on": source_registry.COMPILED_ON,
            "link_check": _stored_link_check(conn, vault),
        },
    )


@router.post("/sources/check")
def sources_check(
    request: Request,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    urls = {s.key: s.url for s in source_registry.all_sources()}
    results = linkcheck.check_links(urls)
    payload = {"checked_at": date.today().isoformat(), "results": results}
    set_setting(conn, vault, LINK_CHECK_SETTING, json.dumps(payload))

    broken = sum(1 for r in results.values() if r.get("status") != linkcheck.STATUS_OK)
    if broken:
        message = (
            f"Checked {len(results)} links: {broken} did not answer. A broken "
            "link doesn't mean the address is wrong — it means nobody can "
            "currently confirm it, so double-check before relying on it."
        )
    else:
        message = f"Checked {len(results)} links — every one still answers."
    return render(
        request,
        "sources.html",
        {
            "active": "agencies",
            "all_sources": source_registry.all_sources(),
            "compiled_on": source_registry.COMPILED_ON,
            "link_check": payload,
            "message": message,
        },
    )


@router.get("/help")
def help_page(request: Request, vault: Vault = Depends(get_vault)):
    return render(request, "help.html", {"active": "help"})


@router.get("/learn")
def learn_page(request: Request, vault: Vault = Depends(get_vault)):
    return render(request, "learn.html", {"active": "learn"})
