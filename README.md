# FrostFile

A local-only tracker for the identity controls you place yourself: credit
freezes across the bureaus most people have never heard of, IRS and Social
Security enrollments, mailing packets for children's freezes, and breach
exposure checks.

It runs on your computer. It has no accounts, no cloud, no subscription, and no
telemetry. It touches the network only when you press a button — a breach
lookup, or the Sources page's agency-link checker — never on its own.

---

## What this is, and what it deliberately isn't

Paid identity-monitoring services sell two things bundled together. The first —
real-time alerts from your credit file — comes from direct contracts with
Equifax, Experian, and TransUnion. There is no consumer or developer tier at any
price: the Fair Credit Reporting Act restricts furnishing consumer reports to
enumerated "permissible purposes," and obtaining one under false pretenses is a
criminal offense, not a terms-of-service violation. **FrostFile cannot and does
not replicate that, and neither can anything else you could build.**

The second thing they sell is knowing which of the fifteen-odd places that hold
a file on you will let you lock it, and keeping track of what you have done.
That part is free, entirely under your control, and nobody does it well.
That is what this is.

There's an asymmetry worth naming: a freeze *prevents* an account from being
opened; monitoring only tells you afterwards. If you have already frozen your
credit, you have replaced the most expensive part of what those services sell.

### What it does

- **Freeze grid** — every family member against ~20 agencies and controls, with
  status, dates, confirmation numbers, and freeze PINs (encrypted).
- **Agency directory** — where each file lives, why it matters, how to freeze
  it, how to lift it, and what it costs (almost always nothing).
- **Mailing packets** — children's freezes are free but mail-only. FrostFile
  prints the cover letter and the per-agency document checklist.
- **Reminders** — IP PIN retrieval, SSA earnings review, report pulls, broker
  opt-outs, freeze re-verification. Exports to `.ics`.
- **Report comparison** — save each credit report pull; see what's new.
- **Breach checks** — password checking is free and sends only a scrambled
  prefix (never the password); email checking needs your own Have I Been Pwned key.

### What it can't do

- Alert you when someone applies for credit. Nothing consumer-accessible can.
- Freeze anything on your behalf. You place every freeze yourself; this tracks it.
- Tell you a child's credit file is clean. It reminds you to ask; the bureau answers.

---

## Everything is cited

Every mailing address, phone number, and procedural claim carries a hyperlinked
superscript to its source. Click any of them.

Sources come in two confidence levels, and the difference is enforced in code:

| Marker | Meaning |
| --- | --- |
| <sup>1</sup> linked to a page tagged **retrieved** | The page was fetched and read when the directory was compiled, and the claim came from its text. |
| <sup>1</sup> linked to a page tagged **not captured** | The organization's own page for the topic, linked so you can check — but its contents weren't recorded. |
| <sup>?</sup> | No source at all. Verify before relying on it. |

**FrostFile will not print a mailing packet for an agency whose address didn't
meet the first bar.** A minor-freeze packet contains a birth certificate and a
Social Security card; mailing one to a stale address is worse than not mailing
it. Those agencies link out to their own page instead.

The full list is on the Sources page in the app, and in `frostfile/sources.py`.
Directory compiled 2026-08-03 — agencies move, so re-check before a big mailing.

---

## Install

You need Python 3.10 or newer. This isn't published to PyPI — you install it
from the folder or from a built wheel.

### From a copy of this folder

```bash
cd FrostFile
pipx install .        # or: uv tool install .
frostfile
```

FrostFile opens in its own window (or your browser, if the window backend
isn't available). If nothing appears, go to <http://localhost:8731>.

`pip install .` works too, but `pipx`/`uv tool` keep the dependencies out of
your system Python, which is what you want for something you hand to someone else.

### Handing it to a coworker

Build a wheel once and send them the single file:

```bash
uv build --wheel          # produces dist/frostfile-0.3.0-py3-none-any.whl
```

They run `pipx install frostfile-0.3.0-py3-none-any.whl` and then `frostfile`.
No repository, no toolchain, no build step.

### Without installing anything permanently

```bash
uvx --from . frostfile
```

### First run

You'll be asked to set a master passphrase. Four or five unrelated words beat
one clever word — length is what matters.

> **There is no password reset.** The passphrase is the only key to your data.
> Nobody can recover it. Put it in your password manager *before* you continue.

---

## Security

**Threat model.** This protects against someone who obtains a copy of your
database — a stolen laptop, a backup that synced somewhere you forgot about, a
shared machine. It does not protect against malware running as you while the
vault is unlocked, and it can't protect against someone who has your passphrase.

**What's encrypted.** Names, dates of birth, SSNs, emails, phone numbers,
addresses, freeze confirmation numbers, freeze PINs, notes, stored report text,
breach results, and your HIBP key. AES-256-GCM per field, key derived with
Argon2id.

**What isn't.** Row ids, whether a person is an adult or a minor, freeze
statuses, and action dates — these stay queryable so the app can sort and filter.
Someone who steals the file learns "this household has two adults and three
minors, frozen at these agencies on these dates" but learns no identities. If
that trade isn't acceptable to you, use full-disk encryption underneath.

**Full SSNs are opt-in and off by default.** They're only needed to pre-fill
mailing packets. Leave it off and packets print a blank line you fill in by hand.

**Network.** Binds to `127.0.0.1` only, and refuses any other interface unless
you set `FROSTFILE_ALLOW_REMOTE=1` — there's no TLS and no multi-user access
control, so exposing it would be a mistake. Outbound traffic happens only on a
button press: the two breach lookups, the one-off API-key validation, and the
Sources page's link checker (which fetches the agency pages to see if they're
alive, sending nothing about you). Password checks use HIBP's k-anonymity range
API, so the password itself never leaves your machine. Email checks do send the
address, which is why they require your own key and are off until you configure
one.

**Auto-lock** after 15 minutes idle (`FROSTFILE_LOCK_MINUTES` to change). The
key lives only in the server process's memory; locking drops it. Restarting
locks the vault.

---

## Backups

Everything lives in one folder. `frostfile --where` prints it.

- macOS: `~/Library/Application Support/FrostFile`
- Linux: `~/.local/share/frostfile`
- Windows: `%LOCALAPPDATA%\FrostFile`

Settings → **Make a backup now** writes a consistent copy while the app is
running. Backups are encrypted with the same passphrase, so they're safe to put
on a USB stick or in cloud storage — and useless without the passphrase.

If you change your passphrase, old backups still need the *old* one. Keep it
until you've made a fresh backup.

---

## Sharing this with people

It's AGPL-licensed — pass it around freely for personal use; anyone who builds
on it or offers it as a service must share their changes under the same terms.
Two things worth saying to whoever you give it to:

1. **The passphrase is unrecoverable.** People will not believe this until it
   happens to them. Say it twice.
2. **The directory has a compile date.** If they're mailing documents months
   after you hand this over, they should click through the citations first.
   That's what they're there for.

If you correct an address or a link, update both `frostfile/seeds.py` and
`frostfile/sources.py` — the value *and* the source backing it — so the fix
carries to everyone.

---

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FROSTFILE_DATA_DIR` | OS app data dir | Where the database lives |
| `FROSTFILE_PORT` | `8731` | Listening port |
| `FROSTFILE_HOST` | `127.0.0.1` | Interface to bind |
| `FROSTFILE_LOCK_MINUTES` | `15` | Idle auto-lock timeout |
| `FROSTFILE_ALLOW_REMOTE` | unset | Required to bind non-loopback |

```
frostfile --help        # all flags
frostfile --where       # print the data directory and database path
frostfile --no-browser  # don't open a browser
```

---

## A short list of things worth doing that this app only reminds you about

- **An IRS IP PIN for every family member, including children.** Refund fraud is
  the fastest way to monetize a stolen SSN, and an IP PIN blocks it outright.
- **Freeze the children's credit at all three bureaus.** Free, mail-only, and the
  single highest-value thing on the list — misuse of a minor's SSN typically goes
  unnoticed for a decade.
- **Claim every account before someone else does** — SSA, USPS Informed Delivery,
  IRS online account.
- **Port-out PIN and number lock with your mobile carrier**, on every line. SIM
  swapping defeats SMS two-factor on everything else you're protecting.
- **If the breach that brought you here offered free monitoring, take it.** It's
  free credit-file visibility you can't otherwise buy.

---

## License

GNU AGPL v3 or later. Free to use and share; anyone who distributes a modified
version — or runs one as a service for others — must make their source
available under the same license. No warranty. This is a record-keeping tool,
not legal or financial advice.
