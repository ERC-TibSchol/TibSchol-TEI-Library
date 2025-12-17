"""
This script processes TEI XML files to extract excerpts and their metadata
"""

import argparse
import glob
import os
from copy import deepcopy

from lxml import etree
import pandas as pd
from tqdm import tqdm

from lookup import get_instance_data

NS = {"tei": "http://www.tei-c.org/ns/1.0"}

ERRORS = []


def process_tei_body(src_body):
    text = etree.Element(f"{{{NS['tei']}}}text")
    body = etree.SubElement(text, f"{{{NS['tei']}}}body")

    # Recursive function to find all seg[@type='excerpt'] in document order
    def recursive_find_segs(element):
        for child in element:
            # check that child.tag is a string
            if not isinstance(child.tag, str):
                continue
            if (
                child.tag.endswith("seg")
                and child.get("type") == "excerpt"
                and child.get("status") in ("finalized", "reviewed", "edited")
            ):
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
        ERRORS.append({"file": os.path.basename(input_file), "problem": str(e)})
        return


def process_tei_header(src_header):
    header = etree.Element(f"{{{NS['tei']}}}teiHeader")
    # Copy all contents except revisionDesc
    # Deepcopy to avoid modifying original
    fileDesc = src_header.find("tei:fileDesc", namespaces=NS)
    title = fileDesc.find("tei:titleStmt", namespaces=NS)
    encodingDesc = src_header.find("tei:encodingDesc", namespaces=NS)
    profileDesc = src_header.find("tei:profileDesc", namespaces=NS)

    idnos = [
        el.text
        for el in src_header.xpath(".//tei:idno", namespaces=NS)
        if el.attrib.get("type") == "TibSchol"
    ]
    bad_idnos = []
    instance_data = {}
    for idno in idnos:
        try:
            instance_data = get_instance_data(idno)
            break
        except ValueError as ve:
            print(ve)
            bad_idnos.append(idno)
            continue

    if not instance_data:
        raise ValueError(f"No valid instance data found - {idnos}")

    title.find("tei:title", namespaces=NS).text = instance_data.get("work_name")
    author = title.find("tei:author", namespaces=NS)
    author.text = instance_data.get("author_name")
    author.set("ref", f"apis:{instance_data.get('author_id')}")
    principal = title.find("tei:principal", namespaces=NS)
    funder = title.find("tei:funder", namespaces=NS)
    if principal is not None:
        title.remove(principal)
    if funder is not None:
        title.remove(funder)

    # Create new <respStmt> for principal
    resp_stmt_principal = etree.Element(f"{{{NS['tei']}}}respStmt")
    resp_stmt_principal.append(principal)

    # Create new <respStmt> for funder
    resp_stmt_funder = etree.Element(f"{{{NS['tei']}}}respStmt")
    resp_stmt_funder.append(funder)

    sourceDesc = fileDesc.find("tei:sourceDesc", namespaces=NS)
    physDesc = etree.SubElement(sourceDesc, f"{{{NS['tei']}}}physDesc")
    objectDesc = etree.SubElement(physDesc, f"{{{NS['tei']}}}objectDesc")
    supportDesc = etree.SubElement(objectDesc, f"{{{NS['tei']}}}supportDesc")
    support = etree.SubElement(supportDesc, f"{{{NS['tei']}}}support")
    additional = etree.SubElement(physDesc, f"{{{NS['tei']}}}additional")
    additional.set("n", "Item description")
    additional.text = instance_data.get("item_description", "unknown")

    dimensions = etree.SubElement(support, f"{{{NS['tei']}}}dimensions")
    dimensions.set("unit", "cm")
    dimensions.set("scope", "width x height")
    dimensions.text = instance_data.get("dimension", "unknown")
    fileDesc.append(resp_stmt_principal)
    fileDesc.append(resp_stmt_funder)
    header.append(deepcopy(fileDesc))
    header.append(deepcopy(encodingDesc))
    header.append(deepcopy(profileDesc))
    if bad_idnos:
        raise ValueError(f"Bad idnos found: {bad_idnos}")
    if not idnos:
        raise ValueError("No idno with type=TibSchol found.")
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

    if ERRORS:
        pd.DataFrame(ERRORS).sort_values("file").to_markdown("errors.md", index=False)
