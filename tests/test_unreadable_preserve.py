"""Audit fix: a corrupt-but-present ciphertext must not be nulled by the next save."""

from __future__ import annotations

from conftest import add_person, csrf_token


def _agency_id(client, name="Equifax"):
    import re

    page = client.get("/agencies").text
    for m in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', page):
        if m.group(2).strip() == name:
            return int(m.group(1))
    raise AssertionError(name)


def test_corrupt_pin_is_preserved_not_destroyed_on_save(unlocked, settings):
    from identilock import db

    person = add_person(unlocked, "PIN Owner")
    agency = _agency_id(unlocked)
    unlocked.post(
        f"/freeze/{person}/{agency}",
        data={
            "status": "active",
            "pin": "REALPIN123",
            "csrf_token": csrf_token(unlocked),
        },
    )

    # Corrupt the stored pin ciphertext, as a bad sync or partial restore would.
    conn = db.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT pin_enc FROM freeze_records WHERE person_id=? AND agency_id=?",
            (person, agency),
        ).fetchone()
        corrupted = bytes(b ^ 0xFF for b in row["pin_enc"][:8]) + row["pin_enc"][8:]
        conn.execute(
            "UPDATE freeze_records SET pin_enc=? WHERE person_id=? AND agency_id=?",
            (corrupted, person, agency),
        )
        conn.commit()
        stored_after_corruption = conn.execute(
            "SELECT pin_enc FROM freeze_records WHERE person_id=? AND agency_id=?",
            (person, agency),
        ).fetchone()["pin_enc"]
    finally:
        conn.close()

    # The page shows a blank PIN (can't decrypt). The user edits something else
    # and saves, submitting an empty pin field.
    unlocked.post(
        f"/freeze/{person}/{agency}",
        data={
            "status": "active",
            "pin": "",  # blank, because it rendered blank
            "notes": "adding a note",
            "csrf_token": csrf_token(unlocked),
        },
    )

    # The corrupt ciphertext is PRESERVED, not overwritten with NULL — so a good
    # backup could still recover it.
    conn = db.connect(settings.db_path)
    try:
        after = conn.execute(
            "SELECT pin_enc, notes_enc FROM freeze_records "
            "WHERE person_id=? AND agency_id=?",
            (person, agency),
        ).fetchone()
    finally:
        conn.close()
    assert after["pin_enc"] == stored_after_corruption  # kept, not nulled
    assert after["notes_enc"] is not None  # the real edit still applied


def test_blank_field_still_clears_when_readable(unlocked, settings):
    # Ensure the guard doesn't block legitimate clearing of a readable field.
    person = add_person(unlocked, "Clearable")
    agency = _agency_id(unlocked)
    unlocked.post(
        f"/freeze/{person}/{agency}",
        data={"status": "active", "pin": "PINTOCLEAR", "csrf_token": csrf_token(unlocked)},
    )
    unlocked.post(
        f"/freeze/{person}/{agency}",
        data={"status": "active", "pin": "", "csrf_token": csrf_token(unlocked)},
    )
    page = unlocked.get(f"/freeze/{person}/{agency}").text
    assert "PINTOCLEAR" not in page
