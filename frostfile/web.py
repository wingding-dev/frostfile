"""Application factory, template environment, and shared dependencies."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import starlette.formparsers
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
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
    settings = request.app.state.settings
    if settings.data_unreachable:
        # Do not open (and thereby create) a database at the dangling path.
        raise HTTPException(status_code=503, detail="data_unreachable")
    conn = db.connect(settings.db_path)
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


# Largest multipart body we will accept (credit-report upload, move-file import).
# The upload cap is 25 MB of decoded content; allow headroom for encoding.
MAX_UPLOAD_BODY_BYTES = 30 * 1024 * 1024
_UPLOAD_PATHS = {"/reports", "/setup/import"}

# Host names this loopback server will answer to. Anything else is a rebinding
# attempt or a misconfiguration. (The test client uses 127.0.0.1.)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", ""}

# Pre-auth mutating endpoints have no session to carry a CSRF token, so they are
# guarded by rejecting cross-site requests via the Sec-Fetch-Site header that
# every modern browser sends. A malicious page's form POST arrives as
# "cross-site"; a legitimate navigation is "same-origin" or "none".
_ORIGIN_GUARDED = {"/setup", "/setup/import"}

# Keep accepted uploads entirely in memory. Starlette otherwise spools any file
# part over 1 MB to a cleartext OS temp file — which for a credit-report PDF is
# a plaintext SSN written to disk. Raising the threshold above the body cap
# means an accepted upload never rolls to disk; the middleware below bounds RAM.
starlette.formparsers.MultiPartParser.spool_max_size = MAX_UPLOAD_BODY_BYTES + (1 << 20)


def create_app(settings: Settings) -> FastAPI:
    # When the real data folder is unreachable (a moved-data pointer to an
    # unplugged drive), do NOT create directories or a database at the dangling
    # path — that would mask the problem behind a fresh empty vault. The app
    # comes up in a warn-only state (see the setup route).
    if not settings.data_unreachable:
        ensure_data_dir(settings)

    app = FastAPI(
        title="FrostFile",
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
    # establishes a passphrase. Skipped entirely when the data folder is
    # unreachable, so db.connect never creates an empty file at the dead path.
    conn = None if settings.data_unreachable else db.connect(settings.db_path)
    try:
        if conn is not None and db.is_initialized(conn):
            from .repo import backfill_all_freeze_records
            from .seeds import seed_agencies

            db.create_schema(conn)
            seed_agencies(conn)
            backfill_all_freeze_records(conn)
    finally:
        if conn is not None:
            conn.close()

    @app.middleware("http")
    async def check_host(request: Request, call_next):
        # DNS-rebinding defense: a remote page can resolve its own name to
        # 127.0.0.1 and reach this server, but the browser sends that foreign
        # name in the Host header. Only serve requests whose Host is a local
        # name, so a rebound origin gets nothing.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host and host not in _ALLOWED_HOSTS:
            return PlainTextResponse("Bad Host header.", status_code=400)
        if request.method == "POST" and request.url.path in _ORIGIN_GUARDED:
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site and fetch_site not in {"same-origin", "none"}:
                return PlainTextResponse("Cross-site request refused.", status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def limit_upload_body(request: Request, call_next):
        # Reject an oversized upload before the body is read or spooled, so a
        # huge file never touches disk or RAM.
        if request.method == "POST" and request.url.path in _UPLOAD_PATHS:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_UPLOAD_BODY_BYTES:
                if request.url.path == "/reports":
                    return RedirectResponse(
                        "/reports?error=That+file+is+too+large.", status_code=303
                    )
                return PlainTextResponse("That file is too large.", status_code=413)
        return await call_next(request)

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
        if exc.status_code == 503 and exc.detail == "data_unreachable":
            return app.state.templates.TemplateResponse(
                request,
                "data_unreachable.html",
                {"data_dir": str(app.state.settings.data_dir)},
                status_code=503,
            )
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
