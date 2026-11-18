"""Package every skill as a .zip that can be unpacked straight into an agent's skills directory.

For each skills/<folder>/ with a SKILL.md, writes skills/<folder>/<name>.zip, where <name> is the `name` in the
front matter of SKILL.md. The archive holds one folder <name>/ with SKILL.md and every other file of the skill
(not the page index.qmd, its images figure-N, or older archives):

    skills/AIS0003-astro-paper-writing/astro-paper-writing.zip
        astro-paper-writing/SKILL.md
        astro-paper-writing/check_aa.py
        astro-paper-writing/aa/aa.cls ...

Quarto runs it before every render (`pre-render` in _quarto.yml); the archives are not committed (.gitignore).
The archives are reproducible: same files, same bytes.

    python3 tools/zip_skills.py
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = re.compile(r"^(index\.qmd|figure-\d+\.\w+|.*\.zip|\..*|_.*)$")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)                    # the same bytes on every build


def skill_name(skill_md):
    m = re.match(r"---\n(.*?)\n---", skill_md.read_text(encoding="utf-8"), re.S)
    n = re.search(r"^name:\s*[\"']?([a-z0-9][a-z0-9-]*)[\"']?\s*$", m.group(1), re.M) if m else None
    return n.group(1) if n else None


def main():
    made = 0
    for skill_md in sorted((ROOT / "skills").glob("*/SKILL.md")):
        folder = skill_md.parent
        name = skill_name(skill_md)
        if not name:
            print(f"{folder.relative_to(ROOT)}: no name in SKILL.md, no archive", file=sys.stderr)
            continue
        files = sorted(p for p in folder.rglob("*") if p.is_file()
                       and not any(SKIP.match(part) for part in p.relative_to(folder).parts))
        out = folder / f"{name}.zip"
        for old in folder.glob("*.zip"):
            if old != out:
                old.unlink()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                info = zipfile.ZipInfo(f"{name}/{p.relative_to(folder).as_posix()}", FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, p.read_bytes())
        made += 1
    print(f"zip_skills: {made} skill archive(s)")


if __name__ == "__main__":
    main()
