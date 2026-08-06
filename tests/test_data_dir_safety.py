"""Audit fix: moved-data pointer must not strand the vault or write to a dead path."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from frostfile.config import load_settings
from frostfile.web import create_app


def test_atomic_prefs_write_leaves_no_partial(tmp_path):
    from frostfile.config import read_prefs, write_prefs

    write_prefs(tmp_path, lock_minutes=30, data_dir=str(tmp_path / "x"))
    assert not (tmp_path / "prefs.json.tmp").exists()
    assert read_prefs(tmp_path)["lock_minutes"] == 30


def test_dangling_pointer_flags_unreachable_not_fresh_setup(tmp_path):
    # An old default dir points at a target that does not exist (unplugged USB).
    home = tmp_path / "home"
    home.mkdir()
    missing = tmp_path / "usb" / "FrostFile"  # never created
    (home / "prefs.json").write_text(json.dumps({"data_dir": str(missing)}))

    # A default launch (no explicit data_dir) resolves from the default dir and
    # follows the pointer; point the default at `home` for the test.
    from frostfile import config

    orig = config.default_data_dir
    config.default_data_dir = lambda: home
    try:
        s = config.load_settings(host="127.0.0.1", port=8811)
    finally:
        config.default_data_dir = orig

    assert s.data_unreachable is True
    assert not (missing / "frostfile.db").exists()  # nothing created at dead path

    # The app comes up warning, never offering a fresh setup, and creates no file.
    app = create_app(s)
    with TestClient(app, base_url="http://127.0.0.1", follow_redirects=True) as client:
        page = client.get("/setup")
        assert page.status_code == 503
        assert "Can't Find Your Data" in page.text
    assert not (missing / "frostfile.db").exists()
