"""Rebuild storefront/index.html from index.template.html + assets/*.json.

The version comes from pyproject.toml, so the site can never disagree with
the app about what the newest version is.
"""
import json, re, pathlib
here = pathlib.Path(__file__).parent
backdrop = json.load(open(here / "assets/backdrop-assets.json"))["backdrop"]
logo = json.load(open(here / "assets/logo-assets.json"))
version = re.search(r'^version = "([^"]+)"',
                    (here.parent / "pyproject.toml").read_text(), re.M).group(1)
html = (here / "index.template.html").read_text()
html = (html.replace("__BACKDROP__", backdrop)
            .replace("__ICON_BLUE__", logo["icon_blue"])
            .replace("__ICON_WHITE__", logo["icon_white"])
            .replace("__WORDMARK_WHITE__", logo["wordmark_white"])
            .replace("__QR__", logo["qr"])
            .replace("__VERSION__", version))
(here / "index.html").write_text(html)
left = re.findall(r"__[A-Z_]+__", html)
print("leftover tokens:", left or "none", "| size:", len(html)//1024, "KB")
