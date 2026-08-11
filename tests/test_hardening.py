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


def test_kdf_params_are_clamped_against_tampering(unlocked, settings):
    from frostfile import db

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

    from frostfile.crypto import KdfParams, derive_key

    params = KdfParams.generate()
    nfd = unicodedata.normalize("NFD", "café-passphrase-xyz")
    nfc = unicodedata.normalize("NFC", "café-passphrase-xyz")
    assert nfd != nfc  # different byte sequences
    assert derive_key(nfd, params) == derive_key(nfc, params)  # same key


def test_zero_network_rule_no_http_client_in_app_code():
    """PROJECT REQUIREMENT: the app makes zero outbound connections.

    Anything needing the internet must be a plain link the user clicks.
    This scans every shipped module for HTTP-client imports so a violation
    fails CI instead of eroding the promise quietly. (Release-time dev
    scripts are exempt — they are never shipped inside the app.)
    """
    from pathlib import Path

    import frostfile

    package_dir = Path(frostfile.__file__).parent
    forbidden = ("import httpx", "import requests", "import aiohttp",
                 "import urllib.request", "from urllib import request",
                 "from urllib.request import")
    offenders = []
    for py in package_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{py.relative_to(package_dir)}: {needle}")
    assert not offenders, f"Outbound HTTP client in shipped code: {offenders}"


def test_settings_declares_zero_network_and_sources_shows_verified_date(unlocked):
    from frostfile import sources as source_registry

    settings_page = unlocked.get("/settings").text
    assert "Nothing. Ever." in settings_page

    sources_page = unlocked.get("/sources").text
    assert source_registry.LINKS_VERIFIED_ON in sources_page
