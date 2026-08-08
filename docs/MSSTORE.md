# Microsoft Store (MSIX): a decision document

Researched 2026-08-08 against Microsoft Store Policies v7.19, the App
Developer Agreement v8.11, and the MSIX packaging documentation.

**Verdict: compatible with the zero-network pillar as written, but not free of
consequences. Three things must be true before it is safe to ship, and one of
them is worth doing whether or not we ever submit.**

The prize is real: Store-distributed apps are signed by Microsoft and **never**
trigger a SmartScreen warning, and they update silently without the app
containing a single line of network code. For an app that deliberately has no
update check, that second point is a genuine user-safety win we cannot
otherwise get.

---

## Does it violate the pillar? No — but read the second half

**The app itself still makes zero outbound connections.** There is no mandatory
SDK, no licensing call, no telemetry hook. The Store Services SDK is optional
and opt-in. A free app with no in-app purchases has no obligation to call any
Store API. `test_zero_network_rule_no_http_client_in_app_code` would pass
untouched, because nothing enters the package.

One Store policy actively rewards the design: products "must not attempt to
fundamentally change or extend [their] described functionality through any form
of dynamic inclusion of code." An app with no HTTP client complies trivially.

**But the promise behind the pillar erodes, and users deserve to hear it.**
All of the following is collected by the OS and the Store client, not by us,
and **there is no documented developer-side switch to turn it off**:

- Monthly and daily active devices *and users*
- Session counts and **average engagement duration**
- 90-day retention cohorts, per-version and per-country
- **User-initiated uninstall counts**
- Crash and hang telemetry (this one *is* gated on the user's optional
  diagnostics setting; the usage metrics above carry no such caveat)

Today, downloading a zip from frostfile.org tells Microsoft nothing. Store
distribution means Microsoft holds a record, tied to a Microsoft account, that
a specific person acquired an identity-protection tool — plus when they run it
and when they remove it.

For most users that is an unremarkable trade for never seeing a scary warning.
For the specific person who needs FrostFile most — someone whose threat model
includes a household member, or who is managing active identity theft — it is
not unremarkable at all. It belongs in plain language on its own page, not
buried in a privacy policy.

**Recommendation: keep the direct download as the primary, privacy-maximal
channel. Treat a Store listing as an additional channel with its own clearly
worded explanation of exactly what Microsoft sees.** That preserves the promise
for the people who need it while removing the barrier for everyone else.

---

## Blocker 1: MSIX deletes the user's database on uninstall

**This is the most serious finding, and it is documented in Microsoft's own
words, twice.**

On Windows we currently store the encrypted database at
`%LOCALAPPDATA%\FrostFile` (`frostfile/config.py:64`). Under MSIX, writes to
`AppData\Local` are **redirected** to a per-user, per-package private location.
And from *Store and retrieve settings and other app data*:

> **Important note about app data:** The lifetime of the app data is tied to
> the lifetime of the app. **If the app is removed, all of the app data will be
> lost as a consequence. Don't use app data to store user data or anything that
> users might perceive as valuable and irreplaceable.**

The packaging documentation confirms uninstall removes "any redirected writes
to AppData or the registry." Microsoft's own taxonomy puts "database records
holding content created by the user" squarely in the category they say must not
live there.

Updates are safe — app data survives them. **Only uninstall destroys it.** A
family uninstalling FrostFile and silently losing every credit-freeze record,
confirmation number, and PIN they entered would be catastrophic and
unrecoverable.

**The escape hatch is closed.** `desktop6:FileSystemWriteVirtualization` can
disable redirection, but it requires the `unvirtualizedResources` restricted
capability, which the docs say is "intended to be used only by certain types of
desktop PC games that are published by Microsoft and our partners" and "is not
intended to be used for other scenarios, because it could compromise the
system's ability to uninstall cleanly." Note the irony: the reason it's gated
is precisely the property we need.

**The fix: move the database out of AppData.** Writes *outside* the package are
explicitly permitted for a full-trust packaged app, are not virtualized, and
survive uninstall. We already have the machinery — `FROSTFILE_DATA_DIR` and the
stored `data_dir` preference both exist in `config.py`.

**Do this regardless of the Store decision.** It also protects users of the
current zip build who "clean up" `%LOCALAPPDATA%` — a thing people do.

A related submission default that must be changed: the product declaration
**"Windows can include this product's data in automatic backups to OneDrive" is
checked by default.** Left alone, an MSIX submission would opt the encrypted
identity database into automatic OneDrive upload. Uncheck it.

If the data lives outside the container, uninstall correctly leaves a folder
behind. Policy 10.2.7 requires we communicate uninstall behaviour — so the app
should tell users where their data lives and that removing the app won't take
it with them.

---

## Blocker 2: loopback must be proven, not assumed

Our entire UI is a loopback web server plus a native window. Under MSIX that is
either a non-issue or a total blocker, depending on one manifest attribute.

**AppContainer kills it.** The archived network-isolation documentation is
blunt: an app listening on an IP loopback address "is prevented from receiving
any incoming packets," and "loopback is permitted only for development
purposes. Usage by a Windows Runtime app installed outside of Visual Studio is
not permitted." `CheckNetIsolation.exe LoopbackExempt` is a **developer-machine
debugging tool** — we cannot ask end users to run it and Store packages get no
exemption.

**Medium-IL full trust avoids it entirely.** Microsoft: "Medium IL apps — which
are also known as full trust apps — **don't run in an AppContainer**." So the
manifest must declare `uap10:TrustLevel="mediumIL"`,
`uap10:RuntimeBehavior="packagedClassicApp"`, and the `runFullTrust` restricted
capability. `runFullTrust` is technically "restricted" and needs justification
at submission, but it is the standard path for every packaged Win32 desktop app
— categorically unlike `unvirtualizedResources`.

**This is documented, not tested.** Nobody has confirmed a PyInstaller +
pywebview app binding 127.0.0.1 inside an installed, signed, full-trust MSIX.
There's a specific sub-risk: pywebview renders via WebView2, whose renderer
processes run in their own AppContainers even when the host is full trust. That
works fine for ordinary unpackaged Win32 hosts; whether MSIX packaging perturbs
it is unverified.

**Prototype this before committing to anything else.** Test a real signed
install, not an F5 loose-file deploy, which behaves differently.

---

## Blocker 3: AGPL needs an affirmative step, or the Store contradicts our licence

Easy to miss and legally real. The **default** Store licence — the Standard
Application License Terms — tells the end user they may not "reverse engineer,
decompile, or disassemble the application" or "publish or otherwise make the
application available for others to copy."

That is flatly incompatible with AGPL-3.0. If it applied, we'd be shipping AGPL
software under terms forbidding exactly what the AGPL grants.

The App Developer Agreement provides the escape: "You may provide a license
agreement to the Customer for your App… **If you do not provide such materials,
then the Standard Application License Terms will apply.**" A supplied licence
must grant rights "no more restrictive" than Microsoft's usage rules — AGPL
restricts *distribution*, not *use*, and clears that bar comfortably.

**So: supply AGPL-3.0 as the licence agreement in the submission. Leave that
field blank and the incompatible default attaches automatically.**

---

## Other requirements worth knowing

**A privacy policy is mandatory, and "we collect nothing" is not an exemption.**
Policy 10.5.1: "Product types that inherently have access to Personal
Information must always have privacy policies. These include… Desktop Bridge
and Win32 products." Both triggers fire for us. Missing it fails certification.
Ours is unusually easy to write and unusually strong.

**Other gotchas for a PyInstaller onedir build:**

- The install directory is genuinely read-only. Audit for anything writing logs
  or `__pycache__` next to the exe.
- The working directory defaults to `System32`, not the app folder. `sys._MEIPASS`
  is fine; anything relying on `os.getcwd()` breaks.
- No elevation, ever — apps requiring it are rejected.
- Avoid shelling out to `cmd.exe`/PowerShell. Worth re-checking the print/export
  paths, which have been a problem area before.
- Windows 10 S compatibility is asserted as a requirement, and "apps that write
  code to disk won't run properly" on S mode — Python writing `.pyc` at runtime
  arguably qualifies. That doc is from 2023 and current enforcement is
  unverified; worth a certification-notes question.
- Policy 10.1.4 requires "an active presence in the Store" — listings can be
  pulled for prolonged inactivity. That's a maintenance commitment.

**A pre-existing-install upgrade case to test.** If a user already runs the
zip build and then installs the Store version, `frostfile.db` exists in real
AppData and opens unvirtualized, but newly created `frostfile.db-wal` and
`-shm` files would land in the package-private location. A SQLite database
whose WAL lives in a different directory than the database is a corruption
scenario. This is inference rather than documented behaviour, but it's cheap to
test and expensive to discover in the field.

---

## Suggested order of work

1. **Move the database out of `%LOCALAPPDATA%`.** Standalone win, no Store
   commitment, protects current users too.
2. **Spike a signed MSIX locally** and test loopback, WebView2, and the
   pre-existing-install upgrade case. If loopback fails, stop — there is no
   workaround.
3. **Only then decide on submission**, with AGPL supplied as the licence, the
   OneDrive backup declaration unchecked, a privacy policy URL, and a listing
   page that says plainly what Microsoft can see.
