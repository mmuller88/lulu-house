#!/usr/bin/env bash
# Merge imports/YYYY-MM-DD or imports/YYYY-week-WW → output + viewer
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DAY="${1:?usage: merge-day.sh YYYY-MM-DD|YYYY-week-WW}"
python3 "$ROOT/scripts/merge_energy_exports.py" --day "$DAY"
echo "open $ROOT/output/energy-report.html"
