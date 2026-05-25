import sys
from collections import defaultdict

if len(sys.argv) != 3:
    raise ValueError("Usage: python invert_reduce.py <input_file> <output_file>")

input_file = sys.argv[1]
output_file = sys.argv[2]

index = defaultdict(set)

with open(input_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 2:
            continue

        word, doc_id = parts
        index[word].add(doc_id)

with open(output_file, "w") as f:
    for word in sorted(index):
        doc_list = ",".join(sorted(index[word]))
        f.write(f"{word}\t{doc_list}\n")
