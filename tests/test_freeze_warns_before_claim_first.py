"""Freeze pages warn while the claim-first accounts are still open.

The claim-first ordering (test_claim_first_ordering.py) puts the four
government accounts above the freezes, but a checklist row can't stop a
person from jumping straight to Equifax. Enrolling in those accounts runs an
identity check that a credit freeze can make fail — the app already says so
on the E-Verify Self Lock row — so the freeze page itself repeats the
warning at the moment it matters, and drops it once there is nothing left
to warn about. A warning that never turns off teaches people to ignore it.
"""

from __future__ import annotations

from conftest import add_person

from frostfile import db
from frostfile.repo import list_agencies, set_freeze_status
from frostfile.seeds import (
    FREEZE_CATEGORIES,
    STATUS_ACTIVE,
    STATUS_NOT_APPLICABLE,
)

CLAIM_FIRST = {"irs_ip_pin", "ssa_account", "everify_self_lock", "usps_informed_delivery"}
MARKER = "Worth doing first:"


def agencies_by_slug(settings):
    conn = db.connect(settings.db_path)
    try:
        return {a.slug: a for a in list_agencies(conn)}
    finally:
        conn.close()


def test_fresh_person_sees_the_warning_on_a_bureau_freeze(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    agencies = agencies_by_slug(settings)
    body = unlocked.get(f"/freeze/{person_id}/{agencies['equifax'].id}").text
    assert MARKER in body
    for slug in CLAIM_FIRST:
        assert agencies[slug].name in body, f"{slug} missing from the warning"


def test_warning_names_only_what_is_still_open(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    agencies = agencies_by_slug(settings)

    conn = db.connect(settings.db_path)
    try:
        set_freeze_status(conn, person_id, agencies["irs_ip_pin"].id, STATUS_ACTIVE)
        set_freeze_status(
            conn, person_id, agencies["everify_self_lock"].id, STATUS_NOT_APPLICABLE
        )
    finally:
        conn.close()

    body = unlocked.get(f"/freeze/{person_id}/{agencies['equifax'].id}").text
    assert MARKER in body
    assert agencies["ssa_account"].name in body
    assert agencies["usps_informed_delivery"].name in body
    assert agencies["irs_ip_pin"].name not in body
    assert agencies["everify_self_lock"].name not in body


def test_warning_disappears_once_every_account_is_claimed(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    agencies = agencies_by_slug(settings)

    conn = db.connect(settings.db_path)
    try:
        for slug in CLAIM_FIRST:
            set_freeze_status(conn, person_id, agencies[slug].id, STATUS_ACTIVE)
    finally:
        conn.close()

    body = unlocked.get(f"/freeze/{person_id}/{agencies['equifax'].id}").text
    assert MARKER not in body


def test_claim_first_rows_do_not_warn_about_themselves(unlocked, settings):
    person_id = add_person(unlocked, "Dana Guardian")
    agencies = agencies_by_slug(settings)
    for slug in CLAIM_FIRST:
        body = unlocked.get(f"/freeze/{person_id}/{agencies[slug].id}").text
        assert MARKER not in body, f"{slug} warns about itself"


def test_every_freeze_category_act_row_carries_the_warning(unlocked, settings):
    """The warning belongs to the freeze side as a whole — specialty bureaus
    included — not just the big three. FYI/covered rows have no freeze to
    place, so they stay quiet."""
    person_id = add_person(unlocked, "Dana Guardian")
    agencies = agencies_by_slug(settings)
    for agency in agencies.values():
        should_warn = agency.category in FREEZE_CATEGORIES and agency.action_kind == "act"
        body = unlocked.get(f"/freeze/{person_id}/{agency.id}").text
        assert (MARKER in body) == should_warn, (
            f"{agency.slug}: warning {'missing' if should_warn else 'unexpected'}"
        )
