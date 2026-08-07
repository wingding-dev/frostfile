"""Teen (16-17) freeze branch: the parent-placed protected-consumer process
covers only under-16s; teens request their own standard freeze by phone/mail."""

from __future__ import annotations

import re
from datetime import date, timedelta

from conftest import add_person, csrf_token


def _dob(years: int) -> str:
    return (date.today() - timedelta(days=365 * years + 200)).isoformat()


def _agency_id(client, name="Equifax"):
    page = client.get("/agencies").text
    for m in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', page):
        if m.group(2).strip() == name:
            return int(m.group(1))
    raise AssertionError(name)


def test_age_bands(unlocked):
    from frostfile.repo import Person

    assert Person(1, "minor", "Kid", birth_date=_dob(10)).is_teen is False
    assert Person(1, "minor", "Teen", birth_date=_dob(16)).is_teen is True
    assert Person(1, "minor", "Teen", birth_date=_dob(17)).is_teen is True
    assert Person(1, "adult", "Grown", birth_date=_dob(17)).is_teen is False
    assert Person(1, "minor", "NoDOB").is_teen is False  # unknown age = child path


def test_teen_gets_teen_letter_not_parent_packet(unlocked):
    add_person(unlocked, "Parent Person")
    teen = add_person(unlocked, "Teen Person", kind="minor", birth_date=_dob(16))
    eq = _agency_id(unlocked)

    page = unlocked.get(f"/letters/{teen}/{eq}").text
    assert "Request for a security freeze on my credit file" in page  # teen letter
    assert "parent or legal guardian of" not in page  # NOT the child packet
    assert "signed by Teen Person" in page

    letters = unlocked.get("/letters").text
    assert "Teen letter" in letters
    assert "requests" in letters and "own" in letters


def test_child_still_gets_parent_packet(unlocked):
    add_person(unlocked, "Parent Person")
    child = add_person(unlocked, "Child Person", kind="minor", birth_date=_dob(9))
    eq = _agency_id(unlocked)
    page = unlocked.get(f"/letters/{child}/{eq}").text
    assert "parent or legal guardian of Child Person" in page
    assert "Request for a security freeze on my credit file" not in page


def test_teen_transition_reminder_seeded(unlocked):
    add_person(unlocked, "Young Kid", kind="minor", birth_date=_dob(10))
    page = unlocked.get("/reminders").text
    assert "Turning 16" in page


def test_teen_pdf_uses_teen_letter(unlocked):
    import io

    import pypdf

    add_person(unlocked, "Parent Person")
    teen = add_person(unlocked, "Teen Person", kind="minor", birth_date=_dob(17))
    eq = _agency_id(unlocked)
    resp = unlocked.get(f"/letters/{teen}/{eq}.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    text = "".join(
        p.extract_text() for p in pypdf.PdfReader(io.BytesIO(resp.content)).pages
    )
    assert "security freeze on my credit" in text
    assert "parent or legal guardian" not in text


def test_single_pdf_download_for_child(unlocked):
    add_person(unlocked, "Parent Person")
    child = add_person(unlocked, "Child Person", kind="minor", birth_date=_dob(8))
    eq = _agency_id(unlocked)
    resp = unlocked.get(f"/letters/{child}/{eq}.pdf")
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"
    assert "Child Person" in resp.headers["content-disposition"]


def test_teen_badge_shown(unlocked):
    teen = add_person(unlocked, "Badge Teen", kind="minor", birth_date=_dob(16))
    page = unlocked.get(f"/people/{teen}").text
    assert ">Teen<" in page
    assert "the freeze process changes" in page
