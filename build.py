#!/usr/bin/env python3
"""
Builds a Fallout-style CRT terminal as a self-contained SVG for a GitHub README.

Everything is baked into one file: the font is embedded as base64 (no web fonts
survive inside an <img>-loaded SVG), the barrel distortion is computed per
character, and all motion is declarative CSS so it runs inside the image.

    python3 build.py

Edit CONFIG below, re-run, commit the assets/ folder.
"""

import base64
import io
import os
from fontTools import subset

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — this is the only part you need to touch
# ─────────────────────────────────────────────────────────────────────────────

# Phase 1: the boot dump. Scrolls past fast, sets the mood.
BOOT = [
    "SET TERMINAL/INQUIRE",
    "",
    "RIT-V300",
    "",
    "SET FILE/PROTECTION=OWNER:RWED ACCOUNTS.F",
    "SET HALT RESTART/MAINT",
    "",
    "RUN DEBUG/ACCOUNTS.F",
    "",
    "INITIALIZING MF BOOT AGENT V2.3.0",
    "RETROS BIOS",
    "RBIOS-4.02.08.00 52EE5.E7.E8",
    "COPYRIGHT 2201-2203 NOVACORP INDUST.",
    "UPPMEM DRIVE",
    "ROOT (5A8)",
    "MAINTENANCE MODE",
    "",
    "RUN TERMLINK",
]

# Phase 2: the screen people actually read.
TITLE = "WELCOME TO TERMLINK"
BODY = [
    "",
    "NOVACORP UNIFIED OPERATING SYSTEM",
    "COPYRIGHT 2075-2077 NOVACORP INDUSTRIES",
    "-SERVER 6-",
    "",
    "USER ............ YOUR-NAME",
    "ROLE ............ SOFTWARE ENGINEER",
    "TERMINAL ........ DURANGO, MX",
    "CLEARANCE ....... LEVEL 3",
    "STATUS .......... ONLINE",
    "",
    "PERSONNEL FILE LOADED. SELECT ENTRY:",
    "",
    "   > PROJECTS",
    "   > SKILLS",
    "   > CONTACT",
    "   > EXIT",
    "",
]
PROMPT = ">"          # cursor sits after this on the last line

# Buttons rendered under the screen (label, filename)
BUTTONS = [
    ("PROJECTS", "btn-projects"),
    ("SKILLS", "btn-skills"),
    ("CONTACT", "btn-contact"),
    ("EXIT", "btn-exit"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Look
# ─────────────────────────────────────────────────────────────────────────────

GREEN = "#2fff6b"          # phosphor core
GREEN_DIM = "#15a844"      # older, decayed lines
SCREEN_BG = "#050f07"      # unlit glass
SCREEN_GLOW = "#0c2c15"    # the lit pool in the middle
SURROUND = "none"           # let the README background show through

W, H = 1200, 780
SX0, SY0, SX1, SY1 = 64, 52, 1136, 728        # screen bounds
CX, CY = (SX0 + SX1) / 2, (SY0 + SY1) / 2
HW, HH = (SX1 - SX0) / 2, (SY1 - SY0) / 2
BARREL = 0.062                                 # 0 = flat, 0.12 = fishbowl

FS = 21                                        # font size
ADV = FS * 0.60186                             # DejaVu Sans Mono advance width
LH = 28                                        # line height
PAD_X, PAD_Y = 66, 76                          # text inset inside the screen

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
GLYPHS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
          "0123456789 .,:;'\"!?-_=+*/\\|()[]{}<>@#$%^&~`")


# ─────────────────────────────────────────────────────────────────────────────


def embed_font(path=FONT_PATH, chars=GLYPHS):
    """Subset a monospace face and return it as a data URI.

    External font URLs are blocked inside an <img>-loaded SVG, but a data URI
    is part of the same document, so it loads. Subsetting keeps it ~8 KB.
    """
    opts = subset.Options()
    opts.layout_features = []
    opts.glyph_names = False
    opts.hinting = False
    opts.notdef_outline = False
    font = subset.load_font(path, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:font/ttf;base64,{b64}"


def warp(x, y):
    """Push a point outward from screen centre — the CRT's barrel bulge."""
    u = (x - CX) / HW
    v = (y - CY) / HH
    f = 1 + BARREL * (u * u + v * v)
    return CX + u * f * HW, CY + v * f * HH


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def warped_line(text, row, cls="", delay=None, x_chars=0):
    """One line of text, each glyph individually placed along the curve.

    A single <text> takes a list of x and y values, one per glyph, so the
    whole line stays one element while every character still lands on the
    warped grid. Spaces are dropped rather than positioned.
    """
    if not text.strip():
        return ""
    base_y = SY0 + PAD_Y + row * LH
    xs, ys, chars = [], [], []
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        px = SX0 + PAD_X + (x_chars + i) * ADV
        wx, wy = warp(px, base_y)
        xs.append(f"{wx:.1f}")
        ys.append(f"{wy:.1f}")
        chars.append(ch)
    style = f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c}{style} x="{" ".join(xs)}" y="{" ".join(ys)}">'
            f'{esc("".join(chars))}</text>')


def screen_path(inset=0.0):
    """The warped outline of the glass, sampled around the rectangle."""
    x0, y0 = SX0 + inset, SY0 + inset
    x1, y1 = SX1 - inset, SY1 - inset
    pts, n = [], 14
    for i in range(n + 1):
        pts.append(warp(x0 + (x1 - x0) * i / n, y0))
    for i in range(1, n + 1):
        pts.append(warp(x1, y0 + (y1 - y0) * i / n))
    for i in range(1, n + 1):
        pts.append(warp(x1 - (x1 - x0) * i / n, y1))
    for i in range(1, n + 1):
        pts.append(warp(x0, y1 - (y1 - y0) * i / n))
    d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
    return d


def build_terminal(font_uri):
    boot_end = 0.15 + len(BOOT) * 0.11 + 0.5
    body_start = boot_end + 0.35

    boot_lines = []
    for i, line in enumerate(BOOT):
        boot_lines.append(warped_line(line, i + 1, "ln dim", 0.15 + i * 0.11))

    body_lines = [warped_line(TITLE, 1, "ln", body_start)]
    for i, line in enumerate(BODY):
        body_lines.append(
            warped_line(line, i + 2, "ln", body_start + 0.18 + i * 0.10))

    prompt_row = len(BODY) + 2
    body_lines.append(
        warped_line(PROMPT, prompt_row, "ln", body_start + 0.18 + len(BODY) * 0.10))

    # cursor sits one character past the prompt, on the same warped baseline
    cur_x = SX0 + PAD_X + len(PROMPT) * ADV
    cur_y = SY0 + PAD_Y + prompt_row * LH
    cwx, cwy = warp(cur_x, cur_y)
    cursor_delay = body_start + 0.5 + len(BODY) * 0.10
    cursor = (f'<rect class="cur" style="animation-delay:{cursor_delay:.2f}s" '
              f'x="{cwx:.1f}" y="{cwy - FS * 0.78:.1f}" '
              f'width="{ADV:.1f}" height="{FS * 0.95:.1f}" fill="{GREEN}"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"
     width="{W}" height="{H}" role="img"
     aria-label="A retro CRT terminal displaying a personnel file. Select an entry below.">
<defs>
  <style>
    @font-face {{
      font-family: "TermMono";
      src: url({font_uri}) format("truetype");
      font-weight: 700;
    }}
    text {{
      font-family: "TermMono", "Courier New", monospace;
      font-size: {FS}px;
      font-weight: 700;
      fill: {GREEN};
      white-space: pre;
    }}
    .dim {{ fill: {GREEN_DIM}; }}

    .ln {{ opacity: 0; animation: on 0.01s linear forwards; }}
    @keyframes on {{ to {{ opacity: 1; }} }}

    .boot {{ animation: off 0.18s linear {boot_end:.2f}s forwards; }}
    @keyframes off {{ to {{ opacity: 0; visibility: hidden; }} }}

    .cur {{ opacity: 0; animation: blink 1.02s steps(1) infinite; }}
    @keyframes blink {{ 0%,49% {{ opacity: 1; }} 50%,100% {{ opacity: 0; }} }}

    .scan {{ animation: drift 0.55s linear infinite; }}
    @keyframes drift {{ to {{ transform: translateY(3px); }} }}

    .roll {{ animation: sweep 8s linear infinite; }}
    @keyframes sweep {{ from {{ transform: translateY(-260px); }}
                        to   {{ transform: translateY({H + 60}px); }} }}

    .flick {{ animation: flick 2.7s ease-in-out infinite; }}
    @keyframes flick {{ 0%,100% {{ opacity: 0; }} 46% {{ opacity: 0.05; }}
                        49% {{ opacity: 0; }} 51% {{ opacity: 0.035; }} }}

    @media (prefers-reduced-motion: reduce) {{
      .ln {{ opacity: 1; animation: none; }}
      .boot {{ opacity: 0; visibility: hidden; animation: none; }}
      .cur {{ opacity: 1; animation: none; }}
      .scan, .roll, .flick {{ animation: none; }}
      .roll {{ opacity: 0; }}
    }}
  </style>

  <filter id="bloom" x="-25%" y="-25%" width="150%" height="150%"
          color-interpolation-filters="sRGB">
    <feGaussianBlur in="SourceGraphic" stdDeviation="0.9" result="b1"/>
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b2"/>
    <feGaussianBlur in="SourceGraphic" stdDeviation="13" result="b3"/>
    <feMerge>
      <feMergeNode in="b3"/><feMergeNode in="b3"/><feMergeNode in="b3"/>
      <feMergeNode in="b2"/><feMergeNode in="b2"/>
      <feMergeNode in="b1"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>

  <pattern id="scanlines" width="3" height="3" patternUnits="userSpaceOnUse">
    <rect width="3" height="1.4" fill="#000" opacity="0.42"/>
  </pattern>

  <radialGradient id="pool" cx="50%" cy="46%" r="66%">
    <stop offset="0%" stop-color="{SCREEN_GLOW}"/>
    <stop offset="100%" stop-color="{SCREEN_BG}"/>
  </radialGradient>

  <radialGradient id="vig" cx="50%" cy="48%" r="70%">
    <stop offset="48%" stop-color="#000" stop-opacity="0"/>
    <stop offset="100%" stop-color="#000" stop-opacity="0.9"/>
  </radialGradient>

  <radialGradient id="halo" cx="50%" cy="48%" r="60%">
    <stop offset="0%" stop-color="{GREEN}" stop-opacity="0.13"/>
    <stop offset="100%" stop-color="{GREEN}" stop-opacity="0"/>
  </radialGradient>

  <linearGradient id="rollbar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{GREEN}" stop-opacity="0"/>
    <stop offset="50%" stop-color="{GREEN}" stop-opacity="0.055"/>
    <stop offset="100%" stop-color="{GREEN}" stop-opacity="0"/>
  </linearGradient>

  <clipPath id="glass"><path d="{screen_path()}"/></clipPath>
</defs>

<rect width="{W}" height="{H}" fill="{SURROUND}"/>
<rect width="{W}" height="{H}" fill="url(#halo)"/>

<path d="{screen_path(-14)}" fill="#0a0d0a"/>
<path d="{screen_path()}" fill="url(#pool)"/>

<g clip-path="url(#glass)">
  <g filter="url(#bloom)">
    <g class="boot">
      {"".join(boot_lines)}
    </g>
    <g>
      {"".join(body_lines)}
      {cursor}
    </g>
  </g>

  <rect class="roll" x="0" y="0" width="{W}" height="240" fill="url(#rollbar)"/>
  <rect class="scan" x="0" y="-4" width="{W}" height="{H + 8}" fill="url(#scanlines)"/>
  <rect width="{W}" height="{H}" fill="url(#vig)"/>
  <rect class="flick" width="{W}" height="{H}" fill="{GREEN}"/>
</g>

<path d="{screen_path()}" fill="none" stroke="#0c1a10" stroke-width="2.5"/>
</svg>
'''


def build_button(label, font_uri, w=272, h=64):
    cx, cy = w / 2, h / 2 + 7
    adv = 19 * 0.60186
    text = f"[ {label} ]"
    x0 = cx - len(text) * adv / 2
    xs = " ".join(f"{x0 + i * adv:.1f}" for i, ch in enumerate(text) if ch != " ")
    chars = "".join(ch for ch in text if ch != " ")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"
     width="{w}" height="{h}" role="img" aria-label="{label}">
<defs>
  <style>
    @font-face {{ font-family:"TermMono"; src:url({font_uri}) format("truetype"); font-weight:700; }}
    text {{ font-family:"TermMono","Courier New",monospace; font-size:19px;
            font-weight:700; fill:{GREEN}; }}
  </style>
  <filter id="g" x="-30%" y="-30%" width="160%" height="160%" color-interpolation-filters="sRGB">
    <feGaussianBlur in="SourceGraphic" stdDeviation="1" result="a"/>
    <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="a"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <pattern id="s" width="3" height="3" patternUnits="userSpaceOnUse">
    <rect width="3" height="1.4" fill="#000" opacity="0.4"/>
  </pattern>
</defs>
<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="5" fill="{SCREEN_BG}"
      stroke="#1c6b34" stroke-width="1.5"/>
<text filter="url(#g)" x="{xs}" y="{cy:.1f}">{esc(chars)}</text>
<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="5" fill="url(#s)"/>
</svg>
'''


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(out, exist_ok=True)
    font_uri = embed_font()

    path = os.path.join(out, "terminal.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_terminal(font_uri))
    print(f"wrote {path} ({os.path.getsize(path) / 1024:.0f} KB)")

    for label, name in BUTTONS:
        p = os.path.join(out, f"{name}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_button(label, font_uri))
        print(f"wrote {p} ({os.path.getsize(p) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
