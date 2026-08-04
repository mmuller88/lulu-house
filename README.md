# lulu-house

House documentation and automation for **Schweriner Str. 6, Ludwigslust**.

## Contents

| Path | Description |
|------|-------------|
| `haus-daten.json` | Building rooms, Grundbuch, heating plan |
| `offer-comparison-summary.md` | Full PV quotes (ELD / 1Komma5°) |
| `waermepumpe-vergleich.md` | Heat pump comparison |
| `docs/energy-context.md` | BKW + iMSys hardware IDs, status, links |
| `docs/homeassistant-setup.md` | HA + Hoymiles + SMGW setup guide |
| `docs/network-smgw.md` | SMGW `192.168.100.x` networking |
| `docs/export-merge.md` | **Merge SmartVisio + Hoymiles CSV exports** |
| `scripts/merge_energy_exports.py` | Merge → CSV + HTML dashboard |
| `docker-compose.yml` | HA (`--profile ha`) + merge tool (`--profile merge`) |
| `docs/docker.md` | Docker quick start |
| `homeassistant/` | HA config (`configuration.yaml`, `packages/`) |

## Energy reports (recommended)

Merge portal exports — **no cable, no HA**. Store history in git:

```bash
# 1. Drop exports: imports/YYYY-MM-DD/smartvisio.csv + hoymiles.csv
# 2. Commit CSVs
# 3. Merge:
./scripts/merge-all.sh
# or single day: ./scripts/merge-day.sh 2026-08-03

# 4. Open output/energy-report.html (switch days via buttons)
```

See `docs/export-merge.md`. Demo: `./scripts/merge-example.sh`

## Home Assistant (optional, later)

Track: [#1 — Hoymiles BKW + iMSys via Home Assistant](https://github.com/mmuller88/lulu-house/issues/1)

SMGW/HAN integration optional — skip if you only use export merge + SmartVisio portal.

```bash
cp homeassistant/secrets.yaml.example homeassistant/secrets.yaml
docker compose --profile ha up -d    # see docs/docker.md
```

## External portals

- Hoymiles plant: https://global.hoymiles.com/website/plant/detail/14313640
- SmartVisio: https://smartvisio-basic.smartoptimo.de/ludwigslust/login
