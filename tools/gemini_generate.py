"""Round 2: refine the two winners (padlock-engraved, ff-monogram) + hybrids."""

import base64
import json
import pathlib
import time

import httpx

KEY = pathlib.Path.home().joinpath(".config/identilock-dev/gemini-api-key").read_text().strip()
OUT = pathlib.Path(__file__).parent / "seals2"
OUT.mkdir(exist_ok=True)

MODEL = "gemini-2.5-flash-image"

BASE = (
    "Design a circular seal/badge logo for 'FrostFile', a home software product "
    "for families freezing their credit. Style: flat vector emblem like a US "
    "national-park badge — bold clean shapes, NO gradients, NO photorealism, "
    "crisp edges, centered on a plain white background. Colors: ice blue and "
    "deep navy only, plus white. Must stay legible shrunk to a tiny icon. "
)

SIMPLE_FLAKE = (
    "The snowflake must be VERY simple: six thick plain arms, no branching "
    "detail, more like a bold asterisk than a lacy crystal. "
)

PROMPTS = [
    ("lock-simple-flake-ring",
     BASE + SIMPLE_FLAKE + "Center: a bold padlock with the simple snowflake "
     "engraved flat on its body. Circular ring text 'FROSTFILE' at top."),
    ("lock-simple-flake-only",
     BASE + SIMPLE_FLAKE + "Center: a bold padlock with the simple snowflake "
     "engraved flat on its body. No text anywhere — symbol only."),
    ("ff-clean-circle",
     BASE + "Center: an elegant interlocked 'FF' monogram, clean geometric "
     "letterforms, nothing decorating the letters. Thin double circle border. "
     "No other text."),
    ("ff-on-padlock",
     BASE + "Center: a bold padlock whose body carries a clean interlocked "
     "'FF' monogram (no decoration on the letters). Circular badge border, no "
     "ring text."),
    ("ff-ring-text",
     BASE + "Center: a clean interlocked 'FF' monogram, undecorated geometric "
     "letterforms. Ring border with the text 'FROSTFILE' along the top arc "
     "and two small diamonds on the bottom arc."),
    ("ff-shackle-frame",
     BASE + "A padlock shackle arches over a clean interlocked 'FF' monogram, "
     "so the shackle and monogram together read as a padlock. Inside a bold "
     "circle. No text."),
    ("ff-keyway",
     BASE + "Center: an interlocked 'FF' monogram where the negative space "
     "between the letters subtly forms a keyhole shape. Thin circle border, "
     "no other text, undecorated letterforms."),
    ("lock-flake-stamp",
     BASE + SIMPLE_FLAKE + "Single deep-navy color only, clean rubber-stamp "
     "style: circular stamp, 'FROSTFILE' ring text, padlock with the simple "
     "snowflake engraved on its body in the center."),
]


def generate(prompt: str) -> bytes | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    r = httpx.post(url, json=body, timeout=120.0)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}")
        return None
    for cand in r.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    return None


if __name__ == "__main__":
    done = 0
    for slug, prompt in PROMPTS:
        target = OUT / f"{slug}.png"
        if target.exists():
            done += 1
            continue
        print(f"[{slug}]")
        for attempt in range(5):
            png = generate(prompt)
            if png:
                target.write_bytes(png)
                print(f"    saved {len(png)//1024} KB")
                done += 1
                break
            time.sleep(12 * (attempt + 1))
        time.sleep(2)
    print(f"{done}/{len(PROMPTS)} generated")
