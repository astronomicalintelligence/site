---
name: astro-paper-writing
description: Write, draft, restructure, edit, or review an astronomy/astrophysics research paper in LaTeX — title, abstract, introduction, methods, results, discussion, conclusions, figures, captions, language and style — following field best practice (Knapen, Chamba & Black 2022) and formatted for A&A (aa.cls). Includes a linter to check a .tex manuscript.
---

# Writing astronomy papers

The main guide here is Knapen, Chamba & Black 2022, "How to write and develop your astronomy
research paper" (arXiv:2110.05503). A&A (aa.cls) is the house format for every paper, and is
covered in the last section.

## Workflow
1. Read the whole `.tex` (and `.bib`) first. Keep the authors' voice, their macros and their
   British or American spelling, used consistently.
2. Before polishing sentences, fix the story. Check that the paper has one clear message, which
   the title, abstract and conclusions all state.
3. Make small, local edits. Never invent numbers, references or results. Mark anything that needs
   the authors' input with `\textbf{[TODO: ...]}`.
4. Run the linter. Its hits are heuristic candidates, so review each one before acting on it:
   `python3 ~/.claude/skills/astro-paper-writing/check_aa.py paper.tex`
5. Compile against the bundled A&A package in `~/.claude/skills/astro-paper-writing/aa/`. If the
   paper folder has its own newer `aa.cls`, LaTeX uses that one instead.
   ```bash
   export TEXINPUTS=~/.claude/skills/astro-paper-writing/aa//: BSTINPUTS=~/.claude/skills/astro-paper-writing/aa//:
   pdflatex -interaction=nonstopmode paper.tex >/dev/null; bibtex paper; pdflatex -interaction=nonstopmode paper.tex >/dev/null; pdflatex -interaction=nonstopmode paper.tex >/dev/null
   grep -E 'Output written|^!|undefined' paper.log
   ```
   Check the page count, especially the 4-page limit for Letters. The first compile can take a
   minute and print METAFONT noise while it generates bitmap fonts, because `cm-super` is not
   installed. Ignore the `etex` and `lineno` warnings.

## Structure
- Follow **IMRaD**: Introduction, Data/Methods, Results, Discussion, Conclusions. Don't mix them.
  The paper has an hourglass shape: broad, then narrow (methods and results), then broad again.
  Break the text into short subsections whose titles carry key words or the key message.
- **Title**: about 15 words or fewer, simple words, no jargon, and no acronyms beyond general use
  (LOFAR is fine). Give the main message or result, and include the words people search for.
  Don't start with "On..." or "Towards...", and avoid jokes. It must match the abstract.
- **Abstract**: about 150–250 words that tell the whole story. Set the scene, state the problem,
  say what was done and how, give the main results *with numbers*, state the conclusion, and end
  with the outlook. Editors use the abstract as a filter, so it must stand alone and agree with
  the body.
- **Introduction**: write it in this order:
  1. the big picture
  2. the sub-topic
  3. the **gap** in knowledge
  4. an explicit aim ("The aim of this paper is ...")
  5. what was done
  6. the outline (for long papers)

  Give all the background needed later, because the Discussion and Conclusions must not introduce
  new background. Don't give the conclusions here, and don't let it grow into a review. Cite key
  and *original* papers rather than everything: use "e.g.", and cite reviews for breadth only.
  Include recent work, but not only recent work. Read every paper you cite to confirm it supports
  your claim. Textbook facts need no citation. Keep self-citation moderate.
- **Data/Methods**: say what data were used, how they were obtained and reduced, and how they
  were analysed, with enough detail to judge their reliability and reproduce the work. Justify
  why these data and methods suit the aims. Report no results here. State the caveats and
  quantify their effect. Don't hide a real problem in an appendix. Leave out steps that don't
  affect the main line. Put the most technical parts in their own subsections so readers can
  skip them.
- **Results**: report what was found, and save the interpretation and comparisons for the
  Discussion. Choose the figures first and build the narrative and subsections around them.
  Open each subsection with *why*: "To test whether x depends on y, Fig.~3 shows ...", not
  "In Fig.~3 we plot ...".
- **Discussion**: answer the question posed at the start, explain how the data support the
  answer, and compare with the literature, theory and models, both where they agree and where
  they disagree. Give alternative explanations without losing the main message. Discuss the
  limitations critically. State the wider implications and the specific future work or
  observations that would settle the open issues. Use a topic sentence at the start of each
  subsection and a summary sentence at its end.
- **Conclusions**: always include them, because many readers go straight there. If they are
  merged into the Discussion, title the section "Discussion and conclusions". Briefly restate the
  aim, the sample, the telescope and the codes, then the main *quantitative* results and their
  interpretation, and point to the key figures. End with a strong sentence that sums up the
  paper, not "more work is needed".
- **Acknowledgements and references**: name the funders with grant numbers, thank the people who
  helped, and include the statements required by the telescopes, archives and surveys
  (LOFAR, VLA/NRAO, Gaia, SDSS, ...). Cite software in the references too (Astropy and others).
  Make every reference complete and correct.
- **Appendices**: use them for material that would lengthen the main text or is too technical,
  such as extra tests, observation logs, long derivations, or series of similar figures.

## Figures and tables
- Plan them early. Use only the key ones, and move series of figures or long tables to
  appendices or online material.
- A figure should tell its part of the story on its own. Include every needed line, point and
  label, and nothing else. Use one style across all figures (font, text size and colour coding).
  Keep axis labels readable at column width, and use vector PDF.
- Use a **colour-blind-safe** palette (about 10% of readers have colour-vision deficiency), and
  **never use colour alone**: pair colour with line or marker style.
- In the caption, explain every line style, symbol and panel. Every figure and table is cited in
  the text, in numerical order.

## Paragraphs and sentences
- Each paragraph starts with a **topic sentence** stating its main idea. The sentences after it
  give the support (facts, examples, analysis). Keep paragraphs to 3–7 sentences. Split any
  paragraph of half a page or more, and give each part its own topic sentence. If a paragraph
  drifts, fix the topic sentence or split the paragraph.
- Open paragraphs in a way that suits the section. In the Introduction, start with a general
  statement. In the Methods, introduce the steps. In the Results, refer to a figure or table.
- Sentences should average 18–32 words, with no more than about one in three or four long and
  complex. Use subject–verb–object order, with the subject close to its verb.
- Put **old information first and new information at the end** of a sentence. Link sentences by
  repeating the key noun ("This galaxy ..."). Never make a bare "this" the subject: say what it
  refers to. Use signposts: "for example" and "such as" for examples, "first", "next" and "finally"
  for sequence, "consequently" and "as a result" for cause, "similarly" for similarity, and
  "however" and "on the other hand" for contrast.
- Prefer the **active voice**. "We" is fine, and so are inanimate subjects ("Figure 2 shows ...").
- **Tenses**: use the present for facts and for what the paper, its figures and tables show. Use
  the past for what was done. Use the present perfect for recent work that still matters. Be
  consistent.
- Use precise verbs: observers *measure* and *find*. Write "dust is concentrated in the centre",
  not "galaxies concentrate dust". Put each modifier next to the word it modifies.

## Word-level rules
- "Data" is plural (datum is the singular). Other irregular plurals are spectrum/spectra,
  analysis/analyses, criterion/criteria, phenomenon/phenomena and index/indices.
- Use **number** for things you count and **amount** for quantities you measure.
- Use "the" when the reader knows which thing is meant: it was already introduced, it is defined,
  or it is unique (the Sun, the Milky Way). Use "a"/"an" for a singular noun introduced for the
  first time. Use no article for plural or uncountable nouns used generally. Don't put "the"
  before personal names.
- Prefer formal single verbs to phrasal verbs: "investigate" not "look into", "discuss" not
  "talk about", "continue" not "go on". Use few adverbs and intensifiers (very, clearly,
  extremely).
- Use "that" for defining clauses and ", which" for non-defining ones, and check that the commas
  don't change the meaning.
- Define each acronym once in the abstract and once in the main text, then use it consistently.
  Drop acronyms used only once or twice.
- **Numbers**: give uncertainties to 1–2 significant figures and the value to the same decimal
  place. Say what the error bars are (1σ, 68%). Keep the numbers identical across the text,
  tables and abstract.

## A&A format (house style for all papers)
The rules come from the A&A Author guide (checked in November 2026) and the bundled A&A package
`aa/` (aa.cls v9.4, 2025/11/27; aa.bst; official template `aa/aa_example.tex`). When unsure how
to typeset something, copy the pattern from the template. If A&A releases a newer package,
replace the files in `aa/`.
- **Class options**: `\documentclass{aa}`. Use `letter` for Letters, `longauth` for long author
  lists (the first 8 authors go on page 1 and the full list moves after the references),
  `referee` for a referee version, and `onecolumn` for a single-column paper.
- **Front matter**:
  `\author{A.~Name\inst{1}\corrauth{email} \and B.~Name\inst{2}\email{email} \and ...}`.
  `\corrauth` marks the corresponding author, and every co-author needs an `\email` address.
  **Don't put ORCIDs in the `.tex` file**, because they are removed; co-authors authenticate
  them in the submission system instead. After the authors come `\institute{... \and ...}`,
  `\date{Received ...}`, `\abstract{...}{...}{...}{...}{...}`, `\keywords{kw1 -- kw2}` and
  `\maketitle`.
- **Structured abstract**: all 5 `{}` groups are mandatory. Aims, Methods and Results must be
  filled in. Context and Conclusions are optional; leave an unused one empty as `{}`. Don't put
  citations in the abstract.
- **Keywords**: at most 6, taken from the keyword list shared by the major astronomy journals.
- **Cross-references**: "Fig."/"Figs." and "Sect."/"Sects." mid-sentence, spelled out at the start
  of a sentence. "Table" and "Appendix" are never abbreviated. Write equations as "Eq. (3)". Put
  `~` before every `\ref`.
- **Citations**: natbib with `\bibliographystyle{aa}`. Use `\citet` (textual), `\citep`
  (parenthetical) and `\citep[e.g.][]{key}`. "et al." is upright. Never type a citation by hand.
- **Figures**: size with `\resizebox{\hsize}{!}{...}` for one column, or `figure*` with
  `\textwidth` for two. The caption goes below the figure, and its first sentence is a descriptive
  phrase without "The", "A" or "An". Use panel letters (a), (b) only if they are drawn in the
  figure; otherwise refer to positions. Put no scientific discussion in captions: it belongs in
  the text, which should not repeat the caption. A figure reused from another paper needs
  permission and a credit in its caption.
- **Tables**: a short title *above* the table, without an initial article. Use horizontal rules
  only: `\hline\hline` at the top, `\hline` below the header and `\hline` at the bottom. Every
  column has a heading, with units in parentheses on the line below the headings. Write `...`
  for missing entries. Notes go in `\tablefoot{}`, with `\tablefootmark{a}` and
  `\tablefoottext{a}{...}`. References in a table are numbered, with
  `\tablebib{(1)~\citet{x}; (2)~\citet{y}.}`. Long tables use `\longtab{...}`, or go in a
  single-column appendix.
- **Units**: upright, with a thin space: `$5\,\mathrm{km\,s^{-1}}$`, `1.4\,GHz`, never "km/s".
  Subscripts that are words are upright: `$L_\mathrm{1.4\,GHz}$`.
- **`\object{}`**: use it only for the main objects, about 10–20 times at most, and never in
  tables.
- **Order**: the `acknowledgements` environment, then `\bibliographystyle{aa}` with
  `\bibliography{file}` (upload the `.bib` file too), then `\begin{appendix}`. Appendices are
  published camera-ready. To keep a wide float under its own appendix title, switch to
  `\onecolumn`, use the `[ht!]` placement and `\FloatBarrier` (from `placeins`), then switch
  back with `\twocolumn`.
- **Letters**: the main body is strictly 4 pages, and appendices are allowed.
