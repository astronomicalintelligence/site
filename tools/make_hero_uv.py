"""Home background: uv-coverage of the real Dutch LOFAR array (24 core + 14 remote LBA stations, positions from
ASTRON's lofarantpos), 12 h centred on transit, source at declination +48 deg.
Tracks coloured by baseline length along the site's spectral palette (short = violet, long = red),
by rank, so the colours are spread evenly over the 703 baselines.

Needs: pip install lofarantpos matplotlib pillow
Run from the repository root: python3 tools/make_hero_uv.py  -> images/hero-uv.jpg
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.collections import LineCollection
from lofarantpos.db import LofarAntennaDatabase

W, H, NAVY = 1600, 896, "#0A1320"
OUT = Path(__file__).resolve().parent.parent / "images"
db = LofarAntennaDatabase()
names = sorted(k for k in db.phase_centres if k[:2] in ("CS", "RS") and k.endswith("LBA"))
xyz = np.array([db.phase_centres[k] for k in names]) / 1000.0          # km, ITRF/ETRS
lon = np.arctan2(xyz[:, 1].mean(), xyz[:, 0].mean())
dec = np.radians(48.0)
h = np.linspace(-np.pi / 2, np.pi / 2, 400) - lon                        # Greenwich hour angle, +-6 h around local transit

spectral = LinearSegmentedColormap.from_list("lines", ["#B48CF0", "#8EA6FF", "#5CC8E6", "#5ED29A", "#F2B44A", "#FF7A6E"])
pairs = [(i, j) for i in range(len(xyz)) for j in range(i + 1, len(xyz))]
allL = np.array([np.linalg.norm(xyz[j] - xyz[i]) for i, j in pairs])
rank = {tuple(p): r / (len(pairs) - 1) for r, p in enumerate(np.array(pairs)[np.argsort(allL)].tolist())}
segs, cols, lws = [], [], []
lens = []
for i in range(len(xyz)):
    for j in range(i + 1, len(xyz)):
        Bx, By, Bz = xyz[j] - xyz[i]
        u = np.sin(h) * Bx + np.cos(h) * By
        v = -np.sin(dec) * np.cos(h) * Bx + np.sin(dec) * np.sin(h) * By + np.cos(dec) * Bz
        L = np.linalg.norm(xyz[j] - xyz[i]); lens.append(L)
        c = spectral(rank[(i, j)])
        a = 0.38 if L > 4 else 0.20
        for s in (1, -1):
            pts = np.column_stack([s * u, s * v]); seg = np.stack([pts[:-1], pts[1:]], axis=1)
            segs.append(seg); cols.append(np.tile([c[0], c[1], c[2], a], (len(seg), 1))); lws.append(np.full(len(seg), 0.9 if L > 4 else 0.6))
print(f"{len(names)} stations, {len(lens)} baselines, {min(lens):.2f}-{max(lens):.0f} km")

def render(name, half):
    f = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = f.add_axes([0, 0, 1, 1]); ax.set_axis_off(); f.patch.set_facecolor(NAVY); ax.set_facecolor(NAVY)
    ax.add_collection(LineCollection(np.concatenate(segs), colors=np.concatenate(cols), linewidths=np.concatenate(lws), capstyle="round"))
    # frame: pattern centred at 70% across and 33% down, height = 2*half*1.5
    hy = half * 1.55; hx = hy * W / H
    ax.set_xlim(-0.70 * 2 * hx, 0.30 * 2 * hx); ax.set_ylim(-0.67 * 2 * hy, 0.33 * 2 * hy)
    import io
    buf = io.BytesIO(); f.savefig(buf, format="png", dpi=100, facecolor=NAVY); plt.close(f)
    im = Image.open(buf).convert("RGB")
    glow = im.filter(ImageFilter.GaussianBlur(6))
    out = Image.blend(im, Image.eval(Image.blend(im, glow, 0.5), lambda x: min(255, int(x * 1.25))), 0.45)
    out.save(OUT / f"{name}.jpg", quality=88, optimize=True, progressive=True)

render("hero-uv", 45)   # core and inner remote stations; the outer tracks run off the frame
print("wrote", OUT / "hero-uv.jpg")
