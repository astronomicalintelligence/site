"""Catalogue numbers and folders of contributions (AI W0001, AI P0001, ...).

Every contribution lives in its own folder, named after its catalogue number and a short name, with the page in
index.qmd and its images and files next to it:

    prompts/AIP0001-pre-submission-review/index.qmd
    skills/AIS0002-astro-research/index.qmd, SKILL.md, figure-1.png

The number is "AI", a letter for the type (workflows W, prompts P, skills S, agent configs A, model checks M,
reviews R, failures F) and four digits. Numbers are never reused or changed once given. To remove a contribution,
delete its folder and add its number to tools/retired.txt, so the number is not given again.

A new contribution arrives with XXXX in place of the number and no `catalog` field: skills/AISXXXX-astro-research/.
With --write, this script gives it the next free number, writes `catalog: "AI S0002"` into the front matter and
renames the folder to skills/AIS0002-astro-research/.

    python3 tools/catalog_ids.py                    # check
    python3 tools/catalog_ids.py --base origin/main # also fail if a number on main has disappeared
    python3 tools/catalog_ids.py --write            # number the new contributions and rename their folders

The publish workflow runs it with --write on every push to main, before rendering, so a contribution is numbered
when its pull request is merged.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = {"workflows": "W", "prompts": "P", "skills": "S", "agent-configs": "A",
         "model-checks": "M", "reviews": "R", "failures": "F"}
FOLDER_RE = re.compile(r"^AI([A-Z])(\d{4}|XXXX)-([a-z0-9][a-z0-9-]*)$")
CAT_RE = re.compile(r'^catalog:\s*["\']?AI ([A-Z])(\d{4})["\']?\s*$', re.M)
DATE_RE = re.compile(r'^date:\s*["\']?(\d{4}-\d{2}-\d{2})', re.M)
SECTION_FILES = {"index.qmd", "_metadata.yml"}           # the section's own list page and settings
RETIRED_FILE = ROOT / "tools" / "retired.txt"


def retired():
    """{(letter, number)} of removed contributions, from tools/retired.txt."""
    if not RETIRED_FILE.exists():
        return set()
    return {(m.group(1), int(m.group(2))) for m in re.finditer(r"^AI ([A-Z])(\d{4})\b", RETIRED_FILE.read_text(), re.M)}


def front(text):
    """The front matter between the first two --- lines, or None."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main(write, base=None):
    problems, done, new = [], [], []
    numbered = {}                                      # (letter, number) -> folder
    gone = retired()
    for section, code in TYPES.items():
        for entry in sorted((ROOT / section).iterdir()):
            name, rel = entry.name, entry.relative_to(ROOT).as_posix()
            if name in SECTION_FILES or name.startswith("."):
                continue
            m = FOLDER_RE.match(name)
            page = entry / "index.qmd"
            if not (entry.is_dir() and m and page.exists()):
                problems.append(f"{rel}: every contribution must be a folder AI{code}XXXX-<name>/ (lowercase name, "
                                f"hyphens) with an index.qmd")
                continue
            text = page.read_text(encoding="utf-8")
            head = front(text)
            if head is None:
                problems.append(f"{rel}/index.qmd: no front matter")
                continue
            letter, num, cat = m.group(1), m.group(2), CAT_RE.search(head)
            if letter != code:
                problems.append(f"{rel}: in {section}/ the folder must start with AI{code}, not AI{letter}")
            elif num == "XXXX":
                if cat:
                    problems.append(f"{rel}: a new contribution has no `catalog` field; it is written on publication")
                elif not re.search(r"^title:", head, re.M):
                    problems.append(f"{rel}/index.qmd: no title")
                else:
                    date = DATE_RE.search(head)
                    new.append((date.group(1) if date else "9999-99-99", section, entry, text))
            else:
                if not cat or cat.group(1) != code or cat.group(2) != num:
                    problems.append(f'{rel}: the folder says AI {code}{num} but the page says '
                                    f'{"AI " + cat.group(1) + cat.group(2) if cat else "no catalogue number"}')
                if (code, int(num)) in gone:
                    problems.append(f"{rel}: AI {code}{num} was removed (tools/retired.txt) and cannot be used again")
                if (code, int(num)) in numbered:
                    problems.append(f"AI {code}{num} used twice: {numbered[code, int(num)]} and {rel}")
                numbered[code, int(num)] = rel

    if base:                                            # a number given on main must still be here
        listing = run("git", "ls-tree", "-d", "--name-only", base, *[f"{s}/" for s in TYPES]).stdout.split()
        for rel in listing:
            m = FOLDER_RE.match(rel.split("/")[-1])
            if m and m.group(2) != "XXXX" and not (ROOT / rel).is_dir() and (m.group(1), int(m.group(2))) not in gone:
                problems.append(f"{rel} is on {base} but not here: catalogue numbers and folders never change "
                                f"(to remove a contribution, add its number to tools/retired.txt)")

    for date, section, entry, text in sorted(new, key=lambda x: (x[0], x[2].name)):
        code = TYPES[section]
        num = max([n for (c, n) in list(numbered) + list(gone) if c == code], default=0) + 1
        numbered[code, num] = section
        label, slug = f"AI {code}{num:04d}", FOLDER_RE.match(entry.name).group(3)
        target = entry.parent / f"AI{code}{num:04d}-{slug}"
        done.append(f"{label}  {entry.relative_to(ROOT)}/  ->  {target.relative_to(ROOT)}/")
        if write:
            # the number goes right after the title
            text = re.sub(r"^(title:.*)$", lambda t: t.group(1) + f'\ncatalog: "{label}"', text, count=1, flags=re.M)
            (entry / "index.qmd").write_text(text, encoding="utf-8")
            if run("git", "mv", str(entry), str(target)).returncode:   # untracked: plain rename
                shutil.move(str(entry), str(target))

    for d in done:
        print(("assigned " if write else "to assign ") + d)
    for p in problems:
        print("ERROR " + p, file=sys.stderr)
    if not done and not problems:
        print("every contribution has its catalogue number and folder")
    return 1 if problems else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main("--write" in args, args[args.index("--base") + 1] if "--base" in args else None))
