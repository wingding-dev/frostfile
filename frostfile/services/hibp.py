"""Have I Been Pwned lookups.

One of two places FrostFile touches the network (the other is the Sources
link checker in services/linkcheck.py); both act only when you press a button.

Two very different endpoints live here:

``check_password``
    Free, no key, and your password never leaves the machine. It is hashed
    locally, only the first five characters of the hash are sent, and matching
    happens against the block of hash suffixes that come back. This is the
    k-anonymity model HIBP documents.

``check_email``
    Requires a paid API key that you supply yourself. This one does send the
    email address to HIBP, because there is no way to ask the question without
    it. Nothing is sent until a key is configured.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

API_ROOT = "https://haveibeenpwned.com/api/v3"
PASSWORD_RANGE_URL = "https://api.pwnedpasswords.com/range"
USER_AGENT = "FrostFile-local-tracker"
TIMEOUT = httpx.Timeout(20.0)

SUBSCRIPTION_URL = "https://haveibeenpwned.com/Subscription"


class HibpError(Exception):
    """A lookup failed in a way worth showing the user verbatim."""


@dataclass
class Breach:
    name: str
    title: str
    domain: str
    breach_date: str
    added_date: str
    pwn_count: int
    description: str
    data_classes: list[str] = field(default_factory=list)
    is_verified: bool = True
    is_sensitive: bool = False

    @property
    def exposed_credentials(self) -> bool:
        return any(
            "password" in cls.lower() or "credential" in cls.lower()
            for cls in self.data_classes
        )

    @property
    def exposed_government_id(self) -> bool:
        needles = ("social security", "government issued ids", "passport", "tax")
        return any(n in cls.lower() for cls in self.data_classes for n in needles)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "domain": self.domain,
            "breach_date": self.breach_date,
            "added_date": self.added_date,
            "pwn_count": self.pwn_count,
            "description": self.description,
            "data_classes": self.data_classes,
            "is_verified": self.is_verified,
            "is_sensitive": self.is_sensitive,
        }


def _breach_from_api(payload: dict[str, Any]) -> Breach:
    return Breach(
        name=payload.get("Name", ""),
        title=payload.get("Title", payload.get("Name", "")),
        domain=payload.get("Domain", ""),
        breach_date=payload.get("BreachDate", ""),
        added_date=payload.get("AddedDate", "")[:10],
        pwn_count=int(payload.get("PwnCount") or 0),
        description=payload.get("Description", ""),
        data_classes=list(payload.get("DataClasses") or []),
        is_verified=bool(payload.get("IsVerified", True)),
        is_sensitive=bool(payload.get("IsSensitive", False)),
    )


def check_email(email: str, api_key: str) -> list[Breach]:
    """Breaches an address appears in. Empty list means none known."""
    if not api_key:
        raise HibpError(
            "No API key configured. Email lookups are a paid HIBP feature; add "
            "your own key in Settings."
        )

    # Addresses contain characters (+, and occasionally #) that must not be
    # read as URL syntax.
    account = quote(email.strip(), safe="")
    try:
        response = httpx.get(
            f"{API_ROOT}/breachedaccount/{account}",
            params={"truncateResponse": "false"},
            headers={"hibp-api-key": api_key, "user-agent": USER_AGENT},
            timeout=TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise HibpError(f"Could not reach Have I Been Pwned: {exc}") from exc

    if response.status_code == 404:
        # HIBP signals "clean" with a 404, which is not an error.
        return []
    if response.status_code == 401:
        raise HibpError("HIBP rejected the API key. Check it in Settings.")
    if response.status_code == 429:
        retry = response.headers.get("retry-after", "a few")
        raise HibpError(f"Rate limited by HIBP. Try again in {retry} seconds.")
    if response.status_code != 200:
        raise HibpError(f"HIBP returned HTTP {response.status_code}.")

    return [_breach_from_api(item) for item in response.json()]


def check_password(password: str) -> int:
    """How many times a password appears in known breaches. 0 is good.

    The password itself is never transmitted — only the first five characters
    of its SHA-1 hash, which match tens of thousands of other hashes.
    """
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]

    try:
        response = httpx.get(
            f"{PASSWORD_RANGE_URL}/{prefix}",
            headers={"user-agent": USER_AGENT, "Add-Padding": "true"},
            timeout=TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise HibpError(f"Could not reach the Pwned Passwords service: {exc}") from exc

    if response.status_code != 200:
        raise HibpError(f"Pwned Passwords returned HTTP {response.status_code}.")

    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix:
            try:
                return int(count)
            except ValueError:
                return 1
    return 0


def verify_key(api_key: str) -> tuple[bool, str]:
    """Cheap validity check so Settings can confirm a key before it is saved."""
    try:
        response = httpx.get(
            f"{API_ROOT}/subscription/status",
            headers={"hibp-api-key": api_key, "user-agent": USER_AGENT},
            timeout=TIMEOUT,
        )
    except httpx.RequestError as exc:
        return False, f"Could not reach Have I Been Pwned: {exc}"

    if response.status_code == 200:
        try:
            data = response.json()
            name = data.get("SubscriptionName", "active")
            until = data.get("SubscribedUntil", "")[:10]
            return True, f"Key is valid — {name} subscription through {until}."
        except ValueError:
            return True, "Key is valid."
    if response.status_code == 401:
        return False, "HIBP rejected that key."
    return False, f"HIBP returned HTTP {response.status_code}."
