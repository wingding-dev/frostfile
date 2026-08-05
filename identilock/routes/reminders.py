"""Recurring identity-hygiene reminders, with calendar export."""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response

from ..crypto import Vault
from ..repo import (
    complete_reminder,
    create_reminder,
    delete_reminder,
    list_people,
    list_reminders,
)
from ..security import Session, verify_csrf
from ..services.ics import build_calendar
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()

VALID_RECURRENCE = {"none", "weekly", "monthly", "quarterly", "yearly"}


@router.get("/reminders")
def reminders_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    reminders = list_reminders(conn, vault)
    return render(
        request,
        "reminders.html",
        {
            "active": "reminders",
            "overdue": [r for r in reminders if r.is_overdue],
            "soon": [r for r in reminders if not r.is_overdue and r.is_soon],
            "later": [r for r in reminders if not r.is_overdue and not r.is_soon],
            "people": list_people(conn, vault),
            "today": date.today().isoformat(),
        },
    )


@router.post("/reminders")
def reminder_create(
    title: str = Form(...),
    due_date: str = Form(...),
    detail: str = Form(""),
    recurrence: str = Form("none"),
    person_id: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    create_reminder(
        conn,
        vault,
        title=title.strip(),
        due_date=due_date.strip(),
        detail=detail.strip(),
        recurrence=recurrence if recurrence in VALID_RECURRENCE else "none",
        person_id=int(person_id) if person_id.isdigit() else None,
    )
    return redirect("/reminders")


@router.post("/reminders/{reminder_id}/complete")
def reminder_complete(
    reminder_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
):
    verify_csrf(session, csrf_token)
    complete_reminder(conn, reminder_id)
    return redirect("/reminders")


@router.post("/reminders/{reminder_id}/delete")
def reminder_delete(
    reminder_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
):
    verify_csrf(session, csrf_token)
    delete_reminder(conn, reminder_id)
    return redirect("/reminders")


@router.get("/reminders.ics")
def reminders_calendar(
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    calendar = build_calendar(list_reminders(conn, vault))
    return Response(
        content=calendar,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="identilock.ics"',
            "Cache-Control": "no-store",
        },
    )
