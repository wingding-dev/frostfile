"""SQLite schema, connection handling, and passphrase lifecycle.

What is encrypted and what is not
---------------------------------
Encrypted: names, dates of birth, SSNs, emails, phones, addresses, freeze
confirmation numbers, freeze PINs, free-text notes, reminder titles and details,
stored credit report text and filenames, and settings values. (The breach_checks
table remains in the schema for vaults created before v1.0.0, when the app could
run breach lookups itself; the app is now fully offline and never writes to it.)

Left in the clear: row ids, whether a person is an adult or a minor, freeze
statuses, the freeze "method" field, and action/due dates. These stay queryable
so the app can sort and filter in SQL. Someone who steals the database learns
"this household has two adults and three minors, frozen at these agencies on
these dates" but learns no identities. That trade is deliberate; if you would
rather not make it, the fix is to encrypt the whole file at the disk level too.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag

from .crypto import (
    KdfParams,
    Vault,
    check_verifier,
    generate_recovery_code,
    make_verifier,
    normalize_recovery_code,
    open_sealed,
    seal,
)

SCHEMA_VERSION = 1

# Every (table, column) holding ciphertext. Used to re-wrap on passphrase change,
# and as the single source of truth for "what is sensitive here".
ENCRYPTED_FIELDS: dict[str, tuple[str, ...]] = {
    "people": (
        "display_name_enc",
        "birth_date_enc",
        "ssn_enc",
        "ssn_last4_enc",
        "email_enc",
        "phone_enc",
        "address_enc",
        "notes_enc",
    ),
    "freeze_records": ("confirmation_enc", "pin_enc", "notes_enc"),
    "reminders": ("title_enc", "detail_enc", "notes_enc"),
    "reports": ("source_name_enc", "text_enc", "extracted_enc"),
    "breach_checks": ("email_enc", "result_enc"),
    "app_settings": ("value_enc",),
}


def context_for(table: str, column: str) -> str:
    """The AEAD associated data for a field. Must be stable across versions."""
    return f"{table}:{column}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value BLOB
);

CREATE TABLE IF NOT EXISTS people (
    id               INTEGER PRIMARY KEY,
    kind             TEXT NOT NULL CHECK (kind IN ('adult', 'minor')),
    sort_order       INTEGER NOT NULL DEFAULT 0,
    display_name_enc BLOB NOT NULL,
    birth_date_enc   BLOB,
    ssn_enc          BLOB,
    ssn_last4_enc    BLOB,
    email_enc        BLOB,
    phone_enc        BLOB,
    address_enc      BLOB,
    notes_enc        BLOB,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agencies (
    id                 INTEGER PRIMARY KEY,
    slug               TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    category           TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    why_it_matters     TEXT NOT NULL DEFAULT '',
    freeze_url         TEXT NOT NULL DEFAULT '',
    phone              TEXT NOT NULL DEFAULT '',
    mail_address       TEXT NOT NULL DEFAULT '',
    address_verified   INTEGER NOT NULL DEFAULT 0,
    source_url         TEXT NOT NULL DEFAULT '',
    citations_json     TEXT NOT NULL DEFAULT '{}',
    supports_online    INTEGER NOT NULL DEFAULT 1,
    supports_minor     INTEGER NOT NULL DEFAULT 0,
    minor_mail_only    INTEGER NOT NULL DEFAULT 1,
    expires_after_days INTEGER,
    thaw_procedure     TEXT NOT NULL DEFAULT '',
    notes              TEXT NOT NULL DEFAULT '',
    action_kind        TEXT NOT NULL DEFAULT 'act',
    action_note        TEXT NOT NULL DEFAULT '',
    protects           TEXT NOT NULL DEFAULT '',
    impact             INTEGER NOT NULL DEFAULT 0,
    is_builtin         INTEGER NOT NULL DEFAULT 1,
    is_active          INTEGER NOT NULL DEFAULT 1,
    sort_order         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS freeze_records (
    id                INTEGER PRIMARY KEY,
    person_id         INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    agency_id         INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    status            TEXT NOT NULL DEFAULT 'not_started',
    method            TEXT NOT NULL DEFAULT '',
    date_requested    TEXT,
    date_confirmed    TEXT,
    expires_on        TEXT,
    last_verified     TEXT,
    confirmation_enc  BLOB,
    pin_enc           BLOB,
    notes_enc         BLOB,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (person_id, agency_id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id             INTEGER PRIMARY KEY,
    person_id      INTEGER REFERENCES people(id) ON DELETE CASCADE,
    agency_id      INTEGER REFERENCES agencies(id) ON DELETE SET NULL,
    kind           TEXT NOT NULL DEFAULT 'custom',
    title          TEXT NOT NULL DEFAULT '',
    detail         TEXT NOT NULL DEFAULT '',
    title_enc      BLOB,
    detail_enc     BLOB,
    due_date       TEXT NOT NULL,
    recurrence     TEXT NOT NULL DEFAULT 'none',
    last_completed TEXT,
    is_active      INTEGER NOT NULL DEFAULT 1,
    notes_enc      BLOB,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY,
    person_id     INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    bureau        TEXT NOT NULL,
    pulled_on     TEXT NOT NULL,
    source_name   TEXT NOT NULL DEFAULT '',
    source_name_enc BLOB,
    text_enc      BLOB,
    extracted_enc BLOB,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breach_checks (
    id         INTEGER PRIMARY KEY,
    person_id  INTEGER REFERENCES people(id) ON DELETE CASCADE,
    email_enc  BLOB,
    checked_at TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hibp',
    result_enc BLOB
);

CREATE TABLE IF NOT EXISTS app_settings (
    key       TEXT PRIMARY KEY,
    value_enc BLOB
);

CREATE INDEX IF NOT EXISTS idx_freeze_person ON freeze_records(person_id);
CREATE INDEX IF NOT EXISTS idx_freeze_agency ON freeze_records(agency_id);
CREATE INDEX IF NOT EXISTS idx_reminder_due  ON reminders(due_date);
CREATE INDEX IF NOT EXISTS idx_reports_person ON reports(person_id, bureau, pulled_on);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    # check_same_thread=False because a connection is opened per request, and a
    # request can straddle two threads: FastAPI runs sync dependencies in a
    # worker thread while an `async def` handler body runs on the event loop.
    # The connection is still only ever touched by one request, and never by two
    # threads at once, so SQLite's serialized threading mode covers this.
    conn = sqlite3.connect(path, detect_types=0, check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Default (rollback journal) rather than WAL: this database is tiny and
        # single-user, and it means "copy the .db file while the app is closed"
        # is a complete backup — which is the instruction most people follow.
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA synchronous = FULL")
        # Overwrite freed content instead of leaving it in freelist pages, so a
        # deleted SSN or migrated-away plaintext does not linger in the file.
        conn.execute("PRAGMA secure_delete = ON")
    except BaseException:
        # sqlite3.connect() succeeds lazily even on a non-database file; the
        # first PRAGMA is what fails. Close before re-raising, or the leaked
        # handle keeps the file locked on Windows and it can't be deleted.
        conn.close()
        raise
    return conn


def _set_meta(conn: sqlite3.Connection, key: str, value: bytes) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _get_meta(conn: sqlite3.Connection, key: str) -> bytes | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def is_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if row is None:
        return False
    return _get_meta(conn, "verifier") is not None


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    """Additive migration: CREATE TABLE IF NOT EXISTS never alters existing
    tables, so columns added after the first release are bolted on here."""
    existing = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _ensure_column(conn, "agencies", "action_kind", "TEXT NOT NULL DEFAULT 'act'")
    _ensure_column(conn, "agencies", "action_note", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "agencies", "protects", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "agencies", "impact", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "reminders", "title_enc", "BLOB")
    _ensure_column(conn, "reminders", "detail_enc", "BLOB")
    _ensure_column(conn, "reports", "source_name_enc", "BLOB")
    conn.commit()


# Plaintext columns kept only to satisfy legacy NOT NULL and to hold pre-0.3
# data until it is migrated into the matching _enc column. New writes put ''
# here and the real value in the encrypted column.
_PLAINTEXT_TO_ENC = (
    ("reminders", "title", "title_enc"),
    ("reminders", "detail", "detail_enc"),
    ("reports", "source_name", "source_name_enc"),
)


def migrate_plaintext_fields(conn: sqlite3.Connection, vault: Vault) -> int:
    """Seal any pre-0.3 plaintext title/detail/source_name into its _enc column
    and blank the cleartext (secure_delete overwrites the freed bytes). Runs at
    unlock; idempotent — only touches rows whose _enc is still NULL."""
    moved = 0
    for table, plain, enc in _PLAINTEXT_TO_ENC:
        rows = conn.execute(
            f"SELECT id, {plain} AS val FROM {table} "
            f"WHERE {enc} IS NULL AND {plain} IS NOT NULL AND {plain} != ''"
        ).fetchall()
        for row in rows:
            sealed = vault.encrypt(context_for(table, enc), row["val"])
            conn.execute(
                f"UPDATE {table} SET {enc} = ?, {plain} = '' WHERE id = ?",
                (sealed, row["id"]),
            )
            moved += 1
    if moved:
        conn.commit()
    return moved


def initialize_vault(conn: sqlite3.Connection, passphrase: str) -> Vault:
    """Create the schema and establish the master passphrase."""
    from .crypto import derive_key

    create_schema(conn)
    params = KdfParams.generate()
    key = derive_key(passphrase, params)

    _set_meta(conn, "schema_version", str(SCHEMA_VERSION).encode())
    _set_meta(conn, "kdf_salt", params.salt)
    _set_meta(conn, "kdf_time_cost", str(params.time_cost).encode())
    _set_meta(conn, "kdf_memory_cost", str(params.memory_cost).encode())
    _set_meta(conn, "kdf_parallelism", str(params.parallelism).encode())
    _set_meta(conn, "verifier", make_verifier(key))
    _set_meta(conn, "created_at", utcnow().encode())
    conn.commit()
    return Vault(key)


def _clamped_int(raw: bytes | None, default: int, lo: int, hi: int) -> int:
    """Parse a meta integer, clamped to a sane range. A tampered file could
    otherwise set kdf_memory_cost to gigabytes and turn every unlock into an
    out-of-memory crash."""
    try:
        value = int((raw or str(default).encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return default
    return max(lo, min(hi, value))


def load_kdf_params(conn: sqlite3.Connection) -> KdfParams:
    salt = _get_meta(conn, "kdf_salt")
    if salt is None:
        raise RuntimeError("vault is not initialized")
    return KdfParams(
        salt=salt,
        time_cost=_clamped_int(_get_meta(conn, "kdf_time_cost"), 3, 1, 20),
        # 8 MiB .. 2 GiB (Argon2 memory_cost is in KiB).
        memory_cost=_clamped_int(
            _get_meta(conn, "kdf_memory_cost"), 65536, 8 * 1024, 2 * 1024 * 1024
        ),
        parallelism=_clamped_int(_get_meta(conn, "kdf_parallelism"), 4, 1, 16),
    )


def load_verifier(conn: sqlite3.Connection) -> bytes:
    verifier = _get_meta(conn, "verifier")
    if verifier is None:
        raise RuntimeError("vault is not initialized")
    return verifier


def unlock(conn: sqlite3.Connection, passphrase: str) -> Vault:
    return Vault.unlock(passphrase, load_kdf_params(conn), load_verifier(conn))


def change_passphrase(
    conn: sqlite3.Connection, current: Vault, new_passphrase: str
) -> tuple[Vault, str]:
    """Re-wrap every ciphertext under a key derived from the new passphrase, and
    issue a fresh recovery code — all in ONE transaction, so a crash can never
    leave the vault holding a recovery wrap of the retired key (a code that
    silently no longer opens anything). Returns (vault, new recovery code).

    Done in a single transaction: either every field moves to the new key or
    none does. A half-rewrapped database would be unrecoverable.
    """
    from .crypto import derive_key

    params = KdfParams.generate()
    new_key = derive_key(new_passphrase, params)

    try:
        conn.execute("BEGIN IMMEDIATE")
        for table, columns in ENCRYPTED_FIELDS.items():
            pk = "key" if table == "app_settings" else "id"
            rows = conn.execute(
                f"SELECT {pk} AS pk, {', '.join(columns)} FROM {table}"
            ).fetchall()
            for row in rows:
                updates: dict[str, bytes | None] = {}
                for column in columns:
                    blob = row[column]
                    if blob is None:
                        continue
                    ctx = context_for(table, column)
                    try:
                        plaintext = open_sealed(current.key, ctx, blob)
                    except (InvalidTag, ValueError):
                        # One corrupt field must not brick the whole passphrase
                        # change (and recovery). It is already unreadable; leave
                        # its bytes untouched and migrate everything else.
                        continue
                    updates[column] = seal(new_key, ctx, plaintext)
                if updates:
                    assignments = ", ".join(f"{c} = ?" for c in updates)
                    conn.execute(
                        f"UPDATE {table} SET {assignments} WHERE {pk} = ?",
                        (*updates.values(), row["pk"]),
                    )

        _set_meta(conn, "kdf_salt", params.salt)
        _set_meta(conn, "kdf_time_cost", str(params.time_cost).encode())
        _set_meta(conn, "kdf_memory_cost", str(params.memory_cost).encode())
        _set_meta(conn, "kdf_parallelism", str(params.parallelism).encode())
        _set_meta(conn, "verifier", make_verifier(new_key))
        # Reissue the recovery code in the SAME transaction as the re-wrap, so
        # the stored wrap always matches the current key.
        recovery_code = _write_recovery(conn, new_key)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return Vault(new_key), recovery_code


# ------------------------------------------------------------ recovery codes
#
# The recovery code is a second way to open the vault: an Argon2-derived key
# from the code wraps the CURRENT data key. Because a passphrase change
# re-encrypts every field under a new key, the old wrap goes stale — so every
# passphrase change (and every recovery) issues a fresh code and the old one
# stops working. The plaintext code itself is never stored.

_RECOVERY_CONTEXT = "meta:recovery_wrap"


def _write_recovery(conn: sqlite3.Connection, data_key: bytes) -> str:
    """Write a fresh recovery wrap into meta (no commit). Returns the code."""
    from .crypto import derive_key

    code = generate_recovery_code()
    params = KdfParams.generate()
    recovery_key = derive_key(normalize_recovery_code(code), params)
    _set_meta(conn, "recovery_salt", params.salt)
    _set_meta(conn, "recovery_time_cost", str(params.time_cost).encode())
    _set_meta(conn, "recovery_memory_cost", str(params.memory_cost).encode())
    _set_meta(conn, "recovery_parallelism", str(params.parallelism).encode())
    _set_meta(conn, "recovery_wrap", seal(recovery_key, _RECOVERY_CONTEXT, data_key))
    return code


def set_recovery(conn: sqlite3.Connection, data_key: bytes) -> str:
    """(Re)issue a recovery code for the current data key. Returns the code."""
    code = _write_recovery(conn, data_key)
    conn.commit()
    return code


def has_recovery(conn: sqlite3.Connection) -> bool:
    return _get_meta(conn, "recovery_wrap") is not None


def recover_data_key(conn: sqlite3.Connection, code: str) -> bytes | None:
    """The data key, if the code is right; None for a wrong or absent code."""
    from .crypto import derive_key

    salt = _get_meta(conn, "recovery_salt")
    wrap = _get_meta(conn, "recovery_wrap")
    if salt is None or wrap is None:
        return None
    params = KdfParams(
        salt=salt,
        time_cost=_clamped_int(_get_meta(conn, "recovery_time_cost"), 3, 1, 20),
        memory_cost=_clamped_int(
            _get_meta(conn, "recovery_memory_cost"), 65536, 8 * 1024, 2 * 1024 * 1024
        ),
        parallelism=_clamped_int(_get_meta(conn, "recovery_parallelism"), 4, 1, 16),
    )
    recovery_key = derive_key(normalize_recovery_code(code), params)
    try:
        data_key = open_sealed(recovery_key, _RECOVERY_CONTEXT, wrap)
    except Exception:
        return None
    if not check_verifier(data_key, load_verifier(conn)):
        return None
    return data_key


def backup_to(conn: sqlite3.Connection, destination: Path) -> Path:
    """Consistent copy of the database, safe to take while the app is running.

    Written to a temp file, integrity-checked, then renamed onto the final name,
    so a disk-full or interrupted copy never leaves a truncated file at the
    destination — which a later restore or the auto-backup freshness check would
    otherwise mistake for a good backup.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.parent / (destination.name + ".tmp")
    tmp.unlink(missing_ok=True)
    target = sqlite3.connect(tmp)
    try:
        with target:
            conn.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("backup failed its integrity check")
        target.close()
    except BaseException:
        target.close()
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, destination)
    return destination
