"""Write how-to-read.html: a key to the markings used on the excerpt pages.

Each example is a short piece of TEI taken from a real excerpt. It is rendered with the same
stylesheet as the pages (tei_to_html.xsl), so the key always matches what the pages show.

Usage (normally called from build_site.py):
    from how_to_read import write_how_to_read
    write_how_to_read(out_dir)
"""

import html
from pathlib import Path
from urllib.parse import quote

import lxml.html
from lxml import etree

from partials import partial_html
from run_tei_to_html import _stylesheet

TEI_NS = "http://www.tei-c.org/ns/1.0"

# (heading, intro, rows). Each row: (TEI snippet, what it looks like, meaning/how to use, example file or None)
SECTIONS = [
    ("Numbers and breaks", "Where a page, line or section begins.", [
        ('<pb n="1a"/>', "[f. 1a]", "Start of folio 1a. With two or more instances the letter of the instance is added, e.g. [f. 1a · A].",
         "1_002_02 Ar_sher phyin rgya grel.xml"),
        ('<lb edRef="inst:4477" n="1b2"/>', "small grey number at the start of a line (here 1b2)",
         "Line 2 of folio 1b. With two or more instances it reads e.g. A:1b2 (letter = instance).",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<milestone unit="section" n="Colophon (5a6-5a7)"/>', "small capitals in gold, on their own line",
         "A section boundary in the text, such as a colophon.", "1_013_03 gTsang nag pa bstan pa byi dar bya.xml"),
    ]),
    ("Corrections and readings", "Where the text as written differs from the form given in the edition.", [
        ('<choice><reg>dbyangs</reg><orig>(d)byangs</orig></choice>', "dbyangs in purple",
         "The regularised form is shown. Hover to see the original spelling (“original: (d)byangs”).",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<choice><corr>dbus</corr><sic>dbu</sic></choice>', "dbus in purple",
         "The corrected form is shown. Hover to see what was written (“sic: dbu”).",
         "1_001_10 rNgog lo_dbus mtha don bsdus.xml"),
        ('<choice><orig>shas</orig><sic>shes</sic></choice>', "shasshes with a dotted underline",
         "Both forms are shown and no choice has been made. Hover to see each one. "
         "Listed in report.md for the editors to decide.",
         "1_001_13 Ngog_PVin dka' gnas.xml"),
        ('<app><lem wit="inst:4664">spang</lem><rdg wit="inst:4664">spang</rdg><rdg wit="inst:6858">dpang</rdg></app>',
         "spang, with a small grey list after it: “: dpang” (and witness letters where there are several instances)",
         "The main reading is shown in the text. Other readings from other witnesses are listed after it in small type.",
         "1_028_02_ dBang phyug rin chen _ byang chub sems dpa'i spyod pa la 'jug pa'i sgrung 'grel.xml"),
        ('<unclear>368</unclear>', "(368)", "The reading is uncertain; brackets show this.", "1_001_06_rNgog_dag yig bsdus.xml"),
        ('<expan>zer ro</expan>', "zer ro",
         "An abbreviation that the editor has expanded.", "1_002_02 Ar_sher phyin rgya grel.xml"),
        ('<gap reason="omitted"/>', "[…] in grey italics", "Text left out. Hover to see why (here: omitted).",
         "1_002_02 Ar_sher phyin rgya grel.xml"),
        ('<foreign xml:lang="sa-Latn-x-wylie">shra ma ni ra</foreign>', "shra ma ni ra in italics",
         "A word in another language (here Sanskrit, in Wylie transliteration). Hover to see the language code.",
         "1_009_03_Phya pa_od ldan ti ka.xml"),
        ('<mentioned>pa</mentioned>', "pa in italics", "The text is shown in italics.",
         "1_001_06_rNgog_dag yig bsdus.xml"),
    ]),
    ("Glosses, notes and quotations", "Additions by the editors, and quoted passages.", [
        ('<note type="gloss">rang</note>', "‹rang› in the line", "A short gloss on the word before it, kept in the line.",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<note type="editorial">"ja" in dbu can</note>', "note ▸ (collapsed)",
         "An editorial note. Click “editorial” to open it. Its label always shows the note type.",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<note type="translation">The Fifty Verses Cleansing the Teacher\'s Teaching, composed by the Shakya monk brTson \'grus seng ge.</note>',
         "translation ▸ (collapsed)", "A translation of the passage, kept out of the way. Click “translation” to read it.",
         "1_013_03 gTsang nag pa bstan pa byi dar bya.xml"),
        ('<quote source="work:3727" n="12a3">passage quoted from the work</quote>', "an indented block of text with a citation under it",
         "A quotation with its source. The line underneath gives the title of the work and the locator (n), e.g. a folio.",
         "1_001_12 rNgog_rigs thigs grel don bsdus.xml"),
        ('<quote>passage quoted without a source</quote>', "an indented block of text, with no citation under it",
         "A quotation without a source. It is shown like other quotations, but without the citation line.",
         "1_001_07_rNgog_shes rab snying bshad don bsdus.xml"),
    ]),
    ("Names and works", "Named people, works and places are coloured by type.", [
        ('<rs type="person" ref="person:3743">slob dpon zhi ba\'i lha</rs>', "maroon", "A person. Hover to see the type and database id.",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<rs type="work" ref="work:3738">mdo kun las bstus pa </rs>', "blue", "A work. Hover to see the type and database id.",
         "1_006_01 rGya_spyod jug grel.xml"),
        ('<rs type="place" ref="place:6216">thon mthing gi gtsug lag khang</rs>', "dark olive green",
         "A place. Hover to see the type and database id.",
         "1_001_05_Rinchen_bde can smon lam.xml"),
    ]),
]

# Extra notes at the top of the page, in plain language
LAYOUT = [
    "<strong>Top:</strong> the title (Wylie and Tibetan), the author and the TibSchol reference. "
    "<strong>⋮</strong> (top right) opens <em>About this text</em> and <em>Credits</em>.",
    "<strong>Side panel:</strong> the instance, the work and the author. On narrow screens it moves below the text.",
    "<strong>Encoded text:</strong> the text itself. Each line of the source is in the same order as in the instance.",
    "<strong>Foot:</strong> the project team, funder and licence. The link <em>TEI XML source</em> at the top opens the file itself.",
]



def render_snippet(tei):
    """Render a TEI fragment with the page stylesheet and return its HTML (without the block wrapper)."""
    doc = (
        f'<TEI xmlns="{TEI_NS}"><teiHeader><fileDesc><titleStmt><title type="main">example</title></titleStmt>'
        "<publicationStmt><p/></publicationStmt><sourceDesc><p/></sourceDesc></fileDesc></teiHeader>"
        f"<text><body><ab>{tei}</ab></body></text>"
        # the work cited by the example quotation (title from 1_001_12); the citation looks it up here
        '<standOff><listBibl><bibl xml:id="work3727"><title type="main">bodhicaryāvatāra</title></bibl></listBibl></standOff>'
        "</TEI>"
    )
    result = _stylesheet()(etree.fromstring(doc.encode("utf-8")))
    page = lxml.html.document_fromstring(str(result))
    ab = page.find(".//div[@class='ab']")
    if ab is None:
        return html.escape(tei)
    inner = html.escape(ab.text or "")
    inner += "".join(lxml.html.tostring(child, encoding="unicode") for child in ab)
    return inner


def _rows_html(rows):
    out = []
    for tei, _, meaning, example in rows:
        if example:
            name = example.rsplit(".", 1)[0]
            link = f'<br><small>Example: <a href="{quote(name)}.html">{html.escape(name)}</a></small>'
        else:
            link = ""
        out.append(
            "<tr>"
            f'<td class="sample">{render_snippet(tei)}</td>'
            f"<td><code>{html.escape(tei)}</code>{link}</td>"
            f"<td>{meaning}</td>"
            "</tr>"
        )
    return "\n".join(out)


def build_page():
    sections = []
    for heading, _intro, rows in SECTIONS:
        sections.append(
            f"<section>\n<h2>{html.escape(heading)}</h2>\n"
            '<div class="table-wrap"><table>\n'
            "<thead><tr><th>Looks like</th><th>In the TEI file</th><th>What it means</th></tr></thead>\n"
            f"<tbody>\n{_rows_html(rows)}\n</tbody></table></div>\n</section>"
        )
    layout = "\n".join(f"<li>{x}</li>" for x in LAYOUT)
    sections_html = "\n".join(sections)
    header = partial_html("header.xml")
    footer = partial_html("footer.xml")
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TibSchol-TEI-Library - How to</title>
  <link rel="stylesheet" href="assets/pico.min.css">
  <link rel="stylesheet" href="assets/tibschol.css">
  <style>
    .table-wrap {{ overflow-x: auto; }}
    .key td.sample {{ min-width: 9rem; }}
    .key td {{ vertical-align: top; }}
    .key code {{ font-size: .78rem; white-space: pre-wrap; word-break: break-word; }}
    .key-page {{ max-width: 62rem; }}
  </style>
</head>
<body>
  <header class="topbar" data-pagefind-ignore="data-pagefind-ignore">
    {header}
  </header>
  <main class="container key-page">
    <h1>How to read the excerpts</h1>
    <p>This is a key to the markings on the excerpt pages. Each example is real TEI taken from the excerpts and
       shown as it appears on the pages. Use the <em>Example</em> link to open the excerpt where it occurs.</p>

    <div class="key">
    {sections_html}
    </div>

    <p class="page-foot"><small>Generated with the excerpts. The examples are rendered by the same stylesheet as the pages.</small></p>
  </main>
  {footer}
</body>
</html>
"""


def write_how_to_read(out_dir):
    path = Path(out_dir, "how-to-read.html")
    path.write_text(build_page(), encoding="utf-8")
    return path
