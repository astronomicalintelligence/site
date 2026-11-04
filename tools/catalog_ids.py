"""Catalogue numbers and folders of contributions (AI W0001, AI P0001, ...).

Every contribution gets a number made of the site prefix "AI", a letter for its
type and a four-digit counter: workflows W, prompts P, skills S, agent configs A,
model checks M, reviews R, failures F. Numbers are never reused or changed once
given.

Every contribution lives in its own folder, named after its number and a short
name, with the page in index.qmd and any images or files next to it:

    prompts/AIP0001-pre-submission-review/index.qmd
    skills/AIS0001-radio-fits-units/index.qmd, SKILL.md

A new contribution arrives without a number, in a folder with XXXX in place of
the number: prompts/AIPXXXX-<name>/index.qmd (prompts/<name>/index.qmd and
prompts/<name>.qmd are accepted too). With --write, this script gives it the next
free number, writes it into the front matter as `catalog: "AI P0002"` and renames
the folder to prompts/AIP0002-<name>/.

    python3 tools/catalog_ids.py                    # check: list what would change, fail on problems
    python3 tools/catalog_ids.py --base origin/main # also fail if a number given on main was changed
    python3 tools/catalog_ids.py --write            # give the missing numbers and rename the folders

The publish workflow runs it with --write on every push to main, so a new
contribution is numbered and moved automatically when it is merged. Contributors
leave the `catalog` field out.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = {"workflows": "W", "prompts": "P", "skills": "S", "agent-configs": "A",
         "model-checks": "M", "reviews": "R", "failures": "F"}
DIGITS = 4
CAT_RE = re.compile(r'^catalog:\s*["\']?AI ([A-Z])(\d+)["\']?\s*$')
PREFIX_RE = re.compile(r"^AI([A-Z])(\d+|XXXX)-(.+)$")     # AIP0001-pre-submission-review, or AIPXXXX-... before publication


def label(code, num):
    return f"AI {code}{num:0{DIGITS}d}"


def folder_name(code, num, slug):
    return f"AI{code}{num:0{DIGITS}d}-{slug}"


def contributions(folder):
    """Pages of one type: <type>/<folder>/index.qmd, and loose <type>/<name>.qmd still to be moved."""
    base = ROOT / folder
    pages = list(base.glob("*/index.qmd"))
    pages += [p for p in base.glob("*.qmd") if p.name != "index.qmd"]
    return sorted(pages)


def front_matter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (1, i), lines
    return None, lines


def catalog_of(text):
    span, lines = front_matter(text)
    for ln in (lines[span[0]:span[1]] if span else []):
        m = CAT_RE.match(ln)
        if m:
            return m.group(1), int(m.group(2))
    return None


def numbers_on(base):
    """{path: (letter, number)} for the contributions on the branch `base`."""
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", base], cwd=ROOT, capture_output=True, text=True)
    out = {}
    for rel in r.stdout.split():
        parts = rel.split("/")
        page = (len(parts) == 2 and rel.endswith(".qmd") and parts[1] != "index.qmd") or \
               (len(parts) == 3 and parts[2] == "index.qmd")
        if parts[0] in TYPES and page:
            show = subprocess.run(["git", "show", f"{base}:{rel}"], cwd=ROOT, capture_output=True, text=True)
            c = catalog_of(show.stdout) if show.returncode == 0 else None
            if c:
                out[rel] = c
    return out


def move(src, dst):
    """Rename with git when the file is tracked, so the history follows it."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        shutil.move(str(src), str(dst))


def main(write, base=None):
    problems, changes = [], []
    old = numbers_on(base) if base else {}
    for folder, code in TYPES.items():
        items = []
        for path in contributions(folder):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            span, lines = front_matter(text)
            if span is None:
                problems.append(f"{rel}: no front matter")
                continue
            loose = path.name != "index.qmd"
            name = path.stem if loose else path.parent.name
            m = PREFIX_RE.match(name)
            slug = m.group(3) if m else name
            num, date = None, "9999-99-99"
            for ln in lines[span[0]:span[1]]:
                c = CAT_RE.match(ln)
                if c:
                    if c.group(1) != code:
                        problems.append(f"{rel}: catalogue letter {c.group(1)} should be {code}")
                    num = int(c.group(2))
                d = re.match(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", ln)
                if d:
                    date = d.group(1)
            if m and m.group(1) != code:
                problems.append(f"{rel}: the folder name starts with AI{m.group(1)} but should start with AI{code}")
            elif m and m.group(2) == "XXXX":
                if num is not None:
                    problems.append(f"{rel}: the page already has {label(code, num)} but its folder says XXXX")
            elif m and (num is None or int(m.group(2)) != num):
                problems.append(f"{rel}: the folder name says AI {m.group(1)}{m.group(2)} but the page says "
                                f"{label(code, num) if num is not None else 'no number'}")
            if rel in old and (old[rel][0] != code or old[rel][1] != num):
                problems.append(f"{rel}: catalogue number changed from {label(*old[rel])} to "
                                f"{label(code, num) if num is not None else 'nothing'}; numbers never change")
            items.append({"path": path, "rel": rel, "loose": loose, "slug": slug, "num": num, "date": date,
                          "lines": lines, "span": span})

        # duplicates: the earliest contribution keeps the number, later ones get a new one
        seen = {}
        for it in sorted(items, key=lambda x: (x["date"], x["rel"])):
            if it["num"] is None:
                continue
            if it["num"] in seen:
                problems.append(f"{label(code, it['num'])} used twice: {seen[it['num']]} and {it['rel']}")
                it["num"], it["new"] = None, True
            else:
                seen[it["num"]] = it["rel"]

        nxt = max(seen, default=0) + 1
        for it in sorted(items, key=lambda x: (x["date"], x["rel"])):
            if it["num"] is None:
                it["num"], it["new"] = nxt, True
                nxt += 1
            target = ROOT / folder / folder_name(code, it["num"], it["slug"]) / "index.qmd"
            if not it.get("new") and target == it["path"]:
                continue
            dest = target.relative_to(ROOT).parent.as_posix() + "/"
            if target.exists() and target != it["path"]:
                problems.append(f"{it['rel']}: cannot move to {dest}, it already exists")
                continue
            what = f"{label(code, it['num'])}  {it['rel']}" + (f"  ->  {dest}" if target != it["path"] else "")
            changes.append(("assigned " if it.get("new") else "moved ") + what if write else
                           ("to assign " if it.get("new") else "to move ") + what)
            if write:
                if it.get("new"):
                    lines, (a, b) = it["lines"], it["span"]
                    head = [ln for ln in lines[a:b] if not CAT_RE.match(ln)]
                    at = next((k + 1 for k, ln in enumerate(head) if ln.startswith("title:")), 0)
                    head.insert(at, f'catalog: "{label(code, it["num"])}"')
                    it["path"].write_text("\n".join(lines[:a] + head + lines[b:]), encoding="utf-8")
                if target != it["path"]:
                    move(it["path"] if it["loose"] else it["path"].parent,
                         target if it["loose"] else target.parent)

    for c in changes:
        print(c)
    for p in problems:
        print("WARNING " + p, file=sys.stderr)
    if not changes:
        print("all contributions have a catalogue number and their folder")
    # in check mode a problem is an error, so a pull request cannot introduce one silently
    return 1 if (problems and not write) else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    base = args[args.index("--base") + 1] if "--base" in args else None
    sys.exit(main("--write" in args, base))
