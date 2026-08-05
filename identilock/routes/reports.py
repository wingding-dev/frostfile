"""Credit report storage and comparison between pulls."""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..crypto import Vault
from ..repo import (
    delete_report,
    get_person,
    get_report,
    list_people,
    list_reports,
    previous_report,
    save_report,
)
from ..security import Session, verify_csrf
from ..services.reportdiff import compare, extract_entities, extract_text
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()

BUREAUS = ["Equifax", "Experian", "TransUnion", "Innovis", "LexisNexis", "Other"]

# Reports run to a few hundred KB of text; anything far past that is a mistake.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.get("/reports")
def reports_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
    error: str = "",
):
    return render(
        request,
        "reports.html",
        {
            "active": "reports",
            "reports": list_reports(conn, vault),
            "people": list_people(conn, vault),
            "bureaus": BUREAUS,
            "today": date.today().isoformat(),
            "error": error,
        },
    )


@router.post("/reports")
async def report_upload(
    request: Request,
    person_id: int = Form(...),
    bureau: str = Form(...),
    pulled_on: str = Form(...),
    upload: UploadFile = File(...),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)

    if get_person(conn, vault, person_id) is None:
        raise HTTPException(status_code=404, detail="No such person.")

    data = await upload.read()
    if not data:
        return redirect("/reports?error=That+file+was+empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        return redirect("/reports?error=That+file+is+too+large.")

    try:
        text = extract_text(data, upload.filename or "")
    except ValueError as exc:
        return redirect(f"/reports?error={str(exc).replace(' ', '+')}")
    except Exception:  # noqa: BLE001 - any parser failure is the same to a user
        return redirect(
            "/reports?error=Could+not+read+that+file.+Try+saving+it+as+PDF+or+text."
        )

    if not text.strip():
        return redirect(
            "/reports?error=No+text+found.+If+the+PDF+is+a+scan,+it+has+no+text+layer."
        )

    # The uploaded file itself is never written to disk — only its extracted
    # text, encrypted, inside the database.
    extraction = extract_entities(text)
    report_id = save_report(
        conn,
        vault,
        person_id=person_id,
        bureau=bureau if bureau in BUREAUS else "Other",
        pulled_on=pulled_on.strip() or date.today().isoformat(),
        source_name=upload.filename or "",
        text=text,
        extracted=extraction.as_dict(),
    )
    return redirect(f"/reports/{report_id}")


@router.get("/reports/{report_id}")
def report_detail(
    report_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
    show_raw: int = 0,
):
    report = get_report(conn, vault, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No such report.")
    person = get_person(conn, vault, report.person_id)
    prior = previous_report(conn, vault, report)

    comparison = compare(
        prior.extracted if prior else None,
        report.extracted,
        previous_text=prior.text or "" if prior else "",
        current_text=report.text or "" if show_raw else "",
    )

    return render(
        request,
        "report_detail.html",
        {
            "active": "reports",
            "report": report,
            "person": person,
            "prior": prior,
            "comparison": comparison,
            "show_raw": bool(show_raw),
        },
    )


@router.post("/reports/{report_id}/delete")
def report_delete(
    report_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
):
    verify_csrf(session, csrf_token)
    delete_report(conn, report_id)
    return redirect("/reports")
