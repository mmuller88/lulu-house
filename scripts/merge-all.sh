#!/usr/bin/env bash
# Merge all import days → output/energy-report.html + docs/index.html (GitHub Pages)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/scripts/merge_energy_exports.py" --all
echo "open $ROOT/output/energy-report.html"
echo "pages  https://mmuller88.github.io/lulu-house/"
