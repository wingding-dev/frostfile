"""The first-use feedback round: split address fields, FYI entities, settings GUI."""

from __future__ import annotations

from conftest import add_person, csrf_token


def test_split_address_fields_round_trip(unlocked):
    person_id = add_person(
        unlocked,
        "Addr Person",
        address_street="12 Elm Street",
        address_city="Springfield",
        address_state="il",
        address_zip="62704",
    )
    # Stored as one block for letters, state upper-cased.
    detail = unlocked.get(f"/people/{person_id}").text
    assert "12 Elm Street" in detail
    assert "Springfield, IL 62704" in detail

    # The edit form splits it back into the separate boxes.
    edit = unlocked.get(f"/people/{person_id}/edit").text
    assert 'value="Springfield"' in edit
    assert 'value="IL"' in edit
    assert 'value="62704"' in edit


def test_old_single_address_field_still_accepted(unlocked):
    person_id = add_person(
        unlocked, "Legacy Poster", address="1 Old Way\nSomewhere, TX 75001"
    )
    assert "Somewhere, TX 75001" in unlocked.get(f"/people/{person_id}").text


def test_unparseable_address_lands_intact_in_street_box(unlocked):
    person_id = add_person(
        unlocked, "Odd Address", address="c/o The Site Office, Gate 4"
    )
    edit = unlocked.get(f"/people/{person_id}/edit").text
    assert "c/o The Site Office, Gate 4" in edit


def test_fyi_agencies_are_off_the_grid_but_in_the_directory(unlocked):
    add_person(unlocked, "Grid Person")
    matrix = unlocked.get("/matrix").text
    before_fyi = matrix.split("Not on the Grid")[0]
    assert "Early Warning Services" not in before_fyi
    assert "Early Warning Services" in matrix  # listed in the FYI section

    directory = unlocked.get("/agencies").text
    assert "FYI — nothing to do" in directory
    assert "covered elsewhere" in directory  # SageStream


def test_fyi_agencies_do_not_count_toward_progress(unlocked):
    add_person(unlocked, "Progress Person")
    page = unlocked.get("/").text
    # 24 agencies seeded, 2 are FYI-only → 22 controls for one adult.
    assert "0 of 22 controls in place" in page


def test_lock_timeout_is_adjustable_from_settings(unlocked, settings):
    response = unlocked.post(
        "/settings/lock",
        data={"minutes": "45", "csrf_token": csrf_token(unlocked)},
    )
    assert response.status_code == 200
    assert "45 minutes" in response.text
    prefs = (settings.data_dir / "prefs.json").read_text()
    assert '"lock_minutes": 45' in prefs

    rejected = unlocked.post(
        "/settings/lock",
        data={"minutes": "0", "csrf_token": csrf_token(unlocked)},
    )
    assert "between 1 and 240" in rejected.text


def test_data_dir_move_copies_db_and_leaves_pointer(unlocked, settings, tmp_path):
    target = tmp_path / "new-home"
    response = unlocked.post(
        "/settings/data-dir",
        data={"folder": str(target), "csrf_token": csrf_token(unlocked)},
    )
    assert response.status_code == 200, response.text
    assert (target / "identilock.db").exists()

    # The pointer must be left in THIS instance's data folder — never in the
    # machine-wide default folder, which would hijack a real install's data
    # (exactly what an earlier version of this feature did to the author).
    pointer = (settings.data_dir / "prefs.json").read_text()
    assert str(target) in pointer

    from identilock.config import load_settings

    # Explicit data_dir wins: pointers are not followed for overridden launches.
    resolved = load_settings(data_dir=settings.data_dir, host="127.0.0.1", port=8899)
    assert resolved.data_dir == settings.data_dir

    # Refuses to overwrite an existing database at the destination.
    again = unlocked.post(
        "/settings/data-dir",
        data={"folder": str(target), "csrf_token": csrf_token(unlocked)},
    )
    assert "already contains" in again.text
