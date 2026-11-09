"""Build main.docx from main.tex inside the Apart Research submission template.

The template's own front matter (title box with hackathon footnote, author grid,
"With Apart Research", abstract box) is kept and filled in; its guidance box is
dropped. The body is converted from main.tex with pandoc (run in WSL), using the
template as the reference document so its heading styles apply, and spliced in
after the front matter. The template's embedded Old Standard TT font is kept and
made the document default.

Usage (Windows, from the repo root or paper/):
    python paper/build_docx.py "<path to template .docx>"
Requires: main.aux from a pdflatex build, pdftoppm, and pandoc in WSL Ubuntu-24.04.
"""

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PAPER = Path(__file__).resolve().parent
BUILD = PAPER / "docx_build"
OUT = PAPER / "main.docx"
AUTHORS = ["Yash Parikh", "Nikhil Maturi", "Aditya Katre"]
AFFILIATION = "[Affiliation]"


def wsl_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return "/mnt/" + s[0].lower() + s[2:]


def pandoc(args, cwd: Path) -> None:
    cmd = ["wsl", "-d", "Ubuntu-24.04", "--cd", wsl_path(cwd), "--", "pandoc", *args]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- LaTeX preprocessing
def labels() -> dict:
    aux = (PAPER / "main.aux").read_text(encoding="utf-8")
    return dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))


def find_group(s: str, i: int) -> int:
    """Index just past the brace group starting at s[i] == '{'."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    raise ValueError("unbalanced braces")


def preprocess(tex: str):
    lab = labels()
    keys = re.findall(r"\\bibitem\{([^}]+)\}", tex)
    num = {k: i + 1 for i, k in enumerate(keys)}

    # Abstract goes into the template's abstract box.
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S).group(1)

    body = tex[tex.index("\\begin{document}"):]
    body = body.replace("\\maketitle", "")
    body = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", "", body, flags=re.S)
    body = body.replace("\\clearpage", "")
    # Thin spaces (\,) become U+2006, which Old Standard TT lacks; Word then swaps the
    # whole run to a fallback font. Use a no-break space instead.
    body = body.replace("\\,", "~")

    body = re.sub(r"\\cite\{([^}]+)\}",
                  lambda m: "[" + ", ".join(str(num[k.strip()]) for k in m.group(1).split(",")) + "]",
                  body)
    body = re.sub(r"\\ref\{([^}]+)\}", lambda m: lab[m.group(1)], body)

    # Numbered sections take the template's "1. Introduction" form; the appendix
    # becomes one "Appendix" section with lettered subsections.
    head, _, appendix = body.partition("\\appendix")
    n = 0

    def number(m):
        nonlocal n
        n += 1
        return "\\section*{%d. %s}" % (n, m.group(1))

    head = re.sub(r"\\section\{([^}]*)\}", number, head)
    letters = iter("ABCDEFGHIJ")
    appendix = re.sub(r"\\section\{([^}]*)\}",
                      lambda m: "\\subsection*{%s. %s}" % (next(letters), m.group(1)), appendix)
    body = head + "\\section*{Appendix}\n" + appendix

    # References as plain "[n] ..." paragraphs under a References heading.
    def bib(m):
        items = re.split(r"\\bibitem\{([^}]+)\}", m.group(1))[1:]
        out = ["\\section*{References}"]
        for k, text in zip(items[0::2], items[1::2]):
            out.append("[%d] %s" % (num[k], text.strip()))
        return "\n\n".join(out) + "\n"

    body = re.sub(r"\\begin\{thebibliography\}\{\d+\}(.*?)\\end\{thebibliography\}", bib, body,
                  flags=re.S)

    # Run-in paragraph headings become a bold lead-in.
    body = re.sub(r"\\paragraph\{([^}]*)\}\s*\n", r"\\textbf{\1} ", body)

    # \path{...} -> \texttt{...} with escaped underscores.
    body = re.sub(r"\\path\{([^}]*)\}",
                  lambda m: "\\texttt{" + m.group(1).replace("_", "\\_") + "}", body)

    # TikZ figures -> rendered PNGs.
    body = re.sub(r"\\resizebox\{[^}]*\}\{!\}\{\\input\{figures/(figure\d)\.tikz\}\}",
                  r"\\includegraphics[width=3.4in]{\1.png}", body)

    # array-package column specs pandoc cannot parse.
    body = re.sub(r">\{\\raggedright(\\arraybackslash)?\}", "", body)

    # Number captions explicitly (Figure 1 / Table 1).
    out, i = [], 0
    for m in re.finditer(r"\\begin\{(figure|table)\}(.*?)\\end\{\1\}", body, re.S):
        env, inner = m.group(1), m.group(2)
        lm = re.search(r"\\label\{([^}]+)\}", inner)
        c = inner.find("\\caption{")
        if lm and c >= 0:
            prefix = ("Figure " if env == "figure" else "Table ") + lab[lm.group(1)] + ". "
            inner = inner[:c + 9] + prefix + inner[c + 9:]
        out.append(body[i:m.start()] + "\\begin{%s}%s\\end{%s}" % (env, inner, env))
        i = m.end()
    body = "".join(out) + body[i:]

    doc = "\\documentclass{article}\n\\usepackage{graphicx}\n\\usepackage{hyperref}\n" + body
    abs_doc = "\\documentclass{article}\n\\begin{document}\n" + abstract + "\n\\end{document}\n"
    return doc, abs_doc


# ---------------------------------------------------------------- XML helpers
def strip_ids(xml: str) -> str:
    return re.sub(r'\s(?:w14:paraId|w14:textId|w:rsid\w*)="[^"]*"', "", xml)


def top_level_blocks(body: str):
    """Split body XML into top-level <w:p>/<w:tbl> blocks (tables may nest)."""
    blocks, i = [], 0
    while True:
        m = re.compile(r"<w:(p|tbl)[ >]").search(body, i)
        if not m:
            return blocks
        tag = m.group(1)
        depth, j = 0, m.start()
        pat = re.compile(r"<w:%s[ >]|</w:%s>" % (tag, tag))
        for t in pat.finditer(body, m.start()):
            depth += 1 if not t.group(0).startswith("</") else -1
            if depth == 0:
                j = t.end()
                break
        blocks.append(body[m.start():j])
        i = j


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def front_matter(tpl_doc: str, title: str, abstract: str, footnote_id: int) -> str:
    body = tpl_doc[tpl_doc.index("<w:body>") + 8:]
    blocks = top_level_blocks(body)
    # blocks: 0 spacer, 1 nested front-matter table (title, authors, "With Apart
    # Research", "Abstract", abstract box), 2 spacer, 3 guidance box (dropped),
    # 4+ template sections (replaced by the converted body).
    assert "PROJECT TITLE" in blocks[1] and "Summarize" in blocks[1] and "How to use" in blocks[3]
    t = blocks[1].replace("PROJECT TITLE", xml_escape(title))
    t = re.sub(r'(<w:footnoteReference[^>]*w:id=")0(")', r"\g<1>%d\2" % footnote_id, t)

    # Inner author table: one row of three, 2300 dxa per author (template cells are
    # 690 dxa, which wraps every name).
    s = t.index('<w:tblStyle w:val="Table3"/>')
    s = t.rindex("<w:tbl>", 0, s)
    e = find_tbl_end(t, s)
    inner = t[s:e]
    rows = re.findall(r"<w:tr>.*?</w:tr>", inner, re.S)
    inner = inner.replace(rows[1], "")
    inner = inner.replace('w:w="2070.0"', 'w:w="6900.0"').replace('<w:gridCol w:w="690"/>',
                                                                  '<w:gridCol w:w="2300"/>')
    for k, name in enumerate(AUTHORS, 1):
        inner = inner.replace("Author name %d" % k, xml_escape(name))
    inner = inner.replace(">Affiliation<", ">%s<" % AFFILIATION)
    t = t[:s] + inner + t[e:]

    # Abstract box: our text, upright, justified, in the template's font.
    paras = [p for p in re.findall(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>", t, re.S)
             if "Summarize" in p]
    assert len(paras) == 1
    first = paras[0]
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", first, re.S).group(0)
    ppr = re.sub(r"<w:i w:val=\"1\"/>|<w:iCs w:val=\"1\"/>|<w:u [^>]*/>", "", ppr)
    run = ('<w:r><w:rPr><w:rFonts w:ascii="Old Standard TT" w:cs="Old Standard TT" '
           'w:eastAsia="Old Standard TT" w:hAnsi="Old Standard TT"/></w:rPr>'
           '<w:t xml:space="preserve">%s</w:t></w:r>' % xml_escape(abstract))
    t = t.replace(first, "<w:p>%s%s</w:p>" % (ppr, run), 1)

    # Widen the abstract box (template: 7095 dxa, indented 780) to 9000 dxa.
    s = t.rindex("<w:tbl>", 0, t.index('<w:tblStyle w:val="Table4"/>'))
    e = find_tbl_end(t, s)
    box = t[s:e]
    old_w = float(re.search(r'<w:tblW w:w="([\d.]+)"', box).group(1))
    scale = 9000 / old_w
    box = re.sub(r'(<w:tblW w:w=")[\d.]+', r"\g<1>9000.0", box, count=1)
    box = re.sub(r'(<w:tblInd w:w=")[\d.]+', r"\g<1>180.0", box, count=1)
    box = re.sub(r'(<w:(?:gridCol|tcW) w:w=")([\d.]+)',
                 lambda m: m.group(1) + str(int(float(m.group(2)) * scale)), box)
    t = t[:s] + box + t[e:]
    return strip_ids("".join([blocks[0], t, blocks[2]]))


def find_tbl_end(s: str, start: int) -> int:
    depth = 0
    for t in re.finditer(r"<w:tbl>|</w:tbl>", s[start:]):
        depth += 1 if t.group(0) == "<w:tbl>" else -1
        if depth == 0:
            return start + t.end()
    raise ValueError("unbalanced table")


# Styles pandoc emits that the template lacks (pandoc 3.1 does not add them itself).
MONO = '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
EXTRA_STYLES = (
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="BodyText"><w:name w:val="Body Text"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="FirstParagraph">'
    '<w:name w:val="First Paragraph"/><w:basedOn w:val="BodyText"/><w:next w:val="BodyText"/>'
    '</w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Compact"><w:name w:val="Compact"/>'
    '<w:basedOn w:val="BodyText"/><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="SourceCode"><w:name w:val="Source Code"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F3F3F3"/>'
    '<w:spacing w:before="0" w:after="120" w:line="240" w:lineRule="auto"/></w:pPr>'
    '<w:rPr>' + MONO + '<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr></w:style>'
    '<w:style w:type="character" w:customStyle="1" w:styleId="VerbatimChar">'
    '<w:name w:val="Verbatim Char"/><w:rPr>' + MONO + '<w:sz w:val="19"/><w:szCs w:val="19"/>'
    '</w:rPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="CaptionedFigure">'
    '<w:name w:val="Captioned Figure"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/>'
    '<w:spacing w:before="120" w:after="0"/><w:jc w:val="center"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="ImageCaption">'
    '<w:name w:val="Image Caption"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:spacing w:before="60" w:after="200" w:line="240" w:lineRule="auto"/></w:pPr>'
    '<w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="TableCaption">'
    '<w:name w:val="Table Caption"/><w:basedOn w:val="ImageCaption"/><w:pPr><w:keepNext/>'
    '<w:spacing w:before="160" w:after="60"/></w:pPr></w:style>'
    '<w:style w:type="character" w:customStyle="1" w:styleId="FootnoteReference">'
    '<w:name w:val="Footnote Reference"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="FootnoteText">'
    '<w:name w:val="Footnote Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0" '
    'w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>'
    '</w:style>'
    '<w:style w:type="character" w:customStyle="1" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
    '<w:rPr><w:color w:val="1155CC"/><w:u w:val="single"/></w:rPr></w:style>'
    '<w:style w:type="table" w:customStyle="1" w:styleId="Table"><w:name w:val="Table"/>'
    '<w:basedOn w:val="TableNormal"/><w:pPr><w:spacing w:before="20" w:after="20" w:line="240" '
    'w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr><w:tblPr>'
    '<w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
    '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/></w:tblBorders>'
    '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
    '</w:tblPr><w:tblStylePr w:type="firstRow"><w:rPr><w:b/></w:rPr><w:tcPr><w:tcBorders>'
    '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/></w:tcBorders></w:tcPr>'
    '</w:tblStylePr></w:style>'
)


# ---------------------------------------------------------------- main
def main(template: Path) -> None:
    BUILD.mkdir(exist_ok=True)
    shutil.copy(template, BUILD / "template.docx")
    for f in ("figure1", "figure2"):
        subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile",
                        str(PAPER / "figures" / (f + ".pdf")), str(BUILD / f)], check=True)

    doc, abs_doc = preprocess((PAPER / "main.tex").read_text(encoding="utf-8"))
    (BUILD / "body.tex").write_text(doc, encoding="utf-8", newline="\n")
    (BUILD / "abstract.tex").write_text(abs_doc, encoding="utf-8", newline="\n")
    pandoc(["body.tex", "-f", "latex", "-t", "docx", "--reference-doc=template.docx",
            "--shift-heading-level-by=1", "-o", "body.docx"], BUILD)
    pandoc(["abstract.tex", "-f", "latex", "-t", "plain", "--wrap=none", "-o", "abstract.txt"],
           BUILD)
    abstract = " ".join((BUILD / "abstract.txt").read_text(encoding="utf-8").split())
    title = re.search(r"\\title\{(.*?)\}\n", (PAPER / "main.tex").read_text(encoding="utf-8")).group(1)

    tpl = zipfile.ZipFile(BUILD / "template.docx")
    src = zipfile.ZipFile(BUILD / "body.docx")
    files = {n: src.read(n) for n in src.namelist()}

    # Title footnote ("Research conducted at the Swarm Alignment Hackathon") + its link.
    fn_xml = files["word/footnotes.xml"].decode()
    ids = [int(x) for x in re.findall(r'<w:footnote [^>]*w:id="(-?\d+)"', fn_xml)]
    fid = max(ids + [0]) + 1
    tfn = tpl.read("word/footnotes.xml").decode()
    note = re.search(r'<w:footnote w:id="0">.*?</w:footnote>', tfn, re.S).group(0)
    trels = tpl.read("word/_rels/footnotes.xml.rels").decode()
    rels_name = "word/_rels/footnotes.xml.rels"
    rels = files.get(rels_name, b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                     b'relationships"></Relationships>').decode()
    for rid, target in re.findall(r'Id="(\w+)"[^>]*Target="([^"]+)"', trels):
        new = "rIdTpl" + rid
        note = note.replace('r:id="%s"' % rid, 'r:id="%s"' % new)
        rels = rels.replace("</Relationships>",
                            '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/'
                            'officeDocument/2006/relationships/hyperlink" Target="%s" '
                            'TargetMode="External"/></Relationships>' % (new, target))
    note = strip_ids(note.replace('w:id="0"', 'w:id="%d"' % fid, 1))
    files["word/footnotes.xml"] = fn_xml.replace("</w:footnotes>", note + "</w:footnotes>").encode()
    files[rels_name] = rels.encode()

    # Splice the template's front matter before the converted body.
    d = files["word/document.xml"].decode()
    fm = front_matter(tpl.read("word/document.xml").decode(), title, abstract, fid)
    i = d.index("<w:body>") + len("<w:body>")
    files["word/document.xml"] = (d[:i] + fm + d[i:]).encode()

    # Template font: embedded files, font table, and the document default.
    for n in tpl.namelist():
        if n.startswith("word/fonts/") or n in ("word/fontTable.xml",
                                                "word/_rels/fontTable.xml.rels"):
            files[n] = tpl.read(n)
    ct = files["[Content_Types].xml"].decode()
    for ext, typ in (("png", "image/png"), ("ttf", "application/x-font-ttf"),
                     ("odttf", "application/vnd.openxmlformats-officedocument.obfuscatedFont")):
        if 'Extension="%s"' % ext not in ct:
            ct = ct.replace("<Default ", '<Default Extension="%s" ContentType="%s"/><Default '
                            % (ext, typ), 1)
    if "fontTable.xml" not in ct:
        ct = ct.replace("</Types>", '<Override PartName="/word/fontTable.xml" ContentType='
                        '"application/vnd.openxmlformats-officedocument.wordprocessingml.'
                        'fontTable+xml"/></Types>')
    files["[Content_Types].xml"] = ct.encode()
    drels = files["word/_rels/document.xml.rels"].decode()
    if "fontTable.xml" not in drels:
        drels = drels.replace("</Relationships>",
                              '<Relationship Id="rIdFontTable" Type="http://schemas.openxmlformats'
                              '.org/officeDocument/2006/relationships/fontTable" '
                              'Target="fontTable.xml"/></Relationships>')
        files["word/_rels/document.xml.rels"] = drels.encode()
    st = files["word/styles.xml"].decode()
    st = re.sub(r'<w:style [^>]*w:styleId="SourceCode".*?</w:style>', "", st, flags=re.S)
    st = st.replace("</w:styles>", EXTRA_STYLES + "</w:styles>")
    st = re.sub(r"(<w:rPrDefault><w:rPr>)<w:rFonts[^>]*/>",
                r'\1<w:rFonts w:ascii="Old Standard TT" w:cs="Old Standard TT" '
                r'w:eastAsia="Old Standard TT" w:hAnsi="Old Standard TT"/>', st, count=1)
    files["word/styles.xml"] = st.encode()
    # pandoc writes malformed list nsids ("A99201"); Word wants 8 hex digits, and
    # bad ones make it restart numbering (1, 1, 2, 3). Give each a valid unique id.
    num = files["word/numbering.xml"].decode()
    # Each list gets its own abstract definition instead of a shared one plus
    # startOverride, which Word miscounts.
    abstracts = {m.group(1): m.group(0) for m in
                 re.finditer(r'<w:abstractNum w:abstractNumId="(\d+)".*?</w:abstractNum>', num, re.S)}
    new_abs, next_id = [], 50000

    def own(m):
        nonlocal next_id
        if "<w:lvlOverride" not in m.group(0):
            return m.group(0)
        next_id += 1
        a = abstracts[m.group(2)].replace('w:abstractNumId="%s"' % m.group(2),
                                          'w:abstractNumId="%d"' % next_id, 1)
        new_abs.append(a)
        return '<w:num w:numId="%s"><w:abstractNumId w:val="%d"/></w:num>' % (m.group(1), next_id)

    num = re.sub(r'<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId w:val="(\d+)"\s*/>.*?</w:num>',
                 own, num, flags=re.S)
    first_num = num.index("<w:num ")
    num = num[:first_num] + "".join(new_abs) + num[first_num:]
    counter = iter(range(1, 10 ** 6))
    num = re.sub(r'<w:nsid w:val="[^"]*"\s*/>',
                 lambda m: '<w:nsid w:val="%08X"/>' % (0x5A000000 + next(counter)), num)
    files["word/numbering.xml"] = num.encode()

    settings = files["word/settings.xml"].decode()
    if "embedTrueTypeFonts" not in settings and "embedTrueTypeFonts" in tpl.read(
            "word/settings.xml").decode():
        # Schema order: ... w:view, w:zoom, w:removePersonalInformation, ...,
        # w:embedTrueTypeFonts. Insert after zoom (or at the start if there is none).
        m = re.search(r"<w:zoom[^>]*/>|<w:zoom[^>]*>.*?</w:zoom>", settings, re.S) or \
            re.search(r"<w:settings[^>]*>", settings)
        settings = settings[:m.end()] + "<w:embedTrueTypeFonts/>" + settings[m.end():]
        files["word/settings.xml"] = settings.encode()

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            if not n.endswith("/"):
                z.writestr(n, b)
    print("wrote", OUT)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
