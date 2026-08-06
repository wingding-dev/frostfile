"""Session handling, idle auto-lock, and CSRF.

The vault key exists only inside a Session object in this process's memory.
Locking — whether by button or by idle timeout — drops the reference, and from
that point the database on disk is just ciphertext again.

Sessions are deliberately in-memory only: restarting the app locks the vault.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from .crypto import Vault

COOKIE_NAME = "frostfile_session"
CSRF_FIELD = "csrf_token"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    token: str
    vault: Vault
    csrf: str
    last_seen: datetime = field(default_factory=_now)
    # A freshly issued recovery code, held in memory only until the user
    # confirms they saved it. Never written anywhere.
    pending_recovery_code: str | None = None


class SessionStore:
    def __init__(self, timeout_minutes: int) -> None:
        self._sessions: dict[str, Session] = {}
        self._timeout = timedelta(minutes=timeout_minutes)

    @property
    def timeout_minutes(self) -> int:
        return int(self._timeout.total_seconds() // 60)

    def set_timeout(self, minutes: int) -> None:
        """Applied immediately, including to the session that changed it."""
        self._timeout = timedelta(minutes=max(1, minutes))

    def create(self, vault: Vault) -> Session:
        # Only ever one user, so a new unlock replaces any prior session.
        self._sessions.clear()
        session = Session(
            token=secrets.token_urlsafe(32),
            vault=vault,
            csrf=secrets.token_urlsafe(32),
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if _now() - session.last_seen > self._timeout:
            self._sessions.pop(token, None)
            return None
        session.last_seen = _now()
        return session

    def drop(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def drop_all(self) -> None:
        self._sessions.clear()

    def seconds_remaining(self, token: str | None) -> int:
        session = self._sessions.get(token or "")
        if session is None:
            return 0
        remaining = self._timeout - (_now() - session.last_seen)
        return max(0, int(remaining.total_seconds()))


def current_session(request: Request) -> Session | None:
    store: SessionStore = request.app.state.sessions
    return store.get(request.cookies.get(COOKIE_NAME))


def require_session(request: Request) -> Session:
    session = current_session(request)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/unlock?next=" + request.url.path},
        )
    return session


def verify_csrf(session: Session, submitted: str | None) -> None:
    if not submitted or not hmac.compare_digest(submitted, session.csrf):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This form expired or came from another page. Go back and retry.",
        )


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="strict",
        # No Secure flag: this is served over plain HTTP on loopback, where a
        # Secure cookie would simply never be sent back.
        secure=False,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
