# Shipping FrostFile v1.0.0 — the runbook

Everything needed to get frostfile.org live and the download working.
Accounts you already have: **Namecheap** (domain) and **Cloudflare** (R2 free
tier). One more is needed if you want automated Windows/Mac builds: **GitHub**
(free).

---

## 0. What gets shipped

| Artifact | Built by | Uploaded to |
| --- | --- | --- |
| `FrostFile-windows.zip` (Windows, zipped folder) | `build\build-windows.bat` on a Windows PC, **or** GitHub Actions | R2 bucket |
| `FrostFile-mac.zip` (Mac .app) | `sh build/build-macos.sh` on a Mac, **or** GitHub Actions | R2 bucket |
| `frostfile-1.0.0.tar.gz` + `.whl` (source — AGPL requires offering it) | `python -m build` anywhere | R2 bucket |
| `index.html` (the storefront) | `storefront/build.py` (already built) | Cloudflare Pages |
| `worker.js` (downloads + hit counter) | already written | Cloudflare Worker |

PyInstaller **cannot cross-compile** — the Windows exe must be built on
Windows, the Mac app on a Mac. If you have neither handy tonight, GitHub
Actions builds both for free (step 5b).

---

## 1. Point the domain at Cloudflare (~10 min + DNS propagation — do this FIRST)

1. Cloudflare dashboard → **Add a site** → `frostfile.org` → Free plan.
2. Cloudflare shows you two nameservers (like `ada.ns.cloudflare.com`).
3. Namecheap → Domain List → frostfile.org → **Nameservers → Custom DNS** →
   paste the two Cloudflare nameservers → save.
4. Propagation is usually minutes but can take a couple of hours — which is
   why this is step 1. Cloudflare emails you when the zone goes active.

## 2. Put the storefront on Cloudflare Pages (~5 min)

1. Cloudflare → **Workers & Pages → Create → Pages → Upload assets**.
2. Project name `frostfile`, upload `storefront/index.html` (just that file).
3. After it deploys: Pages project → **Custom domains** → add `frostfile.org`
   (and `www.frostfile.org` if you want it). Cloudflare wires the DNS itself.

## 3. R2 bucket for downloads (~5 min)

1. Cloudflare → **R2 → Create bucket** → name it `frostfile-downloads`
   (location: automatic).
2. Upload the built artifacts (step 5) with these EXACT names — the site
   links to them:
   - `FrostFile-windows.zip`
   - `FrostFile-mac.zip`
   - `frostfile-1.0.0.tar.gz`  (source; satisfies the AGPL source offer)
3. No public access needed — the Worker reads the bucket via a binding.

## 4. The Worker: downloads + hit counter (~10 min)

1. Cloudflare → **Workers & Pages → Create → Worker**, name `frostfile-api`,
   paste `storefront/worker.js`, deploy.
2. **Storage & Databases → KV** → create namespace `COUNTS`.
3. Worker → Settings → **Bindings**:
   - KV namespace → variable name `COUNTS` → the namespace you just made.
   - R2 bucket → variable name `BUCKET` → `frostfile-downloads`.
4. Worker → Settings → **Domains & Routes → Add → Route**:
   - `frostfile.org/download/*` — zone frostfile.org
   - `frostfile.org/api/*` — zone frostfile.org
5. Test: `https://frostfile.org/api/count` should return
   `{"visits":0,"downloads":0}`, and the storefront's odometer starts moving.

## 4½. Update emails: updates@frostfile.org

DONE 2026-08-06: real frostfile.org mailboxes exist (2 inboxes + 10
aliases), so no Cloudflare Email Routing is needed — point the
`updates@` alias/inbox wherever you read mail. The site, the drive readme,
and the app's Settings page all invite people to email `updates@` to hear
about new versions; a folder/label on that inbox IS the subscriber list.

Two checks since the domain's DNS is moving to Cloudflare tonight:
- **Copy the mail DNS records over.** When a zone joins Cloudflare it
  imports existing DNS, but verify the MX records (and the mail provider's
  SPF/DKIM TXT records) survived — otherwise mail to updates@ bounces.
  Keep MX records set to "DNS only" (grey cloud), never proxied.
- **Send a test** from updates@ to a Gmail address and confirm it lands in
  the inbox, not spam, before drives go out.

Sending updates stays manual and personal: when a version ships, write one
email from updates@frostfile.org and **BCC** the list (BCC, so recipients
never see each other's addresses). Honor "stop" replies by removing that
person. No third party holds the list — the same promise the app makes.

## 5. Build the executables

### 5a. On your own machines
- **Windows PC:** clone/copy the repo, run `build\build-windows.bat` from the
  repo root. Result: `dist\FrostFile-windows.zip`. Run it once — expect the SmartScreen
  blue box ("More info → Run anyway") since we're not code-signed yet.
- **Mac:** `sh build/build-macos.sh`, then
  `cd dist && zip -r FrostFile-mac.zip FrostFile.app`.

### 5b. Or let GitHub build both (free, ~10 min)
1. Create a GitHub account + a repository (public keeps AGPL simplest).
2. `git remote add origin <your-repo-url> && git push -u origin main`
3. `git tag v1.0.0 && git push origin v1.0.0`
4. GitHub → Actions tab → the `build` workflow runs → download the three
   artifacts (`FrostFile-windows`, `FrostFile-macos`, `FrostFile-source`).
5. **Test the exe on a real Windows machine before uploading.** CI proves it
   builds, not that it runs.

### 5c. Source bundle (any machine, 1 min)
Already done on this machine: `dist/frostfile-1.0.0.tar.gz` and the `.whl`.

## 6. Checksums (do this; it's your only integrity story without signing)

- Windows: `certutil -hashfile FrostFile.exe SHA256`
- Mac/Linux: `shasum -a 256 <file>`

Save them into a `SHA256SUMS.txt`, upload it to R2 too, and keep a copy with
the flash-drive masters. If a coworker's antivirus complains, comparing the
hash is how you prove the file is yours.

## 7. Flash drives

Copy onto each drive:
- `FrostFile-windows.zip`
- `FrostFile-mac.zip` (if built)
- `START-HERE.txt` (in `drive-kit/`)
- `SHA256SUMS.txt`

## 8. Code signing with Certum (purchased 2026-08-07)

Product: "Open Source Code Signing in the Cloud" (~$50/yr, SimplySign).
One-time setup, then signing is one script per release:

1. **Activate** (1–3 business days): Certum account → identity documents
   (government photo ID matching the order name) → wait for verification
   email → issue the certificate into SimplySign (no USB token involved).
2. **On your Windows PC**: install the SimplySign Desktop app + the
   SimplySign mobile app (the phone app is the 2FA that unlocks the cloud
   card). Install "Windows SDK Signing Tools" if `signtool` is missing.
3. **Every release**: download the CI-built FrostFile-windows.zip, then
   `build\sign-windows.bat FrostFile-windows.zip` — it extracts, signs
   FrostFile.exe with a Certum timestamp, verifies, re-zips, and prints
   the new SHA-256. Upload the signed zip to R2 under the usual name and
   update SHA256SUMS.txt.
4. Reputation note: signing kills the "unknown publisher" class of warning
   immediately; SmartScreen/AV *reputation* still accrues over the first
   days-to-weeks of downloads. Fewer warnings right away, near-zero later.

## 8b. Still parked, deliberately
- **Custom R2 domain / caching tweaks** — the Worker route is enough.
- **Auto-anything** — releasing stays a human uploading files on purpose.

---

## Release checklist (repeat for every future version)

1. `python -m pytest` — all green.
2. `python tools/linkcheck.py` — fix any FAIL; click any BLOCKED URLs in a
   real browser; update `LINKS_VERIFIED_ON` in `frostfile/sources.py`.
3. Bump version in `pyproject.toml` AND `frostfile/__init__.py`.
4. Build (5a or 5b), test the exe on a real machine, checksum, upload to R2
   under the same names.
5. Update the site's changelog/version line and redeploy Pages.
6. Fresh drives for anyone who asks.
