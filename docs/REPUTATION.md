# Getting rid of the scary screens

The goal: a family member downloads FrostFile on a work laptop and sees nothing
alarming. No "Windows protected your PC", no red browser page, no antivirus
quarantine, no "this site is blocked by your administrator", no update email in
the junk folder.

This document is the map of every place that can show a user a warning, the
door you knock on for each, and what state we're in. The mechanical parts —
who to submit to, what to paste, what's still outstanding — live in
`tools/reputation.py` so that shipping v1.1 isn't a memory exercise.

**All URLs here were verified live on 2026-08-08.** Vendors retire forms
without notice; re-check before leaning on one.

---

## The four screens, and what actually fixes each

These have genuinely different mechanics, and conflating them wastes weeks.

**1. "Windows protected your PC" (SmartScreen).** Caused by an unsigned or
low-reputation binary. Code signing removes the "unknown publisher" class of
warning immediately. The remaining reputation component accrues over roughly
weeks and hundreds of clean installs, against both the file hash and the
publisher certificate. There is no consumer submission form that shortcuts it.

**2. Antivirus quarantine.** Caused by heuristics reacting to PyInstaller
packing, not by anything specific to us. Fixed per-engine by false-positive
submissions — or, far better, by the three *standing* whitelist programs below.

**3. Browser and corporate web filter blocks.** Two separate things wearing the
same coat. A browser block (Safe Browsing, SmartScreen URL) means we're
affirmatively flagged and needs an appeal. A corporate filter block usually
means the domain is simply *uncategorized* — young domains default to
"unknown", which many enterprise policies block. That's fixed by asking
categorization databases to classify us, and it's the highest-value work here
because our users are on employer-managed machines.

**4. Update emails in the junk folder.** Separate problem, mostly already
solved. See the email section.

### The one screen with no door

**Chrome's "isn't commonly downloaded" warning cannot be submitted away.**
There is no form, no queue, and no appeal — it is purely reputation-based.
Chrome's developer documentation routes only to Search Console, which handles
affirmative malware flags, not this. Code signing helps reputation accrue but
does not clear it on day one.

Related, and worth knowing so you don't chase it: Chrome's *"Unverified"*
label doesn't mean anything is wrong with our file. It means **that user has
Safe Browsing switched off**. Nothing we do can affect it.

The honest play is download-page copy telling people the warning may appear and
what to click. That work is already started; keep it.

---

## Strategy: do the standing arrangements first

The single most useful finding in this whole exercise is that **not everything
is per-release**. Three vendors offer standing arrangements that pre-clear
future builds, and several databases classify the *domain*, which never
changes. Front-load those and each subsequent release gets dramatically
cheaper.

### Standing arrangements — do once, benefit forever

| Target | Why it's worth doing first |
| --- | --- |
| **Gen Digital whitelist** | One submission covers **Norton + Avast + AVG + Avira**. The form says so verbatim. Approval brings FTP credentials for future builds. |
| **ESET whitelist** (`whitelist@eset.sk`) | Registration then FTP drops; "all folders are being scanned regularly". The cleanest developer arrangement of any vendor. |
| **Kaspersky Allowlist Program** | Standing partner programme. Wants a company website with a legal address, so may not fit a solo project. |
| **All 15 web categorization targets** | These classify `frostfile.org`, not a build. Done once unless we're re-flagged. |

That's four AV engines cleared by one Gen Digital submission, and two more
standing FTP arrangements — versus filing eight tickets every single release.

**Answer the packing question honestly.** ESET's registration asks directly
about code signing, packing, and obfuscation. PyInstaller, disclosed, is
completely fine. Concealing it is what gets a publisher permanently distrusted.

### Per-release — unavoidable, because the hash changes

19 targets reset to `todo` on each new version. In practice you won't file all
19: run `reputation.py scan` first and only submit to engines that actually
flag the new build. Most releases that should be a short list, and once the
standing arrangements land it should approach zero.

---

## The pipeline

```bash
# after building and updating drive-kit/SHA256SUMS.txt
python tools/reputation.py release 1.1.0 --signed

# who actually flags this build? (needs a free VT_API_KEY)
export VT_API_KEY=...
python tools/reputation.py scan

# for each flagged engine: print what to paste, submit, record it
python tools/reputation.py packet eset-fp
python tools/reputation.py mark eset-fp submitted --ref TICKET-123

python tools/reputation.py todo      # what's left
python tools/reputation.py status    # everything, by category
python tools/reputation.py md        # refresh the table below
```

`packet` prints the eight facts every form asks for — product, publisher,
license, repo, hashes, download URLs, build toolchain — plus a written
false-positive justification, so you're pasting rather than re-composing at
11pm. Edit that text once in `tools/reputation.py` (`PROJECT` and `RATIONALE`)
and every vendor gets the improvement.

`scan` is **observational only**. VirusTotal's own docs are blunt: it "does not
produce any verdicts of its own", and only the vendor that produced a detection
can clear it. Uploading there fixes nothing — it tells you which of the 40+
doors to knock on so you skip the rest. Free tier is 4 requests/minute and 500
per day, and its terms exclude commercial use, which a free AGPL project's
release tooling is comfortably within.

### Practical submission notes

**Submit the flagged `FrostFile.exe`, not the 30–75MB zip.** Four size caps sit
at or below our archive: Bitdefender 25MB, Sophos ~25MB, Microsoft 50MB, Avast
60MB. The single binary clears them and is what analysts actually want. Where
it still doesn't fit, use the URL field pointing at `frostfile.org/download/`.

**Several vendors want the sample zipped with the archive password
`infected`** — Avira, F-Secure, K7, Fortinet, ESET. That's a second zip
wrapping our distribution zip.

**Some sites block automated checking** (McAfee, Malwarebytes, Bitdefender
consumer, Sophos Home, Trend Micro). Their size caps and form fields in the
registry are marked unverified — confirm in a real browser before relying on
them.

---

## Recommended order of attack

1. **OpenText / BrightCloud** — five minutes, no account, 24–48h published SLA,
   and it's OEM'd into a large number of third-party firewalls and UTMs. Best
   effort-to-reach ratio on the entire list.
2. **Gen Digital whitelist** — four AV engines for one submission.
3. **Microsoft Defender** (`Software developer` option) — on by default on
   every Windows machine, so it decides whether most users see anything at all.
4. **ESET whitelist** — the standing FTP arrangement.
5. **Fortinet + Symantec Site Review** — FortiGate dominates small-to-mid
   construction firms; Blue Coat ProxySG dominates large contractors.
6. **Cisco Talos** — one submission covers Umbrella, Secure Web Appliance, and
   Cisco web reputation.
7. **Trellix `trustedsource.org` AND McAfee `sitelookup.mcafee.com`** — these
   split into separate databases in February 2024. You need both.
8. **SmartScreen site form** — pre-emptively; the registry's URL already has
   `frostfile.org` base64-encoded in, so it opens ready to fill.
9. **Google Search Console** — verify domain ownership *now*, while we're
   clean. It's the appeal channel if Safe Browsing ever flags us, and you don't
   want to be doing DNS verification during an incident.
10. Everything else, as time allows.

### Doors that are locked — don't waste an evening

- **CrowdStrike and SentinelOne** have no public ISV intake at all. False
  positives are resolved inside the *customer's own console* by their admin. If
  a user hits this, their IT team must add the exclusion.
- **Forcepoint** is customer-only. Every guide pointing at `csi.forcepoint.com`
  or `csi.websense.com` is stale — those hostnames no longer resolve.
- **Panda / WatchGuard** has no working public endpoint-AV channel; the public
  form is IPS-signatures-only and takes no file.
- **Chrome's uncommon-download warning**, as above.

For all of these, the leverage is the same: if a real user reports a block, ask
*them* to file it from inside their organization's support account. It takes
them two minutes and it's the only path that works.

---

## Code signing and OS trust

### Windows: the free Store path beats everything you're currently paying for

**Microsoft Store distribution is now free for individuals, and Store apps
never see a SmartScreen download warning at all.** Microsoft's own words: "The
simplest way to avoid SmartScreen warnings is to publish through the Microsoft
Store. Store-distributed apps are signed by a Microsoft certificate and are
*never* subject to SmartScreen download warnings." They re-sign the package, so
there's no certificate to buy, renew, or protect.

Registration fees were dropped for both account types across 2025–2026. You
must start at **`storedeveloper.microsoft.com`** — other entry points still
show the legacy paid flow.

The catch: this only works via **MSIX**. Submit an MSI or EXE installer and
Microsoft does *not* re-sign it. So it's a packaging change (PyInstaller → exe →
MSIX), not just an upload. That's real work, but it is the only option on this
entire list that makes the Windows warning disappear rather than merely fade.

### Certificates: OV, EV, and Azure all start from the same place

Microsoft removed the EV-bypass behaviour in 2024 and now documents it plainly:
"EV certificates no longer bypass SmartScreen… paying a premium for EV solely
to avoid SmartScreen warnings is no longer justified." EV is also
organizations-only at both Certum and Azure, so it was never available to you.
**Choose a certificate on cost and CI ergonomics, not on SmartScreen.**

What signing actually buys:

- It removes the "unknown publisher" framing and displays a verified name.
- It lets reputation **carry across releases**. Microsoft: reputation "cannot
  transfer from previous versions unless both were signed using the same
  publisher identity." This is the real argument for signing — unsigned, every
  release starts from zero forever.
- It helps **immediately** with Smart App Control on Windows 11, which allows
  anything chaining to a Trusted Root Program CA. Unlike SmartScreen, that's
  not a waiting game.

Reputation itself takes "several weeks and hundreds of clean installs from a
wide audience," and there is no consumer submission mechanism to speed it up.

Two things that bite this specific build: the zip does **not** shield the exe
(Explorer propagates Mark-of-the-Web to extracted files), and Smart App Control
evaluates *every* binary in a onedir build, not just `FrostFile.exe`.

### Azure Artifact Signing — your in-flight application

It was renamed from *Trusted Signing*; the old name is now stale in docs, tool
names, and the GitHub Action.

**The 3-year business-history rule does not apply to you.** It was always
organizations-only, and the phrase no longer appears anywhere in the current
documentation tree. The individual path validates a human against a government
ID, is available in the USA and Canada, and completes in **minutes**.

Your validation showing "In Progress" is a waiting room. **The signal to watch
for is the status flipping to `Action Required`** — that's your cue, and
nothing further happens until you act on it. Then: sign in with the *exact*
email address on the request (a mismatch produces a confusing permissions
error), verify via Verified ID on your phone, and only then create the
certificate profile.

Check two things before you get there, because both are painful to fix
afterwards: the subscription must be **pay-as-you-go, not free or trial**, and
the billing account type must be **Individual** with your correct legal name —
the certificate is populated from it, read-only. Also note the verification
email link expires in **7 days and cannot be resent**; you'd have to start over.

Cost is $9.99/month, billed from account creation and not pro-rated.

**Unlike Certum, it signs cleanly from GitHub Actions** via
`azure/artifact-signing-action@v2` with OIDC federated credentials — no
hardware token, no secrets on disk.

**One honest caveat.** Azure issues short-lived certificates renewed daily, and
in 2026 Microsoft rotated customers across new intermediate CAs. A Microsoft
staff member confirmed that SmartScreen reputation "is influenced by the
issuing CA's own accumulated trust signal," so a newly-assigned intermediate
can re-trigger warnings on every release. The popular claim that Azure gives
"instant reputation tied to your identity" is **false** and contradicted by
Microsoft's own docs, which state it does *not* provide instant SmartScreen
trust. Don't plan around it.

### Certum — and the likely explanation for your three payments

There are **two** Open Source SKUs, and the €69 **card + reader set is
currently out of stock**. Repeatedly attempting to buy an out-of-stock item is a
very plausible cause of three ambiguous checkouts. **You want the €49 cloud
SKU** (SimplySign, no hardware).

Their purchase conditions are decisive on how to check: if an order isn't
listed under *My Account → My orders*, checkout never completed. Count what's
there, cross-check against actual captures on your card statement, and email
`reklamacje@certum.pl` about duplicates (Mon–Fri 08:00–16:00 CET). Note the
cryptographic card is **non-refundable even on a valid return** — one more
reason to take the cloud SKU.

Signing uses `/sha1 "<thumbprint>"`, not `/n` (see `build/sign-windows.bat`).
The SimplySign session is unlocked interactively by the phone app, so
**unattended CI signing is impractical** — this is where Azure genuinely wins.

### macOS: the v1.0.0 build shipped broken (verified 2026-08-08)

The `FrostFile-mac.zip` currently on frostfile.org is almost certainly
unusable, and the cause is the `zip -r` packaging bug fixed in this change.
Verified by downloading the live artifact (SHA-256 matches `SHA256SUMS.txt`,
so this is the shipped file) and inspecting it:

- The bundle's own signature manifest (`Contents/_CodeSignature/CodeResources`)
  **declares 56 entries as symlinks**.
- The archive contains **zero symlinks**. `zip -r` followed every one and
  stored a copy of the target instead.
- The main executable is **arm64** with an intact embedded signature — so the
  Mach-O itself is fine, but the *bundle seal* no longer matches the structure
  it sealed. `codesign --verify` cannot pass.

On Apple Silicon that is the bad failure mode: not the three-dialog override
path, but "FrostFile.app is damaged and can't be opened", which has **no
override at all**. Anyone who downloaded the Mac build likely could not run it.

The same bug also **triples the download**. Flattening symlinks duplicated
135.5 MB of payload — the 8 MB Python binary is present **eight times**, and
~46.6 MB of the 74.5 MB download is redundant copies. Fixing the packaging
should take the Mac download from roughly 75 MB to under 30 MB, which also
makes the "30–75MB" size copy on the storefront honest again.

**Action: rebuild and re-upload the Mac artifact**, then verify before
shipping with `codesign -vvv --deep --strict FrostFile.app` (expect "valid on
disk") and confirm the rebuilt zip is roughly a third of the old size. Update
`SHA256SUMS.txt` and the drive masters.

### macOS: tell users the truth, and ad-hoc sign regardless

**There is no free path to a warning-free Mac install, and no waiver you can
qualify for.** The Apple fee waiver explicitly excludes individuals and sole
proprietors; being free and open-source is irrelevant to it. A free Apple ID
cannot notarize at all.

**Signing without notarizing buys literally nothing at the dialog** — a
Developer-ID-signed but un-notarized app shows the *same* "Apple could not
verify…" block as an unsigned one.

**The right-click → Open bypass is gone**, removed in Sequoia and still gone in
Tahoe 26. What a user actually faces now: a dialog whose only buttons are
*Done* and *Move to Trash* (no Open), then a trip to System Settings → Privacy
& Security, then a confirmation dialog that again defaults to Move to Trash,
then an admin password. And the "Open Anyway" button is **only available for
about an hour** after the failed launch — a user following written instructions
the next day will not find it and must trigger the failure again first.

Our download-page copy should say this plainly rather than let people discover
it. What we must **not** do is publish an `xattr -dr com.apple.quarantine`
incantation: it works, but it trains non-technical people to paste
security-disabling terminal commands, which is exactly the behaviour Apple
removed the bypass to stop. That would be irresponsible for this audience.

**Regardless of the $99 decision, ad-hoc sign the Mac build.** Apple Silicon
refuses to execute unsigned native arm64 code at the *kernel* level, below
Gatekeeper — "Open Anyway" cannot rescue it. An ad-hoc signature satisfies that
check and moves the app from an unrecoverable "damaged" state into the merely
annoying three-dialog state. PyInstaller normally ad-hoc signs arm64 output
already, **provided packaging doesn't corrupt it**: use
`ditto -c -k --keepParent`, never plain `zip` or Finder's Compress, both of
which mangle symlinks and `_CodeSignature`. A corrupted signature is *worse*
than none, because no override option appears at all.

If you do pay the $99: sign inside-out (never `--deep`, deprecated since macOS
13), use `--options runtime --timestamp`, then **staple the `.app` and re-zip**.
Shipping the submission zip is the classic mistake — it contains an unstapled
app that fails for offline users.

---

## Email deliverability

Largely a solved problem, and smaller than it looked. **You are not a bulk
sender** — the threshold at Gmail, Yahoo, and Microsoft is 5,000 messages per
day, and a few hundred recipients a few times a year is two orders of magnitude
below it. The strict bulk rules (mandatory one-click unsubscribe, DMARC
enforcement) don't bind us.

Current state, verified by DNS lookup on 2026-08-08:

- **SPF**: `v=spf1 include:spf.privateemail.com ~all` — correct.
- **DKIM**: selector `privateemail` — present.
- **DMARC**: `v=DMARC1; p=none; rua=mailto:updates@frostfile.org` — **needs
  fixing.**

The DMARC problem: aggregate reports arrive as gzipped XML from dozens of
receivers, daily, and that `rua` points them at the same mailbox that *is* the
subscriber list. Cloudflare DMARC Management is free on all plans, needs only
that the zone use Cloudflare DNS (it does), and renders them as readable
analytics. Then sit at `p=none` for 4–6 weeks and advance to `quarantine`, and
eventually `reject` with `sp=reject`. Worth doing: `frostfile.org` is exactly
the domain a "download this update" phish would spoof, aimed at exactly the
users least equipped to spot it.

**Google Postmaster Tools**: set it up once, then ignore it. Google suppresses
data below a privacy threshold, so at our volume the dashboards will be empty
essentially always. That's working as designed, not a bug to troubleshoot.

**Skip Microsoft SNDS and JMRP entirely.** Both are keyed to sending IP
addresses you must prove you control. On a hosted provider's shared IPs, the
provider owns them. Wrong tool for us.

**Before each release email**, send the real draft to mail-tester.com (3 free
tests/24h, aim for 10/10), then to a personal Gmail and check *More → Show
original* for three PASSes with `frostfile.org` as the domain, then to an
Outlook.com and a Yahoo address to see Inbox vs Junk. Those test accounts are
the only placement signal available at this volume.

**Sending mechanics that matter**: keep each BCC batch under ~50 recipients,
always put a real address in `To:` (yourself — a message with an empty `To:` and
only BCC recipients is a known spam fingerprint), space the batches over an
hour, keep the From address and display name identical every time, prefer plain
text, link only to `frostfile.org`, and never use a link shortener.

---

## Status

<!-- STATUS:BEGIN -->
_Generated by `tools/reputation.py md` for **1.0.0**. Do not hand-edit between the markers._

### Antivirus engines

| | Target | Cadence | Status | Date | Ref |
| --- | --- | --- | --- | --- | --- |
| ⬜ | [Dr.Web](https://vms.drweb.com/sendvirus/) | per-release | todo |  |  |
| ⬜ | [Emsisoft](https://www.emsisoft.com/en/help/contact/) | per-release | todo |  |  |
| ⬜ | [Webroot (OpenText)](https://snup.webrootcloudav.com/SkyStoreFileUploader/upload.aspx) | per-release | todo |  |  |
| ⬜ | [Gen Digital whitelist (Norton + Avast + AVG + Avira)](https://www.avast.com/whitelist-program-registration) | standing | todo |  |  |
| ⬜ | [Gen Digital false-positive form (per build, if flagged)](https://www.avast.com/report-false-positive) | per-release | todo |  |  |
| ⬜ | [Microsoft Defender](https://www.microsoft.com/en-us/wdsi/filesubmission) | per-release | todo |  |  |
| ⬜ | [ESET whitelist program (standing)](https://support.eset.com/en/kb3345-how-do-i-whitelist-my-software-with-eset) | standing | todo |  |  |
| ⬜ | [ESET false positive (per build, if flagged)](https://support.eset.com/en/kb141-submit-a-virus-website-or-potential-false-positive-sample-to-the-eset-lab) | per-release | todo |  |  |
| ⬜ | [Kaspersky](https://opentip.kaspersky.com/) | per-release | todo |  |  |
| ⬜ | [Bitdefender](https://www.bitdefender.com/en-us/business/submit) | per-release | todo |  |  |
| ⬜ | [Sophos](https://intelix.sophos.com/) | per-release | todo |  |  |
| ⬜ | [McAfee (consumer)](https://www.mcafee.com/en-us/consumer-support/dispute-detection-allowlisting.html) | per-release | todo | 2026-08-08 |  |
| ⬜ | [Malwarebytes](https://forums.malwarebytes.com/forum/42-file-detections/) | per-release | todo |  |  |
| ⬜ | [F-Secure](https://www.f-secure.com/en/support/submit-a-sample) | per-release | todo |  |  |
| ⬜ | [G Data](https://submit.gdatasoftware.com/sample?lang=en) | per-release | todo |  |  |
| ⬜ | [Trend Micro](https://helpcenter.trendmicro.com/en-us/srf/) | per-release | todo |  |  |
| ⬜ | [K7](https://support.k7computing.com/index.php?/ticket/submit-ticket) | per-release | todo |  |  |
| ⬜ | [Fortinet FortiGuard (AV sample)](https://www.fortiguard.com/faq/antivirus-contact) | per-release | todo |  |  |
| ⬜ | [Fortinet classification dispute (software author)](https://www.fortiguard.com/faq/classificationdispute) | standing | todo |  |  |
| ⬜ | [Comodo / Xcitium](https://verdict.xcitium.com/) | per-release | todo |  |  |
| — | [Panda / WatchGuard](https://www.watchguard.com/wgrd-support/security-portal/report-false-positive) | per-release | n/a | 2026-08-08 |  |
| — | [CrowdStrike Falcon](https://supportportal.crowdstrike.com/s/get-help) | standing | n/a | 2026-08-08 |  |
| — | [SentinelOne](https://www.sentinelone.com/) | standing | n/a | 2026-08-08 |  |

### OS trust (signing & notarization)

| | Target | Cadence | Status | Date | Ref |
| --- | --- | --- | --- | --- | --- |
| ⏳ | [Azure Artifact Signing (was Trusted Signing)](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart) | standing | submitted | 2026-08-08 |  |
| 🚫 | [Certum Open Source Code Signing (cloud)](https://shop.certum.eu/code-signing.html) | standing | blocked | 2026-08-08 |  |
| ⬜ | [Microsoft Store (MSIX) — the free, warning-free path](https://storedeveloper.microsoft.com) | standing | todo |  |  |
| ⬜ | [Apple notarization (Developer Program)](https://developer.apple.com/support/compare-memberships/) | standing | todo |  |  |
| ⬜ | [macOS ad-hoc signing (defensive, free)](https://developer.apple.com/documentation/security/resolving-common-notarization-issues) | per-release | todo |  |  |
| — | [SmartScreen file reputation (accrues, no door)](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) | standing | n/a | 2026-08-08 |  |

### Web / URL reputation

| | Target | Cadence | Status | Date | Ref |
| --- | --- | --- | --- | --- | --- |
| ⬜ | [OpenText Threat Intelligence (BrightCloud)](https://support.threatintel.opentext.com/tools/change-request.php) | standing | todo |  |  |
| ⬜ | [Fortinet FortiGuard web filter](https://www.fortiguard.com/faq/wfratingsubmit) | standing | todo |  |  |
| ⬜ | [Symantec / Broadcom WebPulse Site Review](https://sitereview.bluecoat.com/) | standing | todo |  |  |
| ⬜ | [Cisco Talos (also covers Umbrella / OpenDNS)](https://talosintelligence.com/reputation_center/web_categorization) | standing | todo |  |  |
| ⬜ | [Trellix / Skyhigh TrustedSource](https://trustedsource.org/) | standing | todo |  |  |
| ⬜ | [McAfee SiteLookup (consumer web control)](https://sitelookup.mcafee.com/) | standing | todo |  |  |
| ⬜ | [Microsoft SmartScreen — site reputation](https://feedback.smartscreen.microsoft.com/feedback.aspx?v=6&t=512&result=block&url=aHR0cHM6Ly9mcm9zdGZpbGUub3Jn) | standing | todo |  |  |
| ⬜ | [Google Search Console (Safe Browsing review channel)](https://search.google.com/search-console/security-issues) | standing | todo |  |  |
| ⬜ | [Netcraft](https://report.netcraft.com/report/mistake) | standing | todo |  |  |
| ⬜ | [Barracuda Central](https://www.barracudacentral.org/report) | standing | todo |  |  |
| ⬜ | [Palo Alto Networks PAN-DB](https://urlfiltering.paloaltonetworks.com/) | standing | todo |  |  |
| ⬜ | [Zscaler Site Review](https://sitereview.zscaler.com/) | standing | todo |  |  |
| ⬜ | [Sophos web categorization](https://community.sophos.com/community-chat/f/discussions/) | standing | todo |  |  |
| — | [Chrome 'not commonly downloaded' warning](https://support.google.com/chrome/answer/6261569) | standing | n/a | 2026-08-08 |  |
| — | [Forcepoint (formerly Websense)](https://support.forcepoint.com/s/site-lookup) | standing | n/a | 2026-08-08 |  |

### Email deliverability

| | Target | Cadence | Status | Date | Ref |
| --- | --- | --- | --- | --- | --- |
| ⬜ | [DMARC reporting (Cloudflare DMARC Management)](https://dash.cloudflare.com/?to=/:account/:zone/email/dmarc-management) | standing | todo |  |  |
| ⬜ | [DMARC policy: none -> quarantine -> reject](https://developers.cloudflare.com/dmarc-management/) | standing | todo |  |  |
| ⬜ | [Google Postmaster Tools](https://postmaster.google.com/) | standing | todo |  |  |
| ⬜ | [Pre-send deliverability check](https://www.mail-tester.com/) | per-release | todo |  |  |
<!-- STATUS:END -->

---

## Where this plugs into the release checklist

`DEPLOY.md` step 4 (build, test, checksum, upload) gains:

1. Update `drive-kit/SHA256SUMS.txt` with the new hashes.
2. `python tools/reputation.py release <version> --signed`
3. `python tools/reputation.py scan` — submit only to engines that flag it.
4. `python tools/reputation.py md` and commit the refreshed table.

The ledger lives in `docs/reputation-status.json` and is committed, so the
record of what was submitted where, and what came back, survives across
releases and machines.
