"""HIBP client behaviour, without touching the network."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from frostfile.services import hibp


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def test_password_check_sends_only_a_hash_prefix(monkeypatch):
    password = "hunter2"
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(text=f"{suffix}:4821\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:1")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert hibp.check_password(password) == 4821

    # The URL carries the 5-character prefix and nothing else.
    assert captured["url"].endswith(f"/{prefix}")
    assert password not in captured["url"]
    assert suffix not in captured["url"]


def test_password_not_found_returns_zero(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: FakeResponse(text="FFFF:2\nEEEE:9")
    )
    assert hibp.check_password("a-unique-password") == 0


def test_email_check_requires_a_key():
    with pytest.raises(hibp.HibpError, match="No API key"):
        hibp.check_email("someone@example.com", "")


def test_email_404_means_no_breaches(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: FakeResponse(status_code=404))
    assert hibp.check_email("clean@example.com", "key") == []


def test_email_breaches_are_parsed(monkeypatch):
    payload = [
        {
            "Name": "Example",
            "Title": "Example Corp",
            "Domain": "example.com",
            "BreachDate": "2024-01-02",
            "AddedDate": "2024-02-03T00:00:00Z",
            "PwnCount": 1234,
            "Description": "Something leaked.",
            "DataClasses": ["Email addresses", "Passwords", "Social security numbers"],
        }
    ]
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: FakeResponse(json_data=payload)
    )
    breaches = hibp.check_email("someone@example.com", "key")
    assert len(breaches) == 1
    breach = breaches[0]
    assert breach.title == "Example Corp"
    assert breach.pwn_count == 1234
    assert breach.added_date == "2024-02-03"
    assert breach.exposed_credentials
    assert breach.exposed_government_id


def test_email_is_url_encoded(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(status_code=404)

    monkeypatch.setattr(httpx, "get", fake_get)
    hibp.check_email("first+tag@example.com", "key")
    assert "%2B" in captured["url"]
    assert "first+tag" not in captured["url"]


def test_bad_key_and_rate_limit_produce_clear_errors(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: FakeResponse(status_code=401))
    with pytest.raises(hibp.HibpError, match="rejected the API key"):
        hibp.check_email("a@example.com", "bad")

    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: FakeResponse(status_code=429, headers={"retry-after": "3"}),
    )
    with pytest.raises(hibp.HibpError, match="3 seconds"):
        hibp.check_email("a@example.com", "key")


def test_network_failure_is_reported_not_raised_raw(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(hibp.HibpError, match="Could not reach"):
        hibp.check_email("a@example.com", "key")
    with pytest.raises(hibp.HibpError, match="Could not reach"):
        hibp.check_password("anything")


def test_verify_key_reports_validity(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: FakeResponse(
            json_data={"SubscriptionName": "Pwned 1", "SubscribedUntil": "2027-01-01T00:00:00"}
        ),
    )
    ok, detail = hibp.verify_key("key")
    assert ok and "Pwned 1" in detail

    monkeypatch.setattr(httpx, "get", lambda url, **kw: FakeResponse(status_code=401))
    ok, detail = hibp.verify_key("bad")
    assert not ok and "rejected" in detail
