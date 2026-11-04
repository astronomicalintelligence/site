"""Turn approved contribution issues into pull requests, without a language model.

This is the automated version of tools/ISSUE_TO_PAGE.md. It runs in GitHub Actions
(.github/workflows/issue-to-page.yml) whenever a maintainer adds the `ready` label, once a day, and on demand.

For every open issue labelled `ready` (oldest first) it:

1. skips the issue if it has `in-pr`, if an open pull request says `Closes #N`, or if the branch `contrib/issue-N`
   exists; leaves `review` and `update` issues alone (updates need a person: see below);
2. reads the form answers (the `### <field label>` sections, using the labels in .github/ISSUE_TEMPLATE/) and checks
   that every required field is filled, that the licence box is ticked and that L1 comes with model, date and
   test case. If not, it comments with what is missing and swaps `ready` for `needs-info`;
3. writes the page (and SKILL.md and other files of a skill) on the branch `contrib/issue-N`, copying the text as
   written;
4. copies the images with tools/localize_images.py, runs tools/check_images.py, tools/catalog_ids.py and, unless
   --no-render, `quarto render`;
5. commits, pushes, opens the pull request with the REST API, comments on the issue and swaps `ready` for `in-pr`.

What it does not do, unlike a person or Claude following ISSUE_TO_PAGE.md:
- no editing for clarity: the text is published as the contributor wrote it;
- it does not read the issue comments: a maintainer who wants to correct something edits the issue text itself
  (the pull request says how many comments there are, so the reviewer can check);
- it cannot judge whether a proposal is contradictory or unusable: that is the maintainer's job before `ready`;
- `update` issues are left labelled `ready` for a person to handle.

    python3 tools/issue_to_page.py                    # process every ready issue
    python3 tools/issue_to_page.py --issue 21         # only this issue
    python3 tools/issue_to_page.py --dry-run          # write and commit locally; no push, no comments, no labels
    python3 tools/issue_to_page.py --no-render        # skip `quarto render`

Needs: pip install pyyaml pillow requests, and GH_TOKEN (or GITHUB_TOKEN) with contents, issues and pull-requests
write access.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "astronomicalintelligence/site")
API = "https://api.github.com"
NO_RESPONSE = "_No response_"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

FOLDERS = {"workflow": "workflows", "prompt": "prompts", "skill": "skills", "agent-config": "agent-configs",
           "model-check": "model-checks", "failure": "failures"}
TYPE_NAMES = {"workflow": "workflow", "prompt": "prompt", "skill": "skill", "agent-config": "agent config",
              "model-check": "model check", "failure": "failure"}
PHASES = {"Literature": ("Literature", "literature"), "Proposals": ("Proposals", "proposals"),
          "Data and code": ("Data and code", "code"), "Analysis": ("Analysis", "analysis"),
          "Writing": ("Writing", "writing"), "Pre-submission review": ("Pre-submission review", "review"),
          "General (any phase)": ("General", None)}
FIELDS = {"Astronomy and astrophysics": "astronomy", "Physics": "physics",
          "Earth and planetary sciences": "earth-sciences", "Chemistry": "chemistry",
          "Biology and medicine": "biology", "Computer science": "computer-science"}
ORCID = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b")
SAFE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$")
DRAFT = "::: {.callout-note}\n## Draft\nProposed content, not yet tested.\n:::\n\n"


class NeedsInfo(Exception):
    """The proposal cannot be published as it is; the message lists what is missing."""


# --------------------------------------------------------------------------- GitHub REST API

def gh(method, path, data=None, ok404=False):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    req = urllib.request.Request(path if path.startswith("http") else API + path, method=method,
                                 data=None if data is None else json.dumps(data).encode())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "astronomicalintelligence-issue-to-page")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return None
        raise RuntimeError(f"GitHub API {method} {path}: {e.code} {e.read()[:300]!r}") from None


def gh_all(path):
    out, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        items = gh("GET", f"{path}{sep}per_page=100&page={page}")
        out += items
        if len(items) < 100:
            return out
        page += 1


# --------------------------------------------------------------------------- reading the form

def load_templates():
    """{type label: [field dicts]} from the issue forms, so the parser follows the forms when they change."""
    out = {}
    for f in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or "body" not in d:
            continue
        fields = []
        for b in d["body"]:
            if b.get("type") == "markdown":
                continue
            a = b.get("attributes", {})
            required = bool(b.get("validations", {}).get("required"))
            if b["type"] == "checkboxes":
                required = any(o.get("required") for o in a.get("options", []))
            fields.append({"label": a["label"], "type": b["type"], "required": required, "render": a.get("render")})
        for label in d.get("labels", []):
            out[label] = fields
    return out


def parse_form(body, fields):
    """{label: answer}; '' for empty answers. Fields with `render` lose the code fence GitHub puts around them."""
    body = (body or "").replace("\r\n", "\n")
    found, start = [], 0
    for f in fields:                                   # headings in form order, so text in answers can't fake one
        m = re.compile(r"^### " + re.escape(f["label"]) + r"[ \t]*$", re.M).search(body, start)
        if m:
            found.append((f, m.start(), m.end()))
            start = m.end()
    values = {f["label"]: "" for f in fields}
    for i, (f, _, end) in enumerate(found):
        stop = found[i + 1][1] if i + 1 < len(found) else len(body)
        v = body[end:stop].strip()
        if v == NO_RESPONSE:
            v = ""
        elif f.get("render"):
            m = re.fullmatch(r"```[\w+-]*\n(.*?)\n?```", v, re.S)
            if m:
                v = m.group(1)
        values[f["label"]] = v
    return values


def ticked(v):
    return bool(re.search(r"^- \[[xX]\]", v, re.M))


def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_authors(text):
    """'First Last, 0000-0000-0000-0000, Institute' per line (ORCID and institute optional)."""
    authors = []
    for line in text.splitlines():
        for entry in line.split(";"):
            entry = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", entry).strip()
            if not entry:
                continue
            orcid = None
            m = ORCID.search(entry)
            if m:
                orcid = m.group(1)
                entry = re.sub(r"(?:https?://)?(?:www\.)?(?:orcid\.org/)?" + re.escape(orcid), "", entry)
            parts = [p.strip(" ()") for p in entry.split(",")]
            parts = [p for p in parts if p and p.lower() not in {"orcid", "orcid:"}]
            if not parts:
                continue
            authors.append({"name": parts[0], "orcid": orcid, "affiliation": ", ".join(parts[1:]) or None})
    return authors


def slugify(s, maxlen=50):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    out = ""
    for w in re.findall(r"[a-z0-9]+", s):
        if out and len(out) + 1 + len(w) > maxlen:
            break
        out = f"{out}-{w}" if out else w
    return out


def fence(content, lang):
    longest = max([len(m) for m in re.findall(r"`{3,}", content)], default=2)
    f = "`" * max(3, longest + 1)
    return f"{f}{lang}\n{content}\n{f}"


def other_files(text):
    """Files pasted 'one per block with its file name'. Returns ({path: content}, [problems])."""
    files, problems = {}, []
    if not text.strip():
        return files, problems
    lines = text.split("\n")
    i, prev = 0, ""
    while i < len(lines):
        m = re.match(r"^(`{3,}|~{3,})", lines[i])
        if not m:
            if lines[i].strip():
                prev = lines[i].strip()
            i += 1
            continue
        mark, j = m.group(1), i + 1
        while j < len(lines) and not lines[j].startswith(mark):
            j += 1
        content = "\n".join(lines[i + 1:j])
        name = re.sub(r"^[#>*\s-]*(?:file(?:name)?\s*:\s*)?", "", prev, flags=re.I).strip("`*_: ")
        if SAFE_PATH.match(name) and ".." not in name.split("/") and name not in {"SKILL.md", "index.qmd"} \
                and not name.startswith("figures/"):
            files[name] = content + "\n"
        else:
            problems.append(f"a block whose file name could not be read (line before it: {prev[:80]!r})")
        prev, i = "", j + 1
    if not files and not problems:
        problems.append("text without code blocks")
    return files, problems


# --------------------------------------------------------------------------- building the page

def q(s):
    return json.dumps(s, ensure_ascii=False)       # a JSON string is a valid YAML double-quoted string


def front_matter(meta, authors):
    out = ["---"]
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, list):
            out.append(f"{k}: [{', '.join(v)}]")
        elif isinstance(v, dt.date) or k in {"qflag"}:
            out.append(f"{k}: {v}")
        else:
            out.append(f"{k}: {q(v)}")
    out.append("author:")
    for a in authors:
        out.append(f"  - name: {q(a['name'])}")
        if a["orcid"]:
            out.append(f"    orcid: {a['orcid']}")
        if a["affiliation"]:
            out += ["    affiliations:", f"      - name: {q(a['affiliation'])}"]
    out.append("---")
    return "\n".join(out) + "\n\n"


def sections(pairs):
    return "".join(f"## {h}\n\n{t.strip()}\n\n" for h, t in pairs)


def build(kind, issue, v, today):
    """Returns (files {relative path: text}, page path, title, notes for the pull request). Raises NeedsInfo."""
    missing, notes = [], []
    title = re.sub(r"^\s*\[[^\]]*\]\s*", "", issue["title"]).strip()
    if not title:
        missing.append("a title (after the `[Type]` prefix)")
    authors = parse_authors(v.get("Authors to credit", ""))
    if not authors:
        missing.append("**Authors to credit**")
    for label, val in v.items():
        f = next(f for f in TEMPLATES[kind] if f["label"] == label)
        if f["type"] == "checkboxes":
            if f["required"] and not ticked(val):
                missing.append(f"the **{label}** box ticked")
        elif f["required"] and not val.strip() and label != "Authors to credit":
            missing.append(f"**{label}**")

    description = " ".join(v.get("What it does, in one sentence", v.get("What went wrong, in one sentence", "")).split())
    field = FIELDS.get(v.get("Field", ""))
    model, tool = v.get("Model and version", "").strip(), v.get("Tool or interface", "").strip()
    test_case = v.get("Test case", "").strip()
    known = v.get("Known failures", "").strip() or "None known yet."
    names = ", ".join(a["name"] for a in authors)

    qflag, tested = "L0", None
    if kind not in {"model-check", "failure"}:
        if v.get("Verification level", "").startswith("L1"):
            qflag = "L1"
            need = [lab for lab, val in (("Model and version", model), ("Date of your test", v.get("Date of your test", "")),
                                         ("Test case", test_case)) if not val.strip()]
            if need:
                missing.append("for L1, also " + ", ".join(f"**{n}**" for n in need)
                               + " (or choose L0 if it has not been tested yet)")
        raw_date = v.get("Date of your test", "").strip()
        if raw_date:
            tested = parse_date(raw_date)
            if tested is None:
                missing.append(f"**Date of your test** as YYYY-MM-DD (it says {raw_date!r})")
            elif tested > today:
                missing.append(f"a **Date of your test** that is not in the future (it says {raw_date})")

    files, page = {}, None
    if kind == "skill":
        skill = v.get("SKILL.md", "")
        name = None
        m = re.match(r"^---\n(.*?)\n---", skill, re.S)
        try:
            name = (yaml.safe_load(m.group(1)) or {}).get("name") if m else None
        except yaml.YAMLError:
            pass
        if skill and not (isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", name)):
            missing.append("a `name` in the front matter of **SKILL.md** (lowercase letters, digits and hyphens), "
                           "between `---` lines at the top")
        extra, problems = other_files(v.get("Other files", ""))
        if problems:
            missing.append("**Other files** as one code block per file, each preceded by a line with its file name ("
                           + "; ".join(problems) + ")")
        slug = name or slugify(title)
        page = f"skills/{slug}/index.qmd"
        files[f"skills/{slug}/SKILL.md"] = skill + "\n"
        for p, c in extra.items():
            files[f"skills/{slug}/{p}"] = c
    else:
        slug = slugify(title) or f"issue-{issue['number']}"
        page = f"{FOLDERS[kind]}/{slug}.qmd"

    if missing:
        raise NeedsInfo(missing)

    if on_main(str(Path(page).parent) if kind == "skill" else page):
        if kind == "skill":
            raise NeedsInfo([f"a different skill `name`: a skill called `{slug}` already exists"])
        slug = f"{slug}-{issue['number']}"
        page = f"{FOLDERS[kind]}/{slug}.qmd"
        notes.append(f"A page with the same name already exists, so this one is `{page}`.")

    check = v.get("How to check the result", "").strip()
    if test_case:
        check = f"**Tested on:** {test_case}\n\n{check}"
    history = f"## History\n\n- {today}: first version ({qflag}), {names}.\n"

    if kind == "failure":
        meta = {"title": title, "description": description, "date": today,
                "categories": [slugify(v.get("Kind of error", "")) or "other"]}
        seen = "Seen with " + model + (f" in {tool}" if tool else "") \
               + (f", {v['When it happened'].strip()}" if v.get("When it happened", "").strip() else "") + "."
        prompt = v.get("Prompt", "")
        cases = ("Prompt used:\n\n" + fence(prompt, "text")) if prompt.strip() else "To be added: more dated examples."
        body = sections([("What happens", v["What happened"].strip() + "\n\n" + seen),
                         ("How to catch it", v["How you caught it"]),
                         ("How to prevent it", v["How to prevent it"]),
                         ("Cases", cases)])
        history = f"## History\n\n- {today}: first version, {names}.\n"
    elif kind == "model-check":
        meta = {"title": title, "description": description, "categories": [field] if field else None, "date": today}
        body = sections([("Task", v["Task"]), ("Prompt", fence(v["Prompt"], "text")),
                         ("Expected answer and pass rule", v["Expected answer and pass rule"]),
                         ("Results", v.get("Results", "").strip() or "No results yet.")])
        history = f"## History\n\n- {today}: first version, {names}.\n"
    else:
        phase, phase_cat = PHASES.get(v["Research phase"], (v["Research phase"], None))
        meta = {"title": title}
        if kind == "skill":
            meta["resources"] = ["SKILL.md"] + sorted(p.split(f"skills/{slug}/", 1)[1] for p in files
                                                       if not p.endswith("/SKILL.md"))
        meta.update({"description": description, "categories": [c for c in (phase_cat, field) if c] or None,
                     "phase": phase, "model": model or "to be tested", "tool": tool or None,
                     "tested": tested if tested else "not yet", "qflag": qflag})
        if kind == "workflow":
            meta["time-saved"] = v.get("Time saved (measured)", "").strip() or None
        meta["date"] = today
        if kind == "workflow":
            pairs = [("Goal", v["Goal"]), ("What you need", v.get("What you need", "").strip() or "Not specified."),
                     ("Steps", v["Steps"])]
        elif kind == "prompt":
            pairs = [("Prompt", fence(v["Prompt"], "text")),
                     ("Example", v.get("Example", "").strip() or "To be added.")]
        elif kind == "skill":
            pairs = [("What it does", v["What changes when the agent loads it"]),
                     ("SKILL.md", f'[Download SKILL.md](SKILL.md){{download="SKILL.md"}} and put it in a folder '
                                  f'`{slug}` in your agent\'s skills directory.\n\n'
                                  '```{.markdown include="SKILL.md"}\n```')]
        else:  # agent-config
            pairs = [("What it is for", v["What kind of project it is for"]),
                     ("The file to copy", fence(v["The file to copy"], "markdown"))]
        pairs += [("How to check the result", check), ("Known failures", known)]
        body = (DRAFT if qflag == "L0" else "") + sections(pairs)

    files[page] = front_matter(meta, authors) + body + history
    return files, page, title, notes, authors


# --------------------------------------------------------------------------- git and the pull request

def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def git(*args, check=True):
    return run(["git", *args], check=check)


def on_main(path):
    return git("cat-file", "-e", f"origin/main:{path}", check=False).returncode == 0


def comment(n, text, dry):
    if dry:
        print(f"  [dry-run] comment on #{n}:\n" + "\n".join("    " + l for l in text.splitlines()))
    else:
        gh("POST", f"/repos/{REPO}/issues/{n}/comments", {"body": text})


def relabel(n, remove, add, dry):
    if dry:
        print(f"  [dry-run] #{n}: remove {remove}, add {add}")
        return
    gh("DELETE", f"/repos/{REPO}/issues/{n}/labels/{remove}", ok404=True)
    gh("POST", f"/repos/{REPO}/issues/{n}/labels", {"labels": [add]})


def process(issue, open_prs, args, today):
    n, labels = issue["number"], {l["name"] for l in issue["labels"]}
    branch = f"contrib/issue-{n}"
    kinds = [k for k in FOLDERS if k in labels]
    if "review" in labels:
        return "skipped: paper review suggestion, no page to make"
    if "update" in labels:
        return "skipped: updates are made by hand (see tools/ISSUE_TO_PAGE.md)"
    if len(kinds) != 1:
        return f"skipped: needs exactly one type label, has {sorted(labels)}"
    if not args.force:
        if "in-pr" in labels:
            return "skipped: already in-pr"
        if any(re.search(rf"(?i)\b(?:closes|fixes|resolves)\s+#{n}\b", pr.get("body") or "") for pr in open_prs):
            return "skipped: an open pull request already closes it"
        if gh("GET", f"/repos/{REPO}/branches/{branch}", ok404=True):
            return f"skipped: branch {branch} exists"
    kind = kinds[0]

    try:
        files, page, title, notes, authors = build(kind, issue, parse_form(issue["body"], TEMPLATES[kind]), today)
    except NeedsInfo as e:
        comment(n, "Thank you for the proposal! It cannot be published yet because it is missing:\n\n"
                + "\n".join(f"- {m}" for m in e.args[0])
                + "\n\nPlease edit the issue (the `···` menu at the top right, then *Edit*). "
                  "A maintainer will then label it `ready` again.", args.dry_run)
        relabel(n, "ready", "needs-info", args.dry_run)
        return "needs-info: " + "; ".join(re.sub(r"\*\*", "", m) for m in e.args[0])

    git("checkout", "-q", "-B", branch, "origin/main")
    try:
        for p, text in files.items():
            (ROOT / p).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / p).write_text(text, encoding="utf-8")
        img = run([sys.executable, "tools/localize_images.py", page], check=False)
        missing = [l.split(": ", 1)[1] for l in img.stdout.splitlines() if l.startswith("MISSING")]
        no_alt = [l.split(": ", 1)[1] for l in img.stdout.splitlines() if l.startswith("NEEDS ALT TEXT")]
        run([sys.executable, "tools/check_images.py"])
        run([sys.executable, "tools/catalog_ids.py", "--base", "origin/main"])
        if not args.no_render:
            run(["quarto", "render"])
        git("add", "--", str(Path(page).parent if kind == "skill" else page),
            *([str(Path(page).parent / "figures")] if (ROOT / Path(page).parent / "figures").exists() else []))
        type_name = TYPE_NAMES[kind]
        git("-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}", "commit", "-q",
            "-m", f"Add {type_name}: {title} (closes #{n})")

        comments = [c for c in gh_all(f"/repos/{REPO}/issues/{n}/comments") if c["user"]["type"] != "Bot"] \
            if issue.get("comments") else []
        lines = [f"Closes #{n}", "",
                 f"Adds the {type_name} **{title}** from #{n}, written by `tools/issue_to_page.py`.", "",
                 "Files:", *[f"- `{p}`" for p in files], "",
                 "Authors as read from the form (please check): "
                 + "; ".join(a["name"] + (f" ({a['orcid']})" if a["orcid"] else "")
                             + (f", {a['affiliation']}" if a["affiliation"] else "") for a in authors), "",
                 "The text is copied as the contributor wrote it, without editing for clarity."]
        lines += [f"- {x}" for x in notes]
        if comments:
            lines.append(f"- The issue has {len(comments)} comment(s) that the script does not read: "
                         "check them for corrections.")
        if missing:
            lines += ["", "**MISSING images** (add by hand where the page says `<!-- MISSING image ... -->`):", *[f"- {m}" for m in missing]]
        if no_alt:
            lines += ["", "**NEEDS ALT TEXT:**", *[f"- `{a}`" for a in no_alt]]
        lines += ["", "Checks: `check_images.py` and `catalog_ids.py --base origin/main` pass"
                  + ("." if args.no_render else ", `quarto render` succeeds.")]
        pr_body = "\n".join(lines) + "\n"

        if args.dry_run:
            print(f"  [dry-run] committed on local branch {branch}; pull request body:\n"
                  + "\n".join("    " + l for l in pr_body.splitlines()))
            return f"dry-run: branch {branch} ready locally"
        git("push", "-q", "origin", branch)
        pr = gh("POST", f"/repos/{REPO}/pulls", {"title": f"Add {type_name}: {title}", "head": branch,
                                                  "base": "main", "body": pr_body})
        text = f"Thank you! This proposal is now pull request #{pr['number']}: {pr['html_url']}"
        if missing:
            text += ("\n\nThese images could not be copied and must be added by hand:\n"
                     + "\n".join(f"- {m}" for m in missing))
        comment(n, text, False)
        relabel(n, "ready", "in-pr", False)
        return f"pull request opened: {pr['html_url']}"
    finally:
        git("checkout", "-q", "-f", START_BRANCH)
        git("clean", "-q", "-fd", "--", "workflows", "prompts", "skills", "agent-configs", "model-checks",
            "failures", check=False)
        if not args.dry_run:
            git("branch", "-q", "-D", branch, check=False)


def main():
    global TEMPLATES
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--issue", type=int, help="process only this issue (it must still be open and labelled ready)")
    ap.add_argument("--dry-run", action="store_true", help="commit locally only; no push, no comments, no labels")
    ap.add_argument("--no-render", action="store_true", help="skip quarto render")
    ap.add_argument("--force", action="store_true", help="with --dry-run: ignore in-pr, open pull requests and "
                                                         "branches (to test on an issue already handled)")
    args = ap.parse_args()
    if args.force and not args.dry_run:
        ap.error("--force only with --dry-run")
    TEMPLATES = load_templates()
    today = dt.datetime.now(dt.timezone.utc).date()

    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        sys.exit("the working tree has uncommitted changes")
    git("fetch", "-q", "origin", "main")
    global START_BRANCH
    START_BRANCH = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    if args.issue:
        issue = gh("GET", f"/repos/{REPO}/issues/{args.issue}")
        ok = issue["state"] == "open" and "pull_request" not in issue and \
            ("ready" in {l["name"] for l in issue["labels"]} or args.force)
        issues = [issue] if ok else []
    else:
        issues = [i for i in gh_all(f"/repos/{REPO}/issues?labels=ready&state=open&sort=created&direction=asc")
                  if "pull_request" not in i]
    if not issues:
        print("No open issues labelled ready.")
        return 0
    open_prs = gh_all(f"/repos/{REPO}/pulls?state=open")

    report, failed = [], False
    for issue in issues:
        print(f"#{issue['number']} {issue['title']}")
        try:
            result = process(issue, open_prs, args, today)
        except Exception as e:                       # one bad issue must not stop the others
            failed, result = True, f"FAILED, nothing published: {e}"
        print(f"  {result}")
        report.append(f"- #{issue['number']} {issue['title']}: {result}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Ready issues\n\n" + "\n".join(report) + "\n")
    return 1 if failed else 0


TEMPLATES = {}
START_BRANCH = "main"

if __name__ == "__main__":
    sys.exit(main())
