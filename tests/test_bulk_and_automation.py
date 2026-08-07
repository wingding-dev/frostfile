"""Bulk packet printing and the automation pass: mark-as-mailed, auto-backup,
check-everyone."""

from __future__ import annotations

import re
from datetime import date

from conftest import PASSPHRASE, add_person, csrf_token


def _agency_id(client, name: str) -> int:
    page = client.get("/agencies").text
    for match in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', page):
        if match.group(2).strip() == name:
            return int(match.group(1))
    raise AssertionError(f"agency {name!r} not found")


def test_print_all_renders_every_packet(unlocked):
    add_person(unlocked, "Dana Guardian", address="12 Elm St\nSpringfield, IL 62704")
    add_person(unlocked, "Robin Child", kind="minor")
    add_person(unlocked, "Sam Child", kind="minor")

    page = unlocked.get("/letters/all")
    assert page.status_code == 200
    # Two children x every mailable agency; each packet names its child.
    assert page.text.count("Robin Child, a minor") >= 4
    assert page.text.count("Sam Child, a minor") >= 4
    # The title doubles as the suggested PDF filename.
    assert f"Freeze packets - all children - {date.today().isoformat()}" in page.text


def test_print_all_with_no_children_redirects_back(unlocked):
    add_person(unlocked, "Only Adult")
    response = unlocked.get("/letters/all")
    assert response.status_code == 303
    assert response.headers["location"] == "/letters"


def test_pdf_zip_contains_one_named_pdf_per_packet(unlocked):
    import io
    import zipfile

    add_person(unlocked, "Dana Guardian", address="12 Elm St\nSpringfield, IL 62704")
    add_person(unlocked, "Robin Child", kind="minor")

    response = unlocked.get("/letters/all.zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert any(n == "Equifax freeze packet - Robin Child.pdf" for n in names)
    assert len(names) >= 4  # one per mailable agency
    for name in names:
        assert archive.read(name)[:5] == b"%PDF-"


def test_pdf_packet_carries_source_provenance(unlocked):
    from frostfile import db
    from frostfile.repo import get_agency, get_person, list_people
    from frostfile.services import pdfletters

    add_person(unlocked, "Dana Guardian", address="1 A St\nTown, TX 75001")
    child = add_person(unlocked, "Robin Child", kind="minor")
    equifax = _agency_id(unlocked, "Equifax")

    # Build the PDF directly and read its text back to confirm provenance shows.
    import pypdf

    from conftest import PASSPHRASE  # noqa

    import io

    # Pull objects via a fresh connection using the test's unlocked vault path.
    # Simpler: hit the route and extract text from the returned PDF.
    resp = unlocked.get(f"/letters/{child}/{equifax}")
    assert resp.status_code == 200
    # And the downloadable zip PDF must contain the provenance block.
    import zipfile

    zresp = unlocked.get("/letters/all.zip")
    archive = zipfile.ZipFile(io.BytesIO(zresp.content))
    name = next(n for n in archive.namelist() if "Equifax" in n and "Robin" in n)
    reader = pypdf.PdfReader(io.BytesIO(archive.read(name)))
    text = "".join(page.extract_text() for page in reader.pages)
    assert "Where these details came from" in text


def test_pdf_zip_without_children_redirects(unlocked):
    add_person(unlocked, "Only Adult")
    response = unlocked.get("/letters/all.zip")
    assert response.status_code == 303


def test_mark_mailed_fills_the_record(unlocked):
    add_person(unlocked, "Dana Guardian")
    child = add_person(unlocked, "Robin Child", kind="minor")
    agency = _agency_id(unlocked, "Equifax")

    response = unlocked.post(
        f"/letters/{child}/{agency}/mailed",
        data={"csrf_token": csrf_token(unlocked)},
    )
    assert response.status_code == 303

    detail = unlocked.get(f"/freeze/{child}/{agency}").text.replace("'", '"')
    assert 'value="in_progress" selected' in detail
    assert date.today().isoformat() in detail


def test_mark_all_mailed_covers_every_mailable_agency(unlocked):
    add_person(unlocked, "Dana Guardian")
    child = add_person(unlocked, "Robin Child", kind="minor")

    response = unlocked.post(
        "/letters/all/mailed", data={"csrf_token": csrf_token(unlocked)}
    )
    assert response.status_code == 303

    for name in ("Equifax", "Experian", "TransUnion", "ChexSystems"):
        agency = _agency_id(unlocked, name)
        detail = unlocked.get(f"/freeze/{child}/{agency}").text.replace("'", '"')
        assert 'value="in_progress" selected' in detail, name


def test_unlock_makes_a_weekly_auto_backup(unlocked, settings):
    add_person(unlocked, "Backup Person")
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})

    unlocked.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    autos = list(settings.backup_dir.glob("frostfile-auto-*.db"))
    assert len(autos) == 1

    # A second unlock inside the week does not stack up more copies.
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    unlocked.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    assert len(list(settings.backup_dir.glob("frostfile-auto-*.db"))) == 1


def test_breaches_page_lists_family_emails_for_manual_checking(unlocked):
    # Zero-network rule: the page never checks anything itself — it lists the
    # family's emails and links out to HIBP for the user to check in a browser.
    add_person(unlocked, "Has Email", email="someone@example.com")
    page = unlocked.get("/breaches").text
    assert "someone@example.com" in page
    assert "haveibeenpwned.com" in page
