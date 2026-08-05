"""Hand-built FrostFile seal SVG (combo-c redrawn geometrically) + PNG preview."""

import math
import pathlib

import cairosvg

NAVY = "#16324F"
ICE = "#7FB8D8"
CX = CY = 256

def pt(angle_deg, r):
    a = math.radians(angle_deg)
    return (CX + r * math.cos(a), CY - r * math.sin(a))

def arc(a1, a2, r, sweep):
    x1, y1 = pt(a1, r)
    x2, y2 = pt(a2, r)
    return f"M {x1:.2f} {y1:.2f} A {r} {r} 0 0 {sweep} {x2:.2f} {y2:.2f}"

def tick(angle, r_in, r_out, w):
    x1, y1 = pt(angle, r_in)
    x2, y2 = pt(angle, r_out)
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{NAVY}" stroke-width="{w}" stroke-linecap="round"/>')

def diamond(angle, r, s):
    cx, cy = pt(angle, r)
    p = f"{cx:.1f},{cy-s:.1f} {cx+s:.1f},{cy:.1f} {cx:.1f},{cy+s:.1f} {cx-s:.1f},{cy:.1f}"
    return f'<polygon points="{p}" fill="{ICE}"/>'

# --- text arcs (baseline sits in the band between the two rings) ---
TOP = arc(157, 23, 222, 1)          # FROSTFILE, over the top, L->R
BOT = arc(206, 334, 222, 0)          # FAMILY CREDIT FREEZE KIT, under bottom, L->R

# --- side ticks (3 per side) and diamonds, inside the band ---
ticks = "".join(
    tick(a, 202, 240, 7)
    for a in (167, 180, 193, 347, 0, 13)  # left cluster + right cluster
)
diamonds = diamond(180, 221, 9) + diamond(0, 221, 9)

# --- padlock (centred higher so it sits in the circle, not over the text) ---
# shackle (drawn first, behind body)
shackle = (
    f'<path d="M 214 226 L 214 182 A 44 44 0 0 1 302 182 L 302 226" '
    f'fill="none" stroke="{NAVY}" stroke-width="24" stroke-linecap="round"/>'
)
# body
body = f'<rect x="186" y="220" width="144" height="142" rx="18" fill="{NAVY}"/>'

# --- mirrored FF monogram on the body (ice blue) ---
# Right-half F: spine near centre, arms extend right.
gap = 6
st_w = 15          # stem width
top_y, bot_y = 260, 340
arm_h = 15
top_arm_len = 52
mid_arm_len = 40
mid_y = 293
spine_x = CX + gap
right_f = (
    f'<rect x="{spine_x}" y="{top_y}" width="{st_w}" height="{bot_y-top_y}" fill="{ICE}"/>'
    f'<rect x="{spine_x}" y="{top_y}" width="{top_arm_len}" height="{arm_h}" fill="{ICE}"/>'
    f'<rect x="{spine_x}" y="{mid_y}" width="{mid_arm_len}" height="{arm_h-1}" fill="{ICE}"/>'
)
# Left half = mirror of right about x=CX (x -> 2*CX - x = 512 - x)
mono = f'<g>{right_f}</g><g transform="translate(512,0) scale(-1,1)">{right_f}</g>'

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <path id="topArc" d="{TOP}"/>
    <path id="botArc" d="{BOT}"/>
  </defs>
  <circle cx="256" cy="256" r="248" fill="#ffffff"/>
  <circle cx="256" cy="256" r="246" fill="none" stroke="{NAVY}" stroke-width="7"/>
  <circle cx="256" cy="256" r="198" fill="none" stroke="{NAVY}" stroke-width="4"/>
  {ticks}
  {diamonds}
  <text font-family="Georgia, 'Times New Roman', serif" font-weight="700"
        font-size="37" letter-spacing="3" fill="{NAVY}" text-anchor="middle">
    <textPath href="#topArc" startOffset="50%">FROSTFILE</textPath>
  </text>
  <text font-family="Georgia, 'Times New Roman', serif" font-weight="700"
        font-size="22" letter-spacing="1.5" fill="{NAVY}" text-anchor="middle">
    <textPath href="#botArc" startOffset="50%">FAMILY CREDIT FREEZE KIT</textPath>
  </text>
  {shackle}
  {body}
  {mono}
</svg>'''

# --- mono (single-ink rubber-stamp) variant: FF knocked out to paper-white ---
svg_mono = svg.replace(ICE, "#ffffff")

# --- mark only (no ring/text) for favicon & app icon: scale the lock to fill ---
mark = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <g transform="translate(256,262) scale(2.35) translate(-256,-262)">
    {shackle}
    {body}
    {mono}
  </g>
</svg>'''

out_dir = pathlib.Path(__file__).parent


def emit(name, markup, w=600, bg="white"):
    (out_dir / f"{name}.svg").write_text(markup, encoding="utf-8")
    cairosvg.svg2png(bytestring=markup.encode(), write_to=str(out_dir / f"{name}.png"),
                     output_width=w, output_height=w, background_color=bg)


emit("frostfile-seal", svg)
emit("frostfile-seal-mono", svg_mono)
emit("frostfile-mark", mark, bg=None)
# favicon-size previews of the mark
emit("frostfile-mark-32", mark, w=32, bg=None)
emit("frostfile-mark-16", mark, w=16, bg=None)

# --- contact sheet ---
from PIL import Image

def load(name, size):
    im = Image.open(out_dir / f"{name}.png").convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)

sheet = Image.new("RGBA", (960, 560), "white")
sheet.paste(load("frostfile-seal", 400), (30, 40))
sheet.paste(load("frostfile-seal-mono", 400), (500, 40))
# icon strip
for i, px in enumerate((128, 64, 32, 16)):
    m = load("frostfile-mark", px)
    sheet.alpha_composite(m, (40 + i * 150, 470))
sheet.convert("RGB").save(out_dir / "frostfile-contact-sheet.png")
print("wrote seal (2-color), seal-mono, mark (+16/32), contact sheet")
