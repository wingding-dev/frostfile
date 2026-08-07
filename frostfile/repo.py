"""Data access. Every read decrypts through the vault; every write encrypts.

Callers deal in plain dataclasses and never see ciphertext. Keeping that
boundary in one module is what makes it possible to answer "where could a
Social Security number end up in the clear?" by reading a single file.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from . import sources
from .crypto import Vault
from .db import context_for, utcnow
from .seeds import (
    REMINDER_TEMPLATES,
    STATUS_ACTIVE,
    STATUS_NOT_STARTED,
    status_label,
)


# --------------------------------------------------------------------- people


@dataclass
class Person:
    id: int
    kind: str
    display_name: str
    sort_order: int = 0
    birth_date: str | None = None
    ssn: str | None = None
    ssn_last4: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None

    @property
    def is_minor(self) -> bool:
        return self.kind == "minor"

    @property
    def masked_ssn(self) -> str:
        if self.ssn_last4:
            return f"•••-••-{self.ssn_last4}"
        return "—"

    @property
    def has_full_ssn(self) -> bool:
        return bool(self.ssn)


_PERSON_FIELDS = (
    ("display_name", "display_name_enc"),
    ("birth_date", "birth_date_enc"),
    ("ssn", "ssn_enc"),
    ("ssn_last4", "ssn_last4_enc"),
    ("email", "email_enc"),
    ("phone", "phone_enc"),
    ("address", "address_enc"),
    ("notes", "notes_enc"),
)


def _row_to_person(vault: Vault, row: sqlite3.Row) -> Person:
    values: dict[str, Any] = {}
    for attr, column in _PERSON_FIELDS:
        values[attr] = vault.decrypt(context_for("people", column), row[column])
    return Person(
        id=row["id"],
        kind=row["kind"],
        sort_order=row["sort_order"],
        display_name=values.pop("display_name") or "(unreadable)",
        **values,
    )


def list_people(conn: sqlite3.Connection, vault: Vault) -> list[Person]:
    rows = conn.execute("SELECT * FROM people ORDER BY sort_order, id").fetchall()
    people = [_row_to_person(vault, row) for row in rows]
    # Names are encrypted, so alphabetical ordering has to happen here rather
    # than in SQL. Adults first, then children, then by name.
    people.sort(key=lambda p: (p.sort_order, p.kind == "minor", p.display_name.lower()))
    return people


def get_person(conn: sqlite3.Connection, vault: Vault, person_id: int) -> Person | None:
    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    return _row_to_person(vault, row) if row else None


def create_person(conn: sqlite3.Connection, vault: Vault, **values: Any) -> int:
    now = utcnow()
    ssn = _normalize_ssn(values.get("ssn"))
    last4 = values.get("ssn_last4") or (ssn[-4:] if ssn else None)

    payload = {
        "display_name_enc": vault.encrypt(
            context_for("people", "display_name_enc"), values["display_name"]
        ),
        "birth_date_enc": vault.encrypt(
            context_for("people", "birth_date_enc"), values.get("birth_date")
        ),
        "ssn_enc": vault.encrypt(context_for("people", "ssn_enc"), ssn),
        "ssn_last4_enc": vault.encrypt(context_for("people", "ssn_last4_enc"), last4),
        "email_enc": vault.encrypt(
            context_for("people", "email_enc"), values.get("email")
        ),
        "phone_enc": vault.encrypt(
            context_for("people", "phone_enc"), values.get("phone")
        ),
        "address_enc": vault.encrypt(
            context_for("people", "address_enc"), values.get("address")
        ),
        "notes_enc": vault.encrypt(
            context_for("people", "notes_enc"), values.get("notes")
        ),
    }
    columns = ", ".join(["kind", *payload, "created_at", "updated_at"])
    placeholders = ", ".join(["?"] * (len(payload) + 3))
    cursor = conn.execute(
        f"INSERT INTO people ({columns}) VALUES ({placeholders})",
        (values.get("kind", "adult"), *payload.values(), now, now),
    )
    person_id = int(cursor.lastrowid)
    conn.commit()

    ensure_freeze_records(conn, person_id)
    seed_reminders_for(conn, vault, person_id, values.get("kind", "adult"))
    return person_id


def _preserve_unreadable(
    conn: sqlite3.Connection,
    vault: Vault,
    table: str,
    where_sql: str,
    where_params: tuple,
    payload: dict[str, Any],
) -> None:
    """Guard against silent data loss: if an update would write NULL over a
    stored ciphertext that merely failed to decrypt this session (corruption,
    a partial cross-passphrase restore), keep the old bytes instead. Overwriting
    would destroy the only copy that a good backup or repair could recover.

    Only encrypted (`*_enc`) columns are considered, so clearing a plaintext
    field (a date, a status) still works normally."""
    columns = [
        c for c, v in payload.items() if v is None and c.endswith("_enc")
    ]
    if not columns:
        return
    row = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE {where_sql}", where_params
    ).fetchone()
    if row is None:
        return
    for column in columns:
        existing = row[column]
        if existing is not None and not vault.readable(
            context_for(table, column), existing
        ):
            payload[column] = existing


def update_person(
    conn: sqlite3.Connection, vault: Vault, person_id: int, **values: Any
) -> None:
    ssn = _normalize_ssn(values.get("ssn"))
    last4 = values.get("ssn_last4") or (ssn[-4:] if ssn else None)
    payload = {
        "display_name_enc": vault.encrypt(
            context_for("people", "display_name_enc"), values["display_name"]
        ),
        "birth_date_enc": vault.encrypt(
            context_for("people", "birth_date_enc"), values.get("birth_date")
        ),
        "ssn_enc": vault.encrypt(context_for("people", "ssn_enc"), ssn),
        "ssn_last4_enc": vault.encrypt(context_for("people", "ssn_last4_enc"), last4),
        "email_enc": vault.encrypt(
            context_for("people", "email_enc"), values.get("email")
        ),
        "phone_enc": vault.encrypt(
            context_for("people", "phone_enc"), values.get("phone")
        ),
        "address_enc": vault.encrypt(
            context_for("people", "address_enc"), values.get("address")
        ),
        "notes_enc": vault.encrypt(
            context_for("people", "notes_enc"), values.get("notes")
        ),
    }
    _preserve_unreadable(conn, vault, "people", "id = ?", (person_id,), payload)
    assignments = ", ".join(f"{c} = ?" for c in payload)
    conn.execute(
        f"UPDATE people SET kind = ?, {assignments}, updated_at = ? WHERE id = ?",
        (values.get("kind", "adult"), *payload.values(), utcnow(), person_id),
    )
    conn.commit()
    ensure_freeze_records(conn, person_id)


def delete_person(conn: sqlite3.Connection, person_id: int) -> None:
    conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
    conn.commit()


def _normalize_ssn(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


# ------------------------------------------------------------------- agencies


@dataclass
class Agency:
    id: int
    slug: str
    name: str
    category: str
    description: str = ""
    why_it_matters: str = ""
    freeze_url: str = ""
    phone: str = ""
    mail_address: str = ""
    address_verified: bool = False
    source_url: str = ""
    supports_online: bool = True
    supports_minor: bool = False
    minor_mail_only: bool = True
    expires_after_days: int | None = None
    thaw_procedure: str = ""
    notes: str = ""
    action_kind: str = "act"
    action_note: str = ""
    protects: str = ""
    impact: int = 0
    is_builtin: bool = True
    is_active: bool = True
    sort_order: int = 0
    citations: dict[str, list[str]] = field(default_factory=dict)
    minor_requirements: dict[str, list[str]] = field(default_factory=dict)

    @property
    def can_generate_letter(self) -> bool:
        """Only agencies with a confirmed address get a printable packet."""
        return self.supports_minor and self.address_verified and bool(self.mail_address)

    @property
    def is_fyi(self) -> bool:
        """No step a person can take — informational only."""
        return self.action_kind == "fyi"

    @property
    def effort_label(self) -> str:
        """Honest setup cost, derived from how the agency actually takes
        requests rather than from a separate (and uncited) estimate."""
        if self.action_kind != "act":
            return ""
        if self.supports_online:
            return "Minutes, online"
        if self.phone:
            return "A phone call"
        if self.mail_address:
            return "A letter in the mail"
        return "Contact them directly"

    def cite(self, field_name: str) -> list[sources.Source]:
        """Sources backing one field, for the superscript links in the UI."""
        return sources.resolve(self.citations.get(field_name))

    def is_cited(self, field_name: str) -> bool:
        return bool(self.cite(field_name))

    @property
    def all_sources(self) -> list[sources.Source]:
        seen: dict[str, sources.Source] = {}
        for keys in self.citations.values():
            for source in sources.resolve(keys):
                seen[source.key] = source
        return list(seen.values())


def _row_to_agency(row: sqlite3.Row) -> Agency:
    try:
        payload = json.loads(row["citations_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return Agency(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        category=row["category"],
        description=row["description"],
        why_it_matters=row["why_it_matters"],
        freeze_url=row["freeze_url"],
        phone=row["phone"],
        mail_address=row["mail_address"],
        address_verified=bool(row["address_verified"]),
        source_url=row["source_url"],
        supports_online=bool(row["supports_online"]),
        supports_minor=bool(row["supports_minor"]),
        minor_mail_only=bool(row["minor_mail_only"]),
        expires_after_days=row["expires_after_days"],
        thaw_procedure=row["thaw_procedure"],
        notes=row["notes"],
        action_kind=row["action_kind"],
        action_note=row["action_note"],
        protects=row["protects"],
        impact=row["impact"],
        is_builtin=bool(row["is_builtin"]),
        is_active=bool(row["is_active"]),
        sort_order=row["sort_order"],
        citations=payload.get("citations", {}),
        minor_requirements=payload.get("requirements", {}),
    )


def list_agencies(conn: sqlite3.Connection, include_hidden: bool = False) -> list[Agency]:
    where = "" if include_hidden else "WHERE is_active = 1"
    rows = conn.execute(
        f"SELECT * FROM agencies {where} ORDER BY sort_order, name"
    ).fetchall()
    return [_row_to_agency(row) for row in rows]


def get_agency(conn: sqlite3.Connection, agency_id: int) -> Agency | None:
    row = conn.execute("SELECT * FROM agencies WHERE id = ?", (agency_id,)).fetchone()
    return _row_to_agency(row) if row else None


def get_agency_by_slug(conn: sqlite3.Connection, slug: str) -> Agency | None:
    row = conn.execute("SELECT * FROM agencies WHERE slug = ?", (slug,)).fetchone()
    return _row_to_agency(row) if row else None


def set_agency_active(conn: sqlite3.Connection, agency_id: int, active: bool) -> None:
    conn.execute(
        "UPDATE agencies SET is_active = ? WHERE id = ?", (int(active), agency_id)
    )
    conn.commit()


# --------------------------------------------------------------- freeze state


@dataclass
class FreezeRecord:
    id: int
    person_id: int
    agency_id: int
    status: str = STATUS_NOT_STARTED
    method: str = ""
    date_requested: str | None = None
    date_confirmed: str | None = None
    expires_on: str | None = None
    last_verified: str | None = None
    confirmation: str | None = None
    pin: str | None = None
    notes: str | None = None

    def label(self, category: str) -> str:
        return status_label(self.status, category)

    @property
    def is_done(self) -> bool:
        return self.status in {STATUS_ACTIVE, "no_file", "not_applicable"}

    @property
    def is_expiring(self) -> bool:
        if not self.expires_on:
            return False
        try:
            due = date.fromisoformat(self.expires_on)
        except ValueError:
            return False
        return due - date.today() <= timedelta(days=45)


def _row_to_freeze(vault: Vault, row: sqlite3.Row) -> FreezeRecord:
    return FreezeRecord(
        id=row["id"],
        person_id=row["person_id"],
        agency_id=row["agency_id"],
        status=row["status"],
        method=row["method"],
        date_requested=row["date_requested"],
        date_confirmed=row["date_confirmed"],
        expires_on=row["expires_on"],
        last_verified=row["last_verified"],
        confirmation=vault.decrypt(
            context_for("freeze_records", "confirmation_enc"), row["confirmation_enc"]
        ),
        pin=vault.decrypt(context_for("freeze_records", "pin_enc"), row["pin_enc"]),
        notes=vault.decrypt(
            context_for("freeze_records", "notes_enc"), row["notes_enc"]
        ),
    )


def ensure_freeze_records(conn: sqlite3.Connection, person_id: int) -> None:
    """Backfill placeholder rows so the matrix has a cell for every agency."""
    now = utcnow()
    conn.execute(
        """
        INSERT INTO freeze_records (person_id, agency_id, status, created_at, updated_at)
        SELECT ?, a.id, ?, ?, ?
        FROM agencies a
        WHERE a.is_active = 1
          AND NOT EXISTS (
              SELECT 1 FROM freeze_records f
              WHERE f.person_id = ? AND f.agency_id = a.id
          )
        """,
        (person_id, STATUS_NOT_STARTED, now, now, person_id),
    )
    conn.commit()


def backfill_all_freeze_records(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id FROM people").fetchall():
        ensure_freeze_records(conn, row["id"])


def get_freeze_record(
    conn: sqlite3.Connection, vault: Vault, person_id: int, agency_id: int
) -> FreezeRecord | None:
    row = conn.execute(
        "SELECT * FROM freeze_records WHERE person_id = ? AND agency_id = ?",
        (person_id, agency_id),
    ).fetchone()
    return _row_to_freeze(vault, row) if row else None


def freeze_matrix(
    conn: sqlite3.Connection, vault: Vault
) -> dict[int, dict[int, FreezeRecord]]:
    """{person_id: {agency_id: record}} for the whole household."""
    matrix: dict[int, dict[int, FreezeRecord]] = {}
    for row in conn.execute("SELECT * FROM freeze_records").fetchall():
        record = _row_to_freeze(vault, row)
        matrix.setdefault(record.person_id, {})[record.agency_id] = record
    return matrix


def update_freeze_record(
    conn: sqlite3.Connection,
    vault: Vault,
    person_id: int,
    agency_id: int,
    **values: Any,
) -> None:
    ensure_freeze_records(conn, person_id)
    payload = {
        "status": values.get("status", STATUS_NOT_STARTED),
        "method": values.get("method", ""),
        "date_requested": values.get("date_requested") or None,
        "date_confirmed": values.get("date_confirmed") or None,
        "expires_on": values.get("expires_on") or None,
        "last_verified": values.get("last_verified") or None,
        "confirmation_enc": vault.encrypt(
            context_for("freeze_records", "confirmation_enc"),
            values.get("confirmation"),
        ),
        "pin_enc": vault.encrypt(
            context_for("freeze_records", "pin_enc"), values.get("pin")
        ),
        "notes_enc": vault.encrypt(
            context_for("freeze_records", "notes_enc"), values.get("notes")
        ),
    }
    _preserve_unreadable(
        conn,
        vault,
        "freeze_records",
        "person_id = ? AND agency_id = ?",
        (person_id, agency_id),
        payload,
    )
    assignments = ", ".join(f"{c} = ?" for c in payload)
    conn.execute(
        f"UPDATE freeze_records SET {assignments}, updated_at = ? "
        "WHERE person_id = ? AND agency_id = ?",
        (*payload.values(), utcnow(), person_id, agency_id),
    )
    conn.commit()


def set_freeze_status(
    conn: sqlite3.Connection, person_id: int, agency_id: int, status: str
) -> None:
    """Quick status toggle from the matrix, without touching the other fields."""
    today = date.today().isoformat()
    if status == STATUS_ACTIVE:
        conn.execute(
            "UPDATE freeze_records SET status = ?, "
            "date_confirmed = COALESCE(date_confirmed, ?), last_verified = ?, "
            "updated_at = ? WHERE person_id = ? AND agency_id = ?",
            (status, today, today, utcnow(), person_id, agency_id),
        )
    else:
        conn.execute(
            "UPDATE freeze_records SET status = ?, updated_at = ? "
            "WHERE person_id = ? AND agency_id = ?",
            (status, utcnow(), person_id, agency_id),
        )
    conn.commit()


# ------------------------------------------------------------------ reminders


@dataclass
class Reminder:
    id: int
    person_id: int | None
    title: str
    detail: str
    due_date: str
    recurrence: str
    kind: str = "custom"
    last_completed: str | None = None
    is_active: bool = True
    person_name: str | None = None

    @property
    def is_overdue(self) -> bool:
        try:
            return date.fromisoformat(self.due_date) < date.today()
        except ValueError:
            return False

    @property
    def is_soon(self) -> bool:
        try:
            due = date.fromisoformat(self.due_date)
        except ValueError:
            return False
        return date.today() <= due <= date.today() + timedelta(days=30)


_RECURRENCE_DAYS = {"yearly": 365, "quarterly": 91, "monthly": 30, "weekly": 7}


def seed_reminders_for(
    conn: sqlite3.Connection, vault: Vault, person_id: int, kind: str
) -> None:
    today = date.today()
    for template in REMINDER_TEMPLATES:
        if template.get("adults_only") and kind != "adult":
            continue
        if template.get("minors_only") and kind != "minor":
            continue
        exists = conn.execute(
            "SELECT 1 FROM reminders WHERE person_id = ? AND kind = ?",
            (person_id, template["kind"]),
        ).fetchone()
        if exists:
            continue
        due = today + timedelta(days=int(template["offset_days"]))
        # title/detail explicitly '' — a vault upgraded from a pre-encryption
        # schema still has those columns as NOT NULL with no default, so an
        # insert that omits them fails (this is what 500'd when adding a person).
        conn.execute(
            "INSERT INTO reminders (person_id, kind, title, detail, title_enc, "
            "detail_enc, due_date, recurrence, created_at) "
            "VALUES (?, ?, '', '', ?, ?, ?, ?, ?)",
            (
                person_id,
                template["kind"],
                vault.encrypt(context_for("reminders", "title_enc"), template["title"]),
                vault.encrypt(
                    context_for("reminders", "detail_enc"), template["detail"]
                ),
                due.isoformat(),
                template["recurrence"],
                utcnow(),
            ),
        )
    conn.commit()


def list_reminders(
    conn: sqlite3.Connection, vault: Vault, include_inactive: bool = False
) -> list[Reminder]:
    where = "" if include_inactive else "WHERE is_active = 1"
    rows = conn.execute(f"SELECT * FROM reminders {where} ORDER BY due_date").fetchall()
    names = {p.id: p.display_name for p in list_people(conn, vault)}
    return [
        Reminder(
            id=row["id"],
            person_id=row["person_id"],
            title=vault.decrypt(context_for("reminders", "title_enc"), row["title_enc"])
            or row["title"]
            or "",
            detail=vault.decrypt(
                context_for("reminders", "detail_enc"), row["detail_enc"]
            )
            or row["detail"]
            or "",
            due_date=row["due_date"],
            recurrence=row["recurrence"],
            kind=row["kind"],
            last_completed=row["last_completed"],
            is_active=bool(row["is_active"]),
            person_name=names.get(row["person_id"]),
        )
        for row in rows
    ]


def create_reminder(
    conn: sqlite3.Connection,
    vault: Vault,
    *,
    title: str,
    due_date: str,
    detail: str = "",
    recurrence: str = "none",
    person_id: int | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO reminders (person_id, kind, title, detail, title_enc, "
        "detail_enc, due_date, recurrence, created_at) "
        "VALUES (?, 'custom', '', '', ?, ?, ?, ?, ?)",
        (
            person_id,
            vault.encrypt(context_for("reminders", "title_enc"), title),
            vault.encrypt(context_for("reminders", "detail_enc"), detail),
            due_date,
            recurrence,
            utcnow(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def complete_reminder(conn: sqlite3.Connection, reminder_id: int) -> None:
    """Mark done. Recurring reminders roll forward; one-offs deactivate."""
    row = conn.execute(
        "SELECT recurrence, due_date FROM reminders WHERE id = ?", (reminder_id,)
    ).fetchone()
    if row is None:
        return
    today = date.today()
    interval = _RECURRENCE_DAYS.get(row["recurrence"])
    if interval:
        conn.execute(
            "UPDATE reminders SET last_completed = ?, due_date = ? WHERE id = ?",
            (today.isoformat(), (today + timedelta(days=interval)).isoformat(), reminder_id),
        )
    else:
        conn.execute(
            "UPDATE reminders SET last_completed = ?, is_active = 0 WHERE id = ?",
            (today.isoformat(), reminder_id),
        )
    conn.commit()


def delete_reminder(conn: sqlite3.Connection, reminder_id: int) -> None:
    conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()


# -------------------------------------------------------------------- reports


@dataclass
class StoredReport:
    id: int
    person_id: int
    bureau: str
    pulled_on: str
    source_name: str
    text: str | None = None
    extracted: dict[str, Any] = field(default_factory=dict)
    person_name: str | None = None


def save_report(
    conn: sqlite3.Connection,
    vault: Vault,
    *,
    person_id: int,
    bureau: str,
    pulled_on: str,
    source_name: str,
    text: str,
    extracted: dict[str, Any],
) -> int:
    cursor = conn.execute(
        "INSERT INTO reports (person_id, bureau, pulled_on, source_name_enc, "
        "text_enc, extracted_enc, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            person_id,
            bureau,
            pulled_on,
            vault.encrypt(context_for("reports", "source_name_enc"), source_name),
            vault.encrypt(context_for("reports", "text_enc"), text),
            vault.encrypt(
                context_for("reports", "extracted_enc"), json.dumps(extracted)
            ),
            utcnow(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _row_to_report(vault: Vault, row: sqlite3.Row, with_text: bool) -> StoredReport:
    raw = vault.decrypt(context_for("reports", "extracted_enc"), row["extracted_enc"])
    return StoredReport(
        id=row["id"],
        person_id=row["person_id"],
        bureau=row["bureau"],
        pulled_on=row["pulled_on"],
        source_name=vault.decrypt(
            context_for("reports", "source_name_enc"), row["source_name_enc"]
        )
        or row["source_name"]
        or "",
        text=(
            vault.decrypt(context_for("reports", "text_enc"), row["text_enc"])
            if with_text
            else None
        ),
        extracted=json.loads(raw) if raw else {},
    )


def list_reports(
    conn: sqlite3.Connection, vault: Vault, person_id: int | None = None
) -> list[StoredReport]:
    if person_id is None:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY pulled_on DESC, id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reports WHERE person_id = ? ORDER BY pulled_on DESC, id DESC",
            (person_id,),
        ).fetchall()
    names = {p.id: p.display_name for p in list_people(conn, vault)}
    reports = [_row_to_report(vault, row, with_text=False) for row in rows]
    for report in reports:
        report.person_name = names.get(report.person_id)
    return reports


def get_report(
    conn: sqlite3.Connection, vault: Vault, report_id: int
) -> StoredReport | None:
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return _row_to_report(vault, row, with_text=True) if row else None


def previous_report(
    conn: sqlite3.Connection, vault: Vault, report: StoredReport
) -> StoredReport | None:
    """The most recent earlier pull for the same person and bureau."""
    row = conn.execute(
        "SELECT * FROM reports WHERE person_id = ? AND bureau = ? AND id < ? "
        "ORDER BY id DESC LIMIT 1",
        (report.person_id, report.bureau, report.id),
    ).fetchone()
    return _row_to_report(vault, row, with_text=True) if row else None


def delete_report(conn: sqlite3.Connection, report_id: int) -> None:
    conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.commit()


# ------------------------------------------------------------ breach tracking


@dataclass
class BreachCheck:
    id: int
    person_id: int | None
    email: str | None
    checked_at: str
    source: str
    result: dict[str, Any]
    person_name: str | None = None


def save_breach_check(
    conn: sqlite3.Connection,
    vault: Vault,
    *,
    person_id: int | None,
    email: str,
    source: str,
    result: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO breach_checks (person_id, email_enc, checked_at, source, "
        "result_enc) VALUES (?, ?, ?, ?, ?)",
        (
            person_id,
            vault.encrypt(context_for("breach_checks", "email_enc"), email),
            utcnow(),
            source,
            vault.encrypt(
                context_for("breach_checks", "result_enc"), json.dumps(result)
            ),
        ),
    )
    conn.commit()


def list_breach_checks(
    conn: sqlite3.Connection, vault: Vault, limit: int = 50
) -> list[BreachCheck]:
    rows = conn.execute(
        "SELECT * FROM breach_checks ORDER BY checked_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    names = {p.id: p.display_name for p in list_people(conn, vault)}
    checks = []
    for row in rows:
        raw = vault.decrypt(
            context_for("breach_checks", "result_enc"), row["result_enc"]
        )
        checks.append(
            BreachCheck(
                id=row["id"],
                person_id=row["person_id"],
                email=vault.decrypt(
                    context_for("breach_checks", "email_enc"), row["email_enc"]
                ),
                checked_at=row["checked_at"],
                source=row["source"],
                result=json.loads(raw) if raw else {},
                person_name=names.get(row["person_id"]),
            )
        )
    return checks


# ------------------------------------------------------------------- settings


def get_setting(conn: sqlite3.Connection, vault: Vault, key: str) -> str | None:
    row = conn.execute(
        "SELECT value_enc FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    return vault.decrypt(context_for("app_settings", "value_enc"), row["value_enc"])


def set_setting(
    conn: sqlite3.Connection, vault: Vault, key: str, value: str | None
) -> None:
    if value is None or value == "":
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    else:
        conn.execute(
            "INSERT INTO app_settings (key, value_enc) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_enc = excluded.value_enc",
            (key, vault.encrypt(context_for("app_settings", "value_enc"), value)),
        )
    conn.commit()


# ------------------------------------------------------------------- rollups


@dataclass
class Progress:
    done: int
    total: int

    @property
    def percent(self) -> int:
        return round(100 * self.done / self.total) if self.total else 0


def household_progress(
    conn: sqlite3.Connection,
    people: Iterable[Person],
    agencies: Iterable[Agency],
    matrix: dict[int, dict[int, FreezeRecord]],
) -> Progress:
    # FYI-only rows carry no task, so counting them would make the meter
    # unreachable and teach people the number is meaningless.
    agency_list = [a for a in agencies if not a.is_fyi]
    done = total = 0
    for person in people:
        for agency in agency_list:
            record = matrix.get(person.id, {}).get(agency.id)
            if record is None:
                total += 1
                continue
            if record.status == "not_applicable":
                continue
            total += 1
            if record.is_done:
                done += 1
    return Progress(done=done, total=total)
