"""Rebuild the storefront and assemble the deployable site in storefront/dist/.

    .venv/bin/python storefront/build.py
    npx wrangler pages deploy storefront/dist --project-name frostfile

dist/ (git-ignored) is the ONLY thing to deploy — never the storefront/ folder
itself, which would publish worker.js, wrangler.toml and this script.

The version comes from pyproject.toml, so the site can never disagree with
the app about what the newest version is. Everything in site/ is copied into
dist/ with __VERSION__ / __MONTH__ / __DATE__ substituted in text files.
"""
import datetime, json, pathlib, re, shutil
here = pathlib.Path(__file__).parent
backdrop = json.load(open(here / "assets/backdrop-assets.json"))["backdrop"]
logo = json.load(open(here / "assets/logo-assets.json"))
version = re.search(r'^version = "([^"]+)"',
                    (here.parent / "pyproject.toml").read_text(), re.M).group(1)
today = datetime.date.today()

html = (here / "index.template.html").read_text()
# The release month is written by hand in the template (DEPLOY.md step 7); reuse it.
month = re.search(r"Version __VERSION__ · ([A-Z][a-z]+ \d{4})", html).group(1)
subs = {"__BACKDROP__": backdrop, "__ICON_BLUE__": logo["icon_blue"],
        "__ICON_WHITE__": logo["icon_white"], "__WORDMARK_WHITE__": logo["wordmark_white"],
        "__QR__": logo["qr"], "__VERSION__": version, "__MONTH__": month,
        "__DATE__": today.isoformat()}
def fill(text):
    for k, v in subs.items():
        text = text.replace(k, v)
    return text

html = fill(html)
(here / "index.html").write_text(html)
left = re.findall(r"__[A-Z_]+__", html)
print("leftover tokens:", left or "none", "| size:", len(html)//1024, "KB")

# ---- assemble dist/ ----
dist = here / "dist"
shutil.rmtree(dist, ignore_errors=True)
dist.mkdir()
(dist / "index.html").write_text(html)
(dist / "privacy.html").write_text(fill((here / "privacy.html").read_text()))
shutil.copy(here / "assets/og.png", dist / "og.png")
for src in (here / "site").rglob("*"):
    if src.is_dir():
        continue
    dst = dist / src.relative_to(here / "site")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(fill(src.read_text()))  # everything in site/ is text

# sitemap: privacy's lastmod is its last git change; the home page moves every build
import subprocess
def git_date(path):
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)],
                         capture_output=True, text=True, cwd=here.parent).stdout.strip()
    return out or today.isoformat()
pages = [("https://frostfile.org/", today.isoformat(), "1.0"),
         ("https://frostfile.org/privacy", git_date(here / "privacy.html"), "0.3")]
(dist / "sitemap.xml").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod><priority>{p}</priority></url>\n"
            for u, d, p in pages) + "</urlset>\n")

files = sorted(str(p.relative_to(dist)) for p in dist.rglob("*") if p.is_file())
bad = [f for f in files if re.search(r"__[A-Z_]+__", (dist / f).read_text(errors="ignore"))]
print("dist/:", ", ".join(files))
print("unfilled tokens in dist:", bad or "none")
