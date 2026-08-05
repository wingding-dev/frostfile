"""Audit fix: a crafted HTML upload must not hang the parser."""

from __future__ import annotations

import time

from identilock.services.reportdiff import _strip_script_style, extract_text, normalize


def test_unclosed_script_does_not_blow_up():
    # Many <script openings with no closes: the old regex was O(n^2) here.
    hostile = "<html>" + "<script foo>" * 200_000
    start = time.monotonic()
    out = _strip_script_style(hostile)
    assert time.monotonic() - start < 2.0  # linear, finishes instantly
    assert "<script" not in out.lower()


def test_extract_text_handles_hostile_html_fast():
    hostile = ("<html>" + "<script>x</script>" * 50_000 + "<style>y" * 50_000).encode()
    start = time.monotonic()
    text = extract_text(hostile, "report.html")
    assert time.monotonic() - start < 2.0
    assert "x" not in text  # script contents removed


def test_giant_single_line_is_capped():
    huge = "1 " + "A" * 5_000_000
    lines = normalize(huge)
    assert all(len(line) <= 2000 for line in lines)


def test_normal_html_still_extracts():
    html = b"<html><body><p>FIRST BANK</p><p>XXXX1234</p></body></html>"
    text = extract_text(html, "r.html")
    assert "FIRST BANK" in text
    assert "XXXX1234" in text
