from __future__ import annotations

import re

from conftest import add_person

from identilock import sources


def _agency_id(client, name: str) -> int:
    page = client.get("/agencies").text
    for match in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', page):
        if match.group(2).strip() == name:
            return int(match.group(1))
    raise AssertionError(f"agency {name!r} not found")


def test_letter_includes_verified_address_and_checklist(unlocked):
    guardian = add_person(
        unlocked,
        "Dana Guardian",
        address="12 Elm Street\nSpringfield, IL 62704",
        birth_date="1985-04-02",
    )
    child = add_person(unlocked, "Robin Child", kind="minor", birth_date="2016-09-11")

    page = unlocked.get(
        f"/letters/{child}/{_agency_id(unlocked, 'Equifax')}?guardian={guardian}"
    )
    assert page.status_code == 200

    # The address that was confirmed at a primary source.
    assert "P.O. Box 105788" in page.text
    assert "Atlanta, GA 30348" in page.text

    assert "Robin Child" in page.text
    assert "Dana Guardian" in page.text
    assert "12 Elm Street" in page.text

    # Document checklist, taken from Equifax's own form.
    assert "birth certificate" in page.text.lower()
    assert "Social Security card" in page.text

    # And the standing warning against mailing originals.
    assert "copies" in page.text.lower()


def test_letter_leaves_ssn_blank_when_not_stored(unlocked):
    add_person(unlocked, "Dana Guardian")
    child = add_person(unlocked, "Robin Child", kind="minor", ssn="123456789")

    page = unlocked.get(f"/letters/{child}/{_agency_id(unlocked, 'Equifax')}").text
    assert "123456789" not in page
    assert "_______" in page


def test_letter_includes_ssn_when_explicitly_stored(unlocked):
    add_person(unlocked, "Dana Guardian")
    child = add_person(
        unlocked, "Robin Child", kind="minor", ssn="123456789", store_full_ssn="1"
    )
    page = unlocked.get(f"/letters/{child}/{_agency_id(unlocked, 'Equifax')}").text
    assert "123456789" in page


def test_no_packet_for_agency_with_unconfirmed_address(unlocked):
    """The safety property: no envelope unless the address was actually checked."""
    child = add_person(unlocked, "Robin Child", kind="minor")
    response = unlocked.get(f"/letters/{child}/{_agency_id(unlocked, 'Innovis')}")
    assert response.status_code == 400
    assert "not confirmed at a primary source" in response.text


def test_every_letter_capable_agency_has_a_verified_address(unlocked):
    """Guards against a future edit enabling a packet without a source."""
    from identilock import db
    from identilock.repo import list_agencies

    conn = db.connect(unlocked.app.state.settings.db_path)
    try:
        for agency in list_agencies(conn):
            if agency.can_generate_letter:
                assert agency.address_verified, agency.name
                assert agency.mail_address, agency.name
                assert agency.cite("mail_address"), (
                    f"{agency.name} prints a packet but cites no source for its address"
                )
    finally:
        conn.close()


def test_citations_render_as_linked_superscripts(unlocked):
    page = unlocked.get(f"/agencies/{_agency_id(unlocked, 'Equifax')}").text
    assert '<sup class="cite">' in page
    assert "assets.equifax.com" in page
    # Footnote list at the bottom of the page.
    assert "Sources on this page" in page
    assert 'id="source-1"' in page


def test_uncited_fields_are_marked_rather_than_silent(unlocked):
    page = unlocked.get(f"/agencies/{_agency_id(unlocked, 'Mobile carrier port-out lock')}").text
    assert "cite-missing" in page


def test_sources_page_lists_everything(unlocked):
    page = unlocked.get("/sources")
    assert page.status_code == 200
    for source in sources.all_sources():
        assert source.url in page.text


def test_every_citation_key_resolves():
    """A typo in seeds.py would otherwise silently drop a citation."""
    from identilock.seeds import AGENCIES

    for agency in AGENCIES:
        for field_name, keys in agency.get("citations", {}).items():
            for key in keys:
                assert sources.get(key) is not None, (
                    f"{agency['slug']}.{field_name} cites unknown source {key!r}"
                )


def test_verified_addresses_all_carry_a_primary_source():
    """address_verified must mean a page was actually read, not merely linked."""
    from identilock.seeds import AGENCIES

    for agency in AGENCIES:
        if not agency.get("address_verified"):
            continue
        keys = agency.get("citations", {}).get("mail_address", [])
        assert keys, f"{agency['slug']} claims a verified address but cites nothing"
        assert any(sources.get(k).is_primary for k in keys), (
            f"{agency['slug']} claims a verified address with no retrieved source"
        )
