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
    if (url.pathname === "/api/hit" && request.method === "POST") {
      const visits = (parseInt(await env.COUNTS.get("visits")) || 0) + 1;
      await env.COUNTS.put("visits", String(visits));
      const downloads = parseInt(await env.COUNTS.get("downloads")) || 0;
      return json({ visits, downloads });
    }
    if (url.pathname === "/api/count") {
      return json({
        visits: parseInt(await env.COUNTS.get("visits")) || 0,
        downloads: parseInt(await env.COUNTS.get("downloads")) || 0,
      });
    }

    // ---- downloads: serve from R2 and count ----
    if (url.pathname.startsWith("/download/")) {
      const key = url.pathname.slice("/download/".length);
      const object = await env.BUCKET.get(key);
      if (object === null) return new Response("Not found.", { status: 404 });

      const downloads = (parseInt(await env.COUNTS.get("downloads")) || 0) + 1;
      await env.COUNTS.put("downloads", String(downloads));

      return new Response(object.body, {
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": `attachment; filename="${key}"`,
          "Cache-Control": "public, max-age=3600",
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
