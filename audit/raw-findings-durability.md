# Identilock — Data Durability Audit (raw finder output, pre-verification)

Baseline: commit 99b6967 (v0.2.0). Unverified finder report.

## CRITICAL

### C1 — Writes under a stale key after passphrase change permanently strand fields
db.py:283-329 (change_passphrase), security.py:53-62, web.py:32-43, cli.py:87-93
A request holding the OLD Vault can commit ciphertext sealed with the old key AFTER the rewrap
commits; old KDF salt is destroyed => fields permanently undecryptable.
Scenario A (two tabs, one instance): Tab B mid breach-check (multi-sec HIBP call, old Vault resolved);
Tab A completes /settings/passphrase (new salt/verifier overwrite old). B's save_breach_check seals
under old key & commits => decrypt returns None forever.
Scenario B (two instances): double-launch => _find_port silently uses 8732 on SAME data dir (no lock
file). Instance1 changes passphrase; instance2's in-memory session survives; every later edit writes
old-key ciphertext. Fix: meta generation counter checked at write time + data-dir lock file +
re-verify key vs current verifier before any encrypting write.

### C2 — SCHEMA_VERSION is write-only; version-skew rewrap strands newer columns
db.py:34 (defined), db.py:249 (written once, never read/bumped), db.py:38-54, db.py:283-329, web.py:89-99
Nothing checks schema version; older wheel opens newer db; its change_passphrase rewraps only columns
IT knows while destroying old salt. First future *_enc column addition => permanent silent loss if an
older build ever touches the same data dir + a passphrase change. Fix: read schema_version at connect;
refuse (or read-only) when db version > code version; bump on migration.

## HIGH

### H1 — Crash between change_passphrase and set_recovery => no valid recovery credential, silently
routes/auth.py:223-225, routes/settings_routes.py:207-209, db.py:324 vs 343-356
Two separate transactions; between them recovery_wrap wraps OLD key while verifier is new =>
recover_data_key rejects it => vault has NO working recovery code and the new one was never shown.
(dup of crypto M7). Fix: derive recovery key before BEGIN IMMEDIATE, do the wrap inside the txn.

### H2 — Dangling data_dir pointer silently creates fresh empty vault (setup screen)
config.py:96-105, config.py:140-146, web.py:89-99, routes/auth.py:61-65
Pointer target missing (unmounted USB, renamed folder, unsynced cloud path) => resolves to missing
dir w/ no existence check => ensure_data_dir recreates empty => is_initialized False => setup screen.
Non-technical user concludes data gone or creates a divergent second vault. Fix: if a pointer exists
but <target>/identilock.db absent, refuse setup; show "data folder not reachable."

### H3 — Pointer-chain cycle after round-trip move resolves to STALE directory
config.py:97-105 (loop breaks on cycle leaving resolved_dir at intermediate hop), settings_routes.py:141-153
Move A->B then B->A leaves A's prefs pointing at B; resolution terminates at B (stale). User may then
delete the CURRENT dir per on-screen instruction. Fix: when writing pointer at target, clear target's
own data_dir key; prefer last hop before a cycle.

### H4 — Auto-backup failure NOT swallowed (disk-full blocks unlocking) — contradicts design comment
routes/auth.py:28-49 (except OSError only), auth.py:311, db.py:387-396
backup_to raises sqlite3.OperationalError/DatabaseError (not OSError) on disk-full => propagates =>
aborts unlock w/ 500. Docstring promise ("full disk must not stop the vault opening") broken. Bonus:
partial identilock-auto-*.db left w/ fresh mtime => freshness check skips real backups 7 more days,
and newest backup is garbage. Fix: except (OSError, sqlite3.Error); delete partial target on failure.

### H5 — prefs.json written non-atomically; corruption silently drops the moved-data pointer
config.py:43-45 (truncate-in-place write_text, no tmp+rename/fsync), config.py:28-33 (corrupt=>{})
Crash during any prefs write corrupts JSON in old dir => pointer lost => app opens old pre-move
snapshot (unlocks w/ same passphrase!) => user sees stale data, may re-enter => permanent fork.
Fix: write prefs.json.tmp + fsync + os.replace.

## MEDIUM
- M1 Disk-full during manual backup/move-kit/data-dir move: raw 500 + poisonous partial file; retry hits exists() guard telling user to "move it out of the way." settings_routes.py:128-134,242-245,273
- M2 Failed/partial MANUAL backup suppresses auto-backups 7 days (freshness glob matches all identilock-*.db by mtime). auth.py:38-41
- M3 setup_import replace: other in-flight conns hold handles => Windows os.replace PermissionError => 500 + stranded .import-tmp (full vault image); async TOCTOU between is_initialized and replace. auth.py:274-275,242
- M4 setup_import never fsyncs scratch/dir around replace => power loss => torn db. auth.py:251,275
- M5 Move-data-dir under --data-dir/env writes a pointer never followed => UI says "will be used next start" but override wins forever; user edits stale copy, later deletes CURRENT dir. settings_routes.py:141-142, config.py:96
- M6 Corrupt db at startup = bare traceback, no mention of backups next to it. web.py:89-99, cli.py (no handler)

## LOW
- L1 change_passphrase contention window (long rewrap holds BEGIN IMMEDIATE; concurrent write => 5s timeout => 500). db.py:298-317
- L2 Two instances race prefs.json (read-modify-write, no lock, last-write-wins on pointer). config.py:36-45
- L3 Auto-backup retention ~70 days; stranded fields (C1/C2) propagate into every backup, never heal. auth.py:45-47

## Verified CLEAN (finder's explicit non-findings)
PRAGMA journal_mode=DELETE + synchronous=FULL genuinely set (complete-file-backup claim true);
change_passphrase single-process atomic (BEGIN IMMEDIATE, rollback on exception, kill-9 safe);
recover_data_key stale-wrap rejected via verifier (no wrong-key-decrypts-garbage path); backup_to
uses sqlite backup API (consistent snapshots); ensure_freeze_records single INSERT...WHERE NOT EXISTS
+ UNIQUE (no dup race); ordinary two-tab writes serialized by 5s busy timeout, conns closed in finally;
setup crash between initialize_vault and seed_agencies self-heals on restart; AEAD contexts stable;
auto-prune only touches identilock-auto-*, keeps 10, never deletes manual/last; foreign keys on.
