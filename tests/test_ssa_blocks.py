"""The two SSA blocks ship as distinct, fully-cited actions.

The Direct Deposit Fraud Prevention block closes a benefit-redirect path
that never touches ssa.gov (auto-enrollment through a bank); the electronic
access block shuts down all online and automated-phone access to the record.
They were held out of the app until each claim could be tied to a retrieved
SSA source — the research pass's cited publication (EN-05-10064) turned out
to contain neither block, so these tests also pin every citation key to a
real registry entry to keep that from happening silently again.
"""

from __future__ import annotations

from frostfile import db, sources
from frostfile.repo import list_agencies
from frostfile.seeds import AGENCIES

BLOCKS = {"ssa_dd_block", "ssa_eservices_block"}
CLAIM_FIRST_MAX = 4
BUREAU_MIN = 10


def entries():
    return {a["slug"]: a for a in AGENCIES if a["slug"] in BLOCKS}


def test_both_blocks_exist_as_actionable_government_controls():
    rows = entries()
    assert set(rows) == BLOCKS
    for slug, row in rows.items():
        assert row["category"] == "gov_control", slug
        assert row.get("action_kind", "act") == "act", slug
        assert row["phone"] == "1-800-772-1213", slug


def test_blocks_sort_after_the_freezes_not_before():
    """They are judgment calls, not steps in the claim-first race — sorting
    them above the bureaus would tell families to lock their own SSA access
    before freezing credit, which is backwards for most households."""
    for slug, row in entries().items():
        assert row["sort_order"] > BUREAU_MIN, slug
        assert row["sort_order"] > CLAIM_FIRST_MAX, slug


def test_every_citation_key_resolves_to_a_fetched_source():
    for slug, row in entries().items():
        cites = row.get("citations", {})
        assert cites, f"{slug} ships uncited"
        for field, keys in cites.items():
            for key in keys:
                src = sources.SOURCES.get(key)
                assert src is not None, f"{slug}.{field} cites unknown source {key}"
                assert src.checked == "fetched", (
                    f"{slug}.{field} cites {key}, which was never retrieved — "
                    "the EN-05-10064 lesson"
                )


def test_dd_block_does_not_claim_an_online_path():
    """There is no public page for the DD block; it must not render an
    'Official page' link or claim online support."""
    row = entries()["ssa_dd_block"]
    assert row["freeze_url"] == ""
    assert row["supports_online"] is False


def test_eservices_block_says_the_quiet_part_out_loud():
    """The block cuts off the user's own online access; the row must carry
    that tradeoff and bless 'Not applicable' as an answer."""
    row = entries()["ssa_eservices_block"]
    assert "including you" in row["why_it_matters"]
    assert "Not" in row["notes"] and "applicable" in row["notes"]


def test_blocks_reach_a_seeded_database(unlocked, settings):
    conn = db.connect(settings.db_path)
    try:
        slugs = {a.slug for a in list_agencies(conn)}
    finally:
        conn.close()
    assert BLOCKS <= slugs
