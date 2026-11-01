"""Generate the logo, favicon and the spectrum in the home-page hero.

Run from the repository root:  python tools/make_graphics.py
Outputs: images/logo.svg, images/logo-dark.svg, images/favicon.svg, _includes/hero-spectrum.html
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

# ------------------------------------------------------- hero spectrum
# A wide spectrum across the bottom of the home hero; the two strongest
# lines and the red star echo the Ai logo.
HW, HH, HB = 1600, 420, 380
HERO_LINES = [(260, 70, 9), (330, 40, 4), (520, 60, 6), (760, 90, 7), (980, 340, 11),
              (1060, 170, 4), (1240, 70, 6), (1420, 120, 7)]
hrng = random.Random(11)
hpts = []
for x in range(0, HW + 1, 2):
    v = sum(a * math.exp(-0.5 * ((x - x0) / s) ** 2) for x0, a, s in HERO_LINES)
    hpts.append(f"{x},{HB - v + hrng.uniform(-2.0, 2.0):.1f}")
hstar = _fmt(_star(1060, HB - 170 - 34, r=16, s=4.5))
hero = (
    "```{=html}\n"
    '<div class="spectrum-bg" aria-hidden="true">'
    f'<svg viewBox="0 0 {HW} {HH}" preserveAspectRatio="xMidYMax meet">'
    f'<polyline points="{" ".join(hpts)}" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>'
    f'<polygon points="{hstar}" fill="{HALPHA}"/></svg></div>\n'
    "```\n"
)
(ROOT / "_includes/hero-spectrum.html").write_text(hero)

print("written: images/logo.svg, images/logo-dark.svg, images/favicon.svg, _includes/hero-spectrum.html")
