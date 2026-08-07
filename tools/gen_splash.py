"""Generate FrostFile app splash-screen options via Gemini (pure AI, no SVG)."""

import pathlib
import time

from gen_seals2 import generate  # gemini-2.5-flash-image

OUT = pathlib.Path(__file__).parent / "splash"
OUT.mkdir(exist_ok=True)

BASE = (
    "Design a polished SPLASH SCREEN / welcome screen for a desktop app called "
    "'FrostFile', a private tool that helps families freeze their credit and "
    "protect against identity theft. Wide landscape 16:10 composition suitable "
    "for an app window. Color palette: deep navy (#16324F) and ice blue "
    "(#7FB8D8) with white. Mood: trustworthy, calm, secure, premium — not "
    "corporate-cold. Flat modern vector style, crisp, NO photorealism, NO "
    "stock-photo people. Include the brand mark: a padlock whose body carries a "
    "symmetrical monogram of two mirror-image capital letter F's, and the "
    "wordmark 'FrostFile'. "
)

PROMPTS = [
    ("splash-a", BASE + "Centered circular navy badge (padlock + mirrored FF) "
     "glowing softly, with delicate ice-blue frost crystals radiating outward "
     "on a deep navy background. Wordmark 'FrostFile' beneath, small tagline "
     "'Family Credit Freeze Kit'."),
    ("splash-b", BASE + "Split layout: on the left a large navy circular seal "
     "with the padlock and mirrored FF; on the right, big clean 'FrostFile' "
     "wordmark with tagline 'Protect your family's identity — on your computer, "
     "nowhere else.' Subtle frosted-glass texture."),
    ("splash-c", BASE + "Minimal and elegant: deep navy gradient background, a "
     "single small ice-blue padlock-with-FF mark at top center, and a large "
     "refined 'FrostFile' wordmark centered, thin tagline below. Lots of empty "
     "space."),
    ("splash-d", BASE + "Crystalline low-poly ice geometry filling the "
     "background in navy and ice-blue facets, with the padlock-FF badge "
     "centered and softly lit, wordmark 'FrostFile' below."),
    ("splash-e", BASE + "A frosted window pane with delicate frost-fern ice "
     "crystals forming in the corners, deep navy tint, the glowing padlock-FF "
     "seal centered like light through the glass, wordmark 'FrostFile'."),
    ("splash-f", BASE + "Warm and reassuring: deep navy with a soft ice-blue "
     "spotlight glow behind a crisp white circular seal (padlock + mirrored "
     "FF), 'FrostFile' wordmark and tagline 'Family Credit Freeze Kit' in clean "
     "type, a thin snowflake motif border."),
]

if __name__ == "__main__":
    done = 0
    for slug, prompt in PROMPTS:
        target = OUT / f"{slug}.png"
        if target.exists():
            done += 1
            continue
        print(f"[{slug}]", flush=True)
        for attempt in range(6):
            try:
                png = generate(prompt)
            except Exception as exc:  # noqa: BLE001 - network hiccup, just retry
                print(f"    retry ({type(exc).__name__})", flush=True)
                png = None
            if png:
                target.write_bytes(png)
                print(f"    saved {len(png)//1024} KB", flush=True)
                done += 1
                break
            time.sleep(10 * (attempt + 1))
        time.sleep(2)
    print(f"{done}/{len(PROMPTS)} generated")
