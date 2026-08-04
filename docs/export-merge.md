# Export merge — SmartVisio + Hoymiles

Merge portal CSV exports into one table + HTML dashboard. **No HAN cable, no Home Assistant.**

## Workflow

1. Export from **SmartVisio** (Report) → save as `imports/smartvisio.csv`
2. Export from **Hoymiles** (Report) → save as `imports/hoymiles.csv`
3. Run merge → open `output/energy-report.html`

```bash
# local Python 3.11+
python3 scripts/merge_energy_exports.py \
  --smartvisio imports/smartvisio.csv \
  --hoymiles imports/hoymiles.csv

# or Docker (no local Python needed)
docker compose --profile merge run --rm energy-merge
```

Open `output/energy-report.html` in the browser.

## Portal exports

### SmartVisio

1. Login → https://smartvisio-basic.smartoptimo.de/ludwigslust/login
2. Tab **Report** (or **Analytics** → export if available)
3. Meter **1DZG0040468260**, metric **Energie bezogen**
4. Date range (e.g. one day or week)
5. Export **CSV**
6. Save to `imports/smartvisio.csv`

Expected columns (names may vary slightly):

- time: `Display Period - From` or similar
- value: `Energie Bezogen` (kWh per 15 min)

### Hoymiles

1. Login → plant [14313640](https://global.hoymiles.com/website/plant/detail/14313640)
2. Tab **Report**
3. Same date range as SmartVisio
4. Export **CSV**
5. Save to `imports/hoymiles.csv`

Expected: timestamp + production/energy (kWh) or power (W).  
If only power (W) is exported, the script assumes **15-min** intervals.

## Output

| File | Content |
|------|---------|
| `output/merged-energy.csv` | `start`, `grid_import_kwh`, `pv_production_kwh`, `house_consumption_kwh` |
| `output/energy-report.html` | Charts + daily totals |

**Hausverbrauch (geschätzt)** per interval:

```
house_kwh ≈ grid_import_kwh + pv_production_kwh
```

(Assumes negligible feed-in for 800 W BKW; refine later if export column appears.)

## Custom paths

```bash
python3 scripts/merge_energy_exports.py \
  --smartvisio path/to/sv.csv \
  --hoymiles path/to/hm.csv \
  --out-dir reports/2026-08-04 \
  --title "BKW Test August"
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| column not detected | open CSV, check header row matches docs above |
| no intervals parsed | date format / empty export / wrong delimiter |
| mismatched times | use same date range + timezone in both portals |
| house looks wrong | PV export may be power not energy — check Hoymiles CSV units |
