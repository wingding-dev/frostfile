#!/usr/bin/env python3
"""Release-time reputation pipeline: submit, track, verify.

Getting a new build trusted everywhere is ~30 separate web forms, and most of
them want the same eight facts typed in slightly different boxes. This script
holds the facts once, prints a ready-to-paste packet per vendor, remembers what
was submitted for which version, and asks VirusTotal who still flags us.

    python tools/reputation.py release 1.0.1     # seed a new version
    python tools/reputation.py todo              # what still needs doing
    python tools/reputation.py packet eset       # text to paste into the form
    python tools/reputation.py mark eset submitted --ref 12345
    python tools/reputation.py scan              # who still flags the build?
    python tools/reputation.py md                # refresh docs/REPUTATION.md

Zero-network rule note: tools/ is exempt (see tests/test_hardening.py) — this
is a release-time dev script and is never shipped inside the app.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS_FILE = REPO / "tools" / "reputation_targets.json"
LEDGER_FILE = REPO / "docs" / "reputation-status.json"
SUMS_FILE = REPO / "drive-kit" / "SHA256SUMS.txt"
DOC_FILE = REPO / "docs" / "REPUTATION.md"

STATUSES = ("todo", "submitted", "approved", "rejected", "blocked", "n/a")
VT_FILE_API = "https://www.virustotal.com/api/v3/files/"

# Facts every vendor form asks for, in slightly different words. Edit here, not
# in thirty browser tabs.
PROJECT = {
    "product": "FrostFile",
    "vendor": "FrostFile (independent open-source project)",
    "site": "https://frostfile.org",
    "repo": "https://github.com/wingding-dev/frostfile",
    "license": "AGPL-3.0-or-later",
    "contact": "updates@frostfile.org",
    "category": "Desktop utility — offline personal-records tracker",
    "toolchain": "Python 3.12 + PyInstaller (onedir), built by GitHub Actions",
    "download_windows": "https://frostfile.org/download/FrostFile-windows.zip",
    "download_mac": "https://frostfile.org/download/FrostFile-mac.zip",
    "download_source": "https://frostfile.org/download/frostfile-1.0.0.tar.gz",
}

# Why a heuristic engine flags us, in the words a malware analyst wants to read.
# Every claim here is checkable against the public repo, which is the point.
RATIONALE = """\
FrostFile is a free, open-source desktop application that helps a family track
credit freezes and identity-protection paperwork. It is published under the
AGPL, and the complete source for this exact build is public at
{repo}
and was built by GitHub Actions from the tagged commit.

Why an automated scanner may flag it:

* It is packaged with PyInstaller, which bundles a Python interpreter and
  extracts to a temp directory at launch. This packing pattern is shared with
  malware and is a known source of generic/heuristic detections.
* It starts a web server bound to 127.0.0.1 and opens a local window against
  it. The UI is a local web app; the server is loopback-only and never listens
  on an external interface.
* It uses the `cryptography` and `argon2-cffi` libraries to encrypt the user's
  own local database with a passphrase they choose. It encrypts only its own
  data file, in place, at rest — it does not enumerate, traverse, or encrypt
  user documents, and it has no ransom, key-exfiltration, or network path.

What it verifiably does NOT do:

* It makes zero outbound network connections. There is no HTTP client anywhere
  in the shipped package — this is enforced by an automated test
  (tests/test_hardening.py::test_zero_network_rule_no_http_client_in_app_code)
  that fails the build if one is ever added. No telemetry, no update check, no
  analytics, no phone-home of any kind.
* It installs no service or driver, creates no scheduled task, writes nothing
  outside its own data directory, and makes no persistence or autostart
  registry changes.
* It bundles no third-party installers, no adware, and no monetization.

The application is unrelated to any known malware family. I am the author and
am requesting the detection on this file be reviewed and removed.\
""".format(repo=PROJECT["repo"])


# --------------------------------------------------------------------------
# storage


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_targets() -> list[dict]:
    data = _read_json(TARGETS_FILE, None)
    if data is None:
        sys.exit(f"Missing target registry: {TARGETS_FILE}")
    return data["targets"]


def load_ledger() -> dict:
    return _read_json(LEDGER_FILE, {"schema": 1, "current": None, "releases": {}})


def save_ledger(ledger: dict) -> None:
    _write_json(LEDGER_FILE, ledger)


def find_target(targets: list[dict], tid: str) -> dict:
    for t in targets:
        if t["id"] == tid:
            return t
    matches = [t for t in targets if tid.lower() in t["id"].lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        sys.exit("Ambiguous: " + ", ".join(m["id"] for m in matches))
    sys.exit(f"Unknown target '{tid}'. Try: python tools/reputation.py list")


def current_version(ledger: dict) -> str:
    if not ledger.get("current"):
        sys.exit("No current release. Run: python tools/reputation.py release <version>")
    return ledger["current"]


def read_sums() -> dict[str, str]:
    """Parse drive-kit/SHA256SUMS.txt into {filename: sha256}."""
    if not SUMS_FILE.exists():
        return {}
    out = {}
    for line in SUMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            out[parts[1]] = parts[0]
    return out


# --------------------------------------------------------------------------
# commands


def cmd_release(args) -> None:
    """Seed a new version: snapshot hashes, reset per-release targets to todo."""
    ledger = load_ledger()
    targets = load_targets()
    version = args.version
    sums = read_sums()

    if version in ledger["releases"] and not args.force:
        sys.exit(f"Release {version} already exists. Use --force to reset it.")

    prev = ledger.get("current")
    entry = {
        "artifacts": sums,
        "signed_windows": args.signed,
        "notarized_mac": False,
        "targets": {},
    }
    for t in targets:
        if t["cadence"] == "per-release":
            entry["targets"][t["id"]] = {"status": "todo", "date": None, "ref": None, "notes": ""}
        else:
            # Standing items carry their state forward — a site categorization
            # or a notarized signing identity does not expire per build.
            carried = ledger["releases"].get(prev, {}).get("targets", {}).get(t["id"])
            entry["targets"][t["id"]] = carried or {
                "status": "todo", "date": None, "ref": None, "notes": "",
            }

    ledger["releases"][version] = entry
    ledger["current"] = version
    save_ledger(ledger)

    per_release = sum(1 for t in targets if t["cadence"] == "per-release")
    print(f"Seeded release {version}: {per_release} per-release submissions reset to todo.")
    if not sums:
        print(f"WARNING: no hashes found in {SUMS_FILE.relative_to(REPO)} — update it first.")
    else:
        for name, digest in sums.items():
            print(f"  {name}: {digest[:16]}…")
    if not args.signed:
        print("\nNOTE: marked as UNSIGNED. Once the build is code-signed, re-run with")
        print("      --signed so the submission packets say so (it materially helps).")


def cmd_list(args) -> None:
    targets = load_targets()
    ledger = load_ledger()
    version = ledger.get("current")
    state = ledger["releases"].get(version, {}).get("targets", {}) if version else {}

    for t in targets:
        if args.category and t["category"] != args.category:
            continue
        if args.public_only and not t.get("public", True):
            continue
        st = state.get(t["id"], {}).get("status", "todo")
        if args.todo and st not in ("todo", "rejected"):
            continue
        flag = "" if t.get("public", True) else "  [not open to non-customers]"
        print(f"{st:>9}  {t['id']:<24} {t['name']}  ({t['cadence']}){flag}")


def cmd_todo(args) -> None:
    args.category, args.public_only, args.todo = None, True, True
    cmd_list(args)


def cmd_packet(args) -> None:
    """Print everything one vendor's form asks for, ready to paste."""
    targets = load_targets()
    ledger = load_ledger()
    t = find_target(targets, args.target)
    version = args.version or current_version(ledger)
    rel = ledger["releases"].get(version, {})
    sums = rel.get("artifacts", {})
    signed = rel.get("signed_windows", False)

    w = 78
    print("=" * w)
    print(f"  {t['name']}  —  {t['category'].upper()}  ({t['cadence']})")
    print("=" * w)
    print(f"\nSUBMIT AT:  {t['url']}")
    if t.get("email"):
        print(f"OR EMAIL :  {t['email']}")
    print(f"ACCOUNT  :  {t.get('auth') or 'none required'}")
    print(f"ACCEPTS  :  {', '.join(t.get('accepts', [])) or 'see form'}")
    if t.get("max_upload_mb"):
        print(f"MAX SIZE :  {t['max_upload_mb']} MB", end="")
        print("   <-- our zip may exceed this; use the URL field instead"
              if t["max_upload_mb"] < 100 else "")
    if t.get("turnaround"):
        print(f"TURNAROUND: {t['turnaround']}")
    if t.get("notes"):
        print(f"\nNOTE: {t['notes']}")

    print("\n" + "-" * w)
    print("FIELDS")
    print("-" * w)
    print(f"Product name      : {PROJECT['product']} {version}")
    print(f"Publisher/vendor  : {PROJECT['vendor']}")
    print(f"Website           : {PROJECT['site']}")
    print(f"Source repository : {PROJECT['repo']}")
    print(f"License           : {PROJECT['license']}")
    print(f"Contact email     : {PROJECT['contact']}")
    print(f"Category          : {PROJECT['category']}")
    print(f"Built with        : {PROJECT['toolchain']}")
    print(f"Code-signed       : {'yes' if signed else 'NO — not yet signed'}")
    print(f"Download (Windows): {PROJECT['download_windows']}")
    print(f"Download (Mac)    : {PROJECT['download_mac']}")
    if sums:
        print("\nSHA-256:")
        for name, digest in sums.items():
            print(f"  {name}\n    {digest}")

    print("\n" + "-" * w)
    print("DESCRIPTION / WHY THIS IS A FALSE POSITIVE  (paste this)")
    print("-" * w)
    print(RATIONALE)
    print("\n" + "-" * w)
    print(f"After submitting:  python tools/reputation.py mark {t['id']} submitted --ref <ticket>")
    print("-" * w)


def cmd_mark(args) -> None:
    ledger = load_ledger()
    targets = load_targets()
    t = find_target(targets, args.target)
    version = args.version or current_version(ledger)
    if args.status not in STATUSES:
        sys.exit(f"Status must be one of: {', '.join(STATUSES)}")

    entry = ledger["releases"][version]["targets"].setdefault(
        t["id"], {"status": "todo", "date": None, "ref": None, "notes": ""}
    )
    entry["status"] = args.status
    entry["date"] = args.date or time.strftime("%Y-%m-%d")
    if args.ref:
        entry["ref"] = args.ref
    if args.notes:
        entry["notes"] = args.notes
    save_ledger(ledger)
    print(f"{t['name']} → {args.status} ({entry['date']})"
          + (f" ref={entry['ref']}" if entry.get("ref") else ""))


def cmd_status(args) -> None:
    ledger = load_ledger()
    targets = load_targets()
    version = args.version or current_version(ledger)
    state = ledger["releases"][version]["targets"]
    by_cat: dict[str, list] = {}
    for t in targets:
        by_cat.setdefault(t["category"], []).append(t)

    print(f"\nFrostFile {version} — reputation status\n")
    total = done = 0
    for cat, items in by_cat.items():
        print(f"  {cat.upper()}")
        for t in items:
            st = state.get(t["id"], {}).get("status", "todo")
            if st != "n/a":
                total += 1
                if st == "approved":
                    done += 1
            ref = state.get(t["id"], {}).get("ref") or ""
            date = state.get(t["id"], {}).get("date") or ""
            print(f"    {st:>9}  {t['name']:<32} {date:<12} {ref}")
        print()
    print(f"  {done}/{total} cleared\n")


def cmd_md(args) -> None:
    """Regenerate the status table inside docs/REPUTATION.md between markers."""
    ledger = load_ledger()
    targets = load_targets()
    version = args.version or current_version(ledger)
    state = ledger["releases"][version]["targets"]

    icon = {"approved": "✅", "submitted": "⏳", "todo": "⬜", "rejected": "❌",
            "blocked": "🚫", "n/a": "—"}
    lines = [f"_Generated by `tools/reputation.py md` for **{version}**. "
             f"Do not hand-edit between the markers._", ""]
    by_cat: dict[str, list] = {}
    for t in targets:
        by_cat.setdefault(t["category"], []).append(t)
    titles = {"av": "Antivirus engines", "web": "Web / URL reputation",
              "os": "OS trust (signing & notarization)", "email": "Email deliverability"}
    for cat, items in by_cat.items():
        lines += [f"### {titles.get(cat, cat)}", "",
                  "| | Target | Cadence | Status | Date | Ref |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for t in items:
            s = state.get(t["id"], {})
            st = s.get("status", "todo")
            lines.append(
                f"| {icon.get(st, '')} | [{t['name']}]({t['url']}) | {t['cadence']} "
                f"| {st} | {s.get('date') or ''} | {s.get('ref') or ''} |"
            )
        lines.append("")
    block = "\n".join(lines)

    if not DOC_FILE.exists():
        print(block)
        return
    text = DOC_FILE.read_text(encoding="utf-8")
    start, end = "<!-- STATUS:BEGIN -->", "<!-- STATUS:END -->"
    if start not in text or end not in text:
        print(block)
        return
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    DOC_FILE.write_text(f"{head}{start}\n{block}{end}{tail}", encoding="utf-8")
    print(f"Updated status table in {DOC_FILE.relative_to(REPO)} for {version}.")


def cmd_scan(args) -> None:
    """Ask VirusTotal which engines currently flag our artifacts.

    Purely observational. VirusTotal's own docs are blunt about this: it
    "does not produce any verdicts of its own", and only the vendor that
    produced a detection can clear it. Uploading here fixes nothing — it tells
    you WHICH doors to knock on so you skip the other sixty.

    Free public API: 4 requests/minute, 500/day, and per VT's terms not for use
    in commercial products or services. This is internal release tooling for a
    free AGPL project, which is within those terms.
    """
    key = os.environ.get("VT_API_KEY")
    if not key:
        sys.exit("Set VT_API_KEY (free key from virustotal.com → your profile → API key).")

    ledger = load_ledger()
    version = args.version or current_version(ledger)
    artifacts = ledger["releases"][version].get("artifacts", {})
    if not artifacts:
        sys.exit(f"No artifact hashes recorded for {version}.")

    targets = {t["id"]: t for t in load_targets()}
    vt_names = {}
    for t in targets.values():
        for name in t.get("vt_engines", []):
            vt_names[name.lower()] = t["id"]

    flagged_ids: set[str] = set()
    for i, (filename, digest) in enumerate(artifacts.items()):
        if not args.all and not filename.endswith(".zip"):
            continue  # the exe zips are what users download and AV scans
        if i:
            time.sleep(16)  # free tier allows 4 requests/minute
        print(f"\n=== {filename} ===")
        print(f"    {digest}")
        req = urllib.request.Request(VT_FILE_API + digest, headers={"x-apikey": key})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print("    NOT SEEN by VirusTotal yet. Upload it once at "
                      "https://www.virustotal.com/gui/home/upload — files over "
                      "32MB need the large-file upload URL flow.")
                continue
            if exc.code == 429:
                sys.exit("    Rate limited (free tier). Wait a minute and retry.")
            raise

        attrs = data["data"]["attributes"]
        stats = attrs.get("last_analysis_stats", {})
        print(f"    malicious={stats.get('malicious', 0)}  "
              f"suspicious={stats.get('suspicious', 0)}  "
              f"undetected={stats.get('undetected', 0)}")
        results = attrs.get("last_analysis_results", {})
        hits = [(eng, r) for eng, r in results.items()
                if r.get("category") in ("malicious", "suspicious")]
        if not hits:
            print("    CLEAN across all engines. Nothing to submit.")
            continue
        print("    Flagged by:")
        for eng, r in sorted(hits):
            tid = vt_names.get(eng.lower())
            tag = f"  → tools/reputation.py packet {tid}" if tid else "  (no submission target mapped)"
            print(f"      {eng:<22} {r.get('result') or r['category']}{tag}")
            if tid:
                flagged_ids.add(tid)

    if flagged_ids:
        print("\nTargets to submit to for this build:")
        for tid in sorted(flagged_ids):
            print(f"  python tools/reputation.py packet {tid}")
    print("\nReminder: VirusTotal is a mirror, not a door. Clearing a detection "
          "requires the vendor's own false-positive form.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("release", help="seed a new version from SHA256SUMS.txt")
    s.add_argument("version")
    s.add_argument("--signed", action="store_true", help="this build is code-signed")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_release)

    s = sub.add_parser("list", help="list every target and its status")
    s.add_argument("--category", choices=["av", "web", "os", "email"])
    s.add_argument("--todo", action="store_true")
    s.add_argument("--public-only", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("todo", help="what still needs submitting")
    s.set_defaults(func=cmd_todo)

    s = sub.add_parser("packet", help="print a ready-to-paste submission packet")
    s.add_argument("target")
    s.add_argument("--version")
    s.set_defaults(func=cmd_packet)

    s = sub.add_parser("mark", help="record a submission's outcome")
    s.add_argument("target")
    s.add_argument("status", choices=STATUSES)
    s.add_argument("--ref", help="vendor ticket/case number")
    s.add_argument("--notes")
    s.add_argument("--date")
    s.add_argument("--version")
    s.set_defaults(func=cmd_mark)

    s = sub.add_parser("status", help="status of every target for a version")
    s.add_argument("--version")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("md", help="regenerate the table in docs/REPUTATION.md")
    s.add_argument("--version")
    s.set_defaults(func=cmd_md)

    s = sub.add_parser("scan", help="ask VirusTotal who still flags the build")
    s.add_argument("--version")
    s.add_argument("--all", action="store_true", help="include source tarball/wheel")
    s.set_defaults(func=cmd_scan)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
