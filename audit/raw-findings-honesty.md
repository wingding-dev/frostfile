# FrostFile — Honesty of Claims Audit (raw finder output, pre-verification)

Baseline: commit 99b6967 (v0.2.0). Unverified finder report.

## Outbound-network ground truth
1. hibp.py:141 check_password -> api.pwnedpasswords.com/range/{5-char SHA1 prefix} (button)
2. hibp.py:108 check_email -> haveibeenpwned.com (sends email; needs key); looped by "Check Whole Family" using STORED emails (breaches.py:117-125)
3. hibp.py:165 verify_key -> HIBP subscription/status when a key is SAVED (settings_routes.py:172)
4. linkcheck.py:29-48 -> HEAD/GET all ~31 sources.py URLs, "Check All Links Now" (dashboard.py:165-177)
5. Local only: webbrowser.open, pywebview, loopback uvicorn. No telemetry/analytics/update checks.

## HIGH

### H1 — "Network: nothing except the breach page" — FALSE in 4 load-bearing places
README.md:9-10 & 147-148, settings.html:171-172, breaches.html:8-11, setup.html:84-86 all say only the
breach page touches the network. But linkcheck contacts ~31 sites and verify_key contacts HIBP on save.
help.html:18-22 and sources.html:44-46 DO acknowledge linkcheck — copy updated in 2 places, left stale
in the 4 that matter (incl. the Settings "what this app sends" list, which is the one place users audit).

### H2 — FAQ "Neither sends your personal information anywhere" — the email check sends the email
help.html:22-23 (after naming breach + linkcheck exceptions). hibp.py:106-113 sends the email address;
breaches.html:56-58 itself admits it. The FAQ is what a nervous user trusts and it's flatly wrong.

### H3 — "Everything you type is encrypted" — reminder titles/details + report filenames are plaintext
help.html:15-16, README.md:130-139 / db.py:3-14 list the plaintext set as only ids/kind/status/dates.
But reminders.title/.detail plaintext (db.py:130-143, reminders.py:61-68) and reports.source_name
(filename) plaintext (db.py:150, repo.py:634-648). (dup of crypto H4/M1.)

## MEDIUM
- M1 recovery_code.html:36-38 "not saved anywhere in readable form — not on this computer" contradicted by the Save-to-Desktop button on the SAME page (auth.py:127-143).
- M2 "scrambled/gibberish/useless without passphrase" (settings/help/unlock/setup/move-kit) overstates: only listed FIELDS are ciphertext; sqlite reveals adult/minor mix, all freeze statuses/dates, reminder titles, report filenames, check timestamps. README is honest; in-app copy overstates to the least-savvy audience.
- M3 Idle auto-lock does NOT drop the key (lazy expiry, no sweeper) — contradicts README:151-152, config.py:17-18, security.py:3-7. (dup of crypto M6.)
- M4 dashboard.html:47 "Doesn't send your data anywhere" absolute; check-everyone sends STORED emails (breaches.py:100-106); settings.html:175 says "the address you type" but it's addresses on file.
- M5 agency_detail.html:74 "checked against the agency's own paperwork" untrue for TransUnion (mail_address cited only to ca-ag-child-freeze, a CA AG webpage, not TU paperwork). seeds.py:217-219, sources.py:112-118
- M6 FYI rows "never count against your progress" FALSE on Family page: people.py:79-85 uses done/len(agencies) incl. FYI rows => inflated denominator at people_list.html:27. Dashboard meter correctly excludes them (repo.py:820-841). Contradiction.
- M7 PDF packets drop every citation and "?" marker: pdfletters.py renders no citations; LexisNexis minor_requirements is uncited (seeds.py:292-298, set to [] at 922-923) so HTML shows "?" but the MAILED PDF shows the checklist w/ no marker. README:57-58 promises citations everywhere.
- M8 "Freezing a child's credit cannot be done online — mail-only" (letters_index.html:8-10) contradicted by app's own data: LexisNexis minor_mail_only=False, online/phone/mail (seeds.py:274-281) and appears in mailable list. True for the 3 bureaus, overbroad as written.

## LOW
- L1 hibp.py:3-4 & __init__.py:3-5 stale docstrings (only network is HIBP) post-linkcheck.
- L2 reports.py:90-91 "file never written to disk" — Starlette spools >1MiB to temp; MAX_UPLOAD_BYTES=25MB. (dup crypto M3.)
- L3 README:91 "browser opens automatically" — pywebview is default => app window not browser.
- L4 README:101 says dist wheel is 0.1.0; it's 0.2.0.
- L5 README:204 "--where prints the data directory" — prints 2 lines (dir + db path).
- L6 effort_label => "A letter in the mail" for TeleCheck/Certegy which have NO mail address on file and say "Contact directly." repo.py:230-239, seeds.py:429-465, agencies.html:45
- L7 Editorial one-liners (description, protects, action_note) render w/ NO citation and NO "?" marker despite _macros.html:5-8 and seeds.py:5-7 saying everything passes through cite. agencies.html:38-45, matrix.html:38, dashboard.html:114, agency_detail.html:9-10
- L8 README:60 "the difference is enforced in code" — letter gating checks address_verified boolean (repo.py:220-222), not that citations['mail_address'] contains a fetched source. Consistent today by convention on the data, not mechanically.
- L9 breaches "password checking free and offline-safe" — requires internet (range API); "offline-safe" misleads.
- L10 auto-backup skips weekly if ANY frostfile-*.db (incl. manual) <7 days old — "about once a week" defensible but frequent manual backups silently disable auto.

## Verified TRUE (finder's explicit confirmations)
Password check (local SHA1, 5-char prefix only, padded, never stored/logged/echoed, not persisted);
email check (needs key, nothing sent without one, stored encrypted, ~7s pacing matches sleep 6.5);
letter gating (5 mailable agencies each have fetched mail_address citation; others blocked w/ accurate
explanation; "will not print" enforced); citations UI in HTML (uncited => visible "?", legend/tags/Sources
match sources.py, compile date 2026-08-03); recovery codes (never stored readable by default, single-use
enforced, stale after passphrase change via verifier gate, reissue invalidates old, pre-recovery vault
handling accurate); passphrase change atomic; backups consistent + keep-10 + never-delete-manual; import
only on uninitialized vault; encryption of listed fields matches README; SSN opt-in off-by-default used
only for last-4 + letter prefill ("two things and only two" verified incl. pdfletters); loopback-only w/
hard refusal; manual Lock drops session; restart locks; timeout 1-240 configurable applied immediately;
no telemetry/analytics/update/accounts; CSP self-only; external links noopener+no-referrer; report
comparison limits accurately described; config table & CLI flags behave as documented; AGPL present;
ICS export warning accurate; FCRA framing consistent (no bureau connectivity of any kind).

## One-line summary
Core crypto, citation UI, and letter-gating promises are genuinely kept; dishonesty concentrates in
TOTALITY claims: "only the breach page touches the network" (stale since linkcheck+key-validation),
"everything you type is encrypted" (reminders + report filenames aren't), "not saved anywhere readable"
(Desktop save button), "gibberish without the passphrase" (field-level not file-level) — plus PDF packets
silently dropping the "?" markers that are the product's signature honesty device.
