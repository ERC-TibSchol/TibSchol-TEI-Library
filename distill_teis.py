"""
This script processes TEI XML files to extract excerpts and their metadata
"""

import argparse
import glob
import os
from copy import deepcopy

from lxml import etree
from tqdm import tqdm


NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def process_tei_files(tei_repo):
    out_dir = "data/excerpts"
    os.makedirs(out_dir, exist_ok=True)

    for tei_filename in tqdm(tei_repo, total=len(tei_repo)):
        try:
            tree = etree.parse(tei_filename)
        except Exception:
            print("Failed to load ", tei_filename)
            continue

        # All refs still available if needed
        seg_elements = tree.xpath(
            '//tei:seg[@type="excerpt" and (@status="finalized" or @status="reviewed" or @status="edited")]',
            namespaces=NS,
        )
        if not seg_elements:
            continue

        # Build new TEI root
        root = etree.Element(
            "{http://www.tei-c.org/ns/1.0}TEI", nsmap={None: NS["tei"]}
        )

        # Copy teiHeader from source
        src_header = tree.find("tei:teiHeader", namespaces=NS)
        if src_header is not None:
            root.append(deepcopy(src_header))

        # Add text/body
        text = etree.SubElement(root, "{http://www.tei-c.org/ns/1.0}text")
        body = etree.SubElement(text, "{http://www.tei-c.org/ns/1.0}body")

        # Deep-copy qualifying segs into body
        for seg in seg_elements:
            body.append(deepcopy(seg))

        # Write new TEI file with the same filename
        out_path = os.path.join(out_dir, os.path.basename(tei_filename))
        with open(out_path, "wb") as f:
            f.write(
                etree.tostring(
                    root, encoding="UTF-8", pretty_print=True, xml_declaration=True
                )
            )

        print(f"Extracted {len(seg_elements)} finalized/reviewed excerpts → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process TEI XML files for excerpts.")
    parser.add_argument(
        "tei_repo_glob", help="Glob pattern for TEI XML files (e.g., '/path/to/*.xml')"
    )
    args = parser.parse_args()

    tei_repo = glob.glob(args.tei_repo_glob)
    print(len(tei_repo), "files found")
    process_tei_files(tei_repo)
