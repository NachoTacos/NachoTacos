#!/usr/bin/env python3
"""
Builds the Fallout-style CRT terminal: the SVG screens for the GitHub pages,
the SKILLS.md page one of them lives on, and the playable terminal in docs/.

Everything is baked into each file: the font is embedded as base64 (no web fonts
survive inside an <img>-loaded SVG), the barrel distortion is computed per
character, and all motion is declarative CSS so it runs inside the image.

    python3 build.py

The playable page is src/terminal.html with the font, the dump and the skill
list substituted in; the same dump is what assets/skills.svg shows, so the
still image on SKILLS.md is that terminal's opening screen.

Edit CONFIG below, re-run, commit assets/, SKILLS.md and docs/.
"""

import base64
import collections
import io
import json
import os
import random
import string
from fontTools import subset
from fontTools.ttLib import TTFont

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

# Buttons rendered under the main screen (label, filename)
BUTTONS = [
    ("PROJECTS", "btn-projects"),
    ("SKILLS", "btn-skills"),
    ("CONTACT", "btn-contact"),
    ("EXIT", "btn-exit"),
]

# Buttons used on the sub-pages
PAGE_BUTTONS = [
    ("BACK", "btn-back"),
    ("RUN TERMLINK", "btn-run"),
]

# ── Skills screen — the password-hack memory dump ────────────────────────────
#
# PLACEHOLDER CONTENT: replace every entry below with the technologies you
# actually use. Each word is buried in the on-screen garbage *and* printed in
# the readable sector list on SKILLS.md, so this list is the only place to
# edit — both views are generated from it. Keep each word to DUMP_CELL
# characters or fewer: it has to fit on one line of the dump.
SKILL_SECTORS = [
    ("LANGUAGES",  ["LANG-01", "LANG-02", "LANG-03", "LANG-04"]),
    ("FRAMEWORKS", ["FRAME-01", "FRAME-02", "FRAME-03"]),
    ("TOOLING",    ["TOOL-01", "TOOL-02", "TOOL-03"]),
    ("SYSTEMS",    ["SYS-01", "SYS-02", "SYS-03"]),
]

SKILL_HEADER = [
    "NOVACORP INDUSTRIES (TM) TERMLINK PROTOCOL",
    "ENTER PASSWORD NOW",
]
SKILL_ATTEMPTS = 4

# The guess log down the right-hand side. Flavour only — the real instructions
# live in the markdown, where a screen reader can reach them.
SKILL_LOG = [
    ">SECTOR SCAN",
    ">Entry denied.",
    ">2/7 correct.",
    ">TERMLINK",
    ">Entry granted.",
    ">Dump follows.",
    ">",
]

DUMP_ROWS = 15        # rows per column
DUMP_CELL = 12        # garbage characters per address
DUMP_ADDR = 0xF4F0    # first address; each cell advances by DUMP_CELL
LOG_COL = 43          # character column the guess log starts at
DUMP_SEED = 20772210  # first seed tried; the search below settles the rest
TRICKS_MIN = 5        # bracket tricks the dump must contain to be usable

# ── The playable terminal (docs/, served by GitHub Pages) ────────────────────
#
# Enable it under Settings > Pages > Deploy from a branch > main > /docs. Until
# that is on, GAME_URL 404s and the RUN TERMLINK button on SKILLS.md is dead —
# everything else still works.
GAME_URL = "https://nachotacos.github.io/NachoTacos/"
GAME_TITLE = "NOVACORP TERMLINK"
PROFILE_URL = "https://github.com/NachoTacos"
GAME_LOG_LINES = 16   # guesses kept on screen before the log scrolls

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
BARREL = 0.062                                 # glass bulge: 0 = flat, 0.12 = fishbowl

# The text grid gets its own, far gentler bulge. At the glass value the left
# margin swings by more than a character between the top row and the middle,
# which reads as broken alignment rather than as a curved screen — the game
# renders its text dead straight and lets the physical tube do the curving.
TEXT_BARREL = 0.012

# Halo opacity under the glyphs. Stacking blurred copies of the text is what
# blows the letters out, so the halo is drawn once at each radius and dimmed,
# with the sharp text painted over the top. Raise for more phosphor smear.
BLOOM_NEAR = 0.35                              # tight glow, radius 3
BLOOM_FAR = 0.22                               # wide glow, radius 12

FS = 23                                        # font size
LH = 28                                        # line height
# ADV — the width of one character cell — is measured off the face itself,
# just below advance_em().
PAD_X, PAD_Y = 66, 76                          # text inset inside the screen

ROOT = os.path.dirname(os.path.abspath(__file__))
GAME_TEMPLATE = os.path.join(ROOT, "src", "terminal.html")

# Vendored so the build does not depend on what is installed. Share Tech Mono
# is SIL OFL (src/fonts/OFL.txt); the licence reserves the name "Share", which
# is why the embedded face is declared as "TermMono" rather than under its own
# name. Swap the file and the metrics below follow automatically.
FONT_PATH = os.path.join(ROOT, "src", "fonts", "ShareTechMono-Regular.ttf")
GLYPHS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
          "0123456789 .,:;'\"!?-_=+*/\\|()[]{}<>@#$%^&~`")

# The characters the memory dump is padded with. No letters or digits, so the
# hidden words are the only readable thing on screen.
GARBAGE = "!@#$%^&*()-_+=[]{}|\\/<>,.?;:'\""


# ─────────────────────────────────────────────────────────────────────────────


def advance_em(path=FONT_PATH):
    """The face's advance width in em, refusing anything that is not monospace.

    Every x position in this file is a multiple of this, so measuring it beats
    hardcoding it: swapping the font can no longer drift the glyph grid.
    """
    face = TTFont(path)
    cmap = face.getBestCmap()
    missing = [c for c in GLYPHS if ord(c) not in cmap]
    if missing:
        raise ValueError(
            f"{os.path.basename(path)} has no glyph for: {' '.join(missing)}")

    upem = face["head"].unitsPerEm
    widths = {face["hmtx"][cmap[ord(c)]][0] for c in GLYPHS if c != " "}
    if len(widths) != 1:
        raise ValueError(
            f"{os.path.basename(path)} is not monospace: {len(widths)} "
            f"different advance widths across the glyph set")
    return widths.pop() / upem


ADV = FS * advance_em()    # px per character cell; the whole grid keys off it


def embed_font(chars=GLYPHS):
    """Subset a monospace face and return it as a data URI.

    External font URLs are blocked inside an <img>-loaded SVG, but a data URI
    is part of the same document, so it loads. Subsetting keeps it ~8 KB.
    """
    opts = subset.Options()
    opts.layout_features = []
    opts.glyph_names = False
    opts.hinting = False
    opts.notdef_outline = False
    font = subset.load_font(FONT_PATH, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:font/ttf;base64,{b64}"


def warp(x, y, barrel=BARREL):
    """Push a point outward from screen centre — the CRT's barrel bulge."""
    u = (x - CX) / HW
    v = (y - CY) / HH
    f = 1 + barrel * (u * u + v * v)
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
        wx, wy = warp(px, base_y, TEXT_BARREL)
        xs.append(f"{wx:.1f}")
        ys.append(f"{wy:.1f}")
        chars.append(ch)
    style = f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c}{style} x="{" ".join(xs)}" y="{" ".join(ys)}">'
            f'{esc("".join(chars))}</text>')


def block_at(row, col, cls, delay, width, height, rise):
    """A solid rectangle sitting on a character cell of the warped grid."""
    x, y = warp(SX0 + PAD_X + col * ADV, SY0 + PAD_Y + row * LH, TEXT_BARREL)
    return (f'<rect class="{cls}" style="animation-delay:{delay:.2f}s" '
            f'x="{x:.1f}" y="{y - rise:.1f}" '
            f'width="{width:.1f}" height="{height:.1f}" fill="{GREEN}"/>')


def warped_cursor(row, col, delay):
    """The blinking block that sits at a given character cell."""
    return block_at(row, col, "cur", delay, ADV, FS * 0.95, FS * 0.78)


def warped_pip(row, col, delay):
    """One attempt marker. Drawn, not typed — the face has no filled square."""
    side = ADV * 0.78
    return block_at(row, col, "ln", delay, side, side, FS * 0.6)


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


def crt_screen(text_markup, aria_label, font_uri, boot_end=None):
    """The CRT itself: glass, bloom, scanlines, vignette — wrapped round text.

    `boot_end` is the second at which a `.boot` group should be wiped; pass
    None for screens that have no boot phase.
    """
    boot_css = "" if boot_end is None else f'''
    .boot {{ animation: off 0.18s linear {boot_end:.2f}s forwards; }}
    @keyframes off {{ to {{ opacity: 0; visibility: hidden; }} }}'''
    boot_still = "" if boot_end is None else '''
      .boot { opacity: 0; visibility: hidden; animation: none; }'''

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"
     width="{W}" height="{H}" role="img"
     aria-label="{aria_label}">
<defs>
  <style>
    @font-face {{
      font-family: "TermMono";
      src: url({font_uri}) format("truetype");
      font-weight: 400;
    }}
    text {{
      font-family: "TermMono", "Courier New", monospace;
      font-size: {FS}px;
      font-weight: 400;
      fill: {GREEN};
      white-space: pre;
    }}
    .dim {{ fill: {GREEN_DIM}; }}

    .ln {{ opacity: 0; animation: on 0.01s linear forwards; }}
    @keyframes on {{ to {{ opacity: 1; }} }}
{boot_css}
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
      .ln {{ opacity: 1; animation: none; }}{boot_still}
      .cur {{ opacity: 1; animation: none; }}
      .scan, .roll, .flick {{ animation: none; }}
      .roll {{ opacity: 0; }}
    }}
  </style>

  <filter id="bloom" x="-25%" y="-25%" width="150%" height="150%"
          color-interpolation-filters="sRGB">
    <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="near"/>
    <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="far"/>
    <feComponentTransfer in="near" result="nearHalo">
      <feFuncA type="linear" slope="{BLOOM_NEAR}"/>
    </feComponentTransfer>
    <feComponentTransfer in="far" result="farHalo">
      <feFuncA type="linear" slope="{BLOOM_FAR}"/>
    </feComponentTransfer>
    <feMerge>
      <feMergeNode in="farHalo"/>
      <feMergeNode in="nearHalo"/>
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
    {text_markup}
  </g>

  <rect class="roll" x="0" y="0" width="{W}" height="240" fill="url(#rollbar)"/>
  <rect class="scan" x="0" y="-4" width="{W}" height="{H + 8}" fill="url(#scanlines)"/>
  <rect width="{W}" height="{H}" fill="url(#vig)"/>
  <rect class="flick" width="{W}" height="{H}" fill="{GREEN}"/>
</g>

<path d="{screen_path()}" fill="none" stroke="#0c1a10" stroke-width="2.5"/>
</svg>
'''


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

    cursor = warped_cursor(prompt_row, len(PROMPT),
                           body_start + 0.5 + len(BODY) * 0.10)

    markup = (f'<g class="boot">{"".join(boot_lines)}</g>'
              f'<g>{"".join(body_lines)}{cursor}</g>')
    return crt_screen(
        markup,
        "A retro CRT terminal displaying a personnel file. Select an entry below.",
        font_uri, boot_end)


def skill_words():
    """Every technology across every sector, in one flat list."""
    return [word for _, words in SKILL_SECTORS for word in words]


Dump = collections.namedtuple("Dump", "cells placements tricks seed")

# A bracket trick is a run from an opener to its own closer on the same line.
BRACKETS = {"(": ")", "[": "]", "{": "}", "<": ">"}


def fill_cells(rng):
    """One garbage cell per address, some of them with a skill buried inside.

    A word never straddles two cells, so it always reads on a single line —
    the game lets them wrap, but a wrapped word here is one nobody finds.
    Returns the cells and where each word landed, as a flat character index.
    """
    words = skill_words()
    cells_total = DUMP_ROWS * 2

    oversized = [w for w in words if len(w) > DUMP_CELL]
    if oversized:
        raise ValueError(
            f"these skills are longer than a {DUMP_CELL}-character dump cell "
            f"and would not fit on one line: {', '.join(oversized)}")
    if len(words) > cells_total:
        raise ValueError(
            f"{len(words)} skills but only {cells_total} dump cells; "
            f"raise DUMP_ROWS")

    def noise(n):
        return "".join(rng.choice(GARBAGE) for _ in range(n))

    buried = dict(zip(rng.sample(range(cells_total), len(words)), words))
    cells, placements = [], []
    for i in range(cells_total):
        word = buried.get(i)
        if word is None:
            cells.append(noise(DUMP_CELL))
            continue
        lead = rng.randrange(DUMP_CELL - len(word) + 1)
        cells.append(noise(lead) + word + noise(DUMP_CELL - len(word) - lead))
        placements.append((i * DUMP_CELL + lead, word))
    return cells, placements


def find_tricks(cells, placements):
    """Bracket runs the player can select to buy a dud removal or a reset.

    Only runs of pure punctuation count, and only the longest of any set that
    overlap — the same rule the game uses, so nothing is selectable twice.
    """
    taken = set()
    for start, word in placements:
        taken.update(range(start, start + len(word)))

    candidates = []
    for c, cell in enumerate(cells):
        for k, ch in enumerate(cell):
            closer = BRACKETS.get(ch)
            if closer is None:
                continue
            j = cell.find(closer, k + 1)
            if j < 0:
                continue
            run = range(c * DUMP_CELL + k, c * DUMP_CELL + j + 1)
            if any(i in taken for i in run):
                continue
            if any(ch2.isalnum() for ch2 in cell[k:j + 1]):
                continue
            candidates.append((run[0], run[-1]))

    candidates.sort(key=lambda r: (r[0] - r[1], r[0]))   # longest first
    tricks, used = [], set()
    for start, end in candidates:
        span = set(range(start, end + 1))
        if span & used:
            continue
        used |= span
        tricks.append((start, end))
    return sorted(tricks)


def build_dump(tries=400):
    """The dump both screens use, on the first seed that hides enough tricks.

    Garbage is random, so a given seed may not happen to contain the bracket
    pairs the game needs. Walking seeds keeps the result deterministic while
    guaranteeing the mechanic exists.
    """
    for offset in range(tries):
        seed = DUMP_SEED + offset
        cells, placements = fill_cells(random.Random(seed))
        tricks = find_tricks(cells, placements)
        if len(tricks) >= TRICKS_MIN:
            return Dump(cells, placements, tricks, seed)
    raise RuntimeError(
        f"no seed within {tries} of {DUMP_SEED} produced {TRICKS_MIN} bracket "
        f"tricks; lower TRICKS_MIN or raise DUMP_ROWS")


def dump_rows(cells):
    """The two address columns, as full-width lines of text."""
    rows = []
    for r in range(DUMP_ROWS):
        right = DUMP_ROWS + r
        left_cell = f"0x{DUMP_ADDR + r * DUMP_CELL:04X} {cells[r]}"
        right_cell = f"0x{DUMP_ADDR + right * DUMP_CELL:04X} {cells[right]}"
        rows.append(f"{left_cell}  {right_cell}")
    return rows


def build_skills(font_uri, dump):
    rows = dump_rows(dump.cells)

    # The guess log is flush with the bottom of the dump, like the game's.
    log_top = len(rows) - len(SKILL_LOG)
    for i, entry in enumerate(SKILL_LOG):
        row = log_top + i
        rows[row] = rows[row].ljust(LOG_COL) + entry

    lines = []
    for i, line in enumerate(SKILL_HEADER):
        lines.append(warped_line(line, i + 1, "ln", 0.15 + i * 0.12))

    label = f"{SKILL_ATTEMPTS} ATTEMPT(S) LEFT:"
    pip_row = len(SKILL_HEADER) + 2
    lines.append(warped_line(label, pip_row, "ln", 0.45))
    for i in range(SKILL_ATTEMPTS):
        lines.append(warped_pip(pip_row, len(label) + 1 + i * 2, 0.45))

    dump_top = len(SKILL_HEADER) + 4
    for i, line in enumerate(rows):
        lines.append(warped_line(line, dump_top + i, "ln", 0.65 + i * 0.07))

    cursor_row = dump_top + log_top + len(SKILL_LOG) - 1
    cursor_col = LOG_COL + len(SKILL_LOG[-1])
    lines.append(warped_cursor(cursor_row, cursor_col, 0.65 + len(rows) * 0.07))

    words = ", ".join(skill_words())
    return crt_screen(
        f'<g>{"".join(lines)}</g>',
        "A retro CRT terminal showing a password-hack memory dump. Hidden in "
        f"the characters are: {esc(words)}. The same list is written out below.",
        font_uri)


def build_button(label, font_uri, w=272, h=64):
    cx, cy = w / 2, h / 2 + 7
    adv = 19 * (ADV / FS)
    text = f"[ {label} ]"
    x0 = cx - len(text) * adv / 2
    xs = " ".join(f"{x0 + i * adv:.1f}" for i, ch in enumerate(text) if ch != " ")
    chars = "".join(ch for ch in text if ch != " ")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"
     width="{w}" height="{h}" role="img" aria-label="{label}">
<defs>
  <style>
    @font-face {{ font-family:"TermMono"; src:url({font_uri}) format("truetype"); font-weight:400; }}
    text {{ font-family:"TermMono","Courier New",monospace; font-size:19px;
            font-weight:400; fill:{GREEN}; }}
  </style>
  <filter id="g" x="-30%" y="-30%" width="160%" height="160%" color-interpolation-filters="sRGB">
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="a"/>
    <feComponentTransfer in="a" result="halo">
      <feFuncA type="linear" slope="{BLOOM_NEAR}"/>
    </feComponentTransfer>
    <feMerge><feMergeNode in="halo"/><feMergeNode in="SourceGraphic"/></feMerge>
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


def build_skills_page(version):
    """SKILLS.md — the hack screen plus a keyboard-operable sector list.

    Nothing inside an <img>-loaded SVG can be focused or clicked, so the
    navigation is <details>/<summary>: GitHub keeps those, they take Tab focus,
    and Enter or Space opens one. That list is also the plaintext fallback for
    screen readers, so it must stay generated from SKILL_SECTORS.
    """
    sectors = []
    for i, (name, words) in enumerate(SKILL_SECTORS, start=1):
        entries = "\n".join(f"+ {w.ljust(14, '.')} ACCESS GRANTED" for w in words)
        sectors.append(f'''<details>
<summary><code>&gt; SECTOR {i:02d} -- {name}</code></summary>

```diff
{entries}
```

</details>''')

    sep = chr(10) * 2
    return f'''<!-- Generated by build.py. Edit SKILL_SECTORS there, not here. -->
<div align="center">

<img src="assets/skills.svg?v={version}" width="100%" alt="A retro CRT terminal showing a password-hack memory dump, with the technologies below hidden among the characters.">

<a href="{GAME_URL}"><img src="assets/btn-run.svg" height="50" alt="Run the terminal: a playable password hack"></a>
<a href="README.md"><img src="assets/btn-back.svg" height="50" alt="Back to the main terminal"></a>

</div>

That screen is a still. [Run the terminal]({GAME_URL}) to play the hack for
real — arrow keys move the cursor, <kbd>Enter</kbd> submits a guess, four
wrong ones lock you out.

## `> SELECT SECTOR`

Every word buried in the dump above is listed here. <kbd>Tab</kbd> moves
between sectors, <kbd>Enter</kbd> opens the one in focus, and
<kbd>Shift</kbd>+<kbd>Tab</kbd> steps back.

{sep.join(sectors)}
'''


def plaintext_sectors():
    """The skill list as plain HTML — what you get with no JavaScript."""
    blocks = []
    for i, (name, words) in enumerate(SKILL_SECTORS, start=1):
        items = "".join(f"<li>{esc(w)}</li>" for w in words)
        blocks.append(f"<h2>SECTOR {i:02d} -- {esc(name)}</h2><ul>{items}</ul>")
    return "".join(blocks)


def build_game_page(font_uri, dump):
    """docs/index.html — the terminal you can actually play.

    The font, the dump and the skills are substituted into src/terminal.html,
    so the served page makes no outbound requests and the game plays the same
    dump the still image shows.
    """
    with open(GAME_TEMPLATE, encoding="utf-8") as f:
        template = string.Template(f.read())

    data = {
        "rows": DUMP_ROWS,
        "cell": DUMP_CELL,
        "addr": DUMP_ADDR,
        "attempts": SKILL_ATTEMPTS,
        "logLines": GAME_LOG_LINES,
        "cells": dump.cells,
        "words": [[start, word] for start, word in dump.placements],
        "tricks": [list(t) for t in dump.tricks],
        "sectors": [[name, list(words)] for name, words in SKILL_SECTORS],
    }
    # "<" cannot survive raw inside an inline <script>; the dump is full of them
    payload = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")

    return template.substitute(
        TITLE=esc(GAME_TITLE),
        FONT=font_uri,
        PROFILE_URL=esc(PROFILE_URL),
        PLAINTEXT=plaintext_sectors(),
        DATA=payload)


def main():
    out = os.path.join(ROOT, "assets")
    docs = os.path.join(ROOT, "docs")
    os.makedirs(out, exist_ok=True)
    os.makedirs(docs, exist_ok=True)

    font_uri = embed_font()
    dump = build_dump()
    print(f"dump seed {dump.seed}: {len(dump.placements)} skills, "
          f"{len(dump.tricks)} bracket tricks")

    screens = [("terminal.svg", build_terminal(font_uri)),
               ("skills.svg", build_skills(font_uri, dump))]
    for name, svg in screens:
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path} ({os.path.getsize(path) / 1024:.0f} KB)")

    for label, name in BUTTONS + PAGE_BUTTONS:
        p = os.path.join(out, f"{name}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_button(label, font_uri))
        print(f"wrote {p} ({os.path.getsize(p) / 1024:.0f} KB)")

    page = os.path.join(ROOT, "SKILLS.md")
    with open(page, "w", encoding="utf-8") as f:
        f.write(build_skills_page(version=1))
    print(f"wrote {page}")

    game = os.path.join(docs, "index.html")
    with open(game, "w", encoding="utf-8") as f:
        f.write(build_game_page(font_uri, dump))
    print(f"wrote {game} ({os.path.getsize(game) / 1024:.0f} KB)")

    # Pages runs Jekyll over /docs otherwise, which has nothing to do here
    open(os.path.join(docs, ".nojekyll"), "w").close()


if __name__ == "__main__":
    main()
