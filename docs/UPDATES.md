# FrostFile update tracker

One place for everything waiting to go into a release, so nothing gets
forgotten and nothing forces a second release the same day.

**Every content item needs a retrieved-and-verified source before it ships** —
same rule as the app itself. An item sitting at "unverified" is not ready,
however obviously true it looks.

---

## How we decide when to ship

**Critical — ship as soon as it is verified, alone if necessary.**
Something in the app is wrong or missing in a way that makes a user take a
harmful action, or blocks them from protecting themselves. A wrong phone
number, a dead address, an instruction that leaves someone exposed, a build
that will not run. These do not wait for company.

**Important — goes in the next scheduled release.**
Real improvements and corrections that do not put anyone at risk today. Missing
bureaus, better sequencing, clearer copy.

**Minor — whenever convenient.**
Renames, tidying, expectation-setting details.

The rule that matters: **batch the Important and Minor items, never batch a
Critical one.** If a Critical item is ready and the others are not, ship the
Critical item by itself. Shipping a release with a half-finished Important item
in it is how you end up cutting another release the same day.

Before any release, walk `DEPLOY.md`'s release checklist and
`docs/REPUTATION.md`'s pipeline — a new build means new hashes and new
antivirus submissions.

---

## Ready to ship

### v1.0.1 — Mac build is broken (CRITICAL)

The shipped `FrostFile-mac.zip` was packed with `zip -r`, which flattened all
56 symlinks the bundle's own signature seals. On Apple Silicon that produces
"FrostFile.app is damaged and can't be opened" with **no override available**.
Verified by inspecting the live artifact (hash matches `SHA256SUMS.txt`). It
also tripled the download — 135.5 MB of duplicated payload, the Python binary
present eight times.

- [x] `build.yml` and `build-macos.sh` use `ditto -c -k --keepParent`
- [x] Round-trip verification added to both, so this cannot regress silently
- [ ] Re-cut the Mac build and confirm the zip drops from ~75 MB to under 30 MB
- [ ] Upload to R2, update `drive-kit/SHA256SUMS.txt`, refresh drive masters
- [ ] Storefront still says "30–75 MB" — becomes wrong once Mac shrinks

**Nothing in the app changed** — this is purely packaging, so it does not need
to wait for any content item below.

---

## Content corrections

Sourced from a verified post-breach research pass on 2026-08-08. Checked
against what the app already ships, so the list below is only what is
genuinely wrong or missing.

### Sequencing: claim accounts before freezing (IMPORTANT → arguably Critical)

Enrolling in **myE-Verify Self Lock runs an Experian knowledge-based quiz**,
and its own failure page lists "You may have put a security freeze on your
credit report" as a cause. A user who follows FrostFile's freeze list first can
lock themselves out of the employment-fraud control until they thaw.

This is the single most valuable thing on this list because FrostFile *is* a
sequencing tool. See "Knowledge-based questions" below — it generalises well
beyond E-Verify.

- [ ] Order the checklist so account-claiming precedes freezing
- [ ] Warn on the freeze steps that a freeze can block identity verification
      elsewhere, and that a temporary thaw is the fix

### E-Verify Self Lock duration (IMPORTANT)

Self Lock is **indefinite** — "remains active as long as your account remains
valid." The 365-day figure that circulates caps *Self Check*, a different
thing. Two things worth telling users: it will trigger a Tentative
Nonconfirmation at their next E-Verify employer, so **unlock before starting a
new job**; and E-Verify is appropriations-dependent (it went dark 1–8 Oct 2025).

### SSA has two blocks, not one (IMPORTANT)

The one everybody misses is the **Direct Deposit Fraud Prevention block**,
which stops enrolment or changes "through my Social Security **or a financial
institution (via auto-enrollment)**" — closing a benefit-redirect path that
never touches ssa.gov at all. Both are requested by calling **1-800-772-1213**.

Real tradeoff to document honestly: it makes every future address or bank
change a phone call, and removal requires a local office visit.

- [ ] Add both blocks as distinct actions
- [ ] Note that legacy SSA usernames are gone since 7 Jun 2025 — Login.gov or ID.me

### Teletrack has been absorbed into DataX (IMPORTANT)

`seeds.py` still says "Teletrack, which is frozen separately." Both are Equifax
subsidiaries and the CFPB list's separate Teletrack entry is stale.

- [ ] Add **DataX** — mail-only freeze, 800-295-4790, PO Box 740125, Atlanta GA 30374
- [ ] Add **FactorTrust** — 844-773-3321
- [ ] Update the Teletrack note

*Verify both freeze routes before shipping — the mail-only claim needs
confirming against DataX's own page, and the citation rule applies.*

### Specialty freezes are not covered by the federal mandate (MINOR)

15 U.S.C. § 1681c-1(i) defines "consumer reporting agency" as **nationwide**
CRAs only. Every specialty-bureau freeze is free by company policy or state
law, not federal law — ChexSystems says so explicitly, reserving the right to
charge where a state allows it. Practical consequence for users: **Innovis has
three business days to lift, not the federal one hour.** Our Innovis entry says
only "Lift online or by phone at no charge," which sets the wrong expectation
for anyone thawing before a mortgage application.

### IRS notes (MINOR)

- The **IP PIN tool is only open mid-January to mid-November** — worth saying,
  since a user reading this in December will find it gone.
- IRS identity verification is **ID.me**, not Login.gov.
- **Do not add Form 14039 as a precautionary step.** The current Rev. 2-2026
  form dropped the "may at some future time affect my tax records" option and
  now says explicitly not to file if your situation is not one of its listed
  scenarios. (We do not reference it today — this is a "don't add it" note.)

### Checked and already correct — no action

- **NCTUE phone** is already 1-866-349-5355. Correct.
- **Early Warning Services** is already `action_kind: "fyi"` with copy saying
  their pages offer no DIY freeze. Correct, and it matches the CFPB list.
- **E-Verify Self Lock URL** already points at the current path.
- Our **`corelogic` entry is SafeRent Solutions**, which is the rental
  screening company — a *different* entity from CoreLogic Credco (now
  Cotality). The rename does not apply here. Adding Credco/Cotality separately
  is optional; no freeze is documented for it.

---

## Knowledge-based questions are answerable from leaked data (IMPORTANT)

The insight worth building around, and the reason the sequencing item above
matters. The identity questions guarding AnnualCreditReport, USPS Informed
Delivery, myE-Verify, the SSA account and the bureaus themselves are answered
from name, address history, date of birth and SSN — **exactly the data a breach
leaks**. Anyone holding the breach file can often answer them as well as the
real person, or better.

Two consequences, and they point in opposite directions:

1. **Claiming an account is protective.** Registering first means the attacker
   cannot. This is a race, not a checklist item.
2. **Freezing can lock *you* out** of verifications you have not done yet,
   because the quiz provider cannot pull your file.

So the correct order is: **claim the accounts, then throw the freezes.**

- [ ] Storefront: short plain-language section explaining why the security
      questions are not really secret any more
- [ ] App: reorder so account-claiming precedes freezing, with a visible reason
- [ ] App: consider a distinct action kind for "claim before someone else does"
      — it is a different *kind* of task from a freeze and the urgency differs

---

## Housekeeping (not user-facing)

- [ ] DMARC `rua=` currently points at `updates@frostfile.org`, dumping gzipped
      XML into the mailbox that holds the subscriber list. Move to Cloudflare
      DMARC Management (free, zone already on Cloudflare), then advance
      `p=none` → `quarantine` → `reject`. See `docs/REPUTATION.md`.
- [ ] Worker: `Content-Disposition` filename sanitising, `Content-Length` and
      `nosniff` are fixed in-repo but **not deployed** — needs a Worker redeploy.
- [ ] **Cloudflare abuse mitigation — agreed 2026-08-08, remind until done.**
      Two parts: spend the one free rate-limiting rule on `/api/hit`, and
      sample the KV counter write (once per N hits, increment by N). KV writes
      are ~94% of the exposure, and Cloudflare has no hard spend cap. Also cuts
      the viral-traffic bill from ~$31/mo to ~$5.55. See `docs/COSTS.md`.
- [ ] Data directory: `%LOCALAPPDATA%` on Windows is vulnerable to users
      "cleaning up" AppData. Lower priority now the Store path is dropped, but
      the risk of silent data loss is real either way.
