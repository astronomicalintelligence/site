#!/usr/bin/env python3
"""Heuristic linter for A&A (aa.cls) LaTeX manuscripts.

Usage: python3 check_aa.py paper.tex [more.tex ...]
Prints  file:line: [rule] message  for each hit, then a summary. Exit 0 always:
hits are candidates for review, not proven errors. Stdlib only.
"""
import re
import sys
from collections import Counter

HITS = []


def hit(fn, line, rule, msg):
    HITS.append((fn, line, rule, msg))


def strip_comments(text):
    # remove % comments (not \%), keep line structure
    return "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in text.split("\n"))


def lineno(text, pos):
    return text.count("\n", 0, pos) + 1


def brace_groups(text, pos, n):
    """Return up to n consecutive {...} groups starting at pos (skipping whitespace)."""
    groups = []
    i = pos
    while len(groups) < n:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text) or text[i] != "{":
            break
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{" and text[j - 1] != "\\":
                depth += 1
            elif text[j] == "}" and text[j - 1] != "\\":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        groups.append(text[i + 1:j])
        i = j + 1
    return groups


def words(s):
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", s)
    s = re.sub(r"\$[^$]*\$", " X ", s)
    return re.findall(r"[A-Za-z0-9][\w\-']*", s)


# (regex, rule, message) applied to running text, line by line
LINE_RULES = [
    (r"(?<![.!?]\s)(?<!^)\b(Figure|Figures)\s*~?\s*\\ref", "xref", "mid-sentence 'Figure' -> 'Fig.' (A&A); spell out only at sentence start"),
    (r"\bFig(s?)\s*~?\s*\\ref", "xref", "use 'Fig.~\\ref' (with period and ~)"),
    (r"(?<![.!?]\s)(?<!^)\b(Section|Sections)\s*~?\s*\\ref", "xref", "mid-sentence 'Section' -> 'Sect.' (A&A)"),
    (r"\b(Sec\.|Secs\.)~?\\ref", "xref", "A&A abbreviation is 'Sect.' not 'Sec.'"),
    (r"\bTab\.\s*~?\\ref", "xref", "'Table' is never abbreviated in A&A"),
    (r"\b(App\.|Appx\.)\s*~?\\ref", "xref", "'Appendix' is never abbreviated"),
    (r"\b(Eq\.|Eqs\.|Equation)\s*~?\\ref", "xref", "write equations as 'Eq.~(\\ref{..})' or use \\eqref"),
    (r"[^~(\s{]\s+\\(ref|eqref)\{", "tilde", "use a non-breaking space '~' before \\ref"),
    (r"\\cite\{", "cite", "plain \\cite: use \\citet (textual) or \\citep (parenthetical)"),
    (r"\b[A-Z][a-z]+ et al\.?,? \(?(19|20)\d\d", "cite", "hand-typed citation; use \\citet/\\citep"),
    (r"\\(textit|emph|it)\s*\{?\s*et al", "cite", "'et al.' is upright in A&A"),
    (r"\bet al(?!\.)", "cite", "'et al.' needs a period"),
    (r"\bkm/s\b|\bkms\^?-1|\bkm s-1\b", "units", "write $\\mathrm{km\\,s^{-1}}$"),
    (r"\d(GHz|MHz|kHz|Hz|mJy|Jy|kpc|Mpc|pc|keV|arcsec|arcmin|deg)\b", "units", "thin space between number and unit: 1.4\\,GHz"),
    (r"\$[^$]*_\{?(?!\\)[a-zA-Z]{2,}[^$]*\$", "units", "word subscript should be upright: _\\mathrm{...} (check)"),
    (r"\bdata (is|was|has|shows|suggests)\b", "lang", "'data' is plural"),
    (r"(^|[.!?]\s+)(This|These|It) (is|are|was|were|shows?|means|suggests?|implies|indicates?)\b", "lang", "vague 'This/It' as subject: name the thing"),
    (r"\b(very|clearly|obviously|extremely|quite|really|basically|interestingly)\b", "lang", "weak/intensifying adverb: consider removing"),
    (r"\b(look into|talk about|go on|find out|figure out|come up with|carry out)\b", "lang", "phrasal verb: prefer a formal verb"),
    (r"(?i)(more|further|additional) (work|research|studies|observations) (is|are) (needed|required)", "concl", "bland ending; say which work, and what it would test"),
    (r"\b(TODO|FIXME|XXX)\b|\?\?", "todo", "unresolved marker"),
    (r"\\includegraphics(\[[^\]]*\])?\{[^}]*\.(jpe?g|png|gif)\}", "fig", "raster figure: use vector PDF when possible"),
    (r"width\s*=\s*0?\.\d+\\(linewidth|columnwidth)", "fig", "A&A style: width=\\hsize or \\resizebox{\\hsize}{!}{..}"),
]

SPELL_PAIRS = [("colour", "color"), ("behaviour", "behavior"), ("analyse", "analyze"),
               ("centre", "center"), ("modelling", "modeling"), ("favour", "favor"),
               ("normalis", "normaliz"), ("characteris", "characteriz")]


def check_file(fn):
    raw = open(fn, encoding="utf-8", errors="replace").read()
    t = strip_comments(raw)
    lines = t.split("\n")

    # ---------- document-level checks ----------
    m = re.search(r"\\documentclass(\[[^\]]*\])?\{([^}]*)\}", t)
    if m and m.group(2) != "aa":
        hit(fn, lineno(t, m.start()), "class", f"documentclass is '{m.group(2)}', A&A needs 'aa'")
    is_main = bool(m)

    m = re.search(r"\\title\s*", t)
    if m:
        title = brace_groups(t, m.end(), 1)
        if title:
            tw = words(title[0])
            if len(tw) > 15:
                hit(fn, lineno(t, m.start()), "title", f"title has {len(tw)} words (aim <~15)")
            if tw and tw[0].lower() in ("on", "towards", "toward"):
                hit(fn, lineno(t, m.start()), "title", "title starts with 'On'/'Towards': state what was done/found")
            acr = [w for w in tw if re.fullmatch(r"[A-Z]{2,}[0-9]*", w)]
            if acr:
                hit(fn, lineno(t, m.start()), "title", f"abbreviations in title: {', '.join(acr)} (ok if universally known, e.g. LOFAR)")

    m = re.search(r"\\abstract\s*", t)
    if m:
        g = brace_groups(t, m.end(), 6)
        ln = lineno(t, m.start())
        if len(g) == 1:
            hit(fn, ln, "abstract", "unstructured abstract: allowed, but A&A encourages \\abstract{context}{aims}{methods}{results}{conclusions}")
        elif len(g) != 5:
            hit(fn, ln, "abstract", f"\\abstract has {len(g)} groups: expected 5 (leave unused Context/Conclusions as {{}})")
        else:
            for name, part in zip(("Aims", "Methods", "Results"), g[1:4]):
                if not part.strip():
                    hit(fn, ln, "abstract", f"{name} paragraph is empty: Aims, Methods, Results are mandatory")
        nw = sum(len(words(x)) for x in g)
        if nw > 300:
            hit(fn, ln, "abstract", f"abstract is {nw} words: long, consider tightening")
        ab = "".join(g)
        if re.search(r"\\cite", ab):
            hit(fn, ln, "abstract", "citation inside abstract")
        if len(g) == 5 and not re.search(r"\d", g[3]):
            hit(fn, ln, "abstract", "Results part has no numbers: give key quantitative findings")
    elif is_main:
        hit(fn, 1, "abstract", "no \\abstract found")

    m = re.search(r"\\keywords\s*", t)
    if m:
        k = brace_groups(t, m.end(), 1)
        if k:
            nk = len([x for x in k[0].split("--") if x.strip()])
            if nk > 6:
                hit(fn, lineno(t, m.start()), "keywords", f"{nk} keywords (A&A maximum is 6)")
            if "," in k[0] and "--" not in k[0] and nk == 1:
                hit(fn, lineno(t, m.start()), "keywords", "separate keywords with ' -- ', use the official A&A keyword list")
    elif is_main:
        hit(fn, 1, "keywords", "no \\keywords found")

    if is_main and not re.search(r"\\bibliographystyle\{aa\}", t) and "\\bibliography" in t:
        hit(fn, 1, "bib", "use \\bibliographystyle{aa}")
    if is_main and not re.search(r"\\begin\{acknowledgements\}", t):
        hit(fn, 1, "ack", "no acknowledgements environment (funders, facilities, software)")
    if is_main and not re.search(r"data availab", t, re.I):
        hit(fn, 1, "data", "no data availability statement found")
    if is_main and not re.search(r"\\section\*?\{[^}]*(Conclusion|Summary)", t, re.I):
        hit(fn, 1, "concl", "no Conclusions/Summary section")

    # tables: vertical rules, caption position
    for mt in re.finditer(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", t, re.S):
        body = mt.group(2)
        ln = lineno(t, mt.start())
        spec = re.search(r"\\begin\{tabular\*?\}(\{[^}]*\})?\{([^}]*)\}", body)
        if spec and "|" in spec.group(2):
            hit(fn, ln, "table", "vertical rules in tabular: A&A tables use horizontal \\hline only")
        c, tb = body.find("\\caption"), body.find("\\begin{tabular")
        if c > tb >= 0:
            hit(fn, ln, "table", "table caption must be above the tabular")
        if re.search(r"\\footnote", body):
            hit(fn, ln, "table", "use \\tablefoot/\\tablefootmark, not \\footnote, in tables")
    for mf in re.finditer(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", t, re.S):
        body = mf.group(2)
        c, g = body.find("\\caption"), body.find("\\includegraphics")
        if 0 <= c < g:
            hit(fn, lineno(t, mf.start()), "fig", "figure caption should be below the figure")

    # caption first word: no initial article (A&A guide)
    for mc in re.finditer(r"\\caption(\[[^\]]*\])?\{\s*(The|A|An)\s", t):
        hit(fn, lineno(t, mc.start()), "caption", "caption should start with a descriptive phrase without 'The/A/An'")
    # \object usage
    objs = list(re.finditer(r"\\object\{", t))
    if len(objs) > 20:
        hit(fn, 1, "object", f"{len(objs)} \\object tags: A&A wants ~10-20 at most, main objects only")
    for mt in re.finditer(r"\\begin\{(tabular\*?)\}(.*?)\\end\{\1\}", t, re.S):
        if "\\object" in mt.group(2):
            hit(fn, lineno(t, mt.start()), "object", "\\object inside a table: not allowed by A&A")
    # figures/tables cited in numerical order
    for kind in ("figure", "table"):
        envs = re.finditer(r"\\begin\{" + kind + r"\*?\}(.*?)\\end\{" + kind + r"\*?\}", t, re.S)
        order = [m.group(1) for m in (re.search(r"\\label\{([^}]*)\}", e.group(1)) for e in envs) if m]
        first = {}
        for mr in re.finditer(r"\\ref\{([^}]*)\}", t):
            first.setdefault(mr.group(1), mr.start())
        cited = [l for l in sorted(order, key=lambda l: first.get(l, 10**12)) if l in first]
        expect = [l for l in order if l in first]
        if cited != expect:
            hit(fn, 1, "xref", f"{kind}s first cited out of numerical order: {', '.join(cited)}")

    # labels referenced?
    labels = re.findall(r"\\label\{((?:fig|tab)[^}]*)\}", t)
    for lab in labels:
        if not re.search(r"\\(ref|cref|autoref)\{" + re.escape(lab) + r"\}", t):
            hit(fn, 1, "xref", f"{lab} is never referenced in the text")

    # acronyms: used but never defined as "(ACR)"
    body_t = re.sub(r"\\[a-zA-Z]+", " ", t)
    acr = Counter(re.findall(r"\b([A-Z]{2,6}s?)\b", body_t))
    defined = set(re.findall(r"\(([A-Z]{2,6})s?\)", t))
    for a, n in acr.items():
        a0 = a.rstrip("s") if a.endswith("s") and a[:-1].isupper() else a
        if 0 < n <= 2 and a0 in defined:
            hit(fn, 1, "acronym", f"'{a0}' defined but used only {n}x: consider spelling it out")

    # spelling consistency
    low = t.lower()
    for uk, us in SPELL_PAIRS:
        nu, na = len(re.findall(r"\b" + uk, low)), len(re.findall(r"\b" + us, low))
        if nu and na:
            hit(fn, 1, "spelling", f"mixed British/American: '{uk}'x{nu} vs '{us}'x{na}")

    # ---------- line rules (skip verbatim/math-only lines minimal) ----------
    in_doc = not is_main
    for i, l in enumerate(lines, 1):
        if "\\begin{document}" in l:
            in_doc = True
        if not in_doc or not l.strip():
            continue
        for rx, rule, msg in LINE_RULES:
            if msg is None:
                continue
            for mm in re.finditer(rx, l):
                hit(fn, i, rule, f"{msg}  «{l[max(0, mm.start()-15):mm.end()+15].strip()}»")

    # paragraph / sentence length (body only)
    start = t.find("\\maketitle")
    if start < 0:
        start = t.find("\\begin{document}")
    body = t[start:] if start >= 0 else t
    off = lineno(t, start) - 1 if start >= 0 else 0
    pos = 0
    for para in re.split(r"\n\s*\n", body):
        ln = off + body.count("\n", 0, body.find(para, pos)) + 1
        pos = body.find(para, pos) + len(para)
        if re.match(r"\s*\\(begin|end|section|subsection|caption|item|label|includegraphics)", para) and len(para) < 400:
            continue
        clean = re.sub(r"\\begin\{(equation|align|table|figure|tabular)\*?\}.*?\\end\{\1\*?\}", " ", para, flags=re.S)
        nw = len(words(clean))
        if nw > 280:
            hit(fn, ln, "para", f"paragraph of {nw} words: split, each part with its own topic sentence")
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\\])", clean):
            sw = len(words(s))
            if sw > 50:
                hit(fn, ln, "sentence", f"{sw}-word sentence: split  «{' '.join(s.split()[:10])} ...»")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for fn in sys.argv[1:]:
        check_file(fn)
    for fn, ln, rule, msg in sorted(HITS, key=lambda h: (h[0], h[1])):
        print(f"{fn}:{ln}: [{rule}] {msg}")
    c = Counter(h[2] for h in HITS)
    print(f"\n{len(HITS)} hits: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))


if __name__ == "__main__":
    main()
