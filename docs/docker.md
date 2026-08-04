# Docker Compose — Home Assistant

Run HA from this repo. Config lives in `homeassistant/` (git); runtime state stays local (gitignored).

## Quick start

```bash
cp homeassistant/secrets.yaml.example homeassistant/secrets.yaml
docker compose --profile ha up -d
```

Open **http://localhost:8123** (first start: onboarding wizard ~1–2 min).

Logs:

```bash
docker compose logs -f homeassistant
```

Stop:

```bash
docker compose down
```

## Why `network_mode: host`

- Hoymiles WR is reached by **LAN IP** (`secrets.yaml` → `hoymiles_host`)
- SMGW is often **`192.168.100.100`** — see `docs/network-smgw.md`
- Host networking avoids NAT/port-mapping pain for local devices

**Requires Linux** on the machine that runs Docker (Pi, mini-PC, home server).  
Docker Desktop on Mac/Windows: host mode is limited — use a Linux host at Schweriner Str. 6 for real integrations.

## Repo vs runtime

| Tracked in git | Local only (gitignored) |
|----------------|-------------------------|
| `configuration.yaml` | `secrets.yaml` |
| `packages/` | `.storage/` |
| `secrets.yaml.example` | `*.db`, `*.log`, `deps/` |

After first `docker compose up`, HA writes DB + UI state into `homeassistant/` — do not commit.

## HACS (custom integrations)

HACS is not in the image. After onboarding:

1. Install [HACS](https://hacs.xyz/docs/setup/download) via UI
2. Add repos from `docs/homeassistant-setup.md` (Hoymiles, ppc_smgw)

## Dev without home devices

You can start the container anywhere to validate config/UI. Integrations will stay **unavailable** until the container runs on the home LAN with correct IPs.

```bash
./scripts/validate-ha-config.sh
docker compose config   # syntax check
```

## Related

- Integrations: `docs/homeassistant-setup.md`
- SMGW network: `docs/network-smgw.md`
- Issue: [#1](https://github.com/mmuller88/lulu-house/issues/1)
