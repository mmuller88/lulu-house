# Energy context — House Lulu

**Site:** Schweriner Str. 6, 19288 Ludwigslust  
**Last updated:** 2026-08-07  
**Tracking issue:** [#1](https://github.com/mmuller88/lulu-house/issues/1)

## Goals

- Unified view: **PV production** (Hoymiles) + **grid import/export** (iMSys/SMGW)
- Derived **house consumption** ≈ grid import + PV − grid export
- Home Assistant as integration hub (see `docs/homeassistant-setup.md`)

## Balkonkraftwerk (BKW)

| Item | Value |
|------|-------|
| Inverter | Hoymiles **HMS-800W-2T** (2 MPPT) |
| Target capacity | **840 W** (440 W Ost + 400 W West) |
| MPPT1 | 2× WERCHTAY 220W series (Ost) |
| MPPT2 | 2× enjoy solar 200W TOPCon series (West) |
| Mount | Flachdach Ost-West 2×2, ~10°, ballast |
| Hoymiles Cloud plant | [14313640](https://global.hoymiles.com/website/plant/detail/14313640) |

**Last updated:** 2026-08-04 (BKW West mounted)

### BKW status (2026-08-04)

| Step | Status |
|------|--------|
| HMS-800W-2T | ✅ |
| 2× WERCHTAY Ost (MPPT1) | ✅ |
| 2× enjoy West (MPPT2) | ✅ mounted, wired, live in Hoymiles |
| Flachdach mount 4 modules | ✅ |
| MaStR registration | 🔲 within 1 month of commissioning |
| Netzbetreiber BKW notice | ✅ not required since 2024 — MaStR notifies MSB automatically |

### Wiring

```
Ost:  [WERCHTAY]—serie—[WERCHTAY]  → MPPT1  ─┐
                                                ├─ Hoymiles HMS-800W-2T
West: [enjoy]—serie—[enjoy]          → MPPT2  ─┘
```

## Strom / iMSys

| Item | Value |
|------|-------|
| MSB | Stadtwerke Ludwigslust-Grabow |
| iMSys meter | **1DZG0040468260** |
| Old meter | 1APA0198978301 |
| iMSys installed | 2026-07-23 |
| iMSys install cost (one-time) | **186,68 €** (~180 €; Stadtwerke Angebot 22.06.2026) |
| iMSys MSB fee | 30 €/Jahr (50 €/Jahr with PV plant registered) |
| SmartVisio portal | https://smartvisio-basic.smartoptimo.de/ludwigslust/login |
| Portal token (Kd-Nr Messstelle) | **4525208** |
| HAN credentials | SmartVisio → **HAN** tab (→ `secrets.yaml`, not in git) |
| Supplier | LichtBlick ÖkoStrom 12 (~26,73 ct/kWh brutto) |
| Supplier Kd-Nr | 4033441 |

### iMSys status

| Step | Status |
|------|--------|
| iMSys install | ✅ 2026-07-23 |
| SmartVisio registration | ✅ 2026-08-03 |
| Analytics data visible | ✅ from 2026-08-03 |
| HAN → Home Assistant | 🔲 Phase 3 |

**Observed baseline:** quiet nights ~115–130 W (~0,029–0,032 kWh / 15 min; 2026-08-03/04). 2026-08-05 night elevated (~220 W).

### Observed days (merged exports)

| Day | Netzbezug | PV | Haus (est.) | Peak PV |
|-----|-----------|-----|-------------|---------|
| 2026-08-01 | 6,06 kWh | 3,12 kWh | 8,83 kWh | 565 W |
| 2026-08-02 | 4,77 kWh | 4,29 kWh | 8,72 kWh | 550 W |
| 2026-08-03 | 6,49 kWh | 4,24 kWh | 10,39 kWh | 478 W |
| 2026-08-04 | 9,43 kWh | 2,95 kWh | 10,77 kWh | 475 W |
| 2026-08-05 | 10,52 kWh | 3,77 kWh | 13,79 kWh | 486 W |
| 2026-08-06 | 5,35 kWh | 3,28 kWh | 8,19 kWh | 509 W |
| 2026-08-07 | 5,25 kWh | 1,84 kWh | 6,79 kWh | 350 W |

Viewer: `output/energy-report.html` (`./scripts/merge-all.sh`).

## Data sources (no native link)

| Source | Shows | Integration |
|--------|-------|-------------|
| Hoymiles S-Miles Cloud | PV only | [ha-hoymiles-wifi](https://github.com/suaveolent/ha-hoymiles-wifi) |
| SmartVisio | Grid import (15-min), MSB cloud | Manual / export; HA uses SMGW HAN |
| Home Assistant | Combined dashboard | This repo |

## Contacts

| Role | Contact |
|------|---------|
| MSB / iMSys | m.reszies@stw-ludwigslust-grabow.de |
| Netzbetrieb | netzbetrieb@stw-ludwigslust-grabow.de |
| BKW Meldeblatt | https://www.stw-ludwigslust-grabow.de/netzbetrieb/netzanschluss/stromanschluss/ |

## Related repo files

- Dropbox progress (consolidated): `House Lulu/strom/Energie-Progress.md`
- `offer-comparison-summary.md` — full PV quotes (8–10 kWp, not current BKW)
- `waermepumpe-vergleich.md` — heat pump comparison
- `haus-daten.json` — building data
