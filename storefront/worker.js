/**
 * FrostFile storefront Worker — download serving + old-school hit counter.
 *
 * No cookies, no IPs stored, no third-party calls: two integers in KV.
 *
 * Cloudflare setup (one time, ~10 minutes in the dashboard):
 *   1. Workers & Pages -> Create Worker -> paste this file -> Deploy.
 *   2. Storage & Databases -> KV -> create a namespace named COUNTS.
 *      Worker -> Settings -> Bindings -> KV namespace: variable COUNTS.
 *   3. R2 -> your bucket (holding FrostFile-Setup.exe / FrostFile.dmg).
 *      Worker -> Settings -> Bindings -> R2 bucket: variable BUCKET.
 *   4. Worker -> Settings -> Domains & Routes -> add route:
 *         frostfile.org/download/*  and  frostfile.org/api/*
 *      (the static site itself stays on Pages / your existing hosting)
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ---- hit counter API (the page calls this once per visit) ----
    // The free KV tier caps writes at 1,000/day. The counter is decoration:
    // if a write ever fails, the numbers pause — nothing else may break.
    if (url.pathname === "/api/hit" && request.method === "POST") {
      let visits = 0, downloads = 0;
      try {
        visits = (parseInt(await env.COUNTS.get("visits")) || 0) + 1;
        await env.COUNTS.put("visits", String(visits));
        downloads = parseInt(await env.COUNTS.get("downloads")) || 0;
      } catch (e) { /* counter paused; page hides it on bad data */ }
      return json({ visits, downloads });
    }
    if (url.pathname === "/api/count") {
      try {
        return json({
          visits: parseInt(await env.COUNTS.get("visits")) || 0,
          downloads: parseInt(await env.COUNTS.get("downloads")) || 0,
        });
      } catch (e) {
        return json({ visits: 0, downloads: 0 });
      }
    }

    // ---- downloads: serve from R2 and count ----
    if (url.pathname.startsWith("/download/")) {
      const key = url.pathname.slice("/download/".length);
      const object = await env.BUCKET.get(key);
      if (object === null) return new Response("Not found.", { status: 404 });

      // A download must NEVER fail because the odometer couldn't tick.
      try {
        const downloads = (parseInt(await env.COUNTS.get("downloads")) || 0) + 1;
        await env.COUNTS.put("downloads", String(downloads));
      } catch (e) { /* counter paused */ }

      // no-store: when a release is re-cut, a browser that cached the old
      // bytes would silently serve a stale build — worse than the bandwidth.
      return new Response(object.body, {
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": `attachment; filename="${key}"`,
          "Cache-Control": "no-store",
        },
      });
    }

    return new Response("FrostFile API", { status: 200 });
  },
};

function json(data) {
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
