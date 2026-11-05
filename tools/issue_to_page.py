"""Turn approved contribution issues into pull requests, without a language model.

This is the automated version of tools/ISSUE_TO_PAGE.md. It runs in GitHub Actions
(.github/workflows/issue-to-page.yml) whenever a maintainer adds the `ready` label, once a day, and on demand.

For every open issue labelled `ready` (oldest first) it:

1. skips the issue if it has `in-pr`, if an open pull request says `Closes #N`, or if the branch `contrib/issue-N`
   exists; leaves `review` and `update` issues alone (updates need a person: see below);
2. reads the form answers (the `### <field label>` sections, using the labels in .github/ISSUE_TEMPLATE/) and checks
   that every required field is filled. If not, it comments with what is missing and swaps `ready` for `needs-info`.
   The verification level follows "How you tested it": empty is L0 (draft), filled is L1, with the model, tool and
   date read from its first words ("Claude Opus 5.5 in claude.ai, 2026-11-03: ..."). Each author line is "name,
   affiliation, ORCID, @username" (only the name is needed); an @username links the author to that GitHub profile;
3. writes the page (and SKILL.md and the other files of a skill, pasted or from a .zip of the folder) in a new folder `<type>/AI<letter>XXXX-<name>/` on the
   branch `contrib/issue-N`, copying the text as written; XXXX becomes the catalogue number when the pull request is
   merged (tools/catalog_ids.py). Text that Quarto would run or treat as page settings (```{python} blocks,
   shortcodes, `---` lines, <script>) sends the issue to needs-info;
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
import io
import zipfile
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
LETTERS = {"workflow": "W", "prompt": "P", "skill": "S", "agent-config": "A", "model-check": "M", "failure": "F"}
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
HANDLE = re.compile(r"(?:^|[\s,(])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\b")
AUTHORS = "Authors"
TESTED = "How you tested it"
FILES = "Skill folder as a .zip, or other files"
ZIP_URL = re.compile(r"https://github\.com/user-attachments/files/\d+/[^\s)\]\"'>]+\.zip")
for _extra in filter(None, os.environ.get("ZIP_TEST_PREFIXES", "").split(",")):     # for tests only
    ZIP_URL = re.compile(ZIP_URL.pattern + "|" + re.escape(_extra) + r"[^\s)\]\"'>]+\.zip")
ZIP_MAX_FILES, ZIP_MAX_BYTES = 50, 5 * 1024 * 1024
# what the first words of "How you tested it" must look like to be taken as the model
MODEL_NAME = re.compile(r"(?i)\b(?:claude|opus|sonnet|haiku|fable|mythos|gpt|chatgpt|o\d|gemini|gemma|llama|mistral|"
                        r"mixtral|deepseek|qwen|grok|copilot|phi|command|kimi|glm)\b")
# file names of a skill's other files: no hidden or _quarto/_metadata files, nothing Quarto would render or run
SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)*$")
UNSAFE_EXT = {".qmd", ".ipynb", ".rmd", ".lua", ".yml", ".yaml", ".html", ".htm", ".js", ".css", ".scss"}
# constructs that Quarto would run or treat as page settings when they appear in the text of a field
UNSAFE_TEXT = [
    (re.compile(r"^\s*(`{3,}|~{3,})\s*\{\s*[A-Za-z]", re.M), "an executable code block (a fence like ```{python})"),
    (re.compile(r"\{\{<"), "a Quarto shortcode ({{< ... >}})"),
    (re.compile(r"^---\s*$", re.M), "a line with only `---` (it would start a block of page settings)"),
    (re.compile(r"\{=(?:html|latex|tex|openxml|typst)\}"), "a raw output block ({=html})"),
    (re.compile(r"<\s*(?:script|iframe|style|object|embed|form|link|meta)\b", re.I), "HTML that runs or loads code"),
]
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


def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_authors(text):
    """'First Last, 0000-0000-0000-0000, Institute, @username' per line (all but the name optional)."""
    authors = []
    for line in text.splitlines():
        for entry in line.split(";"):
            entry = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", entry).strip()
            if not entry:
                continue
            login = None
            h = HANDLE.search(entry)
            if h:
                login = h.group(1)
                entry = entry[:h.start()] + entry[h.end():]
            orcid = None
            m = ORCID.search(entry)
            if m:
                orcid = m.group(1)
                entry = re.sub(r"(?:https?://)?(?:www\.)?(?:orcid\.org/)?" + re.escape(orcid), "", entry)
            parts = [p.strip(" ()") for p in entry.split(",")]
            parts = [p for p in parts if p and p.lower() not in {"orcid", "orcid:"}]
            if not parts:
                continue
            authors.append({"name": parts[0], "orcid": orcid, "affiliation": ", ".join(parts[1:]) or None,
                            "url": f"https://github.com/{login}" if login else None})
    return authors


def test_info(text, issue, today):
    """(model, tool, date, problem) read from the first words of 'How you tested it'."""
    text = " ".join(text.split())
    date, problem = None, None
    m = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2})\b", text) or \
        re.search(r"\b(\d{1,2} [A-Z][a-z]{2,8} \d{4}|[A-Z][a-z]{2,8} \d{1,2},? \d{4})\b", text)
    if m:
        date = parse_date(m.group(1).replace(",", ""))
    if date is None:
        date = dt.date.fromisoformat(issue["created_at"][:10])
        problem = f"The test has no readable date, so the date of the issue ({date}) is used."
    elif date > today:
        raise NeedsInfo([f"a date in **{TESTED}** that is not in the future (it says {m.group(1)})"])
    head = re.split(r"[,;:(]|\s(?:on|with|using)\s|\s\d{4}[-/]|\s\d{1,2} [A-Z][a-z]+ \d{4}", text, maxsplit=1)[0].strip()
    model, tool = head, None
    if " in " in head:
        model, tool = (x.strip() for x in head.split(" in ", 1))
    if not (2 <= len(model) <= 60 and MODEL_NAME.search(model)):
        model = "see How to check the result"
        problem = ((problem + " ") if problem else "") + "The model could not be read from the first words of the test."
    if tool is not None and not (1 <= len(tool) <= 40):
        tool = None
    return model, tool, date, problem


def skill_zip(text):
    """Files of a skill from a .zip attachment: ({path: text}, [problems]), or (None, []) if there is no .zip."""
    m = ZIP_URL.search(text)
    if not m:
        return None, []
    import requests                                  # only needed for skills sent as a .zip
    headers = {"User-Agent": "astronomicalintelligence-issue-to-page"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and m.group(0).startswith("https://github.com/"):
        headers["Authorization"] = f"token {token}"
    try:
        r = requests.get(m.group(0), headers=headers, timeout=60)
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except Exception as e:                            # network, not a zip ...
        return {}, [f"the .zip could not be opened ({e})"]
    infos = [i for i in zf.infolist() if not i.is_dir()
             and not any(part.startswith((".", "__MACOSX")) for part in i.filename.split("/"))]
    names = [i.filename for i in infos]
    # a single top folder (my-skill/SKILL.md) is the skill folder itself
    tops = {n.split("/")[0] for n in names}
    strip = len(tops) == 1 and all("/" in n for n in names)
    files, problems, total = {}, [], 0
    if len(infos) > ZIP_MAX_FILES:
        return {}, [f"the .zip has {len(infos)} files; at most {ZIP_MAX_FILES} are accepted"]
    for i in infos:
        name = i.filename.split("/", 1)[1] if strip else i.filename
        total += i.file_size
        is_link = (i.external_attr >> 16) & 0o170000 == 0o120000
        if is_link or not SAFE_PATH.match(name) or ".." in name.split("/") or Path(name).suffix.lower() in UNSAFE_EXT \
                or re.match(r"figure-\d+\.", name):
            problems.append(f"`{name}` is not accepted (links, hidden files, .qmd, .lua, .yml, .html, .js and names "
                            "starting with _ are not)")
            continue
        if total > ZIP_MAX_BYTES:
            return {}, ["the files in the .zip are larger than 5 MB in total"]
        try:
            files[name] = zf.read(i).decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"`{name}` is not a text file")
    return files, problems


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
        if SAFE_PATH.match(name) and ".." not in name.split("/") and name != "SKILL.md" \
                and Path(name).suffix.lower() not in UNSAFE_EXT and not re.match(r"figure-\d+\.", name):
            files[name] = content + "\n"
        else:
            problems.append(f"a block whose file name could not be read or is not allowed (line before it: {prev[:80]!r}; "
                            "names are like scripts/beam_area.py; .qmd, .lua, .yml, .html, .js and names starting "
                            "with _ or . are not accepted)")
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
        if a.get("url"):
            out.append(f"    url: {a['url']}")
        if a["orcid"]:
            out.append(f"    orcid: {a['orcid']}")
        if a["affiliation"]:
            out += ["    affiliations:", f"      - name: {q(a['affiliation'])}"]
    out.append("---")
    return "\n".join(out) + "\n\n"


def sections(pairs):
    return "".join(f"## {h}\n\n{t.strip()}\n\n" for h, t in pairs)


def build(kind, issue, v, today):
    """Returns (files {relative path: text}, page path, title, notes for the pull request, authors). Raises NeedsInfo."""
    missing, notes = [], []
    title = re.sub(r"^\s*\[[^\]]*\]\s*", "", issue["title"]).strip()
    if not title:
        missing.append("a title (after the `[Type]` prefix)")
    for f in TEMPLATES[kind]:
        if f["required"] and not v.get(f["label"], "").strip():
            missing.append(f"**{f['label']}**")
    authors = parse_authors(v.get(AUTHORS, ""))       # only an @username links an author to a GitHub profile
    if v.get(AUTHORS, "").strip() and not authors:
        missing.append(f"**{AUTHORS}** as one line per author: name, affiliation, ORCID, @username")

    description = " ".join(v.get("What it does, in one sentence", v.get("What it does, and for which projects",
                            v.get("What it checks, in one sentence", v.get("What went wrong, in one sentence", "")))).split())
    test = v.get(TESTED, "").strip()
    known = v.get("Known failures", "").strip() or "None known yet."
    names = ", ".join(a["name"] for a in authors)

    qflag, model, tool, tested = "L0", None, None, None
    if kind not in {"model-check", "failure"} and test:
        qflag = "L1"
        try:
            model, tool, tested, problem = test_info(test, issue, today)
            if problem:
                notes.append(problem + " Please check the page header.")
        except NeedsInfo as e:
            missing += e.args[0]

    files, page, extra = {}, None, {}
    if kind == "skill":
        skill = v.get("SKILL.md", "").strip()
        zipped, zproblems = skill_zip(v.get(FILES, ""))
        if zproblems:
            notes += [f"Not copied from the .zip: {x}" for x in zproblems if "not accepted" in x or "not a text" in x]
            fatal = [x for x in zproblems if not ("not accepted" in x or "not a text" in x)]
            if fatal:
                missing.append(f"**{FILES}**: " + "; ".join(fatal))
        if zipped is not None:
            zskill = zipped.pop("SKILL.md", None)
            if skill and zskill and zskill.strip() != skill:
                notes.append("SKILL.md was both pasted and in the .zip, and they differ: the pasted one is used.")
            skill = skill or (zskill or "").strip()
            extra = zipped
        else:
            extra, problems = other_files(v.get(FILES, ""))
            if problems:
                missing.append(f"**{FILES}**: a .zip, or one code block per file, each preceded by a line with its "
                               "file name (" + "; ".join(problems) + ")")
        if not skill:
            missing.append("**SKILL.md**: paste it, or drop a .zip of the skill folder")
        name = None
        m = re.match(r"^---\n(.*?)\n---", skill, re.S)
        try:
            name = (yaml.safe_load(m.group(1)) or {}).get("name") if m else None
        except yaml.YAMLError:
            pass
        if skill and not (isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", name)):
            missing.append("a `name` in the front matter of **SKILL.md** (lowercase letters, digits and hyphens), "
                           "between `---` lines at the top")
        slug = name or slugify(title)
    else:
        slug = slugify(title) or f"issue-{issue['number']}"

    for f in TEMPLATES[kind]:                         # prompts and files are shown as code; the rest is page text
        if f["type"] in {"textarea", "input"} and not f.get("render") and f["label"] != FILES:
            for pat, what in UNSAFE_TEXT:
                if pat.search(v.get(f["label"], "")):
                    missing.append(f"**{f['label']}** without {what}")
    if missing:
        raise NeedsInfo(missing)

    if slug_taken(FOLDERS[kind], slug):
        if kind == "skill":
            raise NeedsInfo([f"a different skill `name`: a skill called `{slug}` already exists"])
        slug = f"{slug}-{issue['number']}"
        notes.append(f"A {TYPE_NAMES[kind]} with the same name already exists, so this one is called `{slug}`.")
    # the number is given when the pull request is merged (tools/catalog_ids.py renames the folder)
    folder = f"{FOLDERS[kind]}/AI{LETTERS[kind]}XXXX-{slug}"
    page = f"{folder}/index.qmd"
    if kind == "skill":
        files[f"{folder}/SKILL.md"] = skill + "\n"
        for p, c in extra.items():
            files[f"{folder}/{p}"] = c if c.endswith("\n") else c + "\n"

    check = v.get("How to check the result", "").strip()
    if test:
        check = f"**Tested on:** {test}\n\n{check}"
    history = f"## History\n\n- {today}: first version ({qflag}), {names}.\n"

    if kind == "failure":
        kind_cat = slugify(v.get("Kind of error", ""))
        meta = {"title": title, "description": description, "date": today,
                "categories": [kind_cat] if kind_cat else None}
        body = sections([("What happens", v["What happened"]),
                         ("How to catch or avoid it", v["How to catch or avoid it"]),
                         ("Cases", "To be added: more dated examples.")])
        history = f"## History\n\n- {today}: first version, {names}.\n"
    elif kind == "model-check":
        meta = {"title": title, "description": description, "date": today}
        body = sections([("Task", description), ("Prompt", fence(v["Prompt"], "markdown")),
                         ("Expected answer and pass rule", v["Expected answer and pass rule"]),
                         ("Results", v.get("Results", "").strip() or "No results yet.")])
        history = f"## History\n\n- {today}: first version, {names}.\n"
    else:
        phase, phase_cat = PHASES.get(v.get("Research phase", ""), ("General", None))
        meta = {"title": title}
        if kind == "skill":
            meta["resources"] = ["SKILL.md"] + sorted(p.split(f"{folder}/", 1)[1] for p in files
                                                       if not p.endswith("/SKILL.md"))
        meta.update({"description": description, "categories": [phase_cat] if phase_cat else None,
                     "phase": phase, "model": model or "to be tested", "tool": tool,
                     "tested": tested if tested else "not yet", "qflag": qflag, "date": today})
        if kind == "workflow":
            pairs = [("Goal", description), ("Steps", v["Steps"])]
        elif kind == "prompt":
            pairs = [("Prompt", fence(v["Prompt"], "markdown")),
                     ("Example", v.get("Example", "").strip() or "To be added.")]
        elif kind == "skill":
            pairs = [("What it does", description),
                     ("SKILL.md", f'[Download SKILL.md](SKILL.md){{download="SKILL.md"}} and put it in a folder '
                                  f'`{slug}` in your agent\'s skills directory'
                                  + (", with the other files listed in this page's folder." if extra else ".")
                                  + '\n\n```{.markdown include="SKILL.md"}\n```')]
        else:  # agent-config
            pairs = [("What it is for", description),
                     ("The file to copy", fence(v["The file to copy"], "markdown"))]
        pairs += [("How to check the result", check), ("Known failures", known)]
        body = (DRAFT if qflag == "L0" else "") + sections(pairs)

    files[page] = front_matter(meta, authors) + body + history
    return files, page, title, notes, authors


# --------------------------------------------------------------------------- git and the pull request

def run(cmd, check=True, env=None):
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def git(*args, check=True):
    return run(["git", *args], check=check)


def slug_taken(section, slug):
    """True if main already has a contribution of this type with this short name (AIP0001-<slug>)."""
    names = git("ls-tree", "-d", "--name-only", "origin/main", f"{section}/", check=False).stdout.split()
    return any(re.fullmatch(r"AI[A-Z](?:\d{4}|XXXX)-" + re.escape(slug), n.split("/")[-1]) for n in names)


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
        if not args.no_render:                        # contributor text is rendered: no tokens in its environment
            run(["quarto", "render"], env={k: v for k, v in os.environ.items()
                                           if not re.search(r"TOKEN|SECRET|KEY|PASSWORD", k, re.I)})
        git("add", "--", str(Path(page).parent))
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
                             + (f", {a['affiliation']}" if a["affiliation"] else "")
                             + (f", {a['url']}" if a.get("url") else "") for a in authors), "",
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
    if git("status", "--porcelain", "--", *FOLDERS.values()).stdout.strip():   # they would be cleaned at the end
        sys.exit("the contribution folders have untracked files: commit, move or delete them first")
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
