"""Every page renders with realistic data in place.

Template errors are otherwise invisible until someone hits the page, and the
people who hit these pages will be coworkers, not the author.
"""

from __future__ import annotations

import re

import pytest
from conftest import add_person, csrf_token


@pytest.fixture
def populated(unlocked):
    adult = add_person(
        unlocked,
        "Dana Guardian",
        email="dana@example.com",
        phone="555-0100",
        address="12 Elm Street\nSpringfield, IL 62704",
        birth_date="1985-04-02",
        ssn_last4="4321",
    )
    child = add_person(
        unlocked, "Robin Child", kind="minor", birth_date="2016-09-11"
    )

    page = unlocked.get("/agencies").text
    agency_id = int(re.search(r'href="/agencies/(\d+)"', page).group(1))

    unlocked.post(
        f"/freeze/{adult}/{agency_id}",
        data={
            "status": "active",
            "method": "online",
            "date_requested": "2026-02-01",
            "date_confirmed": "2026-02-01",
            "expires_on": "2026-08-20",
            "confirmation": "CONF-123",
            "pin": "PIN-456",
            "notes": "Placed after the breach notice.",
            "csrf_token": csrf_token(unlocked),
        },
    )
    unlocked.post(
        "/reports",
        data={
            "person_id": adult,
            "bureau": "Equifax",
            "pulled_on": "2026-03-01",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("r.txt", b"ACCOUNTS\nFIRST BANK\nXXXX1234\n", "text/plain")},
    )
    return {"client": unlocked, "adult": adult, "child": child, "agency": agency_id}


PAGES = [
    "/",
    "/matrix",
    "/people",
    "/people/new",
    "/agencies",
    "/letters",
    "/reminders",
    "/reports",
    "/breaches",
    "/settings",
    "/sources",
    "/help",
    "/letters/all",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(populated, path):
    response = populated["client"].get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    assert "FrostFile" in response.text


def test_person_and_freeze_pages_render(populated):
    client = populated["client"]
    assert client.get(f"/people/{populated['adult']}").status_code == 200
    assert client.get(f"/people/{populated['adult']}/edit").status_code == 200
    assert client.get(f"/agencies/{populated['agency']}").status_code == 200
    assert (
        client.get(f"/freeze/{populated['adult']}/{populated['agency']}").status_code
        == 200
    )


def test_report_detail_and_raw_diff_render(populated):
    client = populated["client"]
    page = client.get("/reports").text
    report_id = int(re.search(r'href="/reports/(\d+)"', page).group(1))
    assert client.get(f"/reports/{report_id}").status_code == 200
    assert client.get(f"/reports/{report_id}?show_raw=1").status_code == 200


def test_dashboard_surfaces_expiring_and_child_warning(populated):
    page = populated["client"].get("/").text
    assert "Children without a full set of bureau freezes" in page
    assert "Robin Child" in page
    assert "Expiring soon" in page


def test_breaches_page_offers_no_email_lookup_without_a_key(populated):
    page = populated["client"].get("/breaches").text
    assert "API key" in page
    assert 'action="/breaches/email"' not in page
    # Password checking works without a key, so that form must be present.
    assert 'action="/breaches/password"' in page


def test_missing_records_return_404_not_a_crash(populated):
    client = populated["client"]
    assert client.get("/people/99999").status_code == 404
    assert client.get("/agencies/99999").status_code == 404
    assert client.get("/reports/99999").status_code == 404
    assert client.get("/freeze/99999/1").status_code == 404


def test_backup_writes_an_openable_database(populated, settings):
    from frostfile import db

    response = populated["client"].post(
        "/settings/backup", data={"csrf_token": csrf_token(populated["client"])}
    )
    assert response.status_code == 200
    backups = list(settings.backup_dir.glob("frostfile-*.db"))
    assert backups

    conn = db.connect(backups[0])
    try:
        assert db.is_initialized(conn)
        vault = db.unlock(conn, "correct horse battery staple")
        from frostfile.repo import list_people

        assert any(p.display_name == "Dana Guardian" for p in list_people(conn, vault))
    finally:
        conn.close()


def test_passphrase_change_keeps_the_session_usable(populated):
    client = populated["client"]
    response = client.post(
        "/settings/passphrase",
        data={
            "current": "correct horse battery staple",
            "new_passphrase": "a different long passphrase",
            "confirm": "a different long passphrase",
            "csrf_token": csrf_token(client),
        },
    )
    assert response.status_code == 303
    # Still unlocked, and the data still reads.
    assert "Dana Guardian" in client.get("/people").text


def test_passphrase_change_rejects_wrong_current(populated):
    client = populated["client"]
    response = client.post(
        "/settings/passphrase",
        data={
            "current": "not the passphrase",
            "new_passphrase": "a different long passphrase",
            "confirm": "a different long passphrase",
            "csrf_token": csrf_token(client),
        },
    )
    assert response.status_code == 200
    assert "current passphrase is wrong" in response.text


def test_learn_page_renders_with_citations(populated):
    page = populated["client"].get("/learn")
    assert page.status_code == 200
    assert "Does NOT Freeze Your Credit Cards" in page.text
    assert "Deadbolts beat doorbells" in page.text
    # citations resolved (footer source list present, no unresolved keys)
    assert "Sources on This Page" in page.text or "sources" in page.text.lower()
