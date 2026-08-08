# What FrostFile costs to run, and what could go wrong

Researched 2026-08-08 against current published Cloudflare pricing.

**The short version: organic popularity cannot produce a scary bill.** At a
million downloads a month the infrastructure costs about **$31**, and **$25 of
that is the visitor counter, not the downloads**. Fix the counter and the same
traffic costs about $5.30. No Patreon is needed at any realistic scale.

The one number that makes this safe: **R2 egress is free.** Bandwidth is the
line item that bankrupts file distribution everywhere else, and here 50 TB
costs $0.00. Everything left is per-operation pennies.

---

## The three scenarios

Assuming ~50MB per download and a 5:1 visits-to-downloads ratio.

| | Downloads/mo | Visits/mo | Egress | Monthly cost |
| --- | --- | --- | --- | --- |
| Modest | 1,000 | 5,000 | 50 GB | **$0.00** |
| Popular | 50,000 | 250,000 | 2.5 TB | **$0.00** free / **$5.00** paid |
| Viral | 1,000,000 | 5,000,000 | 50 TB | **~$31.00** |

In the viral case: $5 Workers subscription, $25 KV writes, $0.50 KV reads, and
**$0.00 for all 50 terabytes of actual file transfer**.

Worth knowing: streaming an R2 object does not consume Worker CPU time.
Cloudflare's docs are explicit that waiting on network requests doesn't count,
and there's no duration limit while the client stays connected. A Worker
piping 75MB to a slow phone for 90 seconds bills a few milliseconds.

---

## What breaks first, and whether it matters

The failure ladder, in the order you'd hit it:

| Limit | Breaks at roughly | What actually happens |
| --- | --- | --- |
| **KV writes, 1,000/day** | ~1,000 visits+downloads/day | Counter freezes. **Downloads keep working.** |
| KV same-key writes, 1/sec | any burst over 1 event/sec | Counter undercounts during spikes |
| KV reads, 100,000/day | ~55,000 events/day | Counter reads zero. Downloads fine. |
| **Workers, 100,000 req/day** | ~100,000 events/day | **Error 1027 — downloads go DOWN** |
| R2 Class B, 10M/mo | 10M downloads/mo | Cost only, $0.36/million |
| Egress | never | free at any volume |

**The critical distinction:** when KV hits a limit it throws an exception
*inside* the Worker, so our code decides what happens. When the Workers request
cap is hit, Cloudflare rejects the request *before* our code runs and returns
Error 1027 to the user — we cannot handle it.

**Our code already handles the KV case correctly.** Both counter writes are
wrapped in try/catch, and the download path fetches from R2 *before* touching
KV, so a KV outage can't prevent the file being served. The comment in
`worker.js` — "A download must NEVER fail because the odometer couldn't tick" —
is doing real work. Exceeding the KV free tier costs us a frozen counter and
nothing else.

Neither limit auto-bills. The free tier does not silently upgrade you; you get
errors, not an invoice.

**So the only outage risk is the Workers 100k/day cap, and it costs $5/month to
remove.** Move to Workers Paid at around 30,000 requests/day rather than
waiting — crossing that cliff takes downloads offline with no warning, on
precisely the day you get popular.

---

## The real risk: abuse, because there is no spend cap

**Cloudflare offers no spending limit, budget cap, or auto-shutoff.** Once
you're on a paid plan with a card attached, usage charges accrue without a
ceiling. That's the uncomfortable part of this analysis and it deserves stating
plainly.

Cost of scripted abuse, per million requests, on the paid plan:

| Target | Cost per million | Of which KV writes |
| --- | --- | --- |
| `POST /api/hit` | ~$6.30 | $5.00 (79%) |
| `GET /download/*` | ~$6.16 | $5.00 (81%) |

A sustained 1,000 requests/second against `/api/hit` for 24 hours is about
**$544/day**. A week unnoticed is a four-figure bill. `/api/hit` is the worst
target because it's a cheap POST with no payload — maximum cost inflicted per
byte the attacker sends.

Two things work in our favour. Cloudflare does not bill for attack traffic it
mitigates — their DDoS page promises "no penalty for being attacked" and
absorbs floods at the edge without ever invoking our Worker. And KV writes are
94% of the exposure, which means one change removes most of it.

The gap that remains is low-and-slow scripted abuse that looks like legitimate
traffic. That isn't DDoS, won't be auto-mitigated, and will bill normally.

---

## Recommended, cheapest first

**1. Take the KV write off the unauthenticated hot path.** Highest leverage by
a wide margin: it is simultaneously the biggest organic cost, the entire abuse
exposure, and the first free-tier breakage. Sampling — write only 1 in N hits
and increment by N — cuts KV writes 100× at N=100, sidesteps the 1-write/sec
limit, takes about four lines, and moves the viral bill from ~$31 to ~$5.55.
The tradeoff is that the odometer becomes approximate. Given it's already
decoration that degrades gracefully, and already undercounts during spikes
because of the 1/sec cap, that seems an easy trade — but it's a product call.

**2. Spend the one free rate-limiting rule on `/api/hit`.** The free plan
includes exactly one rule, counting by IP with a 10-second window. That's weak
against a distributed script, but it raises the cost of casual abuse for $0.

**3. Set a calendar reminder to check usage.** Since no hard cap exists, human
attention is the actual backstop. The "Usage Based Billing" notification may
require a Pro zone plan — check the dashboard's Notifications page.

**4. Move to Workers Paid at ~30,000 requests/day**, before the cliff.

### The caching tension, and how to resolve it

`worker.js` sets `Cache-Control: no-store` on downloads so a re-cut release can
never serve stale bytes. The reasoning is sound; the cost is a **0% cache hit
rate forever** — every download is a full R2 read and a full 50MB stream.
Cloudflare respects the header and explicitly does not cache `no-store`.

**Staleness is a naming problem, not a caching problem.** Publish artifacts
under versioned, immutable names (`FrostFile-1.0.0-windows.zip`), serve them
`public, max-age=31536000, immutable`, and keep a stable `/download/latest/...`
entry point as a short-TTL 302. A version's bytes can never change, so a stale
response becomes impossible *by construction* — the same guarantee `no-store`
was bought for, without paying on every request.

The bigger structural win is binding an R2 custom domain (`dl.frostfile.org`)
directly to the bucket, which puts the CDN in front and **bypasses Workers
entirely**. A cache hit then costs nothing at all: no Worker request, no Class
B op, no egress. That converts the dominant abuse surface into approximately
free. Costs: you'd set `Content-Disposition` as R2 object metadata instead of a
Worker header, and you'd lose the per-download counter on that path — which is
arguably a feature, since decoupling the counter from downloads is
recommendation #1 anyway. Don't use `r2.dev` for this; the docs say it's
rate-limited and for development only.

---

## On the terms of service

The old "don't serve disproportionate large files" restriction still exists,
but it lives under **Content Delivery Network (Free, Pro, or Business)** in the
Service-Specific Terms, and it names Developer Platform as one of the paid
services that makes serving large files acceptable. **Workers + R2 is the
Developer Platform.** Serving 30–75MB binaries this way is the sanctioned path,
not a violation of it. (Reading the CDN-cache-in-front case as equally fine is
interpretation rather than a quoted guarantee, but it's the pattern Cloudflare
markets.)

Note Pages caps a single asset at 25 MiB, so the artifacts could never have
lived there. They're correctly on R2.
