"""Audit fix: backups are atomic and failures never block unlock or poison the set."""

from __future__ import annotations

import sqlite3

import pytest

from conftest import PASSPHRASE, add_person, csrf_token


def test_backup_is_atomic_no_partial_on_failure(unlocked, settings, monkeypatch):
    from frostfile import db

    add_person(unlocked, "Backup Person")
    conn = db.connect(settings.db_path)

    # Make the underlying copy raise mid-way, as a full disk would.
    class _Boom:
        def __getattr__(self, name):
            raise sqlite3.OperationalError("database or disk is full")

    real_connect = sqlite3.connect

    def fake_connect(path, *a, **k):
        if str(path).endswith(".tmp"):
            return _Boom()
        return real_connect(path, *a, **k)

    monkeypatch.setattr(db.sqlite3, "connect", fake_connect)
    try:
        dest = settings.backup_dir / "frostfile-auto-fail.db"
        with pytest.raises(Exception):
            db.backup_to(conn, dest)
        assert not dest.exists()
        assert not (settings.backup_dir / "frostfile-auto-fail.db.tmp").exists()
    finally:
        conn.close()


def _fail_backup(monkeypatch):
    from frostfile import db

    def boom(conn, destination):
        raise sqlite3.OperationalError("disk full")

    # Patch the name each caller actually looks up.
    monkeypatch.setattr("frostfile.routes.auth.db.backup_to", boom)
    monkeypatch.setattr("frostfile.routes.settings_routes.db.backup_to", boom)


def test_auto_backup_failure_does_not_block_unlock(unlocked, settings, monkeypatch):
    add_person(unlocked, "Person")
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    for f in settings.backup_dir.glob("*.db"):
        f.unlink()
    _fail_backup(monkeypatch)

    response = unlocked.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    assert response.status_code == 303  # unlock still succeeds despite backup failure
    assert "Person" in unlocked.get("/people").text


def test_manual_backup_reports_failure_cleanly(unlocked, monkeypatch):
    _fail_backup(monkeypatch)
    response = unlocked.post(
        "/settings/backup", data={"csrf_token": csrf_token(unlocked)}
    )
    assert response.status_code == 200
    assert "Could not write the backup" in response.text
