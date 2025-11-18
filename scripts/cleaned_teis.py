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


def process_tei_body(src_body):
    text = etree.Element(f"{{{NS['tei']}}}text")
    body = etree.SubElement(text, f"{{{NS['tei']}}}body")

    # Recursive function to find all seg[@type='excerpt'] in document order
    def recursive_find_segs(element):
        for child in element:
            # check that child.tag is a string
            if not isinstance(child.tag, str):
                continue
            if child.tag.endswith("seg") and child.get("type") == "excerpt":
                yield child
            # Recurse into children
            yield from recursive_find_segs(child)

    segs = list(recursive_find_segs(src_body))
    if segs:
        first_seg = segs[0]
        # Check if first_seg is not the very first node in src_body
        preceding_texts = first_seg.xpath("preceding::text()[normalize-space()]")

        if preceding_texts:
            gap = etree.Element(f"{{{NS['tei']}}}gap")
            gap.set("reason", "omitted")
            body.append(gap)

    for idx, seg in enumerate(segs):
        # Add a gap element if there is skipped content between excerpts
        if idx > 0:
            gap = etree.Element(f"{{{NS['tei']}}}gap")
            gap.set("reason", "omitted")
            body.append(gap)
        # Create new ab element and copy content of seg into it
        ab = etree.Element(f"{{{NS['tei']}}}ab")
        # Move all children of seg to ab
        ab.extend(seg)
        body.append(ab)

    return text


def process_tei_file(input_file):
    try:
        tree = etree.parse(input_file)
        root = etree.Element(
            "{http://www.tei-c.org/ns/1.0}TEI", nsmap={None: NS["tei"]}
        )
        src_header = tree.find("tei:teiHeader", namespaces=NS)
        root.append(process_tei_header(src_header))
        src_body = tree.find("tei:text/tei:body", namespaces=NS)
        root.append(process_tei_body(src_body))
        with open(f"data/excerpts/{os.path.basename(input_file)}", "wb") as f:
            f.write(
                etree.tostring(
                    root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
                )
            )
    except Exception as e:
        print("Failed to load ", input_file)
        print(e)
        return


def process_tei_header(src_header):
    header = etree.Element(f"{{{NS['tei']}}}teiHeader")
    # Copy all contents except revisionDesc
    # Deepcopy to avoid modifying original
    for child in src_header:
        if isinstance(child.tag, str) and not child.tag.endswith("revisionDesc"):
            header.append(deepcopy(child))

    idnos = [el.text for el in src_header.xpath(".//tei:idno", namespaces=NS)]
    print(idnos)
    return header


def extract_inner_element(element, wrapper_tag="ab", nsmap=None):
    new_elem = etree.Element(wrapper_tag, nsmap=nsmap)

    # Add the leading text from the original element
    if element.text:
        new_elem.text = element.text

    # Deep copy each child and append to new element
    for child in element:
        new_child = deepcopy(child)
        new_elem.append(new_child)

    return new_elem


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process TEI XML files for excerpts.")
    parser.add_argument(
        "tei_repo_glob", help="Glob pattern for TEI XML files (e.g., '/path/to/*.xml')"
    )
    args = parser.parse_args()
    os.makedirs("data/excerpts", exist_ok=True)
    tei_repo = glob.glob(args.tei_repo_glob)
    print(len(tei_repo), "files found")
    for file in tqdm(tei_repo):
        process_tei_file(file)
