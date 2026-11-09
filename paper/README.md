# Decision-Bound Verification for Concurrent A2A Agents

`main.tex` is the manuscript source; `main.pdf` is the compiled draft.
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
