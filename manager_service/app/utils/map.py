import sys
import re

if len(sys.argv) != 3:
    raise ValueError("Usage: python mapper.py <input_file> <output_file>")

input_file = sys.argv[1]
output_file = sys.argv[2]

CLEAN = re.compile(r"[^a-z0-9]+")

with open(input_file, "r") as f, open(output_file, "w") as out:
    for line in f:
        for word in line.strip().split():
            cleaned = CLEAN.sub("", word.lower())

            if not cleaned:
                continue

            out.write(f"{cleaned}\t1\n")