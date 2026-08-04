# SMGW network setup

**SMGW is not on your WiFi.** SmartVisio works via **mobile/cellular → MSB cloud** (already running). Local HA access uses the **HAN Ethernet port** (RJ45 at the meter cabinet) — a **cable**, not WLAN.

## Two separate paths

```
SmartVisio (cloud)     SMGW ──LTE/Mobilfunk──► MSB ──► Portal ✅ (no home LAN)

Home Assistant (local) HA host ──LAN-Kabel──► HAN-Port am SMGW
                         ▲
                    HAN user/pass (SmartVisio tab)
```

| Path | Needs WiFi? | Needs LAN cable to SMGW? |
|------|-------------|---------------------------|
| SmartVisio portal | No | No |
| Hoymiles → HA | Yes (WR in WLAN) | No |
| SMGW → HA | No | **Yes** (HAN port) |

## HAN port — what to do

1. **Find the gateway** in the meter cabinet (installed with iMSys 2026-07-23).
2. Look for **„HAN“** RJ45 (often separate from WAN/mobile).
3. **Patch cable** from HAN → router LAN port **or** directly to the Docker/HA host NIC.
4. Some MSBs warn: HAN **must not** be bridged to the public internet (router OK for local LAN only).
5. Test: `curl -k --connect-timeout 3 https://192.168.100.100/` (PPC often `.100.100`; factory sometimes `192.168.1.200`).

If timeout → assign a secondary IP on the HA host in the SMGW subnet (see below).

## Quick test

From a machine on the home network:

```bash
curl -k --connect-timeout 3 https://192.168.100.100/
```

If timeout → assign a secondary IP on the HA host in `192.168.100.0/24`.

## Home Assistant host — secondary IP (Linux)

Replace interface and IP as needed (`eth0`, `192.168.100.12`):

```bash
sudo ip addr add 192.168.100.12/24 dev eth0
```

Persist via NetworkManager, netplan, or HA OS network settings depending on host.

**Important:** SMGW URL stays `https://192.168.100.100/...` — the extra IP only routes traffic to that subnet.

Reference: [ha-ppc-smgw-han network-setup](https://github.com/TRON4R/ha-ppc-smgw-han/blob/main/docs/network-setup.md)

## Firewall

- Allow HA → `192.168.100.100` HTTPS
- Do not expose SMGW to the public internet

## Credentials

HAN username + password: SmartVisio portal → **HAN** tab → store in `homeassistant/secrets.yaml` (gitignored).

## If HAN is not wired yet

- **SmartVisio still works** — no local link required.
- **HA SMGW integration waits** until HAN is cabled (Phase 3 in issue #1).
- Unsure which port / IP? Ask Reszies (`m.reszies@stw-ludwigslust-grabow.de`) or check PPC/Theben handbook for your gateway model.
