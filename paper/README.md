# Decision-Bound Verification for Concurrent A2A Agents

`main.tex` is the manuscript source; `main.pdf` is the compiled draft.
The draft includes the abstract, introduction, motivation, theory of change,
and related work. Implementation and results remain work in progress.

The manuscript includes editable vector figures directly from `figures/`.
Standalone figure PDFs are included alongside their `.tex` wrappers and
`.tikz` sources; shared styles are in `figures/preamble.tex`.

From the repository root, rebuild the tracked manuscript PDF with Tectonic:

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
