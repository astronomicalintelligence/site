"""Copy the images of a contribution page into the repository.

Images that contributors drag into a GitHub issue form arrive in the text as links to GitHub's servers:

    ![image](https://github.com/user-attachments/assets/4f2c9a1e-...)
    <img width="812" alt="residuals" src="https://github.com/user-attachments/assets/4f2c9a1e-..." />

This script, run on a page written from such an issue, downloads every GitHub attachment, checks that it is an image,
resizes it to at most 1600 px wide, removes its metadata (EXIF, GPS), saves it next to the page in `figures/` and
rewrites the reference in place:

    workflows/literature-ads.qmd  ->  workflows/figures/literature-ads-1.png
    skills/radio-fits-units/index.qmd  ->  skills/radio-fits-units/figures/radio-fits-units-1.png

    python3 tools/localize_images.py workflows/literature-ads.qmd [more pages ...]

It prints one line per image. Images that cannot be downloaded, are not images, or come from other websites are left
out of the page and listed under MISSING, so the pull request can say what to add by hand. Images without a useful
description are listed under NEEDS ALT TEXT. Exit code 1 if anything is missing.

Needs: pip install pillow requests
"""
import io
import os
import re
import sys
from pathlib import Path

import requests
from PIL import Image

MAX_WIDTH = 1600
MAX_BYTES = 15 * 1024 * 1024
ATTACHMENT = re.compile(r"https://(?:github\.com/user-attachments/assets/|user-images\.githubusercontent\.com/|"
                        r"private-user-images\.githubusercontent\.com/)[^\s)\"'>]+")
# for tests only: extra URL prefixes treated as attachments
for extra in filter(None, os.environ.get("LOCALIZE_TEST_PREFIXES", "").split(",")):
    ATTACHMENT = re.compile(ATTACHMENT.pattern + "|" + re.escape(extra) + r"[^\s)\"'>]+")

MD_IMG = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>https?://[^\s)]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG = re.compile(r"<img\b(?P<attrs>[^>]*)/?>", re.I)
GENERIC_ALT = {"", "image", "img", "screenshot", "picture", "figure", "untitled"}


def attr(attrs, name):
    m = re.search(rf'\b{name}\s*=\s*"([^"]*)"', attrs, re.I) or re.search(rf"\b{name}\s*=\s*'([^']*)'", attrs, re.I)
    return m.group(1) if m else ""


def download(url):
    headers = {"User-Agent": "astronomicalintelligence-site"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        headers["Authorization"] = f"token {token}"      # dropped by requests on the redirect to the file host
    r = requests.get(url, headers=headers, timeout=60, stream=True)
    r.raise_for_status()
    data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(data) > MAX_BYTES:
        raise ValueError("larger than 15 MB")
    return data


def save(data, out_base):
    im = Image.open(io.BytesIO(data))
    fmt = (im.format or "").upper()
    if fmt not in {"PNG", "JPEG", "GIF", "WEBP"}:
        raise ValueError(f"not a PNG, JPEG, GIF or WebP image ({fmt or 'unknown'})")
    animated = getattr(im, "is_animated", False)
    if fmt == "GIF" and animated:                          # keep animations as they are, metadata-free by format
        path = out_base.with_suffix(".gif"); path.write_bytes(data); return path, im.size
    im.load()
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    if fmt in {"JPEG", "WEBP"} and im.mode not in {"RGBA", "LA", "P"}:
        path = out_base.with_suffix(".jpg"); im.convert("RGB").save(path, "JPEG", quality=85, optimize=True)
    else:
        path = out_base.with_suffix(".png"); im.save(path, "PNG", optimize=True)   # re-encoding drops EXIF/GPS
    return path, im.size


def nearby_text(text, pos):
    """The sentence before the image, as a fallback description."""
    before = text[:pos].rstrip().split("\n")
    for line in reversed(before[-3:]):
        line = re.sub(r"^\s*(?:\d+\.|[-*])\s*", "", line).strip()
        line = re.sub(r"[`*_#>]", "", line)
        if len(line) > 12 and "http" not in line:
            return line[:160]
    return ""


def localize(page):
    page = Path(page)
    text = page.read_text(encoding="utf-8")
    stem = page.parent.name if page.name == "index.qmd" else page.stem
    figdir = page.parent / "figures"
    existing = sorted(figdir.glob(f"{stem}-*")) if figdir.exists() else []
    n = max([int(m.group(1)) for p in existing if (m := re.search(r"-(\d+)$", p.stem))], default=0)
    missing, no_alt, done = [], [], {}

    def handle(url, alt, pos):
        """Download once per URL; every occurrence keeps its own description."""
        nonlocal n
        if url not in done:
            if not ATTACHMENT.match(url):
                missing.append(f"{url}  (not a GitHub attachment: images from other sites are not copied)")
                done[url] = None
            else:
                n += 1
                figdir.mkdir(exist_ok=True)
                try:
                    path, size = save(download(url), figdir / f"{stem}-{n}")
                    done[url] = path.relative_to(page.parent).as_posix()
                    print(f"saved {done[url]}  {size[0]}x{size[1]}")
                except Exception as e:                    # network, not an image, too large ...
                    msg = "not an image" if "cannot identify image" in str(e) else str(e)
                    missing.append(f"{url}  ({msg})"); n -= 1; done[url] = None
        rel = done[url]
        if rel is None:
            return ""
        if alt.strip().lower() in GENERIC_ALT:
            alt = nearby_text(text, pos)
            if not alt:
                no_alt.append(rel); alt = "Figure"
        return f"![{alt}]({rel})"

    # one pass, in document order, over the three ways an image can appear
    ANY = re.compile(MD_IMG.pattern + "|" + HTML_IMG.pattern.replace("(?P<attrs>", "(?P<hattrs>") + "|(?P<bare>" + ATTACHMENT.pattern + ")", re.I)

    def sub(m):
        if m.group("url"):
            return handle(m.group("url"), m.group("alt"), m.start())
        if m.group("bare"):
            return handle(m.group("bare"), "", m.start())
        src = attr(m.group("hattrs"), "src")
        return handle(src, attr(m.group("hattrs"), "alt"), m.start()) if src.startswith("http") else m.group(0)

    new = ANY.sub(sub, text)
    if new != text:
        page.write_text(new, encoding="utf-8")
    return missing, no_alt


def main(pages):
    status = 0
    for p in pages:
        missing, no_alt = localize(p)
        for m in missing:
            print(f"MISSING in {p}: {m}"); status = 1
        for a in no_alt:
            print(f"NEEDS ALT TEXT in {p}: {a}")
    return status


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1:]))
