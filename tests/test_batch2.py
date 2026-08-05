"""Second feedback batch: onboarding landing, protects labels, move kit."""

from __future__ import annotations

from fastapi.testclient import TestClient

from identilock.config import load_settings
from identilock.web import create_app

from conftest import PASSPHRASE, add_person, csrf_token


def test_setup_shows_recovery_code_then_lands_on_dashboard(client):
    response = client.post(
        "/setup",
        data={"passphrase": PASSPHRASE, "confirm": PASSPHRASE, "acknowledged": "1"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/recovery-code"

    page = client.get("/recovery-code")
    assert page.status_code == 200
    assert "Your Recovery Code" in page.text

    ack = client.post("/recovery-code/ack", data={"csrf_token": csrf_token(client)})
    assert ack.headers["location"] == "/"
    # Shown once: after acknowledging, the page no longer exists to revisit.
    assert client.get("/recovery-code").headers["location"] == "/"


def test_grid_and_next_actions_say_what_each_item_gets_you(unlocked):
    add_person(unlocked, "Grid Person")
    matrix = unlocked.get("/matrix").text
    assert "Blocks new loans &amp; credit cards" in matrix
    assert "Blocks new phone, cable &amp; utility accounts" in matrix

    dashboard = unlocked.get("/").text
    assert "What It Gets You" in dashboard
    assert "Blocks new loans &amp; credit cards" in dashboard


def test_impact_and_effort_shown(unlocked):
    add_person(unlocked, "Ranked Person")
    directory = unlocked.get("/agencies").text
    assert "High impact" in directory
    assert "Nice to have" in directory
    assert "Minutes, online" in directory

    dashboard = unlocked.get("/").text
    assert "High impact" in dashboard
    # The undo-fear antidote is stated up front.
    assert "lifting" in dashboard and "free" in dashboard


def test_help_page_covers_portability(unlocked):
    page = unlocked.get("/help").text
    assert "new computer" in page
    assert "Package Everything for the Move" in page


def test_dashboard_scope_table_replaces_paragraph(unlocked):
    add_person(unlocked, "Someone")
    page = unlocked.get("/").text
    assert "What This App Does — and Doesn&#39;t" in page or "and Doesn't" in page
    assert "Doesn't watch your credit for you" in page


def test_move_kit_export_and_import_round_trip(
    unlocked, settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    add_person(unlocked, "Mover Person")

    response = unlocked.post(
        "/settings/move-kit", data={"csrf_token": csrf_token(unlocked)}
    )
    assert response.status_code == 200
    kits = list(tmp_path.glob("Identilock-move-*.db"))
    assert len(kits) == 1

    # "New computer": a fresh app with an empty data dir accepts the kit.
    new_settings = load_settings(
        data_dir=tmp_path / "new-pc", host="127.0.0.1", port=8898
    )
    new_app = create_app(new_settings)
    with TestClient(new_app, base_url="http://127.0.0.1", follow_redirects=False) as new_client:
        imported = new_client.post(
            "/setup/import",
            files={"upload": ("move.db", kits[0].read_bytes(), "application/octet-stream")},
        )
        assert imported.status_code == 303
        assert imported.headers["location"] == "/unlock"

        unlocked_new = new_client.post(
            "/unlock", data={"passphrase": PASSPHRASE, "next": "/"}
        )
        assert unlocked_new.status_code == 303
        assert "Mover Person" in new_client.get("/people").text


def test_setup_import_rejects_a_non_database_file(client):
    response = client.post(
        "/setup/import",
        files={"upload": ("junk.db", b"this is not a database", "application/octet-stream")},
    )
    assert response.status_code == 200
    assert "not an Identilock move file" in response.text


def test_setup_import_refused_once_a_vault_exists(unlocked):
    response = unlocked.post(
        "/setup/import",
        files={"upload": ("junk.db", b"whatever", "application/octet-stream")},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/unlock"
