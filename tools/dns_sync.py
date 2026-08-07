"""One-shot DNS fix for the frostfile.org zone on Cloudflare (2026-08-06).

DEV TOOL — never shipped. The zone was imported while the domain still ran
Namecheap parking + eforward email-forwarding, but the domain now uses
Namecheap Private Email (mx1/mx2.privateemail.com) and the website moves to
Cloudflare Pages. Run before switching nameservers, or mail and web both
break the moment they flip.

Reads the API token (Zone.DNS:Edit) from
~/.config/identilock-dev/cloudflare-api-token.

Usage:  .venv/bin/python tools/dns_sync.py          # dry run, prints plan
        .venv/bin/python tools/dns_sync.py --apply  # make the changes
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ZONE = "d0094eb8f712a894d504d197186227d0"  # frostfile.org
BASE = f"https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records"
TOKEN = (
    (Path.home() / ".config/identilock-dev/cloudflare-api-token")
    .read_text()
    .strip()
)

# Mirrors the records currently live on Namecheap's DNS for Private Email
# (verified against pdns1.registrar-servers.com on 2026-08-06), plus the
# Pages web records. Mail records must stay DNS-only (unproxied).
MAIL_RECORDS = [
    {"type": "MX", "name": "frostfile.org", "content": "mx1.privateemail.com", "priority": 10},
    {"type": "MX", "name": "frostfile.org", "content": "mx2.privateemail.com", "priority": 10},
    {"type": "TXT", "name": "frostfile.org", "content": '"v=spf1 include:spf.privateemail.com ~all"'},
    {"type": "CNAME", "name": "mail", "content": "privateemail.com", "proxied": False},
    {"type": "CNAME", "name": "autoconfig", "content": "privateemail.com", "proxied": False},
    {"type": "CNAME", "name": "autodiscover", "content": "privateemail.com", "proxied": False},
    {"type": "SRV", "name": "_autodiscover._tcp",
     "data": {"priority": 0, "weight": 0, "port": 443, "target": "privateemail.com"}},
]
WEB_RECORDS = [
    {"type": "CNAME", "name": "frostfile.org", "content": "frostfile.pages.dev", "proxied": True},
    {"type": "CNAME", "name": "www", "content": "frostfile.pages.dev", "proxied": True},
]


def api(method: str, url: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(payload).encode() if payload else None,
    )
    with urllib.request.urlopen(req) as response:
        return json.load(response)


def is_stale(record: dict) -> bool:
    return (
        (record["type"] == "MX" and "registrar-servers" in record["content"])
        or (record["type"] == "TXT" and "efwd.registrar-servers" in record["content"])
        or (record["type"] == "A" and record["content"] == "192.64.119.23")
        or (record["type"] == "CNAME" and "parkingpage" in record["content"])
    )


def main() -> int:
    apply = "--apply" in sys.argv
    existing = api("GET", BASE + "?per_page=100")["result"]

    for record in existing:
        if is_stale(record):
            print(f"delete  {record['type']:5} {record['name']:26} {record['content'][:55]}")
            if apply:
                api("DELETE", f"{BASE}/{record['id']}")

    for record in MAIL_RECORDS + WEB_RECORDS:
        label = record.get("content") or record["data"]["target"]
        print(f"create  {record['type']:5} {record['name']:26} {label}")
        if apply:
            api("POST", BASE, record)

    if apply:
        final = api("GET", BASE + "?per_page=100")["result"]
        print(f"\nzone now holds {len(final)} records:")
        for record in final:
            proxied = "PROXIED" if record.get("proxied") else "dns-only"
            print(f"  {record['type']:5} {record['name']:28} {proxied:8} {record['content'][:55]}")
    else:
        print("\nDRY RUN — re-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
