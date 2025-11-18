from pathlib import Path
import pandas as pd
import re

# Get directory of the current script file
current_dir = Path(__file__).resolve().parent

# Build paths relative to current_dir
instances_path = current_dir / "../data/instances.csv"
works_path = current_dir / "../data/works.csv"
persons_path = current_dir / "../data/persons.csv"

# Read CSVs
instances = pd.read_csv(instances_path).fillna("")
works = pd.read_csv(works_path).fillna("")
persons = pd.read_csv(persons_path).fillna("")


def sep_label_and_id(text):

    match = re.match(r"^(.*)\s*\((\d+)\)\s*$", text)
    if match:
        label = match.group(1).strip()
        id = match.group(2).strip()
        return label, id
    else:
        print("No match found")

    return "", ""


def exact_word_match(df, colname, target):
    escaped_target = re.escape(target)
    # Match target preceded and followed by string boundary or whitespace/comma/newline
    pattern = rf"(^|[\s,\\r\\n]){escaped_target}($|[\s,\\r\\n])"

    mask = df[colname].str.contains(pattern, regex=True)
    return df[mask]


def get_author_data(work_id):
    work = works[works.url.str.endswith(f"/{work_id}/")].iloc[0]
    author = {}
    for rel in eval(work["relations"]):
        if "author of" in rel["label"]:
            author["author_name"], author["author_id"] = sep_label_and_id(
                rel["subj"]["label"]
            )
            return author

    return author


def get_instance_data(idno):
    result = exact_word_match(instances, "tibschol_ref", idno)
    data = {}
    if result.empty or len(result) > 1:
        raise ValueError(f"Found {len(result)} instances with tibschol_ref {idno}")

    result = result.iloc[0]
    for rel in eval(result.relations):
        if "has as an instance" in rel["label"]:
            data["work_name"], data["work_id"] = sep_label_and_id(rel["subj"]["label"])
        if "writen at" in rel["label"]:
            data["place"] = rel["obj"]["label"]
        if "scribe of" in rel["label"]:
            data["scribe"] = rel["subj"]["label"]
        if "has other relation with" in rel["label"]:
            data["related_person"] = rel["subj"]["label"]
        if "is copied from" in rel["label"]:
            data["source_instance"] = rel["obj"]["label"]

    data.update(get_author_data(data["work_id"]))
    # data.update(result.iloc[0].to_dict())
    # title from works

    return data
