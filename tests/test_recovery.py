"""Recovery codes: the only honest form of 'password reset'."""

from __future__ import annotations

import re

from conftest import PASSPHRASE, add_person, csrf_token

CODE_RE = re.compile(r"[A-Z2-9]{5}-[A-Z2-9]{5}-[A-Z2-9]{5}-[A-Z2-9]{5}")
NEW_PASSPHRASE = "an entirely different passphrase"


def _grab_code(client) -> str:
    page = client.get("/recovery-code")
    assert page.status_code == 200, "no pending recovery code to show"
    match = CODE_RE.search(page.text)
    assert match, "recovery code not found on page"
    return match.group(0)


def test_recovery_code_resets_the_passphrase(unlocked):
    code = _grab_code(unlocked)
    unlocked.post("/recovery-code/ack", data={"csrf_token": csrf_token(unlocked)})
    add_person(unlocked, "Recovered Person")
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})

    # Forgot the passphrase: the code, entered sloppily, still works.
    sloppy = code.replace("-", " ").lower()
    response = unlocked.post(
        "/recover",
        data={
            "code": sloppy,
            "new_passphrase": NEW_PASSPHRASE,
            "confirm": NEW_PASSPHRASE,
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/recovery-code"

    # A fresh code is issued; the used one is burned.
    new_code = _grab_code(unlocked)
    assert new_code != code
    unlocked.post("/recovery-code/ack", data={"csrf_token": csrf_token(unlocked)})

    # Data survives, the new passphrase works, the old ones don't.
    assert "Recovered Person" in unlocked.get("/people").text
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})

    old_pass = unlocked.post("/unlock", data={"passphrase": PASSPHRASE, "next": "/"})
    assert "did not open the vault" in old_pass.text
    old_code = unlocked.post(
        "/recover",
        data={"code": code, "new_passphrase": "x" * 16, "confirm": "x" * 16},
    )
    assert "did not open the vault" in old_code.text

    fresh = unlocked.post("/unlock", data={"passphrase": NEW_PASSPHRASE, "next": "/"})
    assert fresh.status_code == 303


def test_recovery_code_saves_to_a_file(unlocked, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code = _grab_code(unlocked)
    response = unlocked.post(
        "/recovery-code/save", data={"csrf_token": csrf_token(unlocked)}
    )
    assert response.status_code == 200
    saved = (tmp_path / "Identilock-Recovery-Code.txt").read_text()
    assert code in saved
    assert "Forgot your passphrase?" in saved


def test_letters_demand_a_fresh_address_check(unlocked):
    add_person(unlocked, "Dana Guardian")
    child_page = unlocked.post(
        "/people",
        data={
            "display_name": "Robin Child",
            "kind": "minor",
            "csrf_token": csrf_token(unlocked),
        },
    )
    child = int(child_page.headers["location"].rsplit("/", 1)[1])

    import re

    directory = unlocked.get("/agencies").text
    equifax = next(
        int(m.group(1))
        for m in re.finditer(r'href="/agencies/(\d+)">([^<]+)</a>', directory)
        if m.group(2).strip() == "Equifax"
    )
    letter = unlocked.get(f"/letters/{child}/{equifax}").text
    assert "parking lot" in letter
    assert "line by line" in letter
    # The printed checklist itself carries the check.
    assert "today, by you" in letter

    bulk = unlocked.get("/letters/all").text
    assert "no exceptions" in bulk


def test_recover_rejects_a_wrong_code(unlocked):
    unlocked.post("/recovery-code/ack", data={"csrf_token": csrf_token(unlocked)})
    unlocked.post("/lock", data={"csrf_token": csrf_token(unlocked)})
    response = unlocked.post(
        "/recover",
        data={
            "code": "AAAAA-BBBBB-CCCCC-DDDDD",
            "new_passphrase": NEW_PASSPHRASE,
            "confirm": NEW_PASSPHRASE,
        },
    )
    assert "did not open the vault" in response.text


def test_passphrase_change_reissues_the_code(unlocked):
    first = _grab_code(unlocked)
    unlocked.post("/recovery-code/ack", data={"csrf_token": csrf_token(unlocked)})

    response = unlocked.post(
        "/settings/passphrase",
        data={
            "current": PASSPHRASE,
            "new_passphrase": NEW_PASSPHRASE,
            "confirm": NEW_PASSPHRASE,
            "csrf_token": csrf_token(unlocked),
        },
    )
    assert response.headers["location"] == "/recovery-code"
    assert _grab_code(unlocked) != first


def test_settings_can_reissue_a_code(unlocked):
    unlocked.post("/recovery-code/ack", data={"csrf_token": csrf_token(unlocked)})
    response = unlocked.post(
        "/settings/recovery", data={"csrf_token": csrf_token(unlocked)}
    )
    assert response.headers["location"] == "/recovery-code"
    assert _grab_code(unlocked)
