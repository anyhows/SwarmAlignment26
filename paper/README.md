# Decision-Bound Verification for Concurrent A2A Agents

**Submission files:** `main.docx` (the Apart Research hackathon submission template, filled
in) and `anyhows_swarmalignment2026_submission.pdf` (that document exported from Word). Both are generated from
`main.tex`; edit the LaTeX and rebuild rather than editing the `.docx` by hand.

```bash
cd paper && pdflatex main.tex && pdflatex main.tex     # refreshes main.aux (numbers, labels)
python build_docx.py "<path to the Apart template .docx>"
```

`build_docx.py` needs pandoc in WSL (Ubuntu-24.04) and `pdftoppm`. It keeps the template's
own front matter (title box with the hackathon footnote, author grid, "With Apart Research",
abstract box), drops the template's guidance box, converts the body with the template as the
pandoc reference document, and embeds the template's Old Standard TT font. Export
`anyhows_swarmalignment2026_submission.pdf` from Word (File > Save As > PDF). The body ends on page 8, within the
8-page limit excluding references and appendices.

`main.tex` is the manuscript source; `main.pdf` is the LaTeX rendering.
The manuscript is complete: abstract, introduction, related work, methodology, results
(main experiment, defense comparison, dependency race, calibration), discussion, limitations
and dual use, future work. It merges the team's LaTeX front matter and figures with the
experimental write-up (formerly `draft.md`). All numbers come from `../artifacts/a2a_runs/`.

The manuscript includes editable vector figures directly from `figures/`.
Standalone figure PDFs are included alongside their `.tex` wrappers and
`.tikz` sources; shared styles are in `figures/preamble.tex`.

Rebuild with MiKTeX/TeX Live (run twice for references; output to the ignored `build/`):

```bash
cd paper && pdflatex -output-directory=build main.tex && pdflatex -output-directory=build main.tex && cp build/main.pdf main.pdf
```

Or, from the repository root, with Tectonic:

```bash
tectonic --outdir paper paper/main.tex
```

Rebuild the standalone figures:

```bash
tectonic --outdir paper/figures paper/figures/figure1.tex
tectonic --outdir paper/figures paper/figures/figure2.tex
```

For temporary builds, use `paper/build/`, which is ignored by Git.
LaTeX intermediate files are also ignored; the three published PDFs are tracked.

Imported from the `a2a-python/paper` draft on November 8, 2026.
