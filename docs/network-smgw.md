# SMGW network setup

PPC Smart Meter Gateways are often fixed at **192.168.100.100** and not routed from the home LAN (e.g. 192.168.2.x).

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
