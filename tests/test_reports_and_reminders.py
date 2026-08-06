from __future__ import annotations

from conftest import add_person, csrf_token

from frostfile.services.reportdiff import compare, extract_entities, normalize

REPORT_V1 = """
CREDIT REPORT
Prepared for JOHN Q SAMPLE

PERSONAL INFORMATION
Addresses
120 MAPLE STREET
SPRINGFIELD IL 62704

ACCOUNTS
FIRST NATIONAL BANK
Account XXXX4821
Balance $2,300

INQUIRIES
CAPITAL FUNDING CORP
03/14/2026

EMPLOYERS
ACME MANUFACTURING CO
"""

REPORT_V2 = """
CREDIT REPORT
Prepared for JOHN Q SAMPLE

PERSONAL INFORMATION
Addresses
120 MAPLE STREET
SPRINGFIELD IL 62704
9987 UNKNOWN AVENUE
RENO NV 89501

ACCOUNTS
FIRST NATIONAL BANK
Account XXXX4821
Balance $2,300
QUICKCASH LENDING LLC
Account XXXX7733
Balance $900

INQUIRIES
CAPITAL FUNDING CORP
03/14/2026
QUICKCASH LENDING LLC
07/02/2026

EMPLOYERS
ACME MANUFACTURING CO
"""


def test_extracts_accounts_addresses_and_inquiries():
    found = extract_entities(REPORT_V1)
    assert any("4821" in account for account in found.accounts)
    assert any("MAPLE" in address.upper() for address in found.addresses)
    assert any("CAPITAL FUNDING" in item for item in found.inquiries)


def test_compare_surfaces_new_account_and_address():
    before = extract_entities(REPORT_V1).as_dict()
    after = extract_entities(REPORT_V2).as_dict()
    result = compare(before, after, REPORT_V1, REPORT_V2)

    assert result.has_changes
    added = {item for delta in result.deltas for item in delta.added}
    assert any("7733" in item for item in added)
    assert any("UNKNOWN AVENUE" in item.upper() for item in added)

    # The line diff is the authoritative view and should carry the new lender.
    added_lines = [line for kind, line in result.line_diff if kind == "add"]
    assert any("QUICKCASH" in line for line in added_lines)


def test_identical_pulls_report_no_changes():
    extracted = extract_entities(REPORT_V1).as_dict()
    result = compare(extracted, extracted, REPORT_V1, REPORT_V1)
    assert not result.has_changes
    assert result.added_count == 0


def test_first_pull_has_nothing_to_compare():
    result = compare(None, extract_entities(REPORT_V1).as_dict())
    assert result.only_one_pull
    assert not result.has_changes


def test_normalize_collapses_whitespace():
    assert normalize("  a   b  \n\n\n  c ") == ["a b", "c"]


def test_upload_and_compare_two_pulls(unlocked):
    person_id = add_person(unlocked, "Report Owner")

    first = unlocked.post(
        "/reports",
        data={
            "person_id": person_id,
            "bureau": "Equifax",
            "pulled_on": "2026-01-15",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("report1.txt", REPORT_V1.encode(), "text/plain")},
    )
    assert first.status_code == 303
    page = unlocked.get(first.headers["location"]).text
    assert "first saved report" in page

    second = unlocked.post(
        "/reports",
        data={
            "person_id": person_id,
            "bureau": "Equifax",
            "pulled_on": "2026-07-15",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("report2.txt", REPORT_V2.encode(), "text/plain")},
    )
    page = unlocked.get(second.headers["location"]).text
    assert "new item" in page
    assert "7733" in page


def test_report_text_is_encrypted_at_rest(unlocked, settings):
    person_id = add_person(unlocked, "Report Owner")
    unlocked.post(
        "/reports",
        data={
            "person_id": person_id,
            "bureau": "Equifax",
            "pulled_on": "2026-01-15",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("r.txt", REPORT_V1.encode(), "text/plain")},
    )
    raw = settings.db_path.read_bytes()
    assert b"FIRST NATIONAL BANK" not in raw
    assert b"JOHN Q SAMPLE" not in raw


def test_empty_upload_is_rejected(unlocked):
    person_id = add_person(unlocked, "Report Owner")
    response = unlocked.post(
        "/reports",
        data={
            "person_id": person_id,
            "bureau": "Equifax",
            "pulled_on": "2026-01-15",
            "csrf_token": csrf_token(unlocked),
        },
        files={"upload": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 303
    assert "error" in response.headers["location"]


def test_reminder_completion_rolls_recurring_forward(unlocked):
    import re

    add_person(unlocked, "Alex Adult")
    page = unlocked.get("/reminders").text
    reminder_id = int(re.search(r"/reminders/(\d+)/complete", page).group(1))

    before = unlocked.get("/reminders").text
    unlocked.post(
        f"/reminders/{reminder_id}/complete",
        data={"csrf_token": csrf_token(unlocked)},
    )
    after = unlocked.get("/reminders").text
    # Still present (it recurs), but with a later due date.
    assert f"/reminders/{reminder_id}/complete" in after
    assert before != after


def test_ics_export_is_wellformed(unlocked):
    add_person(unlocked, "Alex Adult")
    response = unlocked.get("/reminders.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")

    body = response.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert body.rstrip().endswith("END:VCALENDAR")
    assert body.count("BEGIN:VEVENT") == body.count("END:VEVENT")
    assert body.count("BEGIN:VEVENT") > 0
    assert "RRULE:FREQ=YEARLY" in body
    assert "Alex Adult" in body
    # Every line must be CRLF-terminated per RFC 5545.
    assert "\r\n" in body
    assert not any(len(line.encode()) > 75 for line in body.split("\r\n"))


def test_custom_reminder_can_be_added_and_deleted(unlocked):
    import re

    response = unlocked.post(
        "/reminders",
        data={
            "title": "Call the carrier about a port-out PIN",
            "due_date": "2026-12-01",
            "recurrence": "yearly",
            "csrf_token": csrf_token(unlocked),
        },
    )
    assert response.status_code == 303
    page = unlocked.get("/reminders").text
    assert "port-out PIN" in page

    reminder_id = int(
        re.search(r"/reminders/(\d+)/delete", page).group(1)
    )
    unlocked.post(
        f"/reminders/{reminder_id}/delete",
        data={"csrf_token": csrf_token(unlocked)},
    )
