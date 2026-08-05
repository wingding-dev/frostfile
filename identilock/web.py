"""Application factory, template environment, and shared dependencies."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, db
from . import sources as source_registry
from .config import Settings, ensure_data_dir
from .crypto import Vault
from .security import Session, SessionStore, current_session
from .seeds import (
    ACTION_KIND_LABELS,
    CATEGORY_LABELS,
    FREEZE_CATEGORIES,
    STATUS_ORDER,
    status_label,
)

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """A fresh connection per request.

    SQLite connections are not shareable across threads, and FastAPI runs sync
    handlers in a threadpool. Opening per request is cheap here and avoids
    needing a lock around every query.
    """
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_session(request: Request) -> Session:
    session = current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="locked")
    return session


def get_vault(session: Session = Depends(get_session)) -> Vault:
    return session.vault


def create_app(settings: Settings) -> FastAPI:
    ensure_data_dir(settings)

    app = FastAPI(
        title="Identilock",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.sessions = SessionStore(settings.lock_timeout_minutes)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals.update(
        app_version=__version__,
        action_kind_labels=ACTION_KIND_LABELS,
        category_labels=CATEGORY_LABELS,
        freeze_categories=FREEZE_CATEGORIES,
        status_order=STATUS_ORDER,
        status_label=status_label,
        # Lets any template cite a standalone claim, not just an agency field:
        #   {{ cite(citer, refs('ftc-fcra')) }}
        refs=lambda *keys: source_registry.resolve(list(keys)),
    )
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # An existing vault gets its schema brought up to date and its built-in
    # agency rows refreshed, so a corrected address reaches installs that were
    # set up before the fix. A brand-new database is left alone until setup
    # establishes a passphrase.
    conn = db.connect(settings.db_path)
    try:
        if db.is_initialized(conn):
            from .repo import backfill_all_freeze_records
            from .seeds import seed_agencies

            db.create_schema(conn)
            seed_agencies(conn)
            backfill_all_freeze_records(conn)
    finally:
        conn.close()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/static"):
            # Without this, locking the vault still leaves SSNs and freeze PINs
            # one Back button away in the browser's cache.
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Everything is served from this origin; nothing external is fetched.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self' 'unsafe-inline'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(HTTPException)
    async def redirect_when_locked(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            target = request.url.path
            if request.method != "GET":
                target = "/"
            return RedirectResponse(f"/unlock?next={target}", status_code=303)
        if exc.status_code == 303 and "Location" in (exc.headers or {}):
            return RedirectResponse(exc.headers["Location"], status_code=303)
        return app.state.templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    from .routes import (
        auth,
        breaches,
        dashboard,
        freezes,
        letters,
        people,
        reminders,
        reports,
        settings_routes,
    )

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(people.router)
    app.include_router(freezes.router)
    app.include_router(letters.router)
    app.include_router(reminders.router)
    app.include_router(reports.router)
    app.include_router(breaches.router)
    app.include_router(settings_routes.router)

    return app


class Citer:
    """Assigns page-local footnote numbers to sources as they are referenced.

    Templates call ``citer.mark(...)`` inline, which returns the numbers to
    print as superscripts, and the base template lists everything collected at
    the bottom of the page. Because Jinja renders the content block before the
    footer, the list is complete by the time it is printed.
    """

    def __init__(self) -> None:
        self._order: list[Any] = []
        self._numbers: dict[str, int] = {}

    def mark(self, refs: list[Any]) -> list[tuple[int, Any]]:
        marked = []
        for source in refs:
            if source.key not in self._numbers:
                self._order.append(source)
                self._numbers[source.key] = len(self._order)
            marked.append((self._numbers[source.key], source))
        return marked

    @property
    def entries(self) -> list[tuple[int, Any]]:
        return list(enumerate(self._order, start=1))

    @property
    def used(self) -> bool:
        return bool(self._order)


def render(
    request: Request, template: str, context: dict[str, Any] | None = None, **extra: Any
) -> HTMLResponse:
    """Render with the bits every page needs already filled in."""
    payload: dict[str, Any] = dict(context or {})
    payload.update(extra)
    session = current_session(request)
    payload.setdefault("session", session)
    payload.setdefault("csrf_token", session.csrf if session else "")
    payload.setdefault("lock_minutes", request.app.state.sessions.timeout_minutes)
    payload.setdefault("citer", Citer())
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, template, payload)


def redirect(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(path, status_code=status_code)
