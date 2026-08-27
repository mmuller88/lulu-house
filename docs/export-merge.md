# Export merge — SmartVisio + Hoymiles

Merge portal CSV exports into one table + HTML dashboard. **No HAN cable, no Home Assistant.**

## History layout (in git)

Store dated exports under `imports/`:

```
imports/
  2026-08-03/
    smartvisio.csv    # SmartVisio portal export
    hoymiles.csv      # Hoymiles portal export
  2026-week-34/       # ISO week (Mon–Sun) — split to days in viewer
    smartvisio-2026-week-34.csv
    historical_….csv  # Hoymiles
```

Day folders override the same date from a week folder.

Commit these CSVs for history. Generated reports stay in `output/` (gitignored).

## Workflow

1. Export from **SmartVisio** (Report) for one day or week → `imports/YYYY-MM-DD/` or `imports/YYYY-week-WW/`
2. Export from **Hoymiles** (Report) for same range → same folder
3. Commit the CSVs
4. Run merge → open `output/energy-report.html` or push `docs/index.html` for GitHub Pages

Day picker uses **shadcn/ui Calendar** in a popover (`viewer/` — built automatically on merge).

```bash
./scripts/merge-all.sh                 # all days/weeks → viewer + docs/index.html
./scripts/merge-day.sh 2026-08-03      # one day + refresh viewer
./scripts/merge-day.sh 2026-week-34    # ISO week → split days in viewer

# or
python3 scripts/merge_energy_exports.py --all
python3 scripts/merge_energy_exports.py --day 2026-08-03
python3 scripts/merge_energy_exports.py --day 2026-week-34

# Docker
DAY=2026-08-03 docker compose --profile merge run --rm energy-merge
DAY=2026-week-34 docker compose --profile merge run --rm energy-merge
```

Demo with synthetic examples: `./scripts/merge-example.sh`

## Absent days

Mark vacation / away days in `imports/absent-days.txt` (one `YYYY-MM-DD` per line, `#` comments ok).
They show with ✈ in the report and are excluded from the **Ø anwesend** averages.

```text
# imports/absent-days.txt
2026-08-09
2026-08-10
```

Re-run `./scripts/merge-all.sh` after edits.

## GitHub Pages

**URL:** https://mmuller88.github.io/lulu-house/

`merge-all.sh` writes `docs/index.html`. Commit it with new imports. Repo **Settings → Pages → Build from branch → `main` → `/docs`**.

Optional: `.github/workflows/pages.yml` rebuilds on push (needs Actions minutes).

## Portal exports

### SmartVisio

1. Login → https://smartvisio-basic.smartoptimo.de/ludwigslust/login
2. Tab **Report** (or **Analytics** → export)
3. Meter **1DZG0040468260**, metric **Energie bezogen**
4. Date range (one day)
5. Export **CSV** → `imports/YYYY-MM-DD/smartvisio.csv` or `imports/YYYY-week-WW/`

Real export shape:

- `;` delimiter, quoted fields
- Row 0: metadata (`1DZG0040468260 / Energie bezogen…`)
- Row 1: headers `Time from…`, `Value`, `Unit`
- Times: `08/03/2026 - 00:00:00` (US) or `17/08/2026 00:00` (EU)

### Hoymiles

1. Login → plant [14313640](https://global.hoymiles.com/website/plant/detail/14313640)
2. Tab **Report**, same date range
3. Export **CSV** → same folder as SmartVisio (`hoymiles.csv` or portal `historical_*.csv`)

Real export shape:

- Header: empty first column + `Production (W)`
- Times: `2026-08-03 00:00` (5-min samples during day)
- Script integrates power → kWh and buckets to 15 min

## Output

| File | Content |
|------|---------|
| `output/energy-report.html` | **Multi-day viewer** — buttons to switch days |
| `output/YYYY-MM-DD/merged-energy.csv` | 15-min intervals per day |

**GitHub Pages:** https://mmuller88.github.io/lulu-house/ — auto-deployed from `main` via `.github/workflows/pages.yml`.

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
  --out-dir reports/custom \
  --title "BKW Test August"
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| missing imports/YYYY-MM-DD/smartvisio.csv | create day or `YYYY-week-WW` folder, drop exports |
| column not detected | open CSV, check header row matches docs above |
| no intervals parsed | date format / empty export / wrong delimiter |
| mismatched times | use same date range + timezone in both portals |
| house looks wrong | check Hoymiles units (W vs kWh) |
