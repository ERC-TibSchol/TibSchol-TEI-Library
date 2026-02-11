"""Build the static HTML site for the public TEI excerpts.

For every TEI file matching the glob:
  * transforms it to HTML with tei_to_html.xsl (via run_tei_to_html.py),
  * copies the XML next to it (the "View TEI XML source" link),
  * writes index.html listing all TEI files by TibSchol reference (linked from each page header).

Usage:
    python scripts/tei2html/build_site.py "data/excerpts/*.xml" -o site/excerpts
"""

import argparse
import glob
import html
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_tei_to_html import transform_one  # noqa: E402
from how_to_read import write_how_to_read  # noqa: E402
from partials import partial_html  # noqa: E402

TEI = "{http://www.tei-c.org/ns/1.0}"


def excerpt_summary(path):
    root = etree.parse(str(path)).getroot()
    header = root.find(f"{TEI}teiHeader")
    title = header.findtext(f"{TEI}fileDesc/{TEI}titleStmt/{TEI}title[@type='main']") or ""
    authors = [a.text or "" for a in header.iterfind(f"{TEI}fileDesc/{TEI}titleStmt/{TEI}author")]
    ids = [i.text for i in header.iterfind(f"{TEI}fileDesc/{TEI}publicationStmt/{TEI}idno[@type='TibSchol']")]
    return {"stem": Path(path).stem, "title": title, "authors": authors, "ids": ids}


# Placeholder intro for the index page (taken from the first paragraph of README.md)
INTRO = ("This repository contains the digital library of annotated textual fragments in TEI format. "
         "It was created in the framework of the project The Dawn of Tibetan Buddhist Scholasticism "
         "(11th-13th c.) (TibSchol).")


def write_index(summaries, out_dir):
    rows = []
    for s in sorted(summaries, key=lambda s: (s["ids"][0] if s["ids"] else s["stem"])):
        ids = ", ".join(s["ids"]) if s["ids"] else s["stem"]
        rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(s['stem'])}.html\">{html.escape(ids)}</a></td>"
            f"<td>{html.escape(s['title'])}</td>"
            f"<td>{html.escape('; '.join(s['authors']))}</td>"
            "</tr>"
        )
    header = partial_html("header.xml")
    footer = partial_html("footer.xml")
    page = f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TibSchol-TEI-Library</title>
  <link rel="stylesheet" href="assets/pico.min.css">
  <link rel="stylesheet" href="assets/tibschol.css">
</head>
<body>
  <header class="topbar" data-pagefind-ignore="data-pagefind-ignore">
    {header}
  </header>
  <main class="container">
    <p class="intro">{html.escape(INTRO)}</p>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>TibSchol reference</th><th>Title (Wylie)</th><th>Author of the work</th></tr></thead>
      <tbody>
        {chr(10).join('        ' + r for r in rows)}
      </tbody>
    </table>
    </div>
  </main>
  {footer}
</body>
</html>
"""
    Path(out_dir, "index.html").write_text(page, encoding="utf-8")


def _text(el):
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def build_search_index(out_dir):
    """Build the Pagefind search index in out_dir/pagefind (needs Node.js: npx)."""
    npx = shutil.which("npx")
    if npx is None:
        print("Search index not built: npx (Node.js) not found. Use --no-search to skip this step.")
        return
    result = subprocess.run([npx, "-y", "pagefind@1.6.0", "--site", str(out_dir)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("Search index failed:", (result.stderr or result.stdout)[-500:])
    else:
        print(f"Search index built in {Path(out_dir, 'pagefind')}/")


def main():
    parser = argparse.ArgumentParser(description="Build the HTML site for the public TEI files.")
    parser.add_argument("tei_glob", help="Glob for the public TEI files, e.g. 'data/excerpts/*.xml'")
    parser.add_argument("-o", "--out-dir", default="site/excerpts")
    parser.add_argument("--no-search", action="store_true", help="do not build the Pagefind search index")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HERE / "assets", out_dir / "assets", dirs_exist_ok=True)

    summaries, failed, problems = [], [], []
    for path in sorted(glob.glob(args.tei_glob)):
        if not path.endswith(".xml"):
            continue
        try:
            _, file_problems = transform_one(Path(path), out_dir)
            problems.extend((os.path.basename(path),) + p for p in file_problems)
            summaries.append(excerpt_summary(path))
        except Exception as e:  # noqa: BLE001 - report and continue
            failed.append((os.path.basename(path), f"{type(e).__name__}: {e}"))

    write_index(summaries, out_dir)
    write_report(problems, failed, len(summaries), out_dir)
    write_how_to_read(out_dir)
    if not args.no_search:
        build_search_index(out_dir)
    print(f"{len(summaries)} pages written to {out_dir}/ (index.html), {len(failed)} failed")
    print(f"{len(problems)} problems noted in {Path(out_dir, 'report.md')}")
    for name, problem in failed:
        print("  FAILED", name, problem)


# Report kinds: what each one means, shown at the top of report.md
REPORT_KINDS = [
    ("choice-unresolved", "A choice with no reg/corr: both forms are shown (dotted underline). Needs an editorial decision."),
    ("app-no-lemma", "A variant with no lem: the first reading is shown in the text, the others are listed."),
    ("unhandled-element", "An element with no template: shown as plain text in a span.unknown. Not styled."),
    ("note-untyped", "A note with no type attribute: shown as a note with the label 'note'."),
]


def write_report(problems, failed, page_count, out_dir):
    """Write report.md: one table per problem kind, one row per occurrence."""
    lines = [
        "# Build report",
        "",
        f"Pages built: {page_count}. Failed pages: {len(failed)}. Problems noted: {len(problems)}.",
        "",
        "## Summary",
        "",
        "| Kind | Count | Meaning |",
        "|---|---|---|",
    ]
    known = {k for k, _ in REPORT_KINDS}
    kinds = REPORT_KINDS + [(k, "(not described)") for k in sorted({p[1] for p in problems} - known)]
    for kind, meaning in kinds:
        count = sum(1 for p in problems if p[1] == kind)
        lines.append(f"| `{kind}` | {count} | {meaning} |")
    for kind, meaning in kinds:
        rows = [p for p in problems if p[1] == kind]
        if not rows:
            continue
        lines += ["", f"## `{kind}` ({len(rows)})", "", meaning, "",
                  "| File | Segment (xml:id) | Detail |", "|---|---|---|"]
        for file, _, location, detail in rows:
            cells = [file, location or "-", detail or "-"]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    if failed:
        lines += ["", "## Failed pages", "", "| File | Error |", "|---|---|"]
        lines += [f"| {f} | {e.replace('|', chr(92) + '|')} |" for f, e in failed]
    Path(out_dir, "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
