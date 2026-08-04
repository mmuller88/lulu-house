# Energy context — House Lulu

**Site:** Schweriner Str. 6, 19288 Ludwigslust  
**Last updated:** 2026-08-04  
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

### BKW status (2026-08-04)

| Step | Status |
|------|--------|
| HMS-800W-2T | ✅ |
| 2× WERCHTAY Ost (MPPT1) | ✅ |
| 2× enjoy West (MPPT2) | ⏳ ordered |
| Flachdach mount 4 modules | ⏳ in progress |
| Temp ~500 W flat on roof | ⏳ partial |
| MaStR registration | 🔲 after commissioning |
| Netzbetreiber BKW notice | 🔲 after commissioning |

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

**Observed baseline:** ~130 W night load (~0,032 kWh / 15 min on 2026-08-03).

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

- `offer-comparison-summary.md` — full PV quotes (8–10 kWp, not current BKW)
- `waermepumpe-vergleich.md` — heat pump comparison
- `haus-daten.json` — building data
