# Home Assistant setup — House Lulu energy

Implements [#1](https://github.com/mmuller88/lulu-house/issues/1) Phases 1–4.

## Prerequisites

- Home Assistant OS on Pi 4/5 or mini-PC on home LAN
- HACS installed
- Hoymiles WR IP address (router DHCP list)
- HAN username + password from SmartVisio portal

## Phase 1 — Base install

1. Install [Home Assistant OS](https://www.home-assistant.io/installation/)
2. Complete onboarding, enable backups
3. Install [HACS](https://hacs.xyz/docs/setup/download)

## Phase 2 — Hoymiles

1. HACS → Custom repository: `https://github.com/suaveolent/ha-hoymiles-wifi`
2. Install **Hoymiles** integration
3. Settings → Devices → Add integration → Hoymiles
4. Host: WR/DTU IP from `secrets.yaml` → `hoymiles_host`
5. **Poll interval ≥ 120 s** (keeps S-Miles Cloud working)
6. Verify sensors: power (W), energy today (kWh)
7. Confirm plant [14313640](https://global.hoymiles.com/website/plant/detail/14313640) still updates in cloud

## Phase 3 — SMGW / HAN

1. Confirm SMGW model (PPC / Theben / EMH) — Stadtwerke or device label
2. Network: see `docs/network-smgw.md`
3. HACS → Custom repository: `https://github.com/jannickfahlbusch/ha-ppc-smgw`
4. Install **ppc_smgw** integration
5. URL / user / password from `secrets.yaml`
6. Update interval: **≥ 5 min** (SMGW often 15–20 min refresh)
7. Verify import (+ export) sensors

## Phase 4 — Packages + Energy Dashboard

1. Copy `homeassistant/packages/energy.yaml` to HA `config/packages/`
2. Edit entity IDs in `energy.yaml` to match your integration sensor names
3. Settings → Dashboards → Energy → configure:
   - **Grid consumption:** SMGW import sensor
   - **Return to grid:** SMGW export sensor (if available)
   - **Solar production:** Hoymiles power / energy sensors
4. Optional Lovelace card: PV | Grid | House consumption | Self-consumption %

## Validation

| Test | Expected |
|------|----------|
| Sunny midday | PV ↑, grid import ↓ |
| Night | PV ≈ 0, grid ≈ baseline (~130 W) |
| HA vs portals | Same day totals roughly match SmartVisio + Hoymiles reports |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Hoymiles cloud stops updating | Increase poll interval to 120 s+ |
| SMGW unreachable | Secondary IP on HA host (`docs/network-smgw.md`) |
| Template sensors unavailable | Check entity_id names in `energy.yaml` |
| Wrong house consumption | Confirm export sensor sign / availability |
