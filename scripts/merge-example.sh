#!/usr/bin/env bash
# Demo merge with example CSVs → output/energy-report.html
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/scripts/merge_energy_exports.py" \
  --smartvisio "$ROOT/imports/example-smartvisio.csv" \
  --hoymiles "$ROOT/imports/example-hoymiles.csv" \
  --out-dir "$ROOT/output/example" \
  --title "House Lulu — Example Report"
echo "open $ROOT/output/example/energy-report.html"
