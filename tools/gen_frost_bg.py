"""Light frost 'framing' backgrounds for all app pages — fog/steam, no veining."""

import pathlib
import time

from gen_seals2 import generate

OUT = pathlib.Path(__file__).parent

PROMPTS = {
    "frost-page-light": (
        "A very subtle background texture for a light-themed software "
        "interface: soft white and extremely pale ice-blue fog, like gentle "
        "steam on a frosted window. The frost mist gathers softly around the "
        "EDGES and corners of the frame, while the CENTER stays almost "
        "completely clean pale white so text remains readable. NO cracks, NO "
        "veins, NO branching crystals, NO objects, NO text — only smooth fog, "
        "vapor and the faintest icy texture. Extremely low contrast, airy, "
        "calm. Square."
    ),
    "frost-page-dark": (
        "A very subtle background texture for a dark-themed software "
        "interface: deep navy blue with soft cold fog and steam drifting "
        "around the EDGES and corners of the frame, faint ice-blue glow in "
        "the mist, while the CENTER stays clean dark navy so light text "
        "remains readable. NO cracks, NO veins, NO branching crystals, NO "
        "objects, NO text — only smooth fog and vapor. Very low contrast, "
        "calm, premium. Square."
    ),
}

if __name__ == "__main__":
    done = 0
    for slug, prompt in PROMPTS.items():
        target = OUT / f"{slug}.png"
        if target.exists():
            done += 1
            continue
        print(f"[{slug}]", flush=True)
        for attempt in range(6):
            try:
                png = generate(prompt)
            except Exception as exc:  # noqa: BLE001
                print(f"    retry ({type(exc).__name__})", flush=True)
                png = None
            if png:
                target.write_bytes(png)
                print(f"    saved {len(png)//1024} KB", flush=True)
                done += 1
                break
            time.sleep(10 * (attempt + 1))
        time.sleep(2)
    print(f"{done}/2 generated")
