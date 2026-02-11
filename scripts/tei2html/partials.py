"""Shared header and footer for the static pages (index, key, excerpts).

The markup lives in partials/header.xml and partials/footer.xml. The XSLT includes them with
document(); the Python pages (index and key) read them here, so all pages show the same header and footer.
"""

from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent


def partial_html(name):
    """Return the HTML of partials/<name>: the root element's contents for the header, the whole element for the footer."""
    root = etree.parse(str(HERE / "partials" / name)).getroot()
    # method="html": empty elements such as <div></div> are written as HTML, not as self-closing tags
    if root.tag == "footer":
        return etree.tostring(root, encoding="unicode", method="html")
    return "".join([root.text or ""] + [etree.tostring(child, encoding="unicode", method="html") for child in root])
