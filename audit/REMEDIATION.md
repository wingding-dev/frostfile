# Identilock — Audit Remediation Summary

Baseline: commit 99b6967 (v0.2.0). All 36 verified findings addressed across
three commit passes. Test suite grew from 101 → 128 (27 new tests, all green).

See CONSOLIDATED-verified.md for the full finding detail; this maps each fixed.

## Pass 1 — Confidentiality & data-loss (HIGH + data-loss MED)

| Finding | Fix | Commit |
| --- | --- | --- |
| Reminder title/detail plaintext; report filename plaintext | Encrypted (title_enc/detail_enc/source_name_enc), migrated on unlock, secure_delete on | reminder/report encryption |
| Uploaded report PDF spooled to plaintext temp file | Raised multipart spool threshold above cap; reject oversized body before parse | uploads-in-memory |
| "Move my data" keeps writing to old folder | Swap live app.state.settings to new dir; clear stale target pointer | data-dir move |
| Moved-data pointer strands vault / silent fresh setup | "Data folder not reachable" page; get_conn refuses to create at dead path; atomic prefs | pointer guard |
| Auto-backup catches only OSError; poisons backup set | Atomic backup_to (tmp+integrity_check+rename); catch sqlite errors everywhere | atomic backups |
| Corrupt ciphertext nulled on next save | _preserve_unreadable keeps present-but-unreadable bytes | preserve unreadable |
| Recovery re-wrap separate txn → dead code after crash | Folded into change_passphrase transaction; returns (vault, code) | recovery in txn |
| One corrupt field bricks passphrase change/recovery | change_passphrase skips corrupt fields, migrates the rest | hardening (P3 tail) |

## Pass 2 — Honesty of claims + DoS

| Finding | Fix |
| --- | --- |
| "Only breach page touches network" (4 places) | Settings list, FAQ, breaches, setup, README, docstrings now name linkcheck + key validation |
| FAQ "sends no personal information" | Corrected: email check does send the address |
| "Everything encrypted / gibberish without passphrase" | Softened to true field-level picture (structure readable, identities not) |
| Recovery "not saved anywhere readable" vs Desktop button | Reworded to note the print/save copies |
| TransUnion "agency's own paperwork" | "verified at a primary source" |
| "mail-only" vs LexisNexis online | Scoped to the three big bureaus |
| PDF packets drop citations/? markers | PDF now names sources and flags uncited fields |
| FYI rows count on Family page | People-page progress excludes FYI + not_applicable (matches dashboard) |
| Catastrophic-backtracking HTML strip (DoS) | Linear finditer scan; line-length cap |
| effort_label / link-check green-tag / editorial one-liners | Corrected wording and neutral "link works" tag |

## Pass 3 — Hardening (LOW + surface MED)

DNS-rebind Host-header check; cross-site guard on pre-auth /setup and
/setup/import (Sec-Fetch-Site); freeze_save 404 (not 500) on bad ids; safe int
parse for breach person_id; KDF params clamped against tampering; passphrase
NFC-normalized (cross-OS move safety); recovery-code and move files written
0600; pypdf extraction bounded against decompression bombs; link-check
User-Agent no longer announces the product; delete-confirm JS-escaped;
PRAGMA secure_delete on.

## Consciously not changed in code (documented instead)

- **Freeze "method" field stays plaintext** — it's a short "online/phone/mail"
  value; disclosed in the db docstring and a UI hint points sensitive text to
  the encrypted Notes field.
- **CSP keeps 'unsafe-inline'** for scripts — required by the inline print/nav
  handlers; compensating controls (no external connect-src/img-src/form-action,
  autoescape on, no proven XSS vector) make removal high-risk, low-reward.
- **Idle auto-lock leaves the key in process memory until a request evicts the
  session** — the verifier rejected this as reachable only under the
  out-of-scope "malware with unlocked vault" threat model.
