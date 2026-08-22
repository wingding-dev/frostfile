// Pages "advanced mode" worker: the ONLY job is collapsing duplicate hosts.
// www.frostfile.org and the bare frostfile.pages.dev both used to serve a
// second 200 copy of the site; search engines treat that as duplicate content.
// Preview deployments (<branch>.frostfile.pages.dev) are left alone.
// Everything else falls through to the static assets (_headers, 404.html apply).
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.frostfile.org" || url.hostname === "frostfile.pages.dev") {
      url.hostname = "frostfile.org";
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    return env.ASSETS.fetch(request);
  },
};
