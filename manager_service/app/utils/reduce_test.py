import sys
from collections import defaultdict
from time import sleep

if len(sys.argv) != 3:
    raise ValueError("Usage: python reducer.py <input_file> <output_file>")

input_file = sys.argv[1]
output_file = sys.argv[2]

counts = defaultdict(int)

sleep(30)

with open(input_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 2:
            continue

        key, value = parts
        counts[key] += int(value)

with open(output_file, "w") as f:
    for key, value in sorted(counts.items()):
        f.write(f"{key}\t{value}\n")

sleep(30)