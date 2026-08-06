from __future__ import annotations

import pytest

from frostfile import db
from frostfile.crypto import (
    KdfParams,
    Vault,
    WrongPassphrase,
    check_verifier,
    derive_key,
    make_verifier,
    open_sealed,
    passphrase_problems,
    seal,
)

# Argon2 at production settings makes the suite crawl; correctness is what is
# under test here, not the work factor.
FAST = KdfParams(salt=b"0123456789abcdef", time_cost=1, memory_cost=8, parallelism=1)


def test_seal_and_open_roundtrip():
    key = derive_key("a passphrase", FAST)
    blob = seal(key, "people:ssn_enc", "123456789")
    assert b"123456789" not in blob
    assert open_sealed(key, "people:ssn_enc", blob) == b"123456789"


def test_ciphertext_is_bound_to_its_column():
    """A value moved into another column must not decrypt."""
    key = derive_key("a passphrase", FAST)
    blob = seal(key, "people:notes_enc", "harmless note")
    with pytest.raises(Exception):
        open_sealed(key, "freeze_records:pin_enc", blob)


def test_wrong_key_does_not_open():
    good = derive_key("right", FAST)
    bad = derive_key("wrong", FAST)
    blob = seal(good, "people:ssn_enc", "secret")
    with pytest.raises(Exception):
        open_sealed(bad, "people:ssn_enc", blob)


def test_verifier_distinguishes_passphrases():
    good = derive_key("right", FAST)
    bad = derive_key("wrong", FAST)
    verifier = make_verifier(good)
    assert check_verifier(good, verifier)
    assert not check_verifier(bad, verifier)


def test_vault_decrypt_returns_none_for_tampered_data():
    vault = Vault(derive_key("passphrase", FAST))
    blob = vault.encrypt("people:notes_enc", "note")
    tampered = bytearray(blob)
    tampered[-1] ^= 0xFF
    assert vault.decrypt("people:notes_enc", bytes(tampered)) is None


def test_empty_values_are_not_encrypted():
    vault = Vault(derive_key("passphrase", FAST))
    assert vault.encrypt("people:notes_enc", None) is None
    assert vault.encrypt("people:notes_enc", "") is None
    assert vault.decrypt("people:notes_enc", None) is None


def test_passphrase_problems_flags_short_and_guessable():
    assert passphrase_problems("short")
    assert passphrase_problems("password")
    assert passphrase_problems("  padded passphrase  ")
    assert not passphrase_problems("four random words here")


def test_unlock_rejects_bad_passphrase(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.initialize_vault(conn, "the right passphrase")
    with pytest.raises(WrongPassphrase):
        db.unlock(conn, "the wrong passphrase")
    assert db.unlock(conn, "the right passphrase") is not None
    conn.close()


def test_change_passphrase_rewraps_every_field(tmp_path):
    from frostfile.repo import create_person, get_person
    from frostfile.seeds import seed_agencies

    conn = db.connect(tmp_path / "t.db")
    vault = db.initialize_vault(conn, "old passphrase here")
    seed_agencies(conn)

    person_id = create_person(
        conn, vault, display_name="Test Person", kind="adult", ssn="123456789"
    )

    new_vault, recovery_code = db.change_passphrase(conn, vault, "new passphrase here")

    # A fresh recovery code is issued in the same transaction, and it opens the
    # re-wrapped vault.
    assert recovery_code
    assert db.recover_data_key(conn, recovery_code) == new_vault.key

    # Readable under the new key...
    person = get_person(conn, new_vault, person_id)
    assert person.display_name == "Test Person"
    assert person.ssn == "123456789"

    # ...and the old key is genuinely dead.
    stale = get_person(conn, vault, person_id)
    assert stale.display_name == "(unreadable)"

    assert db.unlock(conn, "new passphrase here") is not None
    with pytest.raises(WrongPassphrase):
        db.unlock(conn, "old passphrase here")
    conn.close()
