#!/usr/bin/env bash
# Merge imports/YYYY-MM-DD/*.csv → output/YYYY-MM-DD/energy-report.html
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DAY="${1:?usage: merge-day.sh YYYY-MM-DD}"
python3 "$ROOT/scripts/merge_energy_exports.py" --day "$DAY"
echo "open $ROOT/output/energy-report.html"
