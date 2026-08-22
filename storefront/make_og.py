"""Render storefront/assets/og.png (1200x630) — the link-preview card used by
search results, iMessage, Slack, LinkedIn, etc. Run once after brand changes:

    .venv/bin/python storefront/make_og.py

Uses the app's own fonts (frostfile/static/fonts) via playwright + system
chromium so the card matches the site. build.py just copies the PNG.
"""
import base64, json, pathlib
from playwright.sync_api import sync_playwright

here = pathlib.Path(__file__).parent
root = here.parent
logo = json.load(open(here / "assets/logo-assets.json"))
wall = base64.b64encode((root / "frostfile/static/vault-wall.jpg").read_bytes()).decode()
fonts = root / "frostfile/static/fonts"

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Chakra;src:url(file://{fonts}/chakra-petch-600.woff2) format('woff2');font-weight:600}}
@font-face{{font-family:Plex;src:url(file://{fonts}/ibm-plex-sans-400.woff2) format('woff2');font-weight:400}}
html,body{{margin:0;width:1200px;height:630px;overflow:hidden;background:#090f15;}}
.bg{{position:absolute;inset:0;background:url(data:image/jpeg;base64,{wall}) center/cover;filter:brightness(.55) saturate(.9);}}
.veil{{position:absolute;inset:0;background:linear-gradient(90deg,rgba(9,15,21,.92) 0%,rgba(9,15,21,.78) 55%,rgba(9,15,21,.35) 100%);}}
.card{{position:absolute;left:80px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center;gap:26px;width:1040px;}}
.wm{{height:62px;width:auto;}}
h1{{margin:0;font:600 78px/1.02 Chakra,system-ui,sans-serif;color:#e9f2f8;letter-spacing:-.01em;}}
h1 b{{color:#83b9ff;font-weight:600;}}
p{{margin:0;font:400 30px/1.35 Plex,system-ui,sans-serif;color:#b7c7d3;max-width:900px;}}
.tags{{display:flex;gap:14px;margin-top:6px;}}
.tag{{font:400 22px/1 Plex,system-ui,sans-serif;color:#e9f2f8;border:1px solid rgba(90,166,238,.45);border-radius:999px;padding:12px 20px;background:rgba(90,166,238,.12);}}
</style></head><body>
<div class="bg"></div><div class="veil"></div>
<div class="card">
  <img class="wm" src="{logo['wordmark_white']}" alt="">
  <h1><b>Deadbolts</b> beat doorbells.</h1>
  <p>Free tracker for your whole family's credit freezes — runs on your own computer, sends nothing anywhere.</p>
  <div class="tags"><span class="tag">Free forever</span><span class="tag">Zero internet connections</span><span class="tag">Open source</span><span class="tag">Windows &amp; Mac</span></div>
</div>
</body></html>"""

out = here / "assets/og.png"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 1200, "height": 630})
    pg.set_content(html, wait_until="load")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(out), type="png")
    b.close()
print("wrote", out, out.stat().st_size // 1024, "KB")
