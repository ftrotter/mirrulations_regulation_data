"""
Generate an CSV file with the following columns:

name - entity name
count - number of times the entity appears in the document
org - organization name
docket - docket id
comment_id - comment id

Call this script with an argument specifying a directory that contains
one or more agency directories.

entity_map.csv will be written to the directory specified.
"""


from csv import DictWriter
import os
import re
import sys
import spacy
from collections import Counter

nlp = spacy.load("en_core_web_trf")


def process(root, file):
    if not file.endswith(".txt"):
        return
    org, docket, comment_id = get_ids(root, file)
    counts = count_entities(extract_entities(os.path.join(root, file)))
    for name, count in counts.items():
        data = dict(name=name, count=count, org=org, docket=docket, comment_id=comment_id)


def get_ids(dirs, file):
    dir_list = dirs.split("/")
    org = dir_list[0]
    docket = dir_list[1]
    attach_index = file.find("_attachment")
    if attach_index != -1:
        comment_id = file[:attach_index]
    else:
        raise ValueError("Error: no _attachment in filename")

    return org, docket, comment_id


def load_sections(path):
    with open(path, "r") as f:
        sections = re.split('\n\n|\x0C', f.read())
    return sections


def extract_entities(path):
    entities = []
    for section in load_sections(path):
        doc = nlp(section)
        for ent in doc.ents:
            # replace multiple whitespace characters with single space
            entities.append((' '.join(ent.text.split()), ent.label_))

    return entities


def count_entities(entities):
    names = [name for name, etype in entities if etype == "PERSON" or etype == "ORG"]
    counts = Counter(names)
    return counts


class CSVGenerator:

    def __init__(self, data_root):
        self.data_root = data_root
        self.count = 0
        self.csv_file = open(os.path.join(data_root, "entity_map.csv"), "w")
        self.writer = DictWriter(self.csv_file, escapechar='\\', fieldnames=["name", "count", "org", "docket", "comment_id"])
        self.writer.writeheader()

    def process(self, root, file):
        if not file.endswith(".txt"):
            return
        self.count += 1
        print(self.count, file)
        org, docket, comment_id = get_ids(root.replace(self.data_root + '/', ''), file)
        counts = count_entities(extract_entities(os.path.join(root, file)))
        for name, count in counts.items():
            data = dict(name=name, count=count, org=org, docket=docket, comment_id=comment_id)
            self.writer.writerow(data)

    def close(self):
        self.csv_file.close()


def go():

    if len(sys.argv) != 2:
        print("Usage: python entity_map.py <data_root>")
        return
    
    data_root = sys.argv[1]

    generator = CSVGenerator(data_root)
    for root, dirs, files in os.walk(os.path.join(data_root)):
        for file in files:
            generator.process(root, file)


if __name__ == "__main__":
    go()

