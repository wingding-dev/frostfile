from __future__ import annotations

from conftest import PASSPHRASE, add_person, csrf_token


def test_first_run_redirects_to_setup(client):
    assert client.get("/").headers["location"].startswith("/unlock")
    assert client.get("/unlock").headers["location"] == "/setup"
    assert client.get("/setup").status_code == 200


def test_setup_requires_matching_acknowledged_passphrase(client):
    response = client.post(
        "/setup",
        data={"passphrase": "a strong passphrase", "confirm": "different", "acknowledged": "1"},
    )
    assert response.status_code == 200
    assert "do not match" in response.text

    response = client.post(
        "/setup",
        data={"passphrase": "a strong passphrase", "confirm": "a strong passphrase"},
    )
    assert "cannot be recovered" in response.text


def test_locked_pages_redirect_to_unlock(unlocked):
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    response = unlocked.get("/matrix")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/unlock")


def test_unlock_rejects_wrong_passphrase(unlocked):
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    response = unlocked.post("/unlock", data={"passphrase": "nope", "next": "/"})
    assert response.status_code == 200
    assert "did not open the vault" in response.text

    response = unlocked.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    assert response.status_code == 303


def test_unlock_next_cannot_redirect_offsite(unlocked):
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    response = unlocked.post(
        "/unlock", data={"passphrase": PASSPHRASE, "next": "//evil.example.com"}
    )
    assert response.headers["location"] == "/"


def test_csrf_is_enforced_on_mutations(unlocked):
    response = unlocked.post(
        "/people", data={"display_name": "No Token", "kind": "adult"}
    )
    assert response.status_code == 400


def test_add_person_seeds_matrix_and_reminders(unlocked):
    person_id = add_person(unlocked, "Alex Adult")

    matrix = unlocked.get("/matrix")
    assert matrix.status_code == 200
    assert "Alex Adult" in matrix.text
    assert "Equifax" in matrix.text
    assert "ChexSystems" in matrix.text

    reminders = unlocked.get("/reminders")
    assert "IRS IP PIN" in reminders.text
    assert "Social Security earnings" in reminders.text

    detail = unlocked.get(f"/people/{person_id}")
    assert detail.status_code == 200


def test_minor_gets_child_specific_reminder(unlocked):
    add_person(unlocked, "Robin Child", kind="minor")
    reminders = unlocked.get("/reminders").text
    assert "credit file exists for this child" in reminders
    # The adult-only items should not be attached to a child.
    assert "Social Security earnings" not in reminders


def test_full_ssn_is_opt_in(unlocked):
    person_id = add_person(unlocked, "Opt Out", ssn="123456789")
    page = unlocked.get(f"/people/{person_id}").text
    assert "full number stored" not in page

    person_id = add_person(
        unlocked, "Opt In", ssn="123456789", store_full_ssn="1"
    )
    page = unlocked.get(f"/people/{person_id}").text
    assert "full number stored" in page
    # The last four are derived even though only the full number was supplied.
    assert "6789" in page


def test_quick_status_change_records_confirmation_date(unlocked):
    person_id = add_person(unlocked, "Grid User")
    agency_id = _agency_id(unlocked, "Equifax")

    response = unlocked.post(
        "/matrix/quick",
        data={
            "person_id": person_id,
            "agency_id": agency_id,
            "status": "active",
            "back": "/matrix",
            "csrf_token": csrf_token(unlocked),
        },
    )
    assert response.status_code == 303
    detail = unlocked.get(f"/freeze/{person_id}/{agency_id}").text
    assert 'value="active" selected' in detail.replace("'", '"')


def test_quick_status_rejects_unknown_status(unlocked):
    person_id = add_person(unlocked, "Grid User")
    response = unlocked.post(
        "/matrix/quick",
        data={
            "person_id": person_id,
            "agency_id": _agency_id(unlocked, "Equifax"),
            "status": "definitely_not_a_status",
            "csrf_token": csrf_token(unlocked),
        },
    )
    assert response.status_code == 400


def test_freeze_pin_round_trips_and_is_encrypted_on_disk(unlocked, settings):
    person_id = add_person(unlocked, "PIN Holder")
    agency_id = _agency_id(unlocked, "Equifax")

    unlocked.post(
        f"/freeze/{person_id}/{agency_id}",
        data={
            "status": "active",
            "method": "online",
            "pin": "SUPERSECRETPIN42",
            "confirmation": "CONF-99887766",
            "csrf_token": csrf_token(unlocked),
        },
    )
    page = unlocked.get(f"/freeze/{person_id}/{agency_id}").text
    assert "SUPERSECRETPIN42" in page
    assert "CONF-99887766" in page

    raw = settings.db_path.read_bytes()
    assert b"SUPERSECRETPIN42" not in raw
    assert b"CONF-99887766" not in raw
    assert b"PIN Holder" not in raw


def _agency_id(client, name: str) -> int:
    """Find an agency's id by scraping the directory page."""
    import re

    page = client.get("/agencies").text
    for match in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', page):
        if match.group(2).strip() == name:
            return int(match.group(1))
    raise AssertionError(f"agency {name!r} not found")
