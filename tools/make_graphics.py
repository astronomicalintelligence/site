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
# A noisy baseline with one emission line: how astronomers read light,
# and how a language model scores its next token.
def _curve():
    """Smooth emission line on a lightly noisy baseline, 32x28 box."""
    pts = []
    x = 2.0
    while x <= 30.0 + 1e-9:
        peak = 19.5 * math.exp(-0.5 * ((x - 16.5) / 1.2) ** 2)
        noise = (0.55 * math.sin(x * 1.15) + 0.3 * math.sin(x * 2.1 + 1.0)) * (1 - math.exp(-0.5 * ((x - 16.5) / 2.2) ** 2))
        pts.append((x, 23.5 - peak + noise))
        x += 0.5
    return pts


_PTS = _curve()
_fmt = lambda seg: " ".join(f"{x:.1f},{y:.2f}" for x, y in seg)
BASE = _fmt([p for p in _PTS if p[0] <= 13.5])
PEAK = _fmt([p for p in _PTS if 13.5 <= p[0] <= 19.5])
TAIL = _fmt([p for p in _PTS if p[0] >= 19.5])


def mark(ink, stroke):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 28" width="32" height="28" '
        'role="img" aria-label="Astronomical Intelligence">'
        f'<g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="{stroke}">'
        f'<polyline points="{BASE}" stroke="{ink}"/>'
        f'<polyline points="{TAIL}" stroke="{ink}"/>'
        f'<polyline points="{PEAK}" stroke="{HALPHA}"/>'
        "</g></svg>\n"
    )


(ROOT / "images/logo.svg").write_text(mark(INK_LIGHT, 2.2))
(ROOT / "images/logo-dark.svg").write_text(mark(INK_DARK, 2.2))
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
