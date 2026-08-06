"""Audit fix: reminder title/detail and report filenames must be encrypted at rest."""

from __future__ import annotations

from conftest import add_person, csrf_token


def test_reminder_text_is_encrypted_on_disk(unlocked, settings):
    add_person(unlocked, "Parent")
    unlocked.post(
        "/reminders",
        data={
            "title": "Thaw Experian for Jordan PIN 4821",
            "due_date": "2026-09-01",
            "detail": "Marcus passport SECRETDETAIL9",
            "recurrence": "none",
            "csrf_token": csrf_token(unlocked),
        },
    )
    # Round-trips through the UI...
    page = unlocked.get("/reminders").text
    assert "Thaw Experian for Jordan PIN 4821" in page
    assert "SECRETDETAIL9" in page

    # ...but never appears in cleartext in the database file.
    raw = settings.db_path.read_bytes()
    assert b"Thaw Experian for Jordan PIN 4821" not in raw
    assert b"SECRETDETAIL9" not in raw
    assert b"4821" not in raw


def test_seeded_reminder_titles_are_encrypted(unlocked, settings):
    add_person(unlocked, "Seeded Person")
    # Seeded reminders (e.g. the IRS IP PIN one) exist and render...
    assert "IRS IP PIN" in unlocked.get("/reminders").text
    # ...but their titles are not in the clear on disk.
    assert b"IRS IP PIN" not in settings.db_path.read_bytes()


def test_report_filename_is_encrypted_on_disk(unlocked, settings):
    person = add_person(unlocked, "Report Person")
    unlocked.post(
        "/reports",
        data={
            "person_id": person,
            "bureau": "Equifax",
            "pulled_on": "2026-03-01",
            "csrf_token": csrf_token(unlocked),
        },
        files={
            "upload": (
                "Experian_CreditReport_MarcusRiveraJr.txt",
                b"ACCOUNTS\nFIRST BANK\n",
                "text/plain",
            )
        },
    )
    assert "Experian_CreditReport_MarcusRiveraJr" in unlocked.get("/reports").text
    assert b"MarcusRiveraJr" not in settings.db_path.read_bytes()


def test_oversized_upload_rejected_before_parsing(unlocked):
    person = add_person(unlocked, "Big Upload")
    # Declare a body far over the cap; the middleware rejects on Content-Length
    # before the multipart parser could spool anything to disk.
    response = unlocked.post(
        "/reports",
        data={
            "person_id": str(person),
            "bureau": "Equifax",
            "pulled_on": "2026-03-01",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("big.txt", b"x", "text/plain")},
        headers={"content-length": str(40 * 1024 * 1024)},
    )
    assert response.status_code == 303
    assert "too+large" in response.headers["location"]


def test_multipart_spool_threshold_exceeds_cap(unlocked):
    # The guarantee behind "never written to a temp file": Starlette only
    # spools to disk past this threshold, which must sit above the accept cap.
    import starlette.formparsers

    from frostfile.routes.reports import MAX_UPLOAD_BYTES

    assert starlette.formparsers.MultiPartParser.spool_max_size > MAX_UPLOAD_BYTES


def test_legacy_plaintext_reminder_is_migrated_on_unlock(unlocked, settings):
    from frostfile import db

    add_person(unlocked, "Legacy Owner")
    conn = db.connect(settings.db_path)
    try:
        # Simulate a pre-0.3 row: plaintext title, no encrypted column.
        conn.execute(
            "INSERT INTO reminders (person_id, kind, title, detail, due_date, "
            "recurrence, created_at) VALUES (NULL, 'custom', ?, ?, '2026-10-01', "
            "'none', '2026-01-01T00:00:00+00:00')",
            ("Legacy PLAINTITLE7", "Legacy PLAINDETAIL8"),
        )
        conn.commit()
    finally:
        conn.close()

    # Plaintext is on disk before migration.
    assert b"PLAINTITLE7" in settings.db_path.read_bytes()

    # Re-unlock triggers migration.
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    unlocked.post(
        "/unlock", data={"passphrase": "correct horse battery staple", "next": "/"}
    )

    page = unlocked.get("/reminders").text
    assert "Legacy PLAINTITLE7" in page  # still readable
    raw = settings.db_path.read_bytes()
    assert b"PLAINTITLE7" not in raw  # but no longer plaintext
    assert b"PLAINDETAIL8" not in raw
