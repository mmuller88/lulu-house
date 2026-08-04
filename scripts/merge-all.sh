#!/usr/bin/env bash
# Merge all import days → output/energy-report.html (day picker)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/scripts/merge_energy_exports.py" --all
echo "open $ROOT/output/energy-report.html"
