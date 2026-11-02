"""Catalogue numbers for contributions (AI W001, AI P001, ...).

Every contribution gets a number made of the site prefix "AI", a letter for its
type and a counter: workflows W, prompts P, skills S, agent configs A, model
checks M, reviews R, failures F. Numbers are never reused or changed once
given.

    python3 tools/catalog_ids.py           # check: list missing numbers, fail on duplicates
    python3 tools/catalog_ids.py --write   # write the missing numbers into the front matter

The publish workflow runs it with --write on every push to main, so a new
contribution is numbered automatically when it is merged. Contributors leave the
`catalog` field out.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = {"workflows": "W", "prompts": "P", "skills": "S", "agent-configs": "A",
         "model-checks": "M", "reviews": "R", "failures": "F"}
CAT_RE = re.compile(r'^catalog:\s*["\']?AI ([A-Z])(\d{3,})["\']?\s*$')


def contributions(folder):
    base = ROOT / folder
    files = base.glob("*/index.qmd") if folder == "skills" else (p for p in base.glob("*.qmd") if p.name != "index.qmd")
    return sorted(files)


def front_matter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (1, i), lines
    return None, lines


def main(write):
    problems, changes = [], []
    for folder, code in TYPES.items():
        items = []
        for path in contributions(folder):
            text = path.read_text(encoding="utf-8")
            span, lines = front_matter(text)
            if span is None:
                problems.append(f"{path.relative_to(ROOT)}: no front matter")
                continue
            head = lines[span[0]:span[1]]
            num, date = None, "9999-99-99"
            for ln in head:
                m = CAT_RE.match(ln)
                if m:
                    if m.group(1) != code:
                        problems.append(f"{path.relative_to(ROOT)}: catalogue letter {m.group(1)} should be {code}")
                    num = int(m.group(2))
                d = re.match(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", ln)
                if d:
                    date = d.group(1)
            items.append({"path": path, "num": num, "date": date, "lines": lines, "span": span})

        # duplicates: the earliest contribution keeps the number, later ones get a new one
        seen = {}
        for it in sorted(items, key=lambda x: (x["date"], str(x["path"]))):
            if it["num"] is None:
                continue
            if it["num"] in seen:
                problems.append(f"AI {code}{it['num']:03d} used twice: {seen[it['num']].relative_to(ROOT)} and {it['path'].relative_to(ROOT)}")
                it["num"] = None
            else:
                seen[it["num"]] = it["path"]

        nxt = max(seen, default=0) + 1
        for it in sorted((i for i in items if i["num"] is None), key=lambda x: (x["date"], str(x["path"]))):
            label = f"AI {code}{nxt:03d}"
            changes.append(f"{label}  {it['path'].relative_to(ROOT)}")
            if write:
                lines, (a, b) = it["lines"], it["span"]
                head = [ln for ln in lines[a:b] if not CAT_RE.match(ln)]
                at = next((k + 1 for k, ln in enumerate(head) if ln.startswith("title:")), 0)
                head.insert(at, f'catalog: "{label}"')
                it["path"].write_text("\n".join(lines[:a] + head + lines[b:]), encoding="utf-8")
            nxt += 1

    for c in changes:
        print(("assigned " if write else "to assign ") + c)
    for p in problems:
        print("WARNING " + p, file=sys.stderr)
    if not changes:
        print("all contributions have a catalogue number")
    # in check mode a duplicate is an error, so a pull request cannot introduce one silently
    return 1 if (problems and not write) else 0


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
