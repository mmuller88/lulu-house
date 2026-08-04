#!/usr/bin/env python3
"""Merge SmartVisio + Hoymiles CSV exports → CSV + HTML dashboard."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class Interval:
    start: datetime
    grid_kwh: float | None = None
    pv_kwh: float | None = None

    @property
    def house_kwh(self) -> float | None:
        if self.grid_kwh is None or self.pv_kwh is None:
            return None
        return self.grid_kwh + self.pv_kwh


def _norm_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _parse_dt(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).astimezone(TZ)
    except ValueError:
        return None


def _pick_column(headers: list[str], patterns: Iterable[str]) -> int | None:
    normed = [_norm_header(h) for h in headers]
    for pattern in patterns:
        for idx, header in enumerate(normed):
            if re.search(pattern, header):
                return idx
    return None


def read_smartvisio(path: Path) -> dict[datetime, float]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise SystemExit(f"empty file: {path}")

    headers = rows[0]
    time_idx = _pick_column(
        headers,
        [r"display period.*from", r"^from$", r"zeit", r"period.*start", r"datum"],
    )
    energy_idx = _pick_column(
        headers,
        [r"energie bezogen", r"bezogen", r"import", r"verbrauch", r"energy.*import"],
    )
    if time_idx is None or energy_idx is None:
        raise SystemExit(
            f"could not detect SmartVisio columns in {path}\nheaders: {headers}"
        )

    out: dict[datetime, float] = {}
    for row in rows[1:]:
        if len(row) <= max(time_idx, energy_idx):
            continue
        start = _parse_dt(row[time_idx])
        energy = _parse_float(row[energy_idx])
        if start is None or energy is None:
            continue
        out[start] = energy
    if not out:
        raise SystemExit(f"no SmartVisio intervals parsed from {path}")
    return out


def read_hoymiles(path: Path) -> dict[datetime, float]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise SystemExit(f"empty file: {path}")

    headers = rows[0]
    time_idx = _pick_column(
        headers,
        [r"^time$", r"^date$", r"datetime", r"zeit", r"timestamp", r"period"],
    )
    energy_idx = _pick_column(
        headers,
        [r"yield", r"production", r"energy", r"erzeug", r"kwh", r"generation"],
    )
    power_idx = _pick_column(headers, [r"^power$", r"leistung", r"^w$", r"output"])

    if time_idx is None:
        raise SystemExit(
            f"could not detect Hoymiles time column in {path}\nheaders: {headers}"
        )

    out: dict[datetime, float] = {}
    for row in rows[1:]:
        if len(row) <= time_idx:
            continue
        start = _parse_dt(row[time_idx])
        if start is None:
            continue

        energy = None
        if energy_idx is not None and len(row) > energy_idx:
            energy = _parse_float(row[energy_idx])
        if energy is None and power_idx is not None and len(row) > power_idx:
            power_w = _parse_float(row[power_idx])
            if power_w is not None:
                energy = power_w / 1000 / 4  # assume 15-min power → kWh

        if energy is None:
            continue
        out[start] = energy

    if not out:
        raise SystemExit(f"no Hoymiles intervals parsed from {path}")
    return out


def merge(
    smartvisio: dict[datetime, float], hoymiles: dict[datetime, float]
) -> list[Interval]:
    keys = sorted(set(smartvisio) | set(hoymiles))
    return [
        Interval(
            start=key,
            grid_kwh=smartvisio.get(key),
            pv_kwh=hoymiles.get(key),
        )
        for key in keys
    ]


def write_csv(path: Path, intervals: list[Interval]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["start", "grid_import_kwh", "pv_production_kwh", "house_consumption_kwh"]
        )
        for item in intervals:
            writer.writerow(
                [
                    item.start.isoformat(),
                    "" if item.grid_kwh is None else f"{item.grid_kwh:.6f}",
                    "" if item.pv_kwh is None else f"{item.pv_kwh:.6f}",
                    "" if item.house_kwh is None else f"{item.house_kwh:.6f}",
                ]
            )


def _daily_totals(intervals: list[Interval]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for item in intervals:
        day = item.start.date().isoformat()
        bucket = totals.setdefault(day, {"grid": 0.0, "pv": 0.0, "house": 0.0})
        if item.grid_kwh is not None:
            bucket["grid"] += item.grid_kwh
        if item.pv_kwh is not None:
            bucket["pv"] += item.pv_kwh
        if item.house_kwh is not None:
            bucket["house"] += item.house_kwh
    return totals


def write_html(path: Path, intervals: list[Interval], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [item.start.strftime("%H:%M") for item in intervals]
    grid = [item.grid_kwh for item in intervals]
    pv = [item.pv_kwh for item in intervals]
    house = [item.house_kwh for item in intervals]
    daily = _daily_totals(intervals)

    total_grid = sum(v for v in grid if v is not None)
    total_pv = sum(v for v in pv if v is not None)
    total_house = sum(v for v in house if v is not None)
    self_use_pct = (min(total_pv, total_house) / total_pv * 100) if total_pv else 0

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .meta {{ color: #94a3b8; margin-bottom: 1.5rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 1rem; }}
    .card strong {{ display: block; font-size: 1.4rem; margin-top: 0.25rem; }}
    canvas {{ background: #1e293b; border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; }}
    table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
    th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #334155; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">SmartVisio Bezug + Hoymiles Erzeugung · {len(intervals)} Intervalle</p>
  <div class="cards">
    <div class="card">Netzbezug<strong>{total_grid:.2f} kWh</strong></div>
    <div class="card">PV Erzeugung<strong>{total_pv:.2f} kWh</strong></div>
    <div class="card">Hausverbrauch (geschätzt)<strong>{total_house:.2f} kWh</strong></div>
    <div class="card">Eigenverbrauch PV<strong>{self_use_pct:.0f} %</strong></div>
  </div>
  <canvas id="intervalChart" height="120"></canvas>
  <canvas id="dailyChart" height="80"></canvas>
  <table>
    <thead><tr><th>Tag</th><th>Bezug</th><th>PV</th><th>Haus</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td>{day}</td><td>{vals['grid']:.2f}</td><td>{vals['pv']:.2f}</td><td>{vals['house']:.2f}</td></tr>" for day, vals in sorted(daily.items()))}
    </tbody>
  </table>
  <script>
    const labels = {json.dumps(labels)};
  const grid = {json.dumps(grid)};
  const pv = {json.dumps(pv)};
  const house = {json.dumps(house)};
  const dailyLabels = {json.dumps(list(sorted(daily.keys())))};
  const dailyGrid = {json.dumps([daily[d]['grid'] for d in sorted(daily.keys())])};
  const dailyPv = {json.dumps([daily[d]['pv'] for d in sorted(daily.keys())])};

  new Chart(document.getElementById('intervalChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{ label: 'Bezug (kWh/15min)', data: grid, borderColor: '#f97316', tension: 0.2 }},
        {{ label: 'PV (kWh/15min)', data: pv, borderColor: '#22c55e', tension: 0.2 }},
        {{ label: 'Haus (kWh/15min)', data: house, borderColor: '#38bdf8', tension: 0.2 }},
      ],
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }} }} }},
  }});

  new Chart(document.getElementById('dailyChart'), {{
    type: 'bar',
    data: {{
      labels: dailyLabels,
      datasets: [
        {{ label: 'Bezug kWh', data: dailyGrid, backgroundColor: '#f97316' }},
        {{ label: 'PV kWh', data: dailyPv, backgroundColor: '#22c55e' }},
      ],
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }} }} }},
  }});
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smartvisio", type=Path, required=True)
    parser.add_argument("--hoymiles", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument("--title", default="House Lulu — Energy Report")
    args = parser.parse_args()

    intervals = merge(read_smartvisio(args.smartvisio), read_hoymiles(args.hoymiles))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.out_dir / "merged-energy.csv"
    html_path = args.out_dir / "energy-report.html"
    write_csv(csv_path, intervals)
    write_html(html_path, intervals, args.title)

    print(f"wrote {csv_path}")
    print(f"wrote {html_path}")
    print(f"intervals: {len(intervals)}")


if __name__ == "__main__":
    main()
