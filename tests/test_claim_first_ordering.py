"""Accounts you claim must come before the freezes you place.

Whoever registers an IRS, SSA, E-Verify or USPS account first owns it, and the
identity questions asked to prove it draw on the very records a breach exposes.
So this is a race, and a checklist that lists the freezes first walks a family
straight past the starting line.

The ordering is the feature. These tests exist because a sort_order is exactly
the kind of thing that gets nudged during an unrelated edit, silently, with no
symptom until someone loses the race.
"""

from __future__ import annotations

from frostfile import db
from frostfile.repo import list_agencies
from frostfile.seeds import ACTION_KIND_LABELS, AGENCIES

CLAIM_FIRST = {"irs_ip_pin", "ssa_account", "everify_self_lock", "usps_informed_delivery"}


def test_claim_first_agencies_sort_above_every_credit_bureau():
    by_slug = {a["slug"]: a for a in AGENCIES}
    claim_orders = [by_slug[s]["sort_order"] for s in CLAIM_FIRST]
    bureau_orders = [
        a["sort_order"] for a in AGENCIES if a["category"] == "credit_bureau"
    ]
    assert max(claim_orders) < min(bureau_orders), (
        "A claim-first account sorts below a credit bureau. Working the list "
        "top-to-bottom would then place a freeze before the account is claimed."
    )


def test_the_four_government_controls_are_marked_claim_first():
    by_slug = {a["slug"]: a for a in AGENCIES}
    for slug in CLAIM_FIRST:
        assert by_slug[slug].get("action_kind") == "claim_first", slug
        assert by_slug[slug].get("action_note"), f"{slug} needs a reason shown to the user"


def test_claim_first_is_a_known_action_kind():
    assert "claim_first" in ACTION_KIND_LABELS


def test_claim_first_is_a_task_not_an_fyi(unlocked, settings):
    """It must survive the filters that strip informational rows, and keep an
    effort estimate — a task with no effort label reads as nothing to do."""
    conn = db.connect(settings.db_path)
    try:
        agencies = {a.slug: a for a in list_agencies(conn)}
    finally:
        conn.close()
    for slug in CLAIM_FIRST:
        agency = agencies[slug]
        assert agency.is_claim_first is True, slug
        assert agency.is_fyi is False, f"{slug} would be filtered out of the work lists"
        assert agency.effort_label, f"{slug} lost its effort estimate"


def test_detail_page_does_not_tell_you_there_is_nothing_to_do(unlocked, settings):
    """The banner is driven by action_kind; before claim_first existed, any
    non-'act' kind rendered as "Nothing for you to do here" — the exact
    opposite of the message these four need to carry."""
    page = unlocked.get("/agencies").text
    assert "do this first" in page

    conn = db.connect(settings.db_path)
    try:
        ids = {a.slug: a.id for a in list_agencies(conn)}
    finally:
        conn.close()

    for slug in CLAIM_FIRST:
        body = unlocked.get(f"/agencies/{ids[slug]}").text
        assert "Nothing for you to do here" not in body, slug
        assert "Do this one before the freezes." in body, slug
