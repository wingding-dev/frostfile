"""Release-time dead-link check for the citation registry.

DEV TOOL — never shipped inside the app. FrostFile makes zero network
connections at runtime (project requirement), so link rot is caught here
instead: a human runs this before cutting each release, fixes or re-verifies
anything broken, and stamps frostfile/sources.py:LINKS_VERIFIED_ON with the
date. A working URL proves the page exists, not that its contents still say
what was recorded — re-verification of facts stays human.

Usage:  .venv/bin/python tools/linkcheck.py
Exits non-zero if any link fails, so it can gate a release script.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

# A plain browser-like agent — no product name, so a link check does not
# announce to each agency that a tool like this is being used.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = httpx.Timeout(10.0)
MAX_WORKERS = 8

STATUS_OK = "ok"
STATUS_DEAD = "dead"
STATUS_BLOCKED = "blocked"
STATUS_UNREACHABLE = "unreachable"


def _probe(client: httpx.Client, url: str) -> dict:
    try:
        response = client.head(url, follow_redirects=True)
        # Plenty of sites reject HEAD (403/405) while serving GET fine, so a
        # failure gets one streamed GET — headers only, body never downloaded.
        if response.status_code >= 400:
            with client.stream("GET", url, follow_redirects=True) as streamed:
                response = streamed
        if response.status_code < 400:
            status = STATUS_OK
        elif response.status_code == 403:
            # Government and bureau sites routinely 403 scripted requests while
            # serving browsers fine (ssa.gov, transunion.com, optoutprescreen).
            # A human still has to eyeball these in a real browser.
            status = STATUS_BLOCKED
        else:
            status = STATUS_DEAD
        return {"status": status, "code": response.status_code}
    except httpx.RequestError as exc:
        return {"status": STATUS_UNREACHABLE, "error": type(exc).__name__}


def check_links(urls: dict[str, str]) -> dict[str, dict]:
    """{key: url} -> {key: {status, ...}}, fetched concurrently."""
    with httpx.Client(timeout=TIMEOUT, headers={"user-agent": USER_AGENT}) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = pool.map(lambda item: (item[0], _probe(client, item[1])), urls.items())
            return dict(results)


def main() -> int:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from frostfile import sources as source_registry

    entries = source_registry.all_sources()
    print(f"Checking {len(entries)} source links…")
    results = check_links({s.key: s.url for s in entries})
    broken, blocked = 0, 0
    for source in entries:
        result = results[source.key]
        if result["status"] == STATUS_OK:
            print(f"  ok       {source.key}")
        elif result["status"] == STATUS_BLOCKED:
            blocked += 1
            print(f"  BLOCKED  {source.key}  {source.url}")
        else:
            broken += 1
            print(f"  FAIL     {source.key}  {result}  {source.url}")
    if blocked:
        print(f"\n{blocked} site(s) refuse scripted requests (403) — open each "
              "BLOCKED URL in a real browser and confirm it loads.")
    if broken:
        print(f"\n{broken} link(s) failed — fix or re-verify before release.")
        return 1
    print(f"\nNo dead links. Once any BLOCKED URLs are confirmed in a browser, "
          "update LINKS_VERIFIED_ON in frostfile/sources.py to today's date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
