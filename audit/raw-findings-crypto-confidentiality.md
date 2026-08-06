# FrostFile — Cryptography & Data Confidentiality Audit (raw finder output, pre-verification)

Baseline: commit 99b6967 (v0.2.0). This is the unverified finder report; the workflow's
adversarial verification pass filters/adjusts these. Kept verbatim for fix detail.

## HIGH

### H1 — A "burned" recovery code still fully decrypts up to ten auto-backups
db.py:332-338, routes/auth.py:28-49, templates/recovery_code.html:39-42
Recovery codes are single-use only w.r.t. the LIVE db; each weekly auto-backup carries its own
recovery_wrap for the code current when taken. A code the UI says "stops working" keeps opening
~10 weeks of snapshots (backups/frostfile-auto-*.db), each with SSNs + PINs. Fix: reword the
"stops working" claim to note old backups still open with the code current when made (mirror the
existing correct caveat about old passphrases/old backups).

### H2 — Recovery code AND full vault both written unprotected to the Desktop (a cloud-sync root)
routes/auth.py:113-161 (127-128,143), routes/settings_routes.py:229-258 (238-243)
recovery_code_save writes plaintext code to ~/Desktop/FrostFile-Recovery-Code.txt; make_move_kit
writes a full vault copy to ~/Desktop/FrostFile-move-<date>.db. Both default perms (0644), same dir.
(a) OneDrive KFM / iCloud Desktop sync => code + vault auto-upload to same account; one phished
password = both halves. (b) Shared Linux box w/ 0755 home => other local user reads both. Note
config.py:140-146 deliberately chmods the data dir 0700 — these Desktop writes get no chmod.
Fix: os.chmod(target,0o600) on both; don't co-locate; name the risk on the button.

### H3 — Transient unlocked-screen access => permanent vault access via recovery reissue
routes/settings_routes.py:216-226
POST /settings/recovery mints a NEW recovery code with only a live session + CSRF — unlike
/settings/passphrase it never asks for the current passphrase. 90 seconds at an unlocked desk =
photograph a fresh code = permanent access to live vault + all future backups. Fix: require current
passphrase (fresh db.unlock) before reissuing.

### H4 — Reminder titles/details stored plaintext, contradicting "learns no identities"
db.py:130-143 (schema), db.py:38-54 (ENCRYPTED_FIELDS), db.py:1-15 (docstring), repo.py:563-578,
routes/reminders.py:49-69
reminders.title and .detail are plain TEXT (sibling notes_enc IS encrypted). Users type names there
("Re-freeze Equifax for Robin"). Stolen db: SELECT title,detail,person_id FROM reminders => cleartext
+ join to family + people.kind (child/adult). Fix: add title_enc/detail_enc to ENCRYPTED_FIELDS + migrate,
or at minimum fix docstring + label the fields.

## MEDIUM
- M1 reports.source_name (upload filename) plaintext — bureau PDFs named with legal names. db.py:145-154, repo.py:634-648, reports.py:99
- M2 freeze_records.method is plaintext free-text box (sits above encrypted confirmation/pin). db.py:112-128, repo.py:428, freeze_detail.html:34
- M3 Raw report PDFs spooled to OS temp (>1MiB) in cleartext, contradicting reports.py:90-91 comment; MAX_UPLOAD_BYTES checked AFTER full read. reports.py:70
- M4 Tampering plaintext agencies table (is_builtin=0, address_verified=1, mail_address=attacker) makes letter gen mail SSNs to attacker; seed_agencies skips non-builtin so poison is permanent. db.py:84-110, seeds.py:960, letters.py:199-208, pdfletters.py:193, repo.py:219-222. Fix: MAC agency rows, or ignore is_builtin=0 for shipped slugs.
- M5 Unreadable field silently becomes permanent data destruction on next save: Vault.decrypt swallows InvalidTag->None; edit form round-trips None->NULL. crypto.py:142-150, freeze_detail.html:62, repo.py:441. Fix: distinguish absent vs unreadable in interactive paths (change_passphrase already uses raising open_sealed correctly).
- M6 Idle auto-lock never runs on its own; key resident for process life (lazy expiry only, no sweeper). security.py:64-74. Fix: threading.Timer / lifespan sweeper calling drop_all().
- M7 Crash between change_passphrase and set_recovery => has_recovery()=True but no working code. db.py:283-329 & 343-356. Fix: fold set_recovery into the change_passphrase transaction, or make has_recovery verify the wrap opens.
- M8 No secure_delete / VACUUM: unchecking "store full SSN" leaves old blob in freelist pages, still sealed under current key. db.py:181-195. Fix: PRAGMA secure_delete=ON.
- M9 Zip/PDF and .ics downloads leave permanent plaintext copies in ~/Downloads unwarned (SSNs, DOBs); PDF /Title embeds child name. .ics gets a warning, these don't. letters.py:142-167, letters_index.html:21-36, cli.py:143-147.

## LOW
- L1 KDF params read from unauthenticated meta (int() => DoS via huge memory_cost / ValueError). db.py:260-269,371-376. Clamp.
- L2 Ciphertext length leaks plaintext length (name length, PIN digit count, who opted into full SSN). crypto.py:85-91.
- L3 Warn against pasting the MASTER passphrase into the HIBP password box (prefix leak aids offline attack for someone holding the db). hibp.py:131-159, breaches.html:19-34.
- L4 POST /setup and /setup/import unauthenticated & CSRF-free; cross-origin POST to 127.0.0.1:8731 can claim an un-set-up vault. auth.py:68-96,231-276. Add CSRF / Origin / Sec-Fetch-Site check.
- L5 person_form.html:160 onsubmit confirm() — name HTML-escaped but not JS-escaped; O'Brien breaks the handler => delete submits WITHOUT confirm. Use |tojson or move out of attribute.
- L6 No Unicode normalization before KDF (NFD mac vs NFC win => different key on cross-machine move). crypto.py:69-78. unicodedata.normalize("NFC",...).
- L7 Nothing enforces ENCRYPTED_FIELDS covers every *_enc column (matches today; future drift => silent unreadable). Startup assert vs PRAGMA table_info.
- L8 Stale recovery wrap gives "code did not open the vault" (misleading vs wrong code). auth.py:209-211.
- L9 reports.py error query param reflected (escaped, no injection) — support-scam vector for this audience. reports.py:37,79.
- L10 Freeze PINs render into type="text" (visible in screenshots/screen-share), unlike masked SSN. freeze_detail.html:62.

## Verified CLEAN (finder's explicit non-findings)
AES-GCM (random 12B nonce per seal, no reuse path, 32B key enforced); AAD binding blocks cross-column
swap; Argon2id t=3/m=64MiB/p=4 above OWASP; verifier leaks nothing; recovery entropy 98.1 bits, CSPRNG,
documented alphabet; recovery wrap as strong as passphrase path AND check_verifier gate blocks
attacker-installed wrap; change_passphrase covers all 18 enc columns atomically w/ raising open_sealed;
full-SSN opt-out truly discards; no logging of secrets; HTTP no-store + security headers + CSP self-only;
network egress exactly hibp+linkcheck, both button-triggered, no SSRF (URLs not user-controlled);
loopback guard fails closed; cookies HttpOnly+SameSite=Strict; _safe_next blocks open redirect; DNS
rebind neutralized by cookie host-scoping + no CORS; prefs.json holds no secrets; PDF gen escapes via
saxutils + _safe_filename blocks traversal; session store single-session, key never persisted/logged;
data dir 0700 on POSIX.
