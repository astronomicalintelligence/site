"""Fail if any page shows an image from another website.

Every image must live in the repository (see tools/localize_images.py), so pages do not break when a link
disappears and visitors' browsers make no requests to other servers.

    python3 tools/check_images.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = [
    re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)"),                    # ![alt](https://...)
    re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"'](https?://[^\"']+)", re.I),  # <img src="https://...">
    re.compile(r"https://(?:github\.com/user-attachments/assets/|user-images\.githubusercontent\.com/|"
               r"private-user-images\.githubusercontent\.com/)[^\s)\"'>]+"),  # any leftover attachment link
]

problems = []
for page in sorted(ROOT.rglob("*.qmd")):
    if any(part.startswith(("_", ".")) for part in page.relative_to(ROOT).parts):
        continue
    text = page.read_text(encoding="utf-8")
    for pat in PATTERNS:
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{page.relative_to(ROOT)}:{line}: external image {m.group(1) if m.groups() else m.group(0)}")

for p in sorted(set(problems)):
    print(p)
if problems:
    print("Copy these images into the repository with tools/localize_images.py.")
    sys.exit(1)
print("no external images")
