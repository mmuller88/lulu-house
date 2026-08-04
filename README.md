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
| `docker-compose.yml` | Home Assistant container (config from `homeassistant/`) |
| `docs/docker.md` | Docker quick start |
| `homeassistant/` | HA config (`configuration.yaml`, `packages/`) |

## Energy dashboard (in progress)

Track: [#1 — Hoymiles BKW + iMSys via Home Assistant](https://github.com/mmuller88/lulu-house/issues/1)

```
Hoymiles WR (WLAN) ──┐
                     ├──► Home Assistant ──► Energy Dashboard
SMGW / iMSys (HAN) ──┘
```

```bash
cp homeassistant/secrets.yaml.example homeassistant/secrets.yaml
./scripts/validate-ha-config.sh
docker compose up -d    # on home LAN host — see docs/docker.md
```

**Secrets:** `homeassistant/secrets.yaml` — never commit.

## External portals

- Hoymiles plant: https://global.hoymiles.com/website/plant/detail/14313640
- SmartVisio: https://smartvisio-basic.smartoptimo.de/ludwigslust/login
