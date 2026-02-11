"""Transform one TEI file to HTML with tei_to_html.xsl.

Usage: python run_tei_to_html.py <input.xml> <output_dir>
(For a whole folder plus the index page, use build_site.py.)
"""
import shutil
import sys
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
_XSLT = None


def _stylesheet():
    global _XSLT
    if _XSLT is None:
        _XSLT = etree.XSLT(etree.parse(str(HERE / "tei_to_html.xsl")))
    return _XSLT


REPORT_PREFIX = "TIBREPORT|"


def transform_one(src: Path, out_dir: Path):
    """Write <stem>.html and a copy of the XML (for the 'View XML' link) into out_dir.

    Returns (html_path, problems). Each problem is a (kind, location, detail) tuple,
    collected from the xsl:message calls in tei_to_html.xsl.
    """
    src = Path(src).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    transform = _stylesheet()
    result = transform(etree.parse(str(src)), source_href=etree.XSLT.strparam(src.name))

    problems = []
    for entry in transform.error_log:
        message = entry.message.strip()
        if message.startswith(REPORT_PREFIX):
            kind, location, detail = (message[len(REPORT_PREFIX):].split("|", 2) + ["", ""])[:3]
            problems.append((kind, location, detail))

    html_path = out_dir / f"{src.stem}.html"
    html_path.write_text("<!DOCTYPE html>\n" + str(result), encoding="utf-8")
    shutil.copy2(src, out_dir / src.name)
    shutil.copytree(HERE / "assets", out_dir / "assets", dirs_exist_ok=True)
    return html_path, problems


def main() -> None:
    html_path, _ = transform_one(Path(sys.argv[1]), Path(sys.argv[2]))
    print(html_path)


if __name__ == "__main__":
    main()
