"""Settled grid cells frost over; the mark is never color alone.

The grid previously showed state only as text inside each dropdown, so a
finished row looked identical to an untouched one at a glance. Settled cells
(frozen, enrolled, or the confirmed "no file exists" a child wants) now carry
a ❄ mark and an ice wash; "not applicable" recedes. The snowflake exists so
the state survives without color perception — the tint alone is decoration.
"""

from __future__ import annotations

from conftest import add_person

from frostfile import db
from frostfile.repo import list_agencies, set_freeze_status
from frostfile.seeds import (
    STATUS_ACTIVE,
    STATUS_IN_PROGRESS,
    STATUS_NO_FILE,
    STATUS_NOT_APPLICABLE,
)

FROST = "cell-frost"
SETTLED = "cell-settled"
SHELVED = "cell-na"


def set_status(settings, person_id, agency_id, status):
    conn = db.connect(settings.db_path)
    try:
        set_freeze_status(conn, person_id, agency_id, status)
    finally:
        conn.close()


def agency_id(settings, slug):
    conn = db.connect(settings.db_path)
    try:
        return {a.slug: a.id for a in list_agencies(conn)}[slug]
    finally:
        conn.close()


def test_untouched_grid_shows_no_frost(unlocked, settings):
    add_person(unlocked, "Dana Guardian")
    body = unlocked.get("/matrix").text
    assert SETTLED not in body
    assert FROST not in body
    assert SHELVED not in body


def test_frozen_and_no_file_cells_frost_over(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    set_status(settings, person_id, agency_id(settings, "equifax"), STATUS_ACTIVE)
    set_status(settings, person_id, agency_id(settings, "innovis"), STATUS_NO_FILE)
    body = unlocked.get("/matrix").text
    assert body.count(SETTLED) == 2
    assert body.count(FROST) == 2


def test_in_progress_is_not_settled(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    set_status(settings, person_id, agency_id(settings, "equifax"), STATUS_IN_PROGRESS)
    body = unlocked.get("/matrix").text
    assert SETTLED not in body


def test_not_applicable_recedes_without_frost(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    set_status(
        settings, person_id, agency_id(settings, "equifax"), STATUS_NOT_APPLICABLE
    )
    body = unlocked.get("/matrix").text
    assert SHELVED in body
    assert SETTLED not in body
    assert FROST not in body


def test_the_mark_is_hidden_from_screen_readers(unlocked, settings):
    """The dropdown already announces the status; the snowflake repeating it
    as an unlabeled graphic would only add noise."""
    person_id = add_person(unlocked, "Dana Guardian")
    set_status(settings, person_id, agency_id(settings, "equifax"), STATUS_ACTIVE)
    body = unlocked.get("/matrix").text
    assert '<span class="cell-frost" aria-hidden="true">' in body


def test_legend_explains_the_mark(unlocked, settings):
    add_person(unlocked, "Dana Guardian")
    body = unlocked.get("/matrix").text
    assert "settled" in body


ROW = "row-frosted"


def test_row_frosts_only_when_every_person_is_settled(unlocked, settings):
    p1 = add_person(unlocked, "Dana Guardian")
    p2 = add_person(unlocked, "Riley Guardian", kind="minor")
    equifax = agency_id(settings, "equifax")

    set_status(settings, p1, equifax, STATUS_ACTIVE)
    assert ROW not in unlocked.get("/matrix").text  # half a household isn't done

    set_status(settings, p2, equifax, STATUS_NO_FILE)
    assert unlocked.get("/matrix").text.count(ROW) == 1


def test_not_applicable_completes_a_row_but_cannot_carry_it(unlocked, settings):
    p1 = add_person(unlocked, "Dana Guardian")
    p2 = add_person(unlocked, "Riley Guardian", kind="minor")
    equifax = agency_id(settings, "equifax")
    innovis = agency_id(settings, "innovis")

    # frozen + N/A → the line is done for this household
    set_status(settings, p1, equifax, STATUS_ACTIVE)
    set_status(settings, p2, equifax, STATUS_NOT_APPLICABLE)
    # N/A + N/A → shelved, not settled; no frost earned
    set_status(settings, p1, innovis, STATUS_NOT_APPLICABLE)
    set_status(settings, p2, innovis, STATUS_NOT_APPLICABLE)

    assert unlocked.get("/matrix").text.count(ROW) == 1
