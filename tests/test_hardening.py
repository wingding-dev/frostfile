"""Audit fix: P3 hardening — Host check, origin guard, input coercion, KDF clamp, NFC."""

from __future__ import annotations

from conftest import add_person, csrf_token


def test_foreign_host_is_rejected(client):
    r = client.get("/setup", headers={"host": "evil.example.com"})
    assert r.status_code == 400


def test_loopback_host_allowed(client):
    assert client.get("/setup", headers={"host": "localhost:8731"}).status_code == 200


def test_cross_site_setup_post_refused(client):
    r = client.post(
        "/setup",
        data={"passphrase": "x" * 14, "confirm": "x" * 14, "acknowledged": "1"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403


def test_freeze_save_with_bad_ids_is_404_not_500(unlocked):
    r = unlocked.post(
        "/freeze/99999/99999",
        data={"status": "active", "csrf_token": csrf_token(unlocked)},
    )
    assert r.status_code == 404


def test_breach_check_with_junk_person_id_does_not_crash(unlocked):
    # Superscript digit: isdigit() True, int() would raise — must not 500.
    r = unlocked.post(
        "/breaches/email",
        data={"email": "a@b.com", "person_id": "²", "csrf_token": csrf_token(unlocked)},
    )
    assert r.status_code in (200, 303)  # handled, not a 500


def test_kdf_params_are_clamped_against_tampering(unlocked, settings):
    from identilock import db

    conn = db.connect(settings.db_path)
    try:
        # A tampered absurd memory cost must be clamped, not attempted.
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'kdf_memory_cost'",
            (b"999999999",),
        )
        conn.commit()
        params = db.load_kdf_params(conn)
        assert params.memory_cost <= 2 * 1024 * 1024
    finally:
        conn.close()


def test_passphrase_is_nfc_normalized():
    import unicodedata

    from identilock.crypto import KdfParams, derive_key

    params = KdfParams.generate()
    nfd = unicodedata.normalize("NFD", "café-passphrase-xyz")
    nfc = unicodedata.normalize("NFC", "café-passphrase-xyz")
    assert nfd != nfc  # different byte sequences
    assert derive_key(nfd, params) == derive_key(nfc, params)  # same key
