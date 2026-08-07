"""Managing the people whose identities you are tracking."""

from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from ..crypto import Vault
from ..repo import (
    create_person,
    delete_person,
    freeze_matrix,
    get_person,
    list_agencies,
    list_people,
    update_person,
)
from ..security import Session, verify_csrf
from ..web import get_conn, get_session, get_vault, redirect, render

router = APIRouter()

# Storage keeps the address as one block of text ("street\ncity, ST zip") so
# letters can print it verbatim, but the form shows separate boxes because
# browser autofill cannot target a single free-form field. These two functions
# are the seam between those representations.
_CITY_STATE_ZIP = re.compile(
    r"^\s*(?P<city>.*?)[,\s]+(?P<state>[A-Za-z]{2})\.?\s+(?P<zip>\d{5}(?:-\d{4})?)\s*$"
)


def _combine_address(street: str, city: str, state: str, zip_code: str) -> str | None:
    street = street.strip()
    city = city.strip().rstrip(",")
    state = state.strip().upper()
    zip_code = zip_code.strip()
    last_line_bits = []
    if city:
        last_line_bits.append(city + ("," if state or zip_code else ""))
    if state:
        last_line_bits.append(state)
    if zip_code:
        last_line_bits.append(zip_code)
    lines = [part for part in (street, " ".join(last_line_bits)) if part]
    return "\n".join(lines) or None


def split_address(address: str | None) -> dict[str, str]:
    parts = {"street": "", "city": "", "state": "", "zip": ""}
    if not address:
        return parts
    lines = address.strip().splitlines()
    match = _CITY_STATE_ZIP.match(lines[-1]) if len(lines) > 1 else None
    if match:
        parts["street"] = "\n".join(lines[:-1]).strip()
        parts["city"] = match.group("city").rstrip(",")
        parts["state"] = match.group("state").upper()
        parts["zip"] = match.group("zip")
    else:
        # Unrecognized shape (or single line): keep it intact in the street box
        # rather than guess and mangle someone's address.
        parts["street"] = address.strip()
    return parts


@router.get("/people")
def people_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    # Count only actionable agencies, and exclude records marked "not
    # applicable" from the denominator — same rule as the dashboard meter, so
    # the two never disagree and the count is actually reachable.
    agencies = [a for a in list_agencies(conn) if not a.is_fyi]
    matrix = freeze_matrix(conn, vault)
    rows = []
    for person in people:
        cells = matrix.get(person.id, {})
        done = total = 0
        for agency in agencies:
            record = cells.get(agency.id)
            if record is not None and record.status == "not_applicable":
                continue
            total += 1
            if record and record.is_done:
                done += 1
        rows.append({"person": person, "done": done, "total": total})
    return render(request, "people_list.html", {"active": "people", "rows": rows})


def _address_sources(
    conn: sqlite3.Connection, vault: Vault, exclude_id: int | None = None
) -> list:
    """People whose stored address can be copied — families usually share one."""
    return [
        p
        for p in list_people(conn, vault)
        if p.address and p.id != exclude_id
    ]


@router.get("/people/new")
def person_new(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    return render(
        request,
        "person_form.html",
        {
            "active": "people",
            "person": None,
            "errors": [],
            "address_parts": split_address(None),
            "address_sources": _address_sources(conn, vault),
        },
    )


def _form_values(
    display_name: str,
    kind: str,
    birth_date: str,
    ssn: str,
    ssn_last4: str,
    email: str,
    phone: str,
    address: str,
    address_street: str,
    address_city: str,
    address_state: str,
    address_zip: str,
    notes: str,
    store_full_ssn: str,
) -> dict:
    # The full SSN is only kept when explicitly opted in. Without it the app
    # still works — mailing packets simply leave a blank to fill in by hand,
    # which is the safer default for a file you might sync or back up.
    keep_ssn = bool(store_full_ssn)
    combined = _combine_address(
        address_street, address_city, address_state, address_zip
    )
    return {
        "display_name": display_name.strip(),
        "kind": kind if kind in {"adult", "minor"} else "adult",
        "birth_date": birth_date.strip() or None,
        "ssn": ssn.strip() if keep_ssn else None,
        "ssn_last4": (ssn_last4.strip() or None),
        "email": email.strip() or None,
        "phone": phone.strip() or None,
        # The split fields are what the form sends; the single `address` field
        # is still accepted for anything that posts the old shape.
        "address": combined or address.strip() or None,
        "notes": notes.strip() or None,
    }


@router.post("/people")
def person_create(
    request: Request,
    display_name: str = Form(...),
    kind: str = Form("adult"),
    birth_date: str = Form(""),
    ssn: str = Form(""),
    ssn_last4: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    address_street: str = Form(""),
    address_city: str = Form(""),
    address_state: str = Form(""),
    address_zip: str = Form(""),
    notes: str = Form(""),
    store_full_ssn: str = Form(""),
    copy_address_from: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    values = _form_values(
        display_name, kind, birth_date, ssn, ssn_last4, email, phone, address,
        address_street, address_city, address_state, address_zip,
        notes, store_full_ssn,
    )
    _apply_copied_address(conn, vault, values, copy_address_from)
    if not values["display_name"]:
        return render(
            request,
            "person_form.html",
            {
                "active": "people",
                "person": None,
                "errors": ["A name is required."],
                "address_parts": split_address(values["address"]),
                "address_sources": _address_sources(conn, vault),
            },
        )
    person_id = create_person(conn, vault, **values)
    return redirect(f"/people/{person_id}")


def _apply_copied_address(
    conn: sqlite3.Connection, vault: Vault, values: dict, copy_from: str
) -> None:
    """'Same address as X': copying wins over whatever is in the boxes, since
    picking a person is the more deliberate act."""
    if not copy_from:
        return
    try:
        source = get_person(conn, vault, int(copy_from))
    except (TypeError, ValueError):
        return
    if source is not None and source.address:
        values["address"] = source.address


@router.get("/people/{person_id}")
def person_detail(
    person_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    person = get_person(conn, vault, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person.")
    agencies = list_agencies(conn)
    cells = freeze_matrix(conn, vault).get(person_id, {})
    grouped: dict[str, list] = {}
    for agency in agencies:
        # FYI-only entries carry no per-person task; they live in the Directory.
        if agency.is_fyi:
            continue
        grouped.setdefault(agency.category, []).append(
            {"agency": agency, "record": cells.get(agency.id)}
        )
    return render(
        request,
        "person_detail.html",
        {"active": "people", "person": person, "grouped": grouped},
    )


@router.get("/people/{person_id}/edit")
def person_edit(
    person_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    person = get_person(conn, vault, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person.")
    return render(
        request,
        "person_form.html",
        {
            "active": "people",
            "person": person,
            "errors": [],
            "address_parts": split_address(person.address),
            "address_sources": _address_sources(conn, vault, exclude_id=person.id),
        },
    )


@router.post("/people/{person_id}")
def person_update(
    person_id: int,
    request: Request,
    display_name: str = Form(...),
    kind: str = Form("adult"),
    birth_date: str = Form(""),
    ssn: str = Form(""),
    ssn_last4: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    address_street: str = Form(""),
    address_city: str = Form(""),
    address_state: str = Form(""),
    address_zip: str = Form(""),
    notes: str = Form(""),
    store_full_ssn: str = Form(""),
    copy_address_from: str = Form(""),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    verify_csrf(session, csrf_token)
    existing = get_person(conn, vault, person_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No such person.")

    values = _form_values(
        display_name, kind, birth_date, ssn, ssn_last4, email, phone, address,
        address_street, address_city, address_state, address_zip,
        notes, store_full_ssn,
    )
    _apply_copied_address(conn, vault, values, copy_address_from)
    # An unchanged edit form shows the SSN masked rather than in the clear, so
    # a blank field means "leave it alone", not "erase it".
    if store_full_ssn and not values["ssn"]:
        values["ssn"] = existing.ssn
    if not values["ssn_last4"]:
        values["ssn_last4"] = existing.ssn_last4

    if not values["display_name"]:
        return render(
            request,
            "person_form.html",
            {
                "active": "people",
                "person": existing,
                "errors": ["A name is required."],
                "address_parts": split_address(values["address"]),
                "address_sources": _address_sources(conn, vault, exclude_id=person_id),
            },
        )
    update_person(conn, vault, person_id, **values)
    return redirect(f"/people/{person_id}")


@router.post("/people/{person_id}/delete")
def person_delete(
    person_id: int,
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
    conn: sqlite3.Connection = Depends(get_conn),
):
    verify_csrf(session, csrf_token)
    delete_person(conn, person_id)
    return redirect("/people")
