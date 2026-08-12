"""The Documents backup mirror and the setup-screen restore offer.

The scenario this whole feature exists for: the data directory lives in
app-data, which disk-cleanup tools treat as disposable, and the backups used
to live inside it — so one cleanup deleted the vault AND every backup at once.
The mirror keeps spare copies of the closed backup files in Documents, and the
setup screen turns "wiped data dir + surviving mirror" into a one-click
restore instead of silent data loss.
"""

from __future__ import annotations

import dataclasses
import os
import time

import pytest
from fastapi.testclient import TestClient

from frostfile import config
from frostfile.config import load_settings, mirror_backups
from frostfile.web import create_app

from conftest import PASSPHRASE, add_person, csrf_token

README_NAME = "READ ME - what is this folder.txt"


def _make_settings(tmp_path, subdir="data"):
    base = load_settings(data_dir=tmp_path / subdir, host="127.0.0.1", port=8899)
    return dataclasses.replace(
        base, mirror_dir=tmp_path / "Documents" / "FrostFile Backups"
    )


def _make_client(settings):
    return TestClient(
        create_app(settings), base_url="http://127.0.0.1", follow_redirects=False
    )


@pytest.fixture
def mirror_settings(tmp_path):
    return _make_settings(tmp_path)


@pytest.fixture
def munlocked(mirror_settings):
    with _make_client(mirror_settings) as client:
        response = client.post(
            "/setup",
            data={
                "passphrase": PASSPHRASE,
                "confirm": PASSPHRASE,
                "acknowledged": "1",
            },
        )
        assert response.status_code == 303, response.text
        yield client


def _relock(client):
    client.post("/lock", data={"csrf_token": csrf_token(client)})
    response = client.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    assert response.status_code == 303, response.text


# --- the mirror itself ------------------------------------------------------


def test_unlock_mirrors_backups_and_writes_readme(munlocked, mirror_settings):
    _relock(munlocked)
    mirrored = list(mirror_settings.mirror_dir.glob("frostfile-auto-*.db"))
    assert mirrored, "unlock should have mirrored the weekly auto backup"
    originals = list(mirror_settings.backup_dir.glob("frostfile-auto-*.db"))
    assert {p.name for p in mirrored} == {p.name for p in originals}
    assert (mirrored[0].read_bytes()) == (
        mirror_settings.backup_dir / mirrored[0].name
    ).read_bytes()
    readme = mirror_settings.mirror_dir / README_NAME
    assert readme.exists()
    assert "scrambled" in readme.read_text(encoding="utf-8")


def test_mirror_catches_up_when_weekly_backup_is_fresh(munlocked, mirror_settings):
    _relock(munlocked)
    for f in mirror_settings.mirror_dir.glob("frostfile-*.db"):
        f.unlink()
    # The weekly backup is fresh, so no new backup is made — but the mirror
    # must still be refilled from the existing one.
    _relock(munlocked)
    assert list(mirror_settings.mirror_dir.glob("frostfile-auto-*.db"))


def test_mirror_prunes_automatic_copies_only(tmp_path):
    settings = _make_settings(tmp_path)
    settings.backup_dir.mkdir(parents=True)
    for i in range(12):
        (settings.backup_dir / f"frostfile-auto-2026010{i:02d}-000000.db").write_bytes(
            b"x"
        )
    settings.mirror_dir.mkdir(parents=True)
    keepsake = settings.mirror_dir / "my-own-copy.db"
    keepsake.write_bytes(b"mine")

    mirror_backups(settings)

    automatic = list(settings.mirror_dir.glob("frostfile-auto-*.db"))
    assert len(automatic) == config.MIRROR_KEEP
    assert keepsake.exists(), "files the user put there are not ours to delete"


def test_mirror_failure_never_blocks_unlock(munlocked, mirror_settings):
    # Make the mirror path impossible: a file where the folder should be.
    mirror_settings.mirror_dir.parent.mkdir(parents=True, exist_ok=True)
    mirror_settings.mirror_dir.write_bytes(b"not a folder")
    _relock(munlocked)  # asserts unlock succeeded


def test_explicit_data_dir_disables_mirror(tmp_path):
    settings = load_settings(data_dir=tmp_path / "data")
    assert settings.mirror_dir is None
    assert settings.mirror_off_by_pref is False


def test_default_location_resolves_mirror(tmp_path, monkeypatch):
    monkeypatch.delenv("FROSTFILE_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "default_data_dir", lambda: tmp_path / "data")
    docs = tmp_path / "Documents"
    docs.mkdir()
    monkeypatch.setattr(config, "documents_dir", lambda: docs)

    settings = load_settings()
    assert settings.mirror_dir == docs / "FrostFile Backups"

    # The preference turns it off — and is distinguishable from "unavailable".
    config.write_prefs(tmp_path / "data", mirror_backups=False)
    settings = load_settings()
    assert settings.mirror_dir is None
    assert settings.mirror_off_by_pref is True


def test_no_documents_folder_means_no_mirror(tmp_path, monkeypatch):
    monkeypatch.delenv("FROSTFILE_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "default_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(config, "documents_dir", lambda: tmp_path / "missing")

    settings = load_settings()
    assert settings.mirror_dir is None
    assert settings.mirror_off_by_pref is False


# --- the restore offer ------------------------------------------------------


def _wiped_install(tmp_path, mirror_dir):
    """A fresh app instance whose data dir is empty but whose mirror survived."""
    base = load_settings(data_dir=tmp_path / "data-after-wipe", host="127.0.0.1", port=8899)
    return dataclasses.replace(base, mirror_dir=mirror_dir)


def test_setup_offers_restore_from_mirror_and_it_works(
    munlocked, mirror_settings, tmp_path
):
    add_person(munlocked, "Casey")
    _relock(munlocked)  # backup + mirror now hold Casey

    settings2 = _wiped_install(tmp_path, mirror_settings.mirror_dir)
    with _make_client(settings2) as client:
        page = client.get("/setup")
        assert "Bring My Data Back" in page.text
        assert "Your Information Is Not Gone" in page.text

        response = client.post("/setup/restore")
        assert response.status_code == 303
        assert response.headers["location"] == "/unlock"

        response = client.post(
            "/unlock", data={"passphrase": PASSPHRASE, "next": "/"}
        )
        assert response.status_code == 303, "the original passphrase still works"
        assert "Casey" in client.get("/people").text


def test_restore_skips_a_damaged_newest_copy(munlocked, mirror_settings, tmp_path):
    add_person(munlocked, "Casey")
    _relock(munlocked)

    damaged = mirror_settings.mirror_dir / "frostfile-auto-99999999-999999.db"
    damaged.write_bytes(b"this is not a database")
    future = time.time() + 3600
    os.utime(damaged, (future, future))

    settings2 = _wiped_install(tmp_path, mirror_settings.mirror_dir)
    with _make_client(settings2) as client:
        response = client.post("/setup/restore")
        assert response.status_code == 303
        response = client.post(
            "/unlock", data={"passphrase": PASSPHRASE, "next": "/"}
        )
        assert response.status_code == 303
        assert "Casey" in client.get("/people").text


def test_restore_refused_once_a_vault_exists(munlocked):
    # An initialized install must never let its data be silently replaced.
    response = munlocked.post("/setup/restore")
    assert response.status_code == 303
    assert response.headers["location"] == "/unlock"


def test_restore_refuses_cross_site_posts(mirror_settings):
    # Pre-session POSTs have no CSRF token to check, so they live or die on
    # the Sec-Fetch-Site guard — same as /setup and /setup/import.
    with _make_client(mirror_settings) as client:
        response = client.post(
            "/setup/restore", headers={"sec-fetch-site": "cross-site"}
        )
        assert response.status_code == 403


def test_setup_is_plain_when_nothing_to_restore(client):
    page = client.get("/setup")
    assert page.status_code == 200
    assert "Bring My Data Back" not in page.text


def test_restore_with_only_garbage_reports_and_offers_import(
    mirror_settings, tmp_path
):
    mirror_settings.mirror_dir.mkdir(parents=True)
    (mirror_settings.mirror_dir / "frostfile-auto-1.db").write_bytes(b"garbage")
    with _make_client(mirror_settings) as client:
        response = client.post("/setup/restore")
        assert response.status_code == 200
        assert "may have been damaged" in response.text
        assert "/setup/import" in response.text


# --- the Settings toggle ----------------------------------------------------


def test_settings_shows_mirror_and_toggles_it(munlocked, mirror_settings, monkeypatch):
    # Pin the re-enable target: the real ~/Documents may not exist on a CI box.
    monkeypatch.setattr(
        "frostfile.routes.settings_routes.default_mirror_dir",
        lambda: mirror_settings.mirror_dir,
    )
    page = munlocked.get("/settings")
    assert "Spare copies" in page.text
    assert "Stop Keeping Spare Copies" in page.text

    response = munlocked.post(
        "/settings/mirror",
        data={"enable": "0", "csrf_token": csrf_token(munlocked)},
    )
    assert "no new spare copies" in response.text.lower()
    prefs = config.read_prefs(mirror_settings.data_dir)
    assert prefs.get("mirror_backups") is False
    assert "Keep Spare Copies in Documents" in munlocked.get("/settings").text

    response = munlocked.post(
        "/settings/mirror",
        data={"enable": "1", "csrf_token": csrf_token(munlocked)},
    )
    assert "spare copies of your backups now go to" in response.text.lower()
    assert config.read_prefs(mirror_settings.data_dir).get("mirror_backups") is True
    assert (mirror_settings.mirror_dir / README_NAME).exists()
