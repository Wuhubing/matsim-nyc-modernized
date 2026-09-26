#!/usr/bin/env python3
"""Merge the legacy external subpopulation ObjectAttributes into a MATSim population file.

Usage:
  python scripts/merge_subpopulation.py final_population.xml final_subpopulation.xml population.xml.gz
"""
import gzip
import html
import re
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: merge_subpopulation.py POPULATION_XML ATTRIBUTES_XML OUTPUT_XML_GZ")

population = Path(sys.argv[1])
attributes = Path(sys.argv[2])
output = Path(sys.argv[3])

subpops = {}
object_id = None
with attributes.open("r", encoding="utf-8", errors="replace") as f:
    for line in f:
        match = re.search(r'<object id="([^"]+)">', line)
        if match:
            object_id = match.group(1)
            continue
        if object_id is not None and 'name="subpopulation"' in line:
            value = re.search(r'>([^<]+)</attribute>', line)
            if value:
                subpops[object_id] = value.group(1).strip()
        if "</object>" in line:
            object_id = None

merged = 0
missing = []
with population.open("r", encoding="utf-8", errors="replace") as src, gzip.open(
    output, "wt", encoding="utf-8", compresslevel=9, newline="\n"
) as dst:
    for line in src:
        if line.startswith("<!DOCTYPE population"):
            dst.write('<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n')
            continue
        # Population v6 renamed the legacy activity element.
        line = re.sub(r'<(/?)act(?=[\s/>])', r'<\1activity', line)
        dst.write(line)
        match = re.match(r'<person id="([^"]+)">', line.strip())
        if match:
            person_id = match.group(1)
            subpopulation = subpops.get(person_id)
            if subpopulation is None:
                missing.append(person_id)
                subpopulation = "default"
            dst.write("<attributes>\n")
            dst.write(
                f'  <attribute name="subpopulation" class="java.lang.String">'
                f'{html.escape(subpopulation)}</attribute>\n'
            )
            dst.write("</attributes>\n")
            merged += 1

print(f"merged={merged:,}; missing={len(missing):,}; output={output}")
if missing:
    raise SystemExit(f"Missing subpopulation for {len(missing)} people; first IDs: {missing[:10]}")
