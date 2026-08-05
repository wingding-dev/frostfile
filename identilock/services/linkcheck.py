"""Dead-link detection for the citation registry.

The directory ships as static data, so the honest failure mode is rot: an
agency moves a page and a citation quietly points at a 404. This module lets
the user press one button and see which links still resolve — like an
antivirus updating its list, except it only *reports*. It never changes an
address or a letter, because a working URL proves the page exists, not that
its contents still say what was recorded. Re-verification stays human.

Only runs when the user asks. The requests carry no user data — they are the
same anonymous page fetches a browser would make.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; Identilock link check)"
TIMEOUT = httpx.Timeout(10.0)
MAX_WORKERS = 8

STATUS_OK = "ok"
STATUS_DEAD = "dead"
STATUS_UNREACHABLE = "unreachable"


def _probe(client: httpx.Client, url: str) -> dict:
    try:
        response = client.head(url, follow_redirects=True)
        # Plenty of sites reject HEAD (403/405) while serving GET fine, so a
        # failure gets one streamed GET — headers only, body never downloaded.
        if response.status_code >= 400:
            with client.stream("GET", url, follow_redirects=True) as streamed:
                response = streamed
        status = STATUS_OK if response.status_code < 400 else STATUS_DEAD
        return {"status": status, "code": response.status_code}
    except httpx.RequestError as exc:
        return {"status": STATUS_UNREACHABLE, "error": type(exc).__name__}


def check_links(urls: dict[str, str]) -> dict[str, dict]:
    """{key: url} -> {key: {status, ...}}, fetched concurrently."""
    with httpx.Client(timeout=TIMEOUT, headers={"user-agent": USER_AGENT}) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = pool.map(lambda item: (item[0], _probe(client, item[1])), urls.items())
            return dict(results)
