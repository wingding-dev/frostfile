"""Breach exposure guidance.

By project rule, FrostFile makes ZERO internet connections. Breach checking
therefore happens in the user's own browser: this page explains what to check
and links out to Have I Been Pwned. The app itself never sends anything.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request

from ..crypto import Vault
from ..repo import list_people
from ..web import get_conn, get_vault, render

router = APIRouter()


@router.get("/breaches")
def breaches_index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    vault: Vault = Depends(get_vault),
):
    people = list_people(conn, vault)
    return render(
        request,
        "breaches.html",
        {
            "active": "breaches",
            "emails": [p.email for p in people if p.email],
        },
    )
