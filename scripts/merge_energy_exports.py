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
IMPORTS_ROOT = Path("imports")
OUTPUT_ROOT = Path("output")


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

    @property
    def grid_w(self) -> float | None:
        if self.grid_kwh is None:
            return None
        return self.grid_kwh * 4 * 1000

    @property
    def pv_w(self) -> float | None:
        if self.pv_kwh is None:
            return None
        return self.pv_kwh * 4 * 1000

    @property
    def house_w(self) -> float | None:
        if self.house_kwh is None:
            return None
        return self.house_kwh * 4 * 1000


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
    text = (value or "").strip().strip('"')
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    # SmartVisio US format: 08/03/2026 - 00:00:00
    us_match = re.match(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2}):(\d{2}):(\d{2})$",
        text,
    )
    if us_match:
        month, day, year, hour, minute, second = map(int, us_match.groups())
        return datetime(year, month, day, hour, minute, second, tzinfo=TZ)

    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
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


def _detect_delimiter(sample: str) -> str:
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def _read_csv_rows(path: Path) -> list[list[str]]:
    raw = path.read_text(encoding="utf-8-sig")
    delimiter = _detect_delimiter(raw[:4096])
    return list(csv.reader(raw.splitlines(), delimiter=delimiter))


def _pick_column(headers: list[str], patterns: Iterable[str]) -> int | None:
    normed = [_norm_header(h) for h in headers]
    for pattern in patterns:
        for idx, header in enumerate(normed):
            if re.search(pattern, header):
                return idx
    return None


def _find_header_row(rows: list[list[str]]) -> int:
    for idx, row in enumerate(rows):
        normed = [_norm_header(cell) for cell in row]
        has_time = any(
            re.search(r"time.*from|display period.*from|^from$|period.*start", h)
            for h in normed
        )
        has_value = any(
            re.search(r"^value$|energie bezogen|bezogen|import|verbrauch", h)
            for h in normed
        )
        if has_time and has_value:
            return idx
    return 0


def _floor_15min(dt: datetime) -> datetime:
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)


def read_smartvisio(path: Path) -> dict[datetime, float]:
    rows = _read_csv_rows(path)
    if not rows:
        raise SystemExit(f"empty file: {path}")

    header_idx = _find_header_row(rows)
    headers = rows[header_idx]
    time_idx = _pick_column(
        headers,
        [
            r"time.*from",
            r"display period.*from",
            r"^from$",
            r"zeit",
            r"period.*start",
            r"datum",
        ],
    )
    energy_idx = _pick_column(
        headers,
        [
            r"^value$",
            r"energie bezogen",
            r"bezogen",
            r"import",
            r"verbrauch",
            r"energy.*import",
        ],
    )
    if time_idx is None or energy_idx is None:
        raise SystemExit(
            f"could not detect SmartVisio columns in {path}\nheaders: {headers}"
        )

    out: dict[datetime, float] = {}
    for row in rows[header_idx + 1 :]:
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
    rows = _read_csv_rows(path)
    if not rows:
        raise SystemExit(f"empty file: {path}")

    headers = rows[0]
    time_idx = _pick_column(
        headers,
        [r"^time$", r"^date$", r"datetime", r"zeit", r"timestamp", r"period"],
    )
    energy_idx = _pick_column(
        headers,
        [r"yield", r"production.*kwh", r"energy", r"erzeug", r"kwh", r"generation"],
    )
    power_idx = _pick_column(
        headers,
        [r"production.*w", r"^power$", r"leistung", r"^w$", r"output"],
    )

    if time_idx is None:
        # Hoymiles export: empty first header, timestamps in col 0
        for row in rows[1:6]:
            if row and _parse_dt(row[0]) is not None:
                time_idx = 0
                break
    if time_idx is None:
        raise SystemExit(
            f"could not detect Hoymiles time column in {path}\nheaders: {headers}"
        )

    samples: list[tuple[datetime, float | None, float | None]] = []
    for row in rows[1:]:
        if len(row) <= time_idx:
            continue
        start = _parse_dt(row[time_idx])
        if start is None:
            continue

        energy = None
        if energy_idx is not None and len(row) > energy_idx:
            energy = _parse_float(row[energy_idx])

        power_w = None
        if power_idx is not None and len(row) > power_idx:
            power_w = _parse_float(row[power_idx])

        if energy is None and power_w is None:
            continue
        samples.append((start, energy, power_w))

    if not samples:
        raise SystemExit(f"no Hoymiles intervals parsed from {path}")

    # Power-only export: integrate W over sample duration, bucket to 15 min
    if energy_idx is None or all(s[1] is None for s in samples):
        bucket_kwh: dict[datetime, float] = {}
        for i, (start, _, power_w) in enumerate(samples):
            if power_w is None:
                continue
            if i + 1 < len(samples):
                delta_hours = (samples[i + 1][0] - start).total_seconds() / 3600
            else:
                delta_hours = 5 / 60  # last sample: assume 5 min
            if delta_hours <= 0:
                continue
            kwh = power_w / 1000 * delta_hours
            bucket = _floor_15min(start)
            bucket_kwh[bucket] = bucket_kwh.get(bucket, 0.0) + kwh
        if not bucket_kwh:
            raise SystemExit(f"no Hoymiles power samples integrated from {path}")
        return bucket_kwh

    out: dict[datetime, float] = {}
    for start, energy, _ in samples:
        if energy is not None:
            out[_floor_15min(start)] = out.get(_floor_15min(start), 0.0) + energy
    if not out:
        raise SystemExit(f"no Hoymiles energy intervals parsed from {path}")
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
            [
                "start",
                "grid_import_kwh",
                "pv_production_kwh",
                "house_consumption_kwh",
                "grid_import_w",
                "pv_production_w",
                "house_consumption_w",
            ]
        )
        for item in intervals:
            writer.writerow(
                [
                    item.start.isoformat(),
                    "" if item.grid_kwh is None else f"{item.grid_kwh:.6f}",
                    "" if item.pv_kwh is None else f"{item.pv_kwh:.6f}",
                    "" if item.house_kwh is None else f"{item.house_kwh:.6f}",
                    "" if item.grid_w is None else f"{item.grid_w:.1f}",
                    "" if item.pv_w is None else f"{item.pv_w:.1f}",
                    "" if item.house_w is None else f"{item.house_w:.1f}",
                ]
            )


def _find_import_csv(day_dir: Path, kind: str) -> Path | None:
    if kind == "smartvisio":
        candidates = [
            day_dir / "smartvisio.csv",
            *sorted(day_dir.glob("smartvisio*.csv")),
            *sorted(day_dir.glob("*smartvisio*.csv")),
        ]
    else:
        candidates = [
            day_dir / "hoymiles.csv",
            *sorted(day_dir.glob("hoymiles*.csv")),
            *sorted(day_dir.glob("historical*.csv")),
        ]
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def discover_days(imports_root: Path = IMPORTS_ROOT) -> list[str]:
    days: list[str] = []
    for entry in imports_root.iterdir():
        if not entry.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.name):
            continue
        if _find_import_csv(entry, "smartvisio") and _find_import_csv(entry, "hoymiles"):
            days.append(entry.name)
    return sorted(days)


def intervals_payload(intervals: list[Interval]) -> dict:
    grid_kwh = [item.grid_kwh for item in intervals]
    pv_kwh = [item.pv_kwh for item in intervals]
    house_kwh = [item.house_kwh for item in intervals]
    total_grid = sum(v for v in grid_kwh if v is not None)
    total_pv = sum(v for v in pv_kwh if v is not None)
    total_house = sum(v for v in house_kwh if v is not None)
    self_use_pct = (min(total_pv, total_house) / total_pv * 100) if total_pv else 0
    return {
        "labels": [item.start.strftime("%H:%M") for item in intervals],
        "gridKwh": grid_kwh,
        "pvKwh": pv_kwh,
        "houseKwh": house_kwh,
        "gridW": [item.grid_w for item in intervals],
        "pvW": [item.pv_w for item in intervals],
        "houseW": [item.house_w for item in intervals],
        "totals": {
            "grid": round(total_grid, 2),
            "pv": round(total_pv, 2),
            "house": round(total_house, 2),
            "selfUsePct": round(self_use_pct),
            "intervals": len(intervals),
        },
    }


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
    grid_kwh = [item.grid_kwh for item in intervals]
    pv_kwh = [item.pv_kwh for item in intervals]
    house_kwh = [item.house_kwh for item in intervals]
    grid_w = [item.grid_w for item in intervals]
    pv_w = [item.pv_w for item in intervals]
    house_w = [item.house_w for item in intervals]
    daily = _daily_totals(intervals)

    total_grid = sum(v for v in grid_kwh if v is not None)
    total_pv = sum(v for v in pv_kwh if v is not None)
    total_house = sum(v for v in house_kwh if v is not None)
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
    .chart-wrap {{ position: relative; height: 320px; margin-bottom: 1.5rem; background: #1e293b; border-radius: 12px; padding: 1rem; }}
    canvas {{ display: block; width: 100% !important; height: 100% !important; }}
    table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
    th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #334155; }}
    h2 {{ font-size: 1rem; color: #94a3b8; margin: 0 0 0.5rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">SmartVisio Bezug + Hoymiles Erzeugung · {len(intervals)} Intervalle (15 min)</p>
  <div class="cards">
    <div class="card">Netzbezug<strong>{total_grid:.2f} kWh</strong></div>
    <div class="card">PV Erzeugung<strong>{total_pv:.2f} kWh</strong></div>
    <div class="card">Hausverbrauch (geschätzt)<strong>{total_house:.2f} kWh</strong></div>
    <div class="card">Eigenverbrauch PV<strong>{self_use_pct:.0f} %</strong></div>
  </div>
  <h2>Verbrauch &amp; Erzeugung über den Tag (W)</h2>
  <div class="chart-wrap"><canvas id="powerChart"></canvas></div>
  <h2>Energie pro 15 min (kWh)</h2>
  <div class="chart-wrap"><canvas id="intervalChart"></canvas></div>
  <h2>Tageswerte (kWh)</h2>
  <div class="chart-wrap" style="height: 200px"><canvas id="dailyChart"></canvas></div>
  <table>
    <thead><tr><th>Tag</th><th>Bezug</th><th>PV</th><th>Haus</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td>{day}</td><td>{vals['grid']:.2f}</td><td>{vals['pv']:.2f}</td><td>{vals['house']:.2f}</td></tr>" for day, vals in sorted(daily.items()))}
    </tbody>
  </table>
  <script>
    const labels = {json.dumps(labels)};
    const gridKwh = {json.dumps(grid_kwh)};
    const pvKwh = {json.dumps(pv_kwh)};
    const houseKwh = {json.dumps(house_kwh)};
    const gridW = {json.dumps(grid_w)};
    const pvW = {json.dumps(pv_w)};
    const houseW = {json.dumps(house_w)};
    const dailyLabels = {json.dumps(list(sorted(daily.keys())))};
    const dailyGrid = {json.dumps([daily[d]['grid'] for d in sorted(daily.keys())])};
    const dailyPv = {json.dumps([daily[d]['pv'] for d in sorted(daily.keys())])};

    const chartOpts = {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      scales: {{ x: {{ ticks: {{ maxTicksLimit: 24 }} }} }},
      plugins: {{ legend: {{ position: 'bottom' }} }},
    }};

    new Chart(document.getElementById('powerChart'), {{
      type: 'line',
      data: {{
        labels,
        datasets: [
          {{ label: 'Netzbezug (W)', data: gridW, borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV Erzeugung (W)', data: pvW, borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Hausverbrauch (W)', data: houseW, borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ],
      }},
      options: chartOpts,
    }});

    new Chart(document.getElementById('intervalChart'), {{
      type: 'line',
      data: {{
        labels,
        datasets: [
          {{ label: 'Bezug (kWh)', data: gridKwh, borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV (kWh)', data: pvKwh, borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Haus (kWh)', data: houseKwh, borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ],
      }},
      options: chartOpts,
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
      options: chartOpts,
    }});
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def write_viewer_html(path: Path, days_data: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    days_json = json.dumps(days_data)
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>House Lulu — Energy</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .meta {{ color: #94a3b8; margin-bottom: 1rem; }}
    .day-nav {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
    .day-nav button {{ background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 8px; padding: 0.5rem 1rem; cursor: pointer; font-size: 0.95rem; }}
    .day-nav button:hover {{ border-color: #38bdf8; }}
    .day-nav button.active {{ background: #38bdf8; color: #0f172a; border-color: #38bdf8; font-weight: 600; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 1rem; }}
    .card strong {{ display: block; font-size: 1.4rem; margin-top: 0.25rem; }}
    .chart-wrap {{ position: relative; height: 320px; margin-bottom: 1.5rem; background: #1e293b; border-radius: 12px; padding: 1rem; }}
    canvas {{ display: block; width: 100% !important; height: 100% !important; }}
    h2 {{ font-size: 1rem; color: #94a3b8; margin: 0 0 0.5rem; }}
  </style>
</head>
<body>
  <h1 id="title">House Lulu — Energy</h1>
  <p class="meta" id="meta"></p>
  <nav class="day-nav" id="dayNav" aria-label="Tag auswählen"></nav>
  <div class="cards">
    <div class="card">Netzbezug<strong id="totalGrid"></strong></div>
    <div class="card">PV Erzeugung<strong id="totalPv"></strong></div>
    <div class="card">Hausverbrauch (geschätzt)<strong id="totalHouse"></strong></div>
    <div class="card">Eigenverbrauch PV<strong id="totalSelf"></strong></div>
  </div>
  <h2>Verbrauch &amp; Erzeugung über den Tag (W)</h2>
  <div class="chart-wrap"><canvas id="powerChart"></canvas></div>
  <h2>Energie pro 15 min (kWh)</h2>
  <div class="chart-wrap"><canvas id="intervalChart"></canvas></div>
  <h2>Tageswerte (kWh)</h2>
  <div class="chart-wrap" style="height: 200px"><canvas id="dailyChart"></canvas></div>
  <script>
    const daysData = {days_json};
    const dayKeys = Object.keys(daysData).sort();
    let currentDay = dayKeys[dayKeys.length - 1];
    let powerChart, intervalChart, dailyChart;

    const chartOpts = {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      scales: {{ x: {{ ticks: {{ maxTicksLimit: 24 }} }} }},
      plugins: {{ legend: {{ position: 'bottom' }} }},
    }};

    function initCharts() {{
      powerChart = new Chart(document.getElementById('powerChart'), {{
        type: 'line',
        data: {{ labels: [], datasets: [
          {{ label: 'Netzbezug (W)', data: [], borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV Erzeugung (W)', data: [], borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Hausverbrauch (W)', data: [], borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ]}},
        options: chartOpts,
      }});
      intervalChart = new Chart(document.getElementById('intervalChart'), {{
        type: 'line',
        data: {{ labels: [], datasets: [
          {{ label: 'Bezug (kWh)', data: [], borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV (kWh)', data: [], borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Haus (kWh)', data: [], borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ]}},
        options: chartOpts,
      }});
      dailyChart = new Chart(document.getElementById('dailyChart'), {{
        type: 'bar',
        data: {{ labels: [], datasets: [
          {{ label: 'Bezug kWh', data: [], backgroundColor: '#f97316' }},
          {{ label: 'PV kWh', data: [], backgroundColor: '#22c55e' }},
        ]}},
        options: chartOpts,
      }});
    }}

    function showDay(day) {{
      const d = daysData[day];
      document.getElementById('title').textContent = 'House Lulu — ' + day;
      document.getElementById('meta').textContent =
        'SmartVisio Bezug + Hoymiles Erzeugung · ' + d.totals.intervals + ' Intervalle (15 min)';
      document.getElementById('totalGrid').textContent = d.totals.grid.toFixed(2) + ' kWh';
      document.getElementById('totalPv').textContent = d.totals.pv.toFixed(2) + ' kWh';
      document.getElementById('totalHouse').textContent = d.totals.house.toFixed(2) + ' kWh';
      document.getElementById('totalSelf').textContent = d.totals.selfUsePct + ' %';

      powerChart.data.labels = d.labels;
      powerChart.data.datasets[0].data = d.gridW;
      powerChart.data.datasets[1].data = d.pvW;
      powerChart.data.datasets[2].data = d.houseW;
      powerChart.update();

      intervalChart.data.labels = d.labels;
      intervalChart.data.datasets[0].data = d.gridKwh;
      intervalChart.data.datasets[1].data = d.pvKwh;
      intervalChart.data.datasets[2].data = d.houseKwh;
      intervalChart.update();

      dailyChart.data.labels = [day];
      dailyChart.data.datasets[0].data = [d.totals.grid];
      dailyChart.data.datasets[1].data = [d.totals.pv];
      dailyChart.update();
    }}

    function updateNav() {{
      document.querySelectorAll('#dayNav button').forEach((btn) => {{
        btn.classList.toggle('active', btn.dataset.day === currentDay);
      }});
    }}

    const nav = document.getElementById('dayNav');
    dayKeys.forEach((day) => {{
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.day = day;
      btn.textContent = day;
      btn.addEventListener('click', () => {{
        currentDay = day;
        showDay(day);
        updateNav();
      }});
      nav.appendChild(btn);
    }});

    initCharts();
    showDay(currentDay);
    updateNav();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def day_paths(
    day: str, imports_root: Path = IMPORTS_ROOT
) -> tuple[Path, Path, Path]:
    day_dir = imports_root / day
    smartvisio = _find_import_csv(day_dir, "smartvisio")
    hoymiles = _find_import_csv(day_dir, "hoymiles")
    out_dir = OUTPUT_ROOT / day
    if smartvisio is None:
        raise SystemExit(f"missing SmartVisio CSV in {day_dir}")
    if hoymiles is None:
        raise SystemExit(f"missing Hoymiles CSV in {day_dir}")
    return smartvisio, hoymiles, out_dir


def merge_day_intervals(day: str, imports_root: Path = IMPORTS_ROOT) -> list[Interval]:
    smartvisio, hoymiles, _ = day_paths(day, imports_root)
    return merge(read_smartvisio(smartvisio), read_hoymiles(hoymiles))


def refresh_viewer(imports_root: Path = IMPORTS_ROOT) -> Path | None:
    days = discover_days(imports_root)
    if not days:
        return None
    days_data: dict[str, dict] = {}
    for day in days:
        days_data[day] = intervals_payload(merge_day_intervals(day, imports_root))
    viewer_path = OUTPUT_ROOT / "energy-report.html"
    write_viewer_html(viewer_path, days_data)
    return viewer_path


def run_merge(
    smartvisio: Path,
    hoymiles: Path,
    out_dir: Path,
    title: str,
    refresh_viewer_after: bool = True,
    imports_root: Path = IMPORTS_ROOT,
) -> list[Interval]:
    intervals = merge(read_smartvisio(smartvisio), read_hoymiles(hoymiles))
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "merged-energy.csv"
    html_path = out_dir / "energy-report.html"
    write_csv(csv_path, intervals)
    write_html(html_path, intervals, title)

    print(f"wrote {csv_path}")
    print(f"wrote {html_path}")
    print(f"intervals: {len(intervals)}")

    if refresh_viewer_after:
        viewer = refresh_viewer(imports_root)
        if viewer:
            print(f"wrote {viewer}")

    return intervals


def run_all(imports_root: Path = IMPORTS_ROOT) -> None:
    days = discover_days(imports_root)
    if not days:
        raise SystemExit(f"no import days found in {imports_root}")

    for day in days:
        intervals = merge_day_intervals(day, imports_root)
        out_dir = OUTPUT_ROOT / day
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "merged-energy.csv"
        write_csv(csv_path, intervals)
        print(f"wrote {csv_path} ({len(intervals)} intervals)")

    viewer = refresh_viewer(imports_root)
    if viewer:
        print(f"wrote {viewer} ({len(days)} days)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--day",
        help="YYYY-MM-DD → imports/<day>/ → output/<day>/ + refresh viewer",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="merge all import days + output/energy-report.html viewer",
    )
    parser.add_argument("--smartvisio", type=Path)
    parser.add_argument("--hoymiles", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--imports-root",
        type=Path,
        default=IMPORTS_ROOT,
        help="root for imports (default: imports)",
    )
    args = parser.parse_args()

    if args.all:
        run_all(args.imports_root)
        return

    if args.day:
        smartvisio, hoymiles, out_dir = day_paths(args.day, args.imports_root)
        title = args.title or f"House Lulu — {args.day}"
        run_merge(
            smartvisio,
            hoymiles,
            out_dir,
            title,
            refresh_viewer_after=True,
            imports_root=args.imports_root,
        )
        return

    if not args.smartvisio or not args.hoymiles:
        parser.error("provide --day, --all, or both --smartvisio and --hoymiles")

    smartvisio = args.smartvisio
    hoymiles = args.hoymiles
    out_dir = args.out_dir or OUTPUT_ROOT
    title = args.title or "House Lulu — Energy Report"
    run_merge(
        smartvisio,
        hoymiles,
        out_dir,
        title,
        refresh_viewer_after=False,
        imports_root=args.imports_root,
    )


if __name__ == "__main__":
    main()

