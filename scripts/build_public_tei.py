"""
Build the public version of TibSchol TEI files.

The public file is the source TEI itself, cleaned and enriched, rather than a
rebuilt skeleton:

* teiHeader: copied from the source, enriched from the APIS CSV exports
  (title, all authors, one sourceDesc/msDesc per instance, rebuilt from the
  CSVs; the source has no msDesc), availability set to public, revisionDesc
  dropped (use --keep-revision-desc to keep it), comments and PIs removed.
  encodingDesc/listPrefixDef: the 'apis' and 'db' declarations are replaced
  by type-specific prefixes (person, work, place, inst, ...).
* standOff: the persons, works and places the file refers to, and the
  relations whose two ends are both in the file (names from the ODD).
* text: references db:NNNN become person:/work:/place:NNNN by rs @type or
  by the export table.
* text: the original structure (ab with its @type, @xml:space, ...) is kept,
  but only curated segs survive (see KEEP_TYPES / KEEP_STATUSES). Wherever
  text was removed a single <gap reason="omitted"/> is inserted. Comments and
  PIs are removed without losing the text that follows them.
* A kept seg that does not open with a pb/lb gets a copy of the nearest
  preceding pb and lb (only those elements) right before it, per witness
  (@edRef) in multi-witness files.
* part/next chains that run through an omitted seg are relinked across the
  omission and their @part values recomputed.

Usage:
    python scripts/build_public_tei.py "data/examples/*.xml" -o data/excerpts [--rng data/tei_all.rng]
"""

import argparse
import datetime
import json
import ast
import glob
import logging
import os
import re
from bisect import bisect_left
from copy import deepcopy
from pathlib import Path

import pandas as pd
from lxml import etree
from tqdm import tqdm

NS = {"tei": "http://www.tei-c.org/ns/1.0"}
TEI = f"{{{NS['tei']}}}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

KEEP_TYPES = ("excerpt", "shared")
KEEP_STATUSES = ("finalized", "reviewed", "edited")

# Attributes whose values may use private URI prefixes (prefix:value)
POINTER_ATTRS = ("ref", "ana", "target", "corresp", "source", "key", "sameAs")
STANDARD_SCHEMES = ("http", "https", "mailto", "urn", "doi", "file")

ERRORS = []

# Generation date, written as the publication date of every file built in this run
GENERATED_ON = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def is_element(node):
    return isinstance(node.tag, str)


def is_curated_seg(el):
    return (
        is_element(el)
        and el.tag == f"{TEI}seg"
        and el.get("type") in KEEP_TYPES
        and el.get("status") in KEEP_STATUSES
    )


def has_curated_descendant(el):
    return any(is_curated_seg(d) for d in el.iterdescendants())


def has_text(el):
    """True if the element contains any non-whitespace text (comments excluded)."""
    return any(t.strip() for t in el.xpath(".//text()"))


def _join_text(before, after):
    """Join the text around a removed node, collapsing the padding that was
    only there because of the node (e.g. 'phag mo        <!--=X--> la')."""
    before = before or ""
    after = after or ""
    stripped = before.rstrip(" \t")
    if not after:
        return stripped
    if stripped != before and not after[0].isspace():
        return f"{stripped} {after}"
    return stripped + after


def drop_node(node):
    """Remove a node but keep its tail text (lxml's remove() drops the tail)."""
    parent = node.getparent()
    if parent is None:
        return
    prev = node.getprevious()
    if prev is not None:
        prev.tail = _join_text(prev.tail, node.tail)
    else:
        parent.text = _join_text(parent.text, node.tail)
    parent.remove(node)


def remove_comments_and_pis(elem):
    for node in elem.xpath(".//comment() | .//processing-instruction()"):
        drop_node(node)


def tei(tag, text=None, **attrib):
    el = etree.Element(f"{TEI}{tag}", attrib)
    if text is not None:
        el.text = text
    return el


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------


def _text_before_first(seg, tag, edref):
    """True if the seg has non-whitespace text before its first `tag` element
    for witness `edref` (or has none at all). Same rule as extract_excerpts'
    location logic, but comment/PI content and notes don't count as text."""

    def walk(el):
        if el.text and is_element(el):
            yield "text", el.text
        for c in el:
            if is_element(c):
                yield "elem", c
                if c.tag != f"{TEI}note":
                    yield from walk(c)
            if c.tail:
                yield "text", c.tail

    for kind, value in walk(seg):
        if kind == "text" and value.strip():
            return True
        if kind == "elem" and value.tag == tag and value.get("edRef") == edref:
            return False
    return True


class BreakIndex:
    """Document-order index of pb/lb, built once per file so looking up the
    nearest preceding pb/lb is a bisect instead of an XPath preceding:: scan
    (which made big files quadratic)."""

    def __init__(self, src_text):
        # keep references to the proxies so lxml hands back the same objects
        self._elements = list(src_text.iter(etree.Element))
        self.order = {el: i for i, el in enumerate(self._elements)}
        self.positions = {}  # (tag, edRef) -> ([index...], [element...])
        for i, el in enumerate(self._elements):
            if el.tag in (f"{TEI}pb", f"{TEI}lb"):
                idx, els = self.positions.setdefault(
                    (el.tag, el.get("edRef")), ([], [])
                )
                idx.append(i)
                els.append(el)

    def preceding(self, el, tag, edref=None, any_witness=False):
        """Nearest pb/lb before `el` for witness `edref` (or any witness)."""
        start = self.order[el]
        best, best_i = None, -1
        for (t, e), (idx, els) in self.positions.items():
            if t != tag or (not any_witness and e != edref):
                continue
            k = bisect_left(idx, start) - 1
            if k >= 0 and idx[k] > best_i:
                best, best_i = els[k], idx[k]
        return best


def carried_breaks(seg, index):
    """Nearest preceding pb and lb for a seg that does not open with one,
    per witness (@edRef), unless that pb/lb is already published inside
    another kept seg. Witnesses are the ones whose pb/lb occur in the seg;
    if it has none, the witness of the nearest preceding lb."""
    edrefs = {b.get("edRef") for b in seg.iter(f"{TEI}pb", f"{TEI}lb")}
    if not edrefs:
        prev = index.preceding(seg, f"{TEI}lb", any_witness=True)
        edrefs = {prev.get("edRef")} if prev is not None else set()

    breaks = []
    for edref in sorted(edrefs, key=lambda e: e or ""):
        for name in ("pb", "lb"):
            if not _text_before_first(seg, f"{TEI}{name}", edref):
                continue
            prev = index.preceding(seg, f"{TEI}{name}", edref)
            if prev is not None and not any(
                is_curated_seg(a) for a in prev.iterancestors()
            ):
                breaks.append(prev)
    # keep the copies in source document order
    return sorted(breaks, key=index.order.__getitem__)


class _Builder:
    """Copies `src` into `out`, keeping only curated segs and the elements
    that contain them, and inserting one <gap/> per run of removed text."""

    def __init__(self, out, index):
        self.out = out
        self.index = index
        self.last_is_gap = False

    def _add_whitespace(self, text):
        if not text:
            return
        if len(self.out):
            self.out[-1].tail = (self.out[-1].tail or "") + text
        else:
            self.out.text = (self.out.text or "") + text

    def _add_gap(self):
        if not self.last_is_gap:
            self.out.append(tei("gap", reason="omitted"))
            self.last_is_gap = True

    def _add_text(self, text):
        if text and text.strip():
            self._add_gap()
        else:
            self._add_whitespace(text)

    def _add_element(self, el):
        self.out.append(el)
        self.last_is_gap = False

    def run(self, src):
        self._add_text(src.text)
        for child in src:
            if not is_element(child):  # comment / PI
                pass
            elif is_curated_seg(child):
                for brk in carried_breaks(child, self.index):
                    copy = deepcopy(brk)
                    copy.tail = None
                    self._add_element(copy)
                seg = deepcopy(child)
                seg.tail = None
                remove_comments_and_pis(seg)
                self._add_element(seg)
            elif child.tag == f"{TEI}body" or has_curated_descendant(child):
                shell = etree.Element(child.tag, dict(child.attrib))
                self._add_element(shell)
                _Builder(shell, self.index).run(child)
            elif has_text(child) and child.tag in (f"{TEI}lem", f"{TEI}rdg"):
                # gap is not allowed directly in app: keep the reading's
                # shell (and its @wit) with the gap inside
                shell = etree.Element(child.tag, dict(child.attrib))
                shell.append(tei("gap", reason="omitted"))
                self._add_element(shell)
            elif has_text(child):
                self._add_gap()
            self._add_text(child.tail)


def build_public_text(src_text):
    out = etree.Element(src_text.tag, dict(src_text.attrib))
    _Builder(out, BreakIndex(src_text)).run(src_text)
    return out


def relink_chains(src_root, out_text, warnings):
    """Relink part/next chains across omitted segs and recompute @part."""
    src_segs = {s.get(XML_ID): s for s in src_root.iter(f"{TEI}seg") if s.get(XML_ID)}
    kept = {s.get(XML_ID): s for s in out_text.iter(f"{TEI}seg") if s.get(XML_ID)}
    targets = {s.get("next") for s in src_segs.values() if s.get("next")}

    for start_id, start in src_segs.items():
        if not start.get("next") or start_id in targets:
            continue  # not the head of a chain
        chain, seen, cur = [], set(), start_id
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            if cur not in src_segs:
                warnings.append(f"chain {start_id}: @next points to missing id {cur}")
                break
            cur = src_segs[cur].get("next")

        kept_chain = [i for i in chain if i in kept]
        if kept_chain == [i for i in chain if i in src_segs]:
            continue  # nothing omitted
        omitted = [i for i in chain if i in src_segs and i not in kept]
        warnings.append(
            f"chain {start_id}: omitted {', '.join(omitted)}; relinked "
            f"{' -> '.join(kept_chain) or '(nothing kept)'}"
        )
        for pos, seg_id in enumerate(kept_chain):
            seg = kept[seg_id]
            for attr in ("next", "prev"):
                seg.attrib.pop(attr, None)
            if len(kept_chain) == 1:
                seg.attrib.pop("part", None)
                continue
            if pos + 1 < len(kept_chain):
                seg.set("next", kept_chain[pos + 1])
            seg.set(
                "part", "I" if pos == 0 else "F" if pos == len(kept_chain) - 1 else "M"
            )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


def _parse_dimensions(value):
    """'8.5 x 52' -> ('8.5', '52'); anything else -> None."""
    m = re.match(r"^\s*([\d.,]+)\s*[x×X*]\s*([\d.,]+)\s*(cm)?\s*$", value or "")
    return (m.group(1), m.group(2)) if m else None


# ---------------------------------------------------------------------------
# Database export (CSV) and controlled vocabulary
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Error reports of every run (overwritten each run): data/errors/errors.md and errors_by_type.md
ERRORS_DIR = DATA_DIR / "errors"
ODD_PATH = DATA_DIR.parent / "tei_odd" / "TibSchol.odd"  # symlink to the ODD in its own repo
ODD_NS = {"t": "http://www.tei-c.org/ns/1.0"}

# Type-specific prefixes. An APIS pk is written as <prefix>:<pk> in the TEI;
# prefixDef maps it to the local xml:id <prefix><pk> (e.g. person:3933 -> #person3933).
ENTITY_PREFIXES = ("person", "work", "place", "inst", "deity", "school")
RS_TYPE_TO_PREFIX = {"person": "person", "work": "work", "place": "place",
                     "deity": "deity", "school": "school"}
# Attributes that hold pointers or references
POINTER_REF_ATTRS = ("ref", "target", "wit", "edRef", "corresp", "source", "sameAs", "key")
REF_RE = re.compile(r"^(person|work|place|inst|deity|school):(\d+)$")
# APIS entity type (from the URL) -> prefix
APIS_KIND_TO_PREFIX = {"person": "person", "work": "work", "instance": "inst", "place": "place"}
CONFIDENCE_TO_TYPE = {"Positive": "positive", "Uncertain": "uncertain", "Negative": "negative"}


def _odd_values(ident, attr):
    odd = etree.parse(str(ODD_PATH))
    return {
        v.get("ident")
        for v in odd.xpath(
            f'//t:elementSpec[@ident="{ident}"]//t:attDef[@ident="{attr}"]//t:valItem',
            namespaces=ODD_NS,
        )
    }


RELATION_NAMES = _odd_values("relation", "name")

# Citations of the printed sets (Zotero short title, key), as in citation.py: "<short title>, vol. N, pp. P"
CITATIONS_PATH = Path(__file__).resolve().parent / "citations.json"
CITATIONS = json.loads(CITATIONS_PATH.read_text(encoding="utf-8")) if CITATIONS_PATH.exists() else {}
ZOTERO_ITEM = "https://www.zotero.org/groups/4394244/tibschol/items/{key}"
# Zotero records of the references in instances.zotero_ref (key -> short title, year)
ZOTERO_PATH = DATA_DIR / "zotero.csv"
ZOTERO = (pd.read_csv(ZOTERO_PATH, dtype=str).fillna("").set_index("zoteroId").to_dict("index")
          if ZOTERO_PATH.exists() else {})


def _pk(url):
    m = re.search(r"/(\d+)/?$", str(url or ""))
    return int(m.group(1)) if m else None


def _load_export(name):
    df = pd.read_csv(DATA_DIR / f"{name}.csv", dtype=str).fillna("")
    df.index = [_pk(u) for u in df["url"]]
    return df


PERSONS = _load_export("persons")
WORKS = _load_export("works")
INSTANCES = _load_export("instances")
PLACES = _load_export("places")  # name column is "label"


def _entity_key(ref):
    """{'url': '.../apis_ontology.person/3933/', ...} -> ('person', 3933)."""
    m = re.search(r"apis_ontology\.(\w+)/(\d+)/?", ref.get("url", ""))
    if not m or m.group(1) not in APIS_KIND_TO_PREFIX:
        return None
    return APIS_KIND_TO_PREFIX[m.group(1)], int(m.group(2))


def relation_name(rel):
    """Active-form relation name from the label, e.g. 'author-of'."""
    text = rel["label"]
    for side in ("subj", "obj"):
        text = text.replace(rel[side]["label"], "")
    text = re.sub(r"\(\d+\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("uncle"):  # "uncle (maternal/paternal) of" -> "uncle-of"
        return "uncle-of"
    return text.replace(" ", "-")


def _relations_of(df, pk):
    raw = df.loc[pk, "relations"] if pk in df.index else ""
    return ast.literal_eval(raw) if raw else []


# Every relation once, with its endpoints and name resolved
RELATION_INDEX = []
_seen_relations = set()
for _df in (PERSONS, WORKS, INSTANCES, PLACES):
    for _pk_value in _df.index:
        if _pk_value is None:
            continue
        for _rel in _relations_of(_df, _pk_value):
            if _rel["id"] in _seen_relations:
                continue
            _seen_relations.add(_rel["id"])
            RELATION_INDEX.append({
                "id": _rel["id"],
                "subj": _entity_key(_rel["subj"]),
                "obj": _entity_key(_rel["obj"]),
                "name": relation_name(_rel),
                "confidence": _rel.get("confidence", ""),
                "tei_refs": _rel.get("tei_refs", "") or "",
            })

# Instances by each TibSchol reference in tibschol_ref (free text: ids may be separated by spaces, commas or line breaks)
TIBSCHOL_INDEX = {}
for _pk_value, _ref in INSTANCES["tibschol_ref"].items():
    for _tok in re.split(r"[\s,;]+", (_ref or "").strip()):
        if _tok:
            TIBSCHOL_INDEX.setdefault(_tok, []).append(_pk_value)


def _clean_name(text):
    """Drop the APIS disambiguator, e.g. 'rin chen bzang po (1)'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", text or "").strip()


def _clean_bo(text):
    """Drop the APIS number at the end of a Tibetan name, e.g. '༼༡༽'."""
    return re.sub(r"\s*༼[^༽]*༽\s*$", "", text or "").strip()


def _literal_list(text):
    try:
        value = ast.literal_eval(text) if text else []
    except (ValueError, SyntaxError):
        return []
    return value if isinstance(value, list) else []


def _iso(text):
    return text if re.match(r"^\d{4}-\d{2}-\d{2}$", text or "") else ""


def manuscript_ids(src_header):
    ids = []
    for el in src_header.xpath(
        "tei:fileDesc/tei:publicationStmt/tei:idno[@type='TibSchol']", namespaces=NS
    ):
        value = (el.text or "").strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def works_of_instance(pk):
    works = []
    for rel in _relations_of(INSTANCES, pk):
        if relation_name(rel) == "has-as-an-instance":
            key = _entity_key(rel["subj"])
            if key and key[0] == "work" and key[1] not in works:
                works.append(key[1])
    return works


def authors_of_work(pk):
    """All authors, not only the first (a work can have several)."""
    authors = []
    for rel in _relations_of(WORKS, pk):
        if relation_name(rel) != "author-of":
            continue
        subj, obj = _entity_key(rel["subj"]), _entity_key(rel["obj"])
        if subj and subj[0] == "person" and obj == ("work", pk) and subj[1] not in authors:
            authors.append(subj[1])
    return authors


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


def _volume_text(value):
    """'1.0' -> '1' (the database stores volumes as floats)."""
    try:
        number = float(value)
    except ValueError:
        return value
    return str(int(number)) if number.is_integer() else value


def _text_with_line_breaks(p, text):
    """Keep the line breaks of a text as <lb/> elements inside the element p."""
    lines = [line.rstrip("\r") for line in re.split(r"\r?\n", text.strip())]
    p.text = lines[0]
    for line in lines[1:]:
        lb = tei("lb")
        lb.tail = line
        p.append(lb)
    return p


def build_zotero_bibls(row, warnings):
    """One <bibl> per Zotero key in instances.zotero_ref: short title linked to the Zotero item, then the year.
    Keys are separated by line breaks or spaces; brackets around a key (as used in the comments) are removed."""
    bibls = []
    for token in re.split(r"[\s,;]+", row["zotero_ref"].strip()):
        key = token.strip("[]")
        if not key:
            continue
        record = ZOTERO.get(key)
        if record is None:
            warnings.append(f"Zotero key '{key}' is not in zotero.csv; kept as text")
            bibls.append(tei("bibl", key))
            continue
        short = record.get("shortTitle", "").strip() or key
        bibl = tei("bibl")
        ref = tei("ref", short, target=ZOTERO_ITEM.format(key=key))
        bibl.append(ref)
        year = record.get("year", "").strip()
        if year:
            ref.tail = ", "
            bibl.append(tei("date", year))
        bibls.append(bibl)
    return bibls


def build_citation(row, warnings):
    """<bibl> for the printed set: short title (linked to the Zotero item), volume, pages and text number."""
    items = []
    set_num = row["set_num"]
    if set_num:
        cit = CITATIONS.get(set_num)
        if cit:
            short = (cit.get("data", {}).get("shortTitle") or "").strip() or cit["key"]
            items.append(tei("ref", short, target=ZOTERO_ITEM.format(key=cit["key"])))
        else:
            warnings.append(f"set '{set_num}' has no entry in citations.json")
            items.append(tei("title", set_num))
    if row["volume"]:
        items.append(tei("biblScope", _volume_text(row["volume"]), unit="vol"))
    if row["pp_kdsb"]:
        items.append(tei("biblScope", row["pp_kdsb"], unit="pp"))
    if row["sb_text_number"]:
        items.append(tei("biblScope", row["sb_text_number"], unit="text"))
    if not items:
        return None
    bibl = tei("bibl")
    for i, item in enumerate(items):
        if i:
            items[i - 1].tail = ", "
        bibl.append(item)
    return bibl


# Relations of a manuscript that are written in its header (not in listRelation)
HEADER_PERSON_ROLES = {"scribe-of": "scribe", "owner-of": "owner", "sponsor-of": "sponsor", "annotator-of": "annotator"}
HEADER_COVERED_RELATIONS = set(HEADER_PERSON_ROLES) | {"written-at", "has-source"}


def header_people(inst_pk):
    """(role, person pk) for the people related to the manuscript, in the order of the relations."""
    people = []
    for rel in _relations_of(INSTANCES, inst_pk):
        role = HEADER_PERSON_ROLES.get(relation_name(rel))
        person = _entity_key(rel["subj"])
        if role and person and person[0] == "person" and (role, person[1]) not in people:
            people.append((role, person[1]))
    return people


def written_at_places(inst_pk):
    places = []
    for rel in _relations_of(INSTANCES, inst_pk):
        if relation_name(rel) == "written-at":
            place = _entity_key(rel["obj"])
            if place and place[0] == "place" and place[1] not in places:
                places.append(place[1])
    return places


def source_links(inst_pk):
    """('source', pk) when this manuscript has the other as its source; ('isSourceFor', pk) when it is the source."""
    links = []
    for rel in _relations_of(INSTANCES, inst_pk):
        if relation_name(rel) != "has-source":
            continue
        subj, obj = _entity_key(rel["subj"]), _entity_key(rel["obj"])
        if not (subj and obj and subj[0] == "inst" and obj[0] == "inst"):
            continue
        if subj[1] == inst_pk and ("source", obj[1]) not in links:
            links.append(("source", obj[1]))
        if obj[1] == inst_pk and ("isSourceFor", subj[1]) not in links:
            links.append(("isSourceFor", subj[1]))
    return links


def build_ms_desc(inst_pk, manuscript_ids_for_inst, work_pks, warnings):
    row = INSTANCES.loc[inst_pk]
    ms = etree.Element(f"{TEI}msDesc")
    ms.set(XML_ID, f"inst{inst_pk}")

    ident = etree.SubElement(ms, f"{TEI}msIdentifier")
    ident.append(tei("idno", str(inst_pk), type="APIS"))
    for eid in manuscript_ids_for_inst:
        ident.append(tei("idno", eid, type="TibSchol"))
    signature = " ".join(x for x in (row["signature_letter"], row["signature_number"]) if x)
    if signature:
        ident.append(tei("idno", signature, type="signature"))
    if row["drepung_number"]:
        ident.append(tei("idno", row["drepung_number"], type="drepung"))
    for link in re.split(r"\s+", row["external_links"].strip()):
        if "bdrc" in link:
            ident.append(tei("idno", link, type="BDRC"))
    if row["name"]:
        ident.append(tei("msName", row["name"]))
    if row["tibetan_transliteration"]:
        ident.append(tei("msName", _clean_bo(row["tibetan_transliteration"]),
                         **{"{http://www.w3.org/XML/1998/namespace}lang": "bo"}))
    for alt in _literal_list(row["alternative_names"]):
        label = (alt.get("label") or "").strip() if isinstance(alt, dict) else ""
        if label:
            attrs = {"type": "alt"}
            if alt.get("language"):
                attrs["{http://www.w3.org/XML/1998/namespace}lang"] = alt["language"]
            ident.append(tei("msName", label, **attrs))

    if work_pks:
        contents = etree.SubElement(ms, f"{TEI}msContents")
        for wpk in work_pks:
            item = etree.SubElement(contents, f"{TEI}msItem")
            work_name = WORKS.loc[wpk, "name"] if wpk in WORKS.index else ""
            if not work_name:
                warnings.append(f"work {wpk} of instance {inst_pk} not in export")
            title = tei("title", work_name or None)
            title.set("ref", f"work:{wpk}")
            item.append(title)

    item_description = row["item_description"].strip()
    dimension = row["dimension"].strip()
    folios = row["num_folios"].strip()
    if item_description or dimension or folios:
        supports = etree.SubElement(
            etree.SubElement(etree.SubElement(ms, f"{TEI}physDesc"), f"{TEI}objectDesc"),
            f"{TEI}supportDesc",
        )
        if item_description or dimension:
            support = etree.SubElement(supports, f"{TEI}support")
            if item_description:
                support.append(_text_with_line_breaks(tei("p"), item_description))
            if dimension:
                dims = _parse_dimensions(dimension)
                dimensions = etree.SubElement(support, f"{TEI}dimensions", unit="cm")
                if dims:
                    dimensions.append(tei("width", dims[0]))
                    dimensions.append(tei("height", dims[1]))
                else:
                    warnings.append(f"dimension '{dimension}' is not 'W x H'; kept as text")
                    dimensions.append(tei("p", dimension))
        if folios:
            supports.append(tei("extent", folios))

    people = header_people(inst_pk)
    scribes = [pk for role, pk in people if role == "scribe"]
    sponsors = [pk for role, pk in people if role == "sponsor"]
    owners = [pk for role, pk in people if role == "owner"]
    annotators = [pk for role, pk in people if role == "annotator"]
    written_at = written_at_places(inst_pk)
    sources = source_links(inst_pk)

    def person_name(ppk):
        if ppk not in PERSONS.index:
            warnings.append(f"person {ppk} in a manuscript relation is not in the export")
            return str(ppk)
        return _clean_name(PERSONS.loc[ppk, "name"])

    if row["provenance"] or owners or written_at or scribes or sponsors or sources:
        history = etree.SubElement(ms, f"{TEI}history")
        if written_at or scribes or sponsors or sources:
            origin = etree.SubElement(history, f"{TEI}origin")
            for ppk in written_at:
                label = PLACES.loc[ppk, "label"] if ppk in PLACES.index else ""
                if not label:
                    warnings.append(f"written-at place {ppk} not in the place export")
                origin.append(tei("origPlace", label or None, ref=f"place:{ppk}"))
            for ppk in scribes:
                origin.append(tei("persName", person_name(ppk), ref=f"person:{ppk}", role="scribe"))
            for ppk in sponsors:
                origin.append(tei("persName", person_name(ppk), ref=f"person:{ppk}", role="sponsor"))
            for kind, other in sources:
                if other not in INSTANCES.index:
                    warnings.append(f"source manuscript {other} is not in the export")
                    continue
                other_row = INSTANCES.loc[other]
                bibl = tei("bibl", type=kind)
                bibl.append(tei("name", _clean_name(other_row["name"])))
                for token in re.split(r"[\s,;]+", other_row["tibschol_ref"].strip()):
                    if token:
                        bibl.append(tei("idno", token, type="TibSchol"))
                bibl.append(tei("idno", str(other), type="APIS"))
                origin.append(bibl)
        if row["provenance"] or owners:
            provenance = tei("provenance")
            if row["provenance"]:
                provenance.text = row["provenance"]
            for ppk in owners:
                if len(provenance):
                    provenance[-1].tail = ", "
                provenance.append(tei("persName", person_name(ppk), ref=f"person:{ppk}", role="owner"))
            history.append(provenance)

    if annotators:
        phys = ms.find(f"{TEI}physDesc")
        if phys is None:
            phys = etree.SubElement(ms, f"{TEI}physDesc")
        additions = etree.SubElement(phys, f"{TEI}additions")
        p = tei("p", "Annotated by ")
        for i, ppk in enumerate(annotators):
            if i:
                p[-1].tail = ", "
            p.append(tei("persName", person_name(ppk), ref=f"person:{ppk}", role="annotator"))
        additions.append(p)

    # additional: adminInfo first, then the citations (TEI order)
    set_bibl = build_citation(row, warnings)
    citations = ([set_bibl] if set_bibl is not None else []) + build_zotero_bibls(row, warnings)
    if row["availability"] or row["comments"] or citations:
        additional = etree.SubElement(ms, f"{TEI}additional")
        if row["availability"] or row["comments"]:
            info = etree.SubElement(additional, f"{TEI}adminInfo")
            if row["availability"]:
                availability = tei("availability")
                availability.append(tei("p", row["availability"]))
                info.append(availability)
            if row["comments"]:
                info.append(tei("note", row["comments"], type="comment"))
        if citations:
            list_bibl = etree.SubElement(additional, f"{TEI}listBibl")
            for citation in citations:
                list_bibl.append(citation)
    return ms


# Licence of the public TEI files and of the HTML pages built from them (same as the repository's LICENSE).
# Set here by the build, not copied from the source files, which still carry CC BY 4.0.
PUBLIC_LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
PUBLIC_LICENCE_TEXT = ("The Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0) "
                       "licence applies to this document.")


def set_public_licence(pub):
    """Set the licence in publicationStmt/availability: target URL and statement text."""
    avail = pub.find("tei:availability", namespaces=NS)
    if avail is None:
        avail = tei("availability")
        pub.append(avail)
    licence = avail.find("tei:licence", namespaces=NS)
    if licence is None:
        licence = tei("licence")
        avail.append(licence)
    licence.set("target", PUBLIC_LICENCE_URL)
    p = licence.find("tei:p", namespaces=NS)
    if p is None:
        p = tei("p")
        licence.append(p)
    p.text = PUBLIC_LICENCE_TEXT


def build_public_header(src_header, instance_pks, inst_ids, work_pk, author_pks,
                        work_pks_by_inst, warnings, keep_revision_desc=False):
    header = deepcopy(src_header)
    remove_comments_and_pis(header)
    title_stmt = header.find("tei:fileDesc/tei:titleStmt", namespaces=NS)

    titles = title_stmt.findall("tei:title", namespaces=NS)
    main_title = next((t for t in titles if t.get("type") == "main"), titles[0] if titles else None)
    if work_pk is not None and work_pk in WORKS.index:
        row = WORKS.loc[work_pk]
        if main_title is None:
            main_title = tei("title", type="main")
            title_stmt.insert(0, main_title)
        main_title.text = row["name"]
        for child in list(main_title):
            main_title.remove(child)
        if row["tibetan_transliteration"]:
            bo = next((t for t in titles if t.get("{http://www.w3.org/XML/1998/namespace}lang") == "bo"), None)
            if bo is None:
                bo = tei("title")
                bo.set("{http://www.w3.org/XML/1998/namespace}lang", "bo")
                main_title.addnext(bo)
            bo.text = _clean_bo(row["tibetan_transliteration"])
    else:
        warnings.append("work not in export; kept the source title")

    # Authors: one <author> per author of the work; none are dropped
    for old in title_stmt.findall("tei:author", namespaces=NS):
        title_stmt.remove(old)
    anchor = title_stmt.findall("tei:title", namespaces=NS)[-1]
    if author_pks:
        for apk in reversed(author_pks):
            author = tei("author", _clean_name(PERSONS.loc[apk, "name"]) if apk in PERSONS.index else None)
            author.set("ref", f"person:{apk}")
            anchor.addnext(author)
    else:
        warnings.append("no author of the work in export")

    # sourceDesc: one msDesc per instance
    source_desc = header.find("tei:fileDesc/tei:sourceDesc", namespaces=NS)
    had_content = any(has_text(c) or len(c) for c in source_desc)
    if had_content:
        warnings.append("sourceDesc had content; replaced by msDesc per instance")
    for child in list(source_desc):
        source_desc.remove(child)
    source_desc.text = None
    for ipk in instance_pks:
        source_desc.append(build_ms_desc(ipk, inst_ids[ipk], work_pks_by_inst[ipk], warnings))

    # Publication date = the date these TEI files are generated
    pub = header.find("tei:fileDesc/tei:publicationStmt", namespaces=NS)
    date_el = pub.find("tei:date", namespaces=NS)
    if date_el is None:
        date_el = tei("date")
        pub.append(date_el)
    date_el.text = GENERATED_ON
    date_el.set("when", GENERATED_ON)
    for avail in header.iterfind("tei:fileDesc/tei:publicationStmt/tei:availability", namespaces=NS):
        avail.set("status", "free")
    set_public_licence(pub)
    if not keep_revision_desc:
        rev = header.find("tei:revisionDesc", namespaces=NS)
        if rev is not None:
            header.remove(rev)
    return header


def set_prefix_defs(header, used_prefixes):
    """Replace the declared prefixes: drop the old 'apis' and 'db' declarations,
    keep the project's own (corpusmd, per, zot), and declare the entity prefixes in use."""
    enc = header.find("tei:encodingDesc", namespaces=NS)
    if enc is None:
        enc = tei("encodingDesc")
        header.find("tei:fileDesc", namespaces=NS).addnext(enc)
    lst = enc.find("tei:listPrefixDef", namespaces=NS)
    if lst is None:
        lst = etree.SubElement(enc, f"{TEI}listPrefixDef")
    for old in lst.findall("tei:prefixDef", namespaces=NS):
        if old.get("ident") in ("apis", "db"):
            lst.remove(old)
    declared = {p.get("ident") for p in lst.findall("tei:prefixDef", namespaces=NS)}
    for prefix in sorted(used_prefixes):
        if prefix in declared:
            continue
        pd_el = tei("prefixDef", ident=prefix, matchPattern="^(\\d+)$",
                    replacementPattern=f"#{prefix}$1")
        pd_el.append(tei("p", f"Local identifier of a {prefix} record from the APIS export; "
                              f"resolves to the element with xml:id '{prefix}' followed by the number."))
        lst.append(pd_el)


# ---------------------------------------------------------------------------
# Body references
# ---------------------------------------------------------------------------


def _kind_of_pk(pk):
    """APIS pks are unique across persons, works and instances, so the table tells the kind."""
    if pk in PERSONS.index:
        return "person"
    if pk in WORKS.index:
        return "work"
    if pk in INSTANCES.index:
        return "inst"
    if pk in PLACES.index:
        return "place"
    return None


def convert_body_prefixes(text, warnings):
    """db:NNNN -> person:NNNN / work:NNNN / place:NNNN / deity:NNNN / school:NNNN.
    The kind comes from the rs @type when there is one (rs is typed), otherwise from
    the export tables (quote/@source has no type). Other prefixes are left alone."""
    for el in text.iter(etree.Element):
        for attr in POINTER_REF_ATTRS:
            value = el.get(attr)
            if not value or not value.startswith("db:"):
                continue
            pk = int(value[3:]) if value[3:].isdigit() else None
            kind = el.get("type") if el.tag == f"{TEI}rs" else None
            if kind not in RS_TYPE_TO_PREFIX:
                kind = _kind_of_pk(pk) if pk is not None else None
                if kind == "inst":
                    kind = None  # instances are referenced as inst:, never db:
            if kind in RS_TYPE_TO_PREFIX:
                el.set(attr, f"{RS_TYPE_TO_PREFIX[kind]}:{pk}")
            else:
                warnings.append(f"'{value}' on <{etree.QName(el).localname}>: kind unknown (not in the export); left as db:")


def collect_refs(root):
    found = set()
    for el in root.iter(etree.Element):
        for attr in POINTER_REF_ATTRS:
            for token in (el.get(attr) or "").split():
                m = REF_RE.match(token)
                if m:
                    found.add((m.group(1), int(m.group(2))))
    return found


def used_prefixes(root):
    prefixes = set()
    for el in root.iter(etree.Element):
        for attr in POINTER_REF_ATTRS:
            for token in (el.get(attr) or "").split():
                m = re.match(r"^([A-Za-z][\w.+-]*):", token)
                if m:
                    prefixes.add(m.group(1))
    return prefixes


# ---------------------------------------------------------------------------
# standOff: persons, works and relations
# ---------------------------------------------------------------------------


def _person_element(pk):
    row = PERSONS.loc[pk]
    person = tei("person", **{XML_ID: f"person{pk}"})
    person.append(tei("persName", _clean_name(row["name"]), type="main", **{"{http://www.w3.org/XML/1998/namespace}lang": "bo-Latn-x-wylie"}))
    if row["tibetan_transliteration"]:
        person.append(tei("persName", _clean_bo(row["tibetan_transliteration"]), **{"{http://www.w3.org/XML/1998/namespace}lang": "bo"}))
    for alt in _literal_list(row["alternative_names"]):
        label = alt.get("label", "") if isinstance(alt, dict) else ""
        if label:
            person.append(tei("persName", label, type="alt", **{"{http://www.w3.org/XML/1998/namespace}lang": "bo-Latn-x-wylie"}))
    birth_attrs = {}
    if _iso(row["start_date_from"]):
        birth_attrs["notBefore"] = row["start_date_from"]
    if _iso(row["start_date_to"]):
        birth_attrs["notAfter"] = row["start_date_to"]
    if birth_attrs or row["start"]:
        person.append(tei("birth", row["start"] or None, **birth_attrs))
    death_attrs = {}
    if _iso(row["end_date_from"]):
        death_attrs["notBefore"] = row["end_date_from"]
    if _iso(row["end_date_to"]):
        death_attrs["notAfter"] = row["end_date_to"]
    if death_attrs or row["end"]:
        person.append(tei("death", row["end"] or None, **death_attrs))
    if row["gender"]:
        sex = {"male": "M", "female": "F"}.get(row["gender"].lower())
        if sex:
            person.append(tei("sex", value=sex))
    if row["nationality"]:
        person.append(tei("nationality", row["nationality"]))
    for link in re.split(r"\s+", row["external_links"].strip()):
        if "bdrc" in link:
            person.append(tei("idno", link, type="BDRC"))
    person.append(tei("idno", str(pk), type="APIS"))
    if row["comments"]:
        person.append(tei("note", row["comments"], type="comment"))
    return person


# Relations of a work written in its own entry (listBibl/bibl), not in listRelation
WORK_RESP_ROLES = {"translator-of": "translator", "prompter-of": "prompter"}   # respStmt
WORK_RELATED_TYPES = {"biographed-in": "biographyOf", "addressee-of": "addressedTo",   # relatedItem @type
                      "records-the-teaching-of": "recordsTeachingOf",
                      "commentary-on": "commentaryOn", "contains-citations-of": "citesWork"}
HEADER_WORK_RELATIONS = set(WORK_RESP_ROLES) | set(WORK_RELATED_TYPES)
WORK_OWNER_IS_OBJECT = {"translator-of", "prompter-of", "biographed-in", "addressee-of"}  # person -> work


def work_header_ends(rel):
    """(owner, other) entity keys: the owner is the work whose entry holds the relation."""
    subj, obj = _entity_key(rel["subj"]), _entity_key(rel["obj"])
    if relation_name(rel) in WORK_OWNER_IS_OBJECT:
        return obj, subj
    return subj, obj


def _in_export(key):
    kind, pk = key
    return (kind == "person" and pk in PERSONS.index) or (kind == "work" and pk in WORKS.index)


def work_header_links(wpk):
    """(kind, value, other) for the work relations held in this work's entry."""
    links = []
    for rel in _relations_of(WORKS, wpk):
        name = relation_name(rel)
        if name not in HEADER_WORK_RELATIONS:
            continue
        owner, other = work_header_ends(rel)
        if owner != ("work", wpk) or not other or not _in_export(other):
            continue
        if name in WORK_RESP_ROLES:
            links.append(("resp", WORK_RESP_ROLES[name], other))
        else:
            links.append(("related", WORK_RELATED_TYPES[name], other))
    return links


def _work_element(pk, author_pks, header=False):
    row = WORKS.loc[pk]
    bibl = tei("bibl", **{XML_ID: f"work{pk}"})
    bibl.append(tei("title", row["name"], type="main", **{"{http://www.w3.org/XML/1998/namespace}lang": "bo-Latn-x-wylie"}))
    if row["tibetan_transliteration"]:
        bibl.append(tei("title", _clean_bo(row["tibetan_transliteration"]), **{"{http://www.w3.org/XML/1998/namespace}lang": "bo"}))
    for alt in _literal_list(row["alternative_names"]):
        label = alt.get("label", "") if isinstance(alt, dict) else ""
        if label:
            bibl.append(tei("title", label, type="alt", **{"{http://www.w3.org/XML/1998/namespace}lang": "bo-Latn-x-wylie"}))
    if row["original_language"] == "Tibetan":
        bibl.append(tei("textLang", mainLang="bo"))
    date_attrs = {}
    if _iso(row["start_date_from"]):
        date_attrs["notBefore"] = row["start_date_from"]
    if _iso(row["start_date_to"]):
        date_attrs["notAfter"] = row["start_date_to"]
    if date_attrs or row["start"]:
        bibl.append(tei("date", row["start"] or None, type="composition", **date_attrs))
    for apk in author_pks:
        bibl.append(tei("author", _clean_name(PERSONS.loc[apk, "name"]) if apk in PERSONS.index else None, ref=f"person:{apk}"))
    if row["isExtant"]:
        bibl.append(tei("note", row["isExtant"], type="isExtant"))
    if row["comments"]:
        bibl.append(tei("note", row["comments"], type="comment"))
    for kind, value, other in (work_header_links(pk) if header else []):
        if kind == "resp":
            resp_stmt = etree.SubElement(bibl, f"{TEI}respStmt")
            resp_stmt.append(tei("resp", value))
            resp_stmt.append(tei("name", _clean_name(PERSONS.loc[other[1], "name"]), ref=f"person:{other[1]}"))
        else:
            bibl.append(tei("relatedItem", type=value, target=f"{other[0]}:{other[1]}"))
    bibl.append(tei("idno", str(pk), type="APIS"))
    return bibl


def _place_element(pk):
    row = PLACES.loc[pk]
    place = tei("place", **{XML_ID: f"place{pk}"})
    if row["feature_code"]:
        place.set("type", row["feature_code"])
    place.append(tei("placeName", row["label"], **{"{http://www.w3.org/XML/1998/namespace}lang": "bo-Latn-x-wylie"}))
    if row["tibetan_transliteration"]:
        place.append(tei("placeName", _clean_bo(row["tibetan_transliteration"]), **{"{http://www.w3.org/XML/1998/namespace}lang": "bo"}))
    for alt in _literal_list(row["alternative_names"]):
        label = alt.get("label", "") if isinstance(alt, dict) else ""
        if label:
            place.append(tei("placeName", label, type="alt", **{"{http://www.w3.org/XML/1998/namespace}lang": "bo"}))
    if row["latitude"] and row["longitude"]:
        location = etree.SubElement(place, f"{TEI}location")
        location.append(tei("geo", f"{row['latitude']} {row['longitude']}"))
    place.append(tei("idno", str(pk), type="APIS"))
    return place


def build_standoff(refs, author_pks_by_work, work_pks, inst_pks, body_ids, warnings):
    """Entities for the file and the relations of its focus: the works and
    instances of the file, and the authors of those works. Each relation's other
    end gets its own entry too, so the file stands alone (see
    docs/tei-mapping/mapping.md, 4.4). Relations are not limited to those evidenced
    in the file. Relations to an instance that is not in the file are skipped,
    since that instance has no msDesc here."""
    persons = {pk for p, pk in refs if p == "person"}
    works = {pk for p, pk in refs if p == "work"} | set(work_pks)
    places = {pk for p, pk in refs if p == "place"}
    for prefix, pk in refs:
        if prefix in ("deity", "school"):
            warnings.append(f"{prefix}:{pk} referenced; no export for this type, no entry in standOff")
        if prefix == "inst" and pk not in inst_pks:
            warnings.append(f"inst:{pk} referenced in the text but no msDesc for it")
    focus_authors = {a for w in work_pks for a in author_pks_by_work.get(w, [])}
    persons |= focus_authors
    focus = ({("work", w) for w in work_pks} | {("inst", i) for i in inst_pks}
             | {("person", a) for a in focus_authors})

    # Relations of the focus (one end in focus); has-as-an-instance is in msContents
    selected = []
    skipped_other_instance = 0
    for rel in RELATION_INDEX:
        if not rel["subj"] or not rel["obj"]:
            continue
        if rel["name"] in HEADER_COVERED_RELATIONS:
            continue  # written in the manuscript description (origin, provenance, additions)
        if rel["name"] == "has-as-an-instance":
            continue
        if rel["subj"] not in focus and rel["obj"] not in focus:
            continue
        if rel["name"] in HEADER_WORK_RELATIONS:
            owner, other = (rel["obj"], rel["subj"]) if rel["name"] in WORK_OWNER_IS_OBJECT else (rel["subj"], rel["obj"])
            if owner and owner[1] in work_pks and other and _in_export(other):
                (persons if other[0] == "person" else works).add(other[1])
                continue  # written in the work's entry
        if rel["name"] not in RELATION_NAMES:
            # Kept: the name is not in the ODD yet (update the ODD); the relation is not dropped
            warnings.append(f"relation {rel['id']} '{rel['name']}' not in the ODD list; kept, update the ODD")
        if not CONFIDENCE_TO_TYPE.get(rel["confidence"]):
            warnings.append(f"relation {rel['id']} has confidence '{rel['confidence']}'; skipped")
            continue
        if any(k[0] == "inst" and k[1] not in inst_pks for k in (rel["subj"], rel["obj"])):
            skipped_other_instance += 1
            continue
        selected.append(rel)
        for kind, pk in (rel["subj"], rel["obj"]):
            {"person": persons, "work": works, "place": places}.get(kind, set()).add(pk)
    if skipped_other_instance:
        warnings.append(f"{skipped_other_instance} relation(s) to instances not in this file skipped")

    standoff = etree.Element(f"{TEI}standOff")
    for w in list(works):  # the authors of every work in the file are defined too
        persons |= set(authors_of_work(w))
    list_person_pks = sorted(persons)
    list_person = etree.SubElement(standoff, f"{TEI}listPerson")
    for pk in list_person_pks:
        if pk in PERSONS.index:
            list_person.append(_person_element(pk))
        else:
            warnings.append(f"person {pk} referenced but not in the export")
    if not len(list_person):
        standoff.remove(list_person)

    list_bibl = etree.SubElement(standoff, f"{TEI}listBibl")
    for pk in sorted(works):
        if pk in WORKS.index:
            list_bibl.append(_work_element(pk, authors_of_work(pk), header=pk in work_pks))
        else:
            warnings.append(f"work {pk} referenced but not in the export")
    if not len(list_bibl):
        standoff.remove(list_bibl)

    list_place = etree.SubElement(standoff, f"{TEI}listPlace")
    for pk in sorted(places):
        if pk in PLACES.index:
            list_place.append(_place_element(pk))
        else:
            warnings.append(f"place {pk} referenced but not in the export")
    if not len(list_place):
        standoff.remove(list_place)

    members = {("person", pk) for pk in persons if pk in PERSONS.index}
    members |= {("place", pk) for pk in places if pk in PLACES.index}
    members |= {("work", pk) for pk in works if pk in WORKS.index}
    members |= {("inst", pk) for pk in inst_pks}
    relations = etree.Element(f"{TEI}listRelation")
    for rel in selected:
        if rel["subj"] not in members or rel["obj"] not in members:
            warnings.append(f"relation {rel['id']} has an end not in the export; skipped")
            continue
        el = etree.SubElement(relations, f"{TEI}relation", {
            XML_ID: f"rel{rel['id']}",
            "name": rel["name"],
            "active": f"#{rel['subj'][0]}{rel['subj'][1]}",
            "passive": f"#{rel['obj'][0]}{rel['obj'][1]}",
            "type": CONFIDENCE_TO_TYPE[rel["confidence"]],
        })
        evidence = [t for t in re.split(r"[\s\"']+", rel["tei_refs"].replace("xml:id=", " ")) if t]
        evidence = [t for t in evidence if t in body_ids]
        if evidence:
            desc = etree.SubElement(el, f"{TEI}desc")
            desc.text = "Evidence: "
            for t in evidence:
                desc.append(tei("ptr", target=f"#{t}"))
    if len(relations):
        standoff.append(relations)
    return standoff


# ---------------------------------------------------------------------------
# Public TEI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_prefixes(root, warnings):
    defined = {p.get("ident") for p in root.iter(f"{TEI}prefixDef")}
    used = {}
    for el in root.iter(etree.Element):
        for attr in POINTER_ATTRS:
            for value in (el.get(attr) or "").split():
                m = re.match(r"^([A-Za-z][\w.+-]*):", value)
                if m and m.group(1) not in STANDARD_SCHEMES:
                    used.setdefault(m.group(1), value)
    for prefix, example in sorted(used.items()):
        if prefix not in defined:
            warnings.append(
                f"prefix '{prefix}:' used (e.g. {example}) but no prefixDef"
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _strip_indentation(el):
    """Drop whitespace-only text in the header so pretty_print can re-indent
    it after nodes were removed. The text is left alone (xml:space)."""
    for node in el.iter():
        if node.text is not None and not node.text.strip():
            node.text = None
        if node.tail is not None and not node.tail.strip():
            node.tail = None


def write_tei(root, path):
    etree.indent(root.find("tei:teiHeader", namespaces=NS), space="   ", level=1)
    root.text = "\n   "
    root.find("tei:teiHeader", namespaces=NS).tail = "\n   "
    with open(path, "wb") as f:
        f.write(
            etree.tostring(
                root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
            )
        )


def make_public_tei(src_tree, keep_revision_desc=False):
    """Return (public_root, warnings) for a parsed source TEI tree."""
    warnings = []
    src_root = src_tree.getroot()
    src_header = src_root.find("tei:teiHeader", namespaces=NS)
    src_text = src_root.find("tei:text", namespaces=NS)

    ids = manuscript_ids(src_header)
    if not ids:
        raise ValueError("no idno type=TibSchol in publicationStmt")

    inst_pks, inst_ids = [], {}
    for eid in ids:
        matches = TIBSCHOL_INDEX.get(eid, [])
        if not matches:
            warnings.append(f"no instance has tibschol_ref {eid}")
        for ipk in matches:
            if ipk not in inst_pks:
                inst_pks.append(ipk)
            inst_ids.setdefault(ipk, []).append(eid)
    if not inst_pks:
        raise ValueError(f"no instance found for TibSchol references {ids}")

    work_pks_by_inst = {ipk: works_of_instance(ipk) for ipk in inst_pks}
    for ipk, works in work_pks_by_inst.items():
        if not works:
            warnings.append(f"instance {ipk} has no work in the export")
    work_pks = []
    for works in work_pks_by_inst.values():
        for w in works:
            if w not in work_pks:
                work_pks.append(w)
    if not work_pks:
        raise ValueError("no work for the instances")

    text = build_public_text(src_text)
    relink_chains(src_root, text, warnings)
    convert_body_prefixes(text, warnings)
    body_ids = {el.get(XML_ID) for el in text.iter(f"{TEI}seg") if el.get(XML_ID)}

    # Work of the file: the one cited most in the text, if several instances disagree
    cited = {}
    for el in text.iter(f"{TEI}rs"):
        m = REF_RE.match(el.get("ref") or "")
        if m and m.group(1) == "work":
            cited[int(m.group(2))] = cited.get(int(m.group(2)), 0) + 1
    main_work = max(work_pks, key=lambda w: cited.get(w, 0))
    if len(work_pks) > 1:
        warnings.append(f"instances belong to several works {work_pks}; title from {main_work}")
    author_pks = authors_of_work(main_work)
    author_pks_by_work = {w: authors_of_work(w) for w in work_pks}

    refs = collect_refs(text)
    header = build_public_header(src_header, inst_pks, inst_ids, main_work, author_pks,
                                 work_pks_by_inst, warnings, keep_revision_desc)
    _strip_indentation(header)
    for ipk in inst_pks:  # people and places named in the manuscript description must be defined too
        refs |= {("person", pk) for _, pk in header_people(ipk)}
        refs |= {("place", pk) for pk in written_at_places(ipk)}
    standoff = build_standoff(refs, author_pks_by_work, work_pks, set(inst_pks), body_ids, warnings)

    root = etree.Element(src_root.tag, dict(src_root.attrib), nsmap={None: NS["tei"]})
    root.append(header)
    if len(standoff):
        root.append(standoff)
    text.tail = "\n"
    root.append(text)

    prefixes = used_prefixes(root) & set(ENTITY_PREFIXES)
    set_prefix_defs(header, prefixes)
    if not any(True for _ in text.iter(f"{TEI}seg")):
        warnings.append("no curated segs: body contains only a gap")
    check_prefixes(root, warnings)
    return root, warnings


def _problem_type(message):
    """Group key for a problem: the same kind of problem with different ids or line numbers is one type."""
    text = re.sub(r"invalid \(line \d+\): ", "invalid: ", message)
    text = re.sub(r"'[^']*'", "'…'", text)
    text = re.sub(r"\b\d[\d_.\-/]*\b", "N", text)
    return text.strip()


def write_problem_summary(rows, path):
    """errors_by_type.md: one section per type of problem, with the number of files and the file names."""
    groups = {}
    for row in rows:
        groups.setdefault(_problem_type(row["problem"]), []).append(row)
    lines = [
        "# Problems by type",
        "",
        f"Run date: {GENERATED_ON}",
        "",
        f"{len(rows)} problems in {len({r['file'] for r in rows})} files, in {len(groups)} types. "
        "Each type lists the files it affects; the per-file list is in errors.md.",
        "",
        "| type | problems | files | example |",
        "|---|---|---|---|",
    ]
    ordered = sorted(groups.items(), key=lambda kv: (-len({r["file"] for r in kv[1]}), kv[0]))
    for kind, items in ordered:
        files = sorted({r["file"] for r in items})
        example = items[0]["problem"].replace("|", "/")
        lines.append(f"| {kind.replace('|', '/')} | {len(items)} | {len(files)} | {example} |")
    lines.append("")
    for kind, items in ordered:
        files = sorted({r["file"] for r in items})
        lines += [f"## {kind}", "", f"{len(items)} problems in {len(files)} files:", ""]
        lines += [f"- {name}" for name in files]
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Create public TEI versions from the source TEIs and the APIS CSV exports.")
    parser.add_argument("tei_repo_glob", help="Glob pattern for source TEI XML files (e.g., 'data/examples/*.xml')")
    parser.add_argument("-o", "--out-dir", default="data/excerpts")
    parser.add_argument("--keep-revision-desc", action="store_true")
    parser.add_argument("--rng", help="RelaxNG schema to validate the output against")
    args = parser.parse_args()

    schema = etree.RelaxNG(etree.parse(args.rng)) if args.rng else None
    os.makedirs(args.out_dir, exist_ok=True)
    files = sorted(glob.glob(args.tei_repo_glob))
    print(len(files), "files found")

    report = []
    for file in tqdm(files):
        name = os.path.basename(file)
        try:
            root, warnings = make_public_tei(etree.parse(file), args.keep_revision_desc)
        except Exception as e:  # noqa: BLE001 - collect and continue
            ERRORS.append({"file": name, "problem": f"{type(e).__name__}: {e}"})
            continue
        out_path = os.path.join(args.out_dir, name)
        write_tei(root, out_path)
        if schema is not None and not schema.validate(etree.parse(out_path)):
            for err in schema.error_log:
                warnings.append(f"invalid (line {err.line}): {err.message}")
        report.extend({"file": name, "problem": w} for w in warnings)

    os.makedirs(ERRORS_DIR, exist_ok=True)
    with open(ERRORS_DIR / "errors.md", "w", encoding="utf-8") as f:
        f.write(f"# Errors and warnings per file\n\nRun date: {GENERATED_ON}\n\n")
        f.write("| file | problem |\n|---|---|\n")
        for row in sorted(ERRORS, key=lambda r: r["file"]) + report:
            f.write(f"| {row['file']} | {row['problem'].replace('|', '/')} |\n")
    write_problem_summary(ERRORS + report, ERRORS_DIR / "errors_by_type.md")
    print(f"{len(ERRORS)} files failed, {len(report)} warnings; see {ERRORS_DIR}/errors.md and errors_by_type.md")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
