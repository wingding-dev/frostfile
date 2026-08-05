"""Passphrase-derived encryption for sensitive fields.

Threat model
------------
Protects against: someone who obtains a copy of the database file (stolen
laptop, a backup synced to cloud storage, a shared machine). Without the
passphrase, the sensitive fields are unreadable.

Does NOT protect against: malware running as you while the vault is unlocked,
or anyone who has your passphrase. The derived key lives in the server
process's memory for as long as the session is unlocked; Python offers no
reliable way to scrub it, so we shorten the exposure with an idle auto-lock
rather than pretending we can erase it.

Field values are sealed with AES-256-GCM. The associated data binds each
ciphertext to its table and column, so a tampered database cannot swap a
person's notes into the PIN column. It does not bind to a row id (that is not
known until after INSERT), so an attacker with write access to the file could
move ciphertext between rows of the same column. They still cannot read or
forge it, and any such swap is an integrity nuisance rather than a disclosure.
"""

from __future__ import annotations

import hmac
import os
import secrets
import unicodedata
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"IL1"
NONCE_BYTES = 12
KEY_BYTES = 32
SALT_BYTES = 16

# Tuned to be unpleasant for an offline cracker while staying tolerable on a
# five-year-old laptop, which is what a coworker is most likely running this on.
DEFAULT_TIME_COST = 3
DEFAULT_MEMORY_COST = 64 * 1024  # KiB
DEFAULT_PARALLELISM = 4

_VERIFIER_PLAINTEXT = b"identilock-vault-v1"
_VERIFIER_CONTEXT = "meta:verifier"


class VaultLocked(Exception):
    """Raised when a decryption is attempted without an unlocked vault."""


class WrongPassphrase(Exception):
    """Raised when the supplied passphrase does not open the vault."""


@dataclass(frozen=True)
class KdfParams:
    salt: bytes
    time_cost: int = DEFAULT_TIME_COST
    memory_cost: int = DEFAULT_MEMORY_COST
    parallelism: int = DEFAULT_PARALLELISM

    @classmethod
    def generate(cls) -> "KdfParams":
        return cls(salt=os.urandom(SALT_BYTES))


def derive_key(passphrase: str, params: KdfParams) -> bytes:
    # Normalize to NFC so an accented passphrase typed on macOS (NFD) and on
    # Windows (NFC) derives the same key — the app encourages moving the vault
    # between machines, and a normalization mismatch would be a silent lockout.
    passphrase = unicodedata.normalize("NFC", passphrase)
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=params.salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def _aad(context: str) -> bytes:
    return context.encode("utf-8")


def seal(key: bytes, context: str, plaintext: str | bytes) -> bytes:
    """Encrypt a value. `context` should be "table:column"."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _aad(context))
    return MAGIC + nonce + ciphertext


def open_sealed(key: bytes, context: str, blob: bytes) -> bytes:
    """Decrypt a value sealed with the same key and context."""
    if not blob.startswith(MAGIC):
        raise ValueError("not an Identilock ciphertext")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    ciphertext = blob[len(MAGIC) + NONCE_BYTES :]
    return AESGCM(key).decrypt(nonce, ciphertext, _aad(context))


def make_verifier(key: bytes) -> bytes:
    """A sealed sentinel used to check a passphrase without touching real data."""
    return seal(key, _VERIFIER_CONTEXT, _VERIFIER_PLAINTEXT)


def check_verifier(key: bytes, verifier: bytes) -> bool:
    try:
        opened = open_sealed(key, _VERIFIER_CONTEXT, verifier)
    except (InvalidTag, ValueError):
        return False
    return hmac.compare_digest(opened, _VERIFIER_PLAINTEXT)


class Vault:
    """Holds the derived key for the duration of an unlocked session."""

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError("unexpected key length")
        self._key = key

    @classmethod
    def unlock(cls, passphrase: str, params: KdfParams, verifier: bytes) -> "Vault":
        key = derive_key(passphrase, params)
        if not check_verifier(key, verifier):
            raise WrongPassphrase("passphrase did not open the vault")
        return cls(key)

    @property
    def key(self) -> bytes:
        return self._key

    def encrypt(self, context: str, plaintext: str | None) -> bytes | None:
        if plaintext is None or plaintext == "":
            return None
        return seal(self._key, context, plaintext)

    def decrypt(self, context: str, blob: bytes | None) -> str | None:
        if blob is None:
            return None
        try:
            return open_sealed(self._key, context, blob).decode("utf-8")
        except (InvalidTag, ValueError):
            # A field that will not open means the database was tampered with
            # or partially restored from a backup made under another passphrase.
            return None

    def readable(self, context: str, blob: bytes | None) -> bool:
        """True if the blob is absent (nothing to lose) or decrypts cleanly;
        False for a present-but-corrupt blob. Used to avoid overwriting
        recoverable ciphertext that merely failed to decrypt this session."""
        if blob is None:
            return True
        try:
            open_sealed(self._key, context, blob)
            return True
        except (InvalidTag, ValueError):
            return False


# Recovery codes: a second credential that can open the vault when the
# passphrase is forgotten. The code never leaves this machine — it is shown
# once for the user to print or write down, and only an Argon2-wrapped copy of
# the data key is stored. Losing both the passphrase AND the code still means
# the data is gone; that is the deal, and the UI says so.
#
# Alphabet drops 0/O, 1/I/L, and U (voice-confusable with V) so a code read
# over the phone or copied by hand cannot be mis-transcribed. 20 characters of
# a 30-letter alphabet is ~98 bits — far past brute force even before the KDF.
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
RECOVERY_LENGTH = 20


def generate_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
    return "-".join(raw[i : i + 5] for i in range(0, RECOVERY_LENGTH, 5))


def normalize_recovery_code(code: str) -> str:
    """Forgiving input: case, dashes, and spaces don't matter."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def passphrase_problems(passphrase: str) -> list[str]:
    """Cheap, honest feedback. Not a strength meter — length is what matters."""
    problems: list[str] = []
    if len(passphrase) < 12:
        problems.append("Use at least 12 characters. Longer beats complicated.")
    if passphrase.strip() != passphrase:
        problems.append("Leading or trailing spaces are easy to mistype later.")
    if passphrase.lower() in {"password", "identilock", "letmein", "123456789012"}:
        problems.append("That passphrase is guessable.")
    return problems
