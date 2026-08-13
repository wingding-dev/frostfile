"""The version number must agree everywhere it appears, and be visible in the app.

The user IS the update checker (the app never phones home), so the whole
scheme rests on two things staying true: every copy of the version number
matches, and the running app shows its own version where a user will see it.
"""

from __future__ import annotations

from pathlib import Path

from frostfile import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_agrees_everywhere():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{__version__}"' in pyproject

    vinfo = (ROOT / "build" / "version_info.txt").read_text()
    assert f'"{__version__}.0"' in vinfo, "build/version_info.txt not bumped"

    # The built site is committed; build.py injects the version from
    # pyproject.toml. If this fails after a bump, rerun storefront/build.py.
    site = (ROOT / "storefront" / "index.html").read_text()
    assert f"v{__version__}" in site, "storefront/index.html stale — rerun build.py"


def test_template_carries_placeholder_not_number():
    # The version in the site template must stay a __VERSION__ token; a
    # hand-typed number there would silently drift from pyproject.toml.
    template = (ROOT / "storefront" / "index.template.html").read_text()
    assert "__VERSION__" in template
    assert __version__ not in template


def test_banner_and_footer_show_version(unlocked):
    page = unlocked.get("/").text
    assert 'id="version-banner"' in page
    assert 'id="version-banner-close"' in page
    assert f"v{__version__}" in page
    assert "https://frostfile.org" in page


def test_footer_version_shows_even_before_unlock(client):
    # No session on the setup page, so the banner is absent — but the footer
    # version still renders, letting anyone read their version while locked.
    page = client.get("/setup").text
    assert 'id="version-banner"' not in page
    assert f"v{__version__}" in page
