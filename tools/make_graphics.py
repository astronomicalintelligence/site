"""Generate the logo, favicon and the home-page spectrum.

Run from the repository root:  python tools/make_graphics.py
Outputs: images/logo.svg, images/logo-dark.svg, images/favicon.svg, _includes/spectrum.html
"""
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INK_LIGHT, INK_DARK, HALPHA = "#17324D", "#BFD3EA", "#C8323C"

# ---------------------------------------------------------------- logo
# "Ai" drawn as a spectrum: a tall emission line for the A, a smaller narrow
# line for the i, and a red star as the dot of the i.
LOGO_W, LOGO_H, LOGO_BASE = 35, 28, 23.5
XA, HA = 11.5, 20.5      # the A
XI, HI = 24.2, 11.0      # the i


def _pvoigt(x, x0, h, fwhm, eta):
    """Pseudo-Voigt profile: a natural-looking spectral line."""
    s = fwhm / 2.3548
    g = math.exp(-0.5 * ((x - x0) / s) ** 2)
    lor = 1 / (1 + ((x - x0) / (fwhm / 2)) ** 2)
    return h * ((1 - eta) * g + eta * lor)


def _logo_flux(x):
    quiet = (1 - math.exp(-0.5 * ((x - XA) / 4.0) ** 2)) * (1 - math.exp(-0.5 * ((x - XI) / 2.0) ** 2))
    wiggle = 0.3 * (0.65 * math.sin(x * 1.15) + 0.35 * math.sin(x * 2.1 + 1.0)) * quiet
    return LOGO_BASE - _pvoigt(x, XA, HA, 3.4, 0.25) - _pvoigt(x, XI, HI, 1.3, 0.15) + wiggle


def _star(cx, cy, r=2.9, s=0.8):
    pts = []
    for k in range(8):
        a = math.pi / 4 * k - math.pi / 2
        rad = r if k % 2 == 0 else s
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _fmt(pts):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def mark(ink, stroke):
    xs = [2 + 0.25 * k for k in range(int((LOGO_W - 4) / 0.25) + 1)]
    line = _fmt([(x, _logo_flux(x)) for x in xs])
    star = _fmt(_star(XI, LOGO_BASE - HI - 4.6))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LOGO_W} {LOGO_H}" '
        f'width="{LOGO_W}" height="{LOGO_H}" role="img" aria-label="Astronomical Intelligence">'
        f'<polyline points="{line}" fill="none" stroke="{ink}" stroke-width="{stroke}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<polygon points="{star}" fill="{HALPHA}"/>'
        "</svg>\n"
    )


(ROOT / "images/logo.svg").write_text(mark(INK_LIGHT, 2.6))
(ROOT / "images/logo-dark.svg").write_text(mark(INK_DARK, 2.6))
(ROOT / "images/favicon.svg").write_text(mark(INK_LIGHT, 2.8))

# ------------------------------------------------------------ spectrum
# Research phases drawn as identified emission lines.
W, H, BASEY = 1000, 210, 180
LINES = [  # (label, category slug, x, height)
    ("Literature", "literature", 105, 78),
    ("Proposals", "proposals", 265, 50),
    ("Data and code", "code", 445, 128),
    ("Analysis", "analysis", 600, 92),
    ("Writing", "writing", 760, 58),
    ("Review", "review", 900, 70),
]
SIGMA = 5.5
rng = random.Random(7)


def flux(x):
    y = sum(h * math.exp(-0.5 * ((x - x0) / SIGMA) ** 2) for _, _, x0, h in LINES)
    return y + rng.uniform(-2.2, 2.2)


pts = " ".join(f"{x},{BASEY - flux(x):.1f}" for x in range(0, W + 1, 2))

parts = [
    "```{=html}",
    f'<figure class="spectrum" aria-label="Workflows by research phase">',
    f'<svg viewBox="0 0 {W} {H + 26}" role="group" preserveAspectRatio="xMidYMid meet">',
    f'<polyline class="spec-line" points="{pts}"/>',
]
for label, slug, x0, h in LINES:
    top = BASEY - h - 10
    parts.append(
        f'<a class="spec-id" href="workflows/index.html#category={slug}" aria-label="{label} workflows">'
        f'<rect x="{x0 - 55}" y="{top - 44}" width="110" height="{h + 60}" fill="transparent"/>'
        f'<line x1="{x0}" y1="{top - 4}" x2="{x0}" y2="{top - 20}"/>'
        f'<text x="{x0}" y="{top - 28}" text-anchor="middle">{label}</text></a>'
    )
parts += [
    f'<line class="spec-axis" x1="0" y1="{H + 4}" x2="{W - 8}" y2="{H + 4}"/>',
    f'<path class="spec-axis-head" d="M{W - 12},{H} L{W},{H + 4} L{W - 12},{H + 8}"/>',
    f'<text class="spec-axis-label" x="{W - 18}" y="{H + 22}" text-anchor="end">research phase</text>',
    "</svg></figure>",
    "```",
]
out = ROOT / "_includes/spectrum.html"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(parts) + "\n")
print("written:", "images/logo.svg, images/logo-dark.svg, images/favicon.svg,", out.relative_to(ROOT))
