#!/usr/bin/env bash
# Rebuild data/*.geojson from the floor plan PDF.
#   CQ3_PDF=/path/to/CQ3_FP.pdf ./tools/run.sh
# Needs: pip install pymupdf shapely opencv-python-headless scipy numpy
set -euo pipefail
cd "$(dirname "$0")"
for i in 0 1 2 3 4 5 6 7 8; do python3 runall.py "$i"; done   # one sheet at a time (each needs ~2 GB RAM)
python3 outline.py 0
python3 build.py ../data
