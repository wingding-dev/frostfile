"""Rebuild storefront/index.html from index.template.html + assets/*.json."""
import json, re, pathlib
here = pathlib.Path(__file__).parent
hero = json.load(open(here / "assets/store-assets.json"))["hero"]
logo = json.load(open(here / "assets/logo-assets.json"))
html = (here / "index.template.html").read_text()
html = (html.replace("__HERO__", hero)
            .replace("__ICON_BLUE__", logo["icon_blue"])
            .replace("__ICON_WHITE__", logo["icon_white"])
            .replace("__WORDMARK_WHITE__", logo["wordmark_white"])
            .replace("__QR__", logo["qr"]))
(here / "index.html").write_text(html)
left = re.findall(r"__[A-Z_]+__", html)
print("leftover tokens:", left or "none", "| size:", len(html)//1024, "KB")
