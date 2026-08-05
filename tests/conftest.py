from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from identilock.config import load_settings
from identilock.web import create_app

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def settings(tmp_path):
    return load_settings(data_dir=tmp_path / "data", host="127.0.0.1", port=8899)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def unlocked(client):
    """A client that has completed setup and holds an unlocked session."""
    response = client.post(
        "/setup",
        data={
            "passphrase": PASSPHRASE,
            "confirm": PASSPHRASE,
            "acknowledged": "1",
        },
    )
    assert response.status_code == 303, response.text
    return client


def csrf_token(client) -> str:
    """Pull the CSRF token out of any rendered page."""
    page = client.get("/people/new")
    assert page.status_code == 200
    marker = 'name="csrf_token" value="'
    start = page.text.index(marker) + len(marker)
    return page.text[start : page.text.index('"', start)]


def add_person(client, name: str, kind: str = "adult", **extra) -> int:
    payload = {
        "display_name": name,
        "kind": kind,
        "csrf_token": csrf_token(client),
        **extra,
    }
    response = client.post("/people", data=payload)
    assert response.status_code == 303, response.text
    return int(response.headers["location"].rsplit("/", 1)[1])
