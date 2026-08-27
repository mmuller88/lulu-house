#!/usr/bin/env python3
"""Merge SmartVisio + Hoymiles CSV exports → CSV + HTML dashboard."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
IMPORTS_ROOT = Path("imports")
OUTPUT_ROOT = Path("output")
PAGES_INDEX = Path("docs/index.html")
VIEWER_DIR = Path("viewer")
VIEWER_DIST = VIEWER_DIR / "dist"
DATE_PICKER_ASSETS = VIEWER_DIST
DAY_DIR_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
WEEK_DIR_RE = re.compile(r"\d{4}-week-\d{2}")


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

    # SmartVisio EU: 17/08/2026 00:00 or 17/08/2026 00:00:00
    eu_match = re.match(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$",
        text,
    )
    if eu_match:
        day, month, year, hour, minute, second = eu_match.groups()
        try:
            return datetime(
                int(year),
                int(month),
                int(day),
                int(hour),
                int(minute),
                int(second or 0),
                tzinfo=TZ,
            )
        except ValueError:
            pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
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


def _has_import_csvs(entry: Path) -> bool:
    return bool(
        _find_import_csv(entry, "smartvisio") and _find_import_csv(entry, "hoymiles")
    )


def discover_import_dirs(imports_root: Path = IMPORTS_ROOT) -> list[str]:
    names: list[str] = []
    for entry in imports_root.iterdir():
        if not entry.is_dir():
            continue
        if not (DAY_DIR_RE.fullmatch(entry.name) or WEEK_DIR_RE.fullmatch(entry.name)):
            continue
        if _has_import_csvs(entry):
            names.append(entry.name)
    return sorted(names)


def discover_days(imports_root: Path = IMPORTS_ROOT) -> list[str]:
    return [n for n in discover_import_dirs(imports_root) if DAY_DIR_RE.fullmatch(n)]


def split_by_day(intervals: list[Interval]) -> dict[str, list[Interval]]:
    by_day: dict[str, list[Interval]] = {}
    for item in intervals:
        by_day.setdefault(item.start.date().isoformat(), []).append(item)
    return by_day


def collect_day_intervals(
    imports_root: Path = IMPORTS_ROOT,
) -> dict[str, list[Interval]]:
    """Expand folders to calendar days. Named day folder > week > spillover."""
    from_weeks: dict[str, list[Interval]] = {}
    from_named: dict[str, list[Interval]] = {}
    from_spill: dict[str, list[Interval]] = {}
    for name in discover_import_dirs(imports_root):
        split = split_by_day(merge_day_intervals(name, imports_root))
        if WEEK_DIR_RE.fullmatch(name):
            from_weeks.update(split)
            continue
        if name in split:
            from_named[name] = split[name]
        for day, intervals in split.items():
            if day != name:
                from_spill.setdefault(day, intervals)
    return dict(sorted({**from_spill, **from_weeks, **from_named}.items()))


def load_absent_days(imports_root: Path = IMPORTS_ROOT) -> set[str]:
    path = imports_root / "absent-days.txt"
    if not path.is_file():
        return set()
    absent: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        day = line.split("#", 1)[0].strip()
        if day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            absent.add(day)
    return absent


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
        "zeroBezugSpans": _zero_bezug_spans(intervals),
        "totals": {
            "grid": round(total_grid, 2),
            "pv": round(total_pv, 2),
            "house": round(total_house, 2),
            "selfUsePct": round(self_use_pct),
            "zeroBezugPct": _zero_bezug_pct(intervals),
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


ZERO_GRID_W = 5.0
ZERO_PV_W = 50.0


def _is_zero_bezug_interval(item: Interval) -> bool:
    return (
        item.grid_w is not None
        and item.grid_w <= ZERO_GRID_W
        and item.pv_w is not None
        and item.pv_w >= ZERO_PV_W
    )


def _zero_bezug_pct(intervals: list[Interval]) -> int:
    """Share of PV-on 15-min slots with grid import ~0 W."""
    pv_on = sum(
        1 for item in intervals if item.pv_w is not None and item.pv_w >= ZERO_PV_W
    )
    zero = sum(1 for item in intervals if _is_zero_bezug_interval(item))
    return round(zero / pv_on * 100) if pv_on else 0


def _zero_bezug_spans(intervals: list[Interval]) -> list[list[int]]:
    """Index spans: Bezug ~0 W while PV is on (likely feed-in)."""
    spans: list[list[int]] = []
    start: int | None = None
    for i, item in enumerate(intervals):
        if _is_zero_bezug_interval(item):
            if start is None:
                start = i
        elif start is not None:
            spans.append([start, i - 1])
            start = None
    if start is not None:
        spans.append([start, len(intervals) - 1])
    return spans


ZERO_BEZUG_CHART_JS = """
Chart.register({
  id: 'zeroBezugHighlight',
  beforeDatasetsDraw(chart, _args, opts) {
    const spans = opts.spans || [];
    if (!spans.length) return;
    const { ctx, chartArea, scales: { x } } = chart;
    const n = chart.data.labels.length;
    const half = n > 1 ? Math.abs(x.getPixelForValue(1) - x.getPixelForValue(0)) / 2 : 8;
    ctx.save();
    ctx.fillStyle = 'rgba(168, 85, 247, 0.2)';
    for (const [from, to] of spans) {
      const x1 = x.getPixelForValue(from) - half;
      const x2 = x.getPixelForValue(to) + half;
      ctx.fillRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top);
    }
    ctx.restore();
  },
});
"""


def _interval_labels(intervals: list[Interval]) -> list[str]:
    days = {item.start.date() for item in intervals}
    fmt = "%m-%d %H:%M" if len(days) > 1 else "%H:%M"
    return [item.start.strftime(fmt) for item in intervals]


def write_html(path: Path, intervals: list[Interval], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = _interval_labels(intervals)
    grid_kwh = [item.grid_kwh for item in intervals]
    pv_kwh = [item.pv_kwh for item in intervals]
    house_kwh = [item.house_kwh for item in intervals]
    grid_w = [item.grid_w for item in intervals]
    pv_w = [item.pv_w for item in intervals]
    house_w = [item.house_w for item in intervals]
    zero_spans = _zero_bezug_spans(intervals)
    daily = _daily_totals(intervals)

    total_grid = sum(v for v in grid_kwh if v is not None)
    total_pv = sum(v for v in pv_kwh if v is not None)
    total_house = sum(v for v in house_kwh if v is not None)
    self_use_pct = (min(total_pv, total_house) / total_pv * 100) if total_pv else 0
    zero_bezug_pct = _zero_bezug_pct(intervals)

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
    .chart-legend {{ font-size: 0.85rem; color: #a855f7; margin: -0.25rem 0 0.75rem; }}
    .chart-legend span {{ display: inline-block; width: 0.9rem; height: 0.9rem; background: rgba(168, 85, 247, 0.35); border-radius: 2px; vertical-align: -0.1rem; margin-right: 0.35rem; }}
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
    <div class="card">0 Bezug (PV-Zeit)<strong>{zero_bezug_pct} %</strong></div>
  </div>
  <h2>Verbrauch &amp; Erzeugung über den Tag (W)</h2>
  <p class="chart-legend"><span></span>Bezug ≈ 0 bei PV — {zero_bezug_pct}% der PV-Intervalle (evtl. Einspeisung)</p>
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
    const zeroBezugSpans = {json.dumps(zero_spans)};
    const dailyLabels = {json.dumps(list(sorted(daily.keys())))};
    const dailyGrid = {json.dumps([daily[d]['grid'] for d in sorted(daily.keys())])};
    const dailyPv = {json.dumps([daily[d]['pv'] for d in sorted(daily.keys())])};

    const chartOpts = {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      scales: {{ x: {{ ticks: {{ maxTicksLimit: 24 }} }} }},
      plugins: {{
        legend: {{ position: 'bottom' }},
        zeroBezugHighlight: {{ spans: zeroBezugSpans }},
      }},
    }};
    const dailyChartOpts = {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      scales: {{ x: {{ ticks: {{ maxTicksLimit: 24 }} }} }},
      plugins: {{ legend: {{ position: 'bottom' }} }},
    }};

    {ZERO_BEZUG_CHART_JS}

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
      options: dailyChartOpts,
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
<html lang="de" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>House Lulu — Energy</title>
  <link rel="stylesheet" href="./assets/date-picker.css" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      margin: 0 auto;
      padding: 1rem;
      padding-bottom: calc(1rem + env(safe-area-inset-bottom));
      max-width: 1200px;
      background: #0f172a;
      color: #e2e8f0;
    }}
    h1 {{ margin: 0 0 0.25rem; font-size: clamp(1.1rem, 4.5vw, 1.75rem); line-height: 1.25; }}
    .meta {{ color: #94a3b8; margin-bottom: 0.75rem; font-size: 0.9rem; line-height: 1.4; }}
    .overview-hint {{ color: #94a3b8; margin: -0.25rem 0 0.5rem; font-size: 0.85rem; line-height: 1.4; }}
    .absent-banner {{ background: #422006; border: 1px solid #ca8a04; color: #fde68a; padding: 0.5rem 0.75rem; border-radius: 8px; margin-bottom: 0.75rem; font-size: 0.9rem; line-height: 1.4; }}
    .present-summary {{ color: #94a3b8; margin: 0 0 1rem; font-size: 0.85rem; line-height: 1.45; }}
    .day-fallback {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }}
    .day-fallback button {{
      background: #1e293b;
      color: #e2e8f0;
      border: 1px solid #334155;
      border-radius: 8px;
      min-height: 40px;
      padding: 0 0.75rem;
      cursor: pointer;
      font-size: 0.9rem;
    }}
    .day-fallback button:hover {{ border-color: #38bdf8; }}
    .day-fallback button:disabled {{ opacity: 0.35; cursor: default; }}
    .day-fallback .day-label {{
      flex: 1;
      min-width: 200px;
      text-align: left;
      padding: 0 1rem;
    }}
    .picker-error {{
      color: #fca5a5;
      font-size: 0.85rem;
      margin: -0.5rem 0 1rem;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.65rem;
      margin-bottom: 1rem;
    }}
    @media (min-width: 720px) {{
      .cards {{ gap: 1rem; }}
      body {{ padding: 1.5rem; }}
    }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 0.75rem; font-size: 0.85rem; }}
    .card strong {{ display: block; font-size: clamp(1.1rem, 4vw, 1.4rem); margin-top: 0.2rem; }}
    .chart-wrap {{
      position: relative;
      height: clamp(220px, 48vh, 380px);
      margin-bottom: 1rem;
      background: #1e293b;
      border-radius: 12px;
      padding: 0.65rem;
    }}
    .chart-scroll {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior-x: contain;
      margin-bottom: 1rem;
      border-radius: 12px;
    }}
    .chart-scroll .chart-wrap--overview {{
      height: clamp(200px, 36vh, 280px);
      min-width: max(100%, calc(var(--day-count, 14) * 2.75rem));
      margin-bottom: 0;
    }}
    canvas {{ display: block; width: 100% !important; height: 100% !important; }}
    h2 {{ font-size: 0.95rem; color: #94a3b8; margin: 0 0 0.35rem; }}
    .chart-legend {{ font-size: 0.8rem; color: #a855f7; margin: -0.15rem 0 0.5rem; line-height: 1.35; }}
    .chart-legend span {{ display: inline-block; width: 0.85rem; height: 0.85rem; background: rgba(168, 85, 247, 0.35); border-radius: 2px; vertical-align: -0.1rem; margin-right: 0.3rem; }}
    code {{ font-size: 0.8em; word-break: break-all; }}
  </style>
</head>
<body>
  <h1 id="title">House Lulu — Energy</h1>
  <p class="meta" id="meta"></p>
  <p id="absentBanner" class="absent-banner" hidden>Abwesend — niedriger Verbrauch erwartbar, nicht in Ø „anwesend“.</p>
  <p class="present-summary" id="presentSummary"></p>
  <div id="lulu-date-picker">
    <div id="lulu-date-fallback" class="day-fallback" aria-label="Tag wählen">
      <button type="button" id="fallbackPrev" aria-label="Vorheriger Tag">←</button>
      <button type="button" id="fallbackLabel" class="day-label"></button>
      <button type="button" id="fallbackNext" aria-label="Nächster Tag">→</button>
    </div>
  </div>
  <p id="pickerError" class="picker-error" hidden></p>
  <div class="cards">
    <div class="card">Netzbezug<strong id="totalGrid"></strong></div>
    <div class="card">PV Erzeugung<strong id="totalPv"></strong></div>
    <div class="card">Hausverbrauch (geschätzt)<strong id="totalHouse"></strong></div>
    <div class="card">Eigenverbrauch PV<strong id="totalSelf"></strong></div>
    <div class="card">0 Bezug (PV-Zeit)<strong id="totalZeroBezug"></strong></div>
  </div>
  <h2>Verbrauch &amp; Erzeugung über den Tag (W)</h2>
  <p class="chart-legend" id="zeroBezugLegend"><span></span>Bezug ≈ 0 bei PV</p>
  <div class="chart-wrap"><canvas id="powerChart"></canvas></div>
  <h2>Energie pro 15 min (kWh)</h2>
  <div class="chart-wrap"><canvas id="intervalChart"></canvas></div>
  <h2>Tageswerte — alle Tage (kWh)</h2>
  <p class="overview-hint">Grau = abwesend · Balken anklicken wechselt den Tag oben</p>
  <div class="chart-scroll" id="dailyScroll">
    <div class="chart-wrap chart-wrap--overview"><canvas id="dailyChart"></canvas></div>
  </div>
  <script>
    const daysData = {days_json};
    const dayKeys = Object.keys(daysData).sort();
    const hashDay = location.hash.slice(1);
    let currentDay = daysData[hashDay] ? hashDay : dayKeys[dayKeys.length - 1];
    let powerChart, intervalChart, dailyChart;

    function dayIndex(day) {{
      return dayKeys.indexOf(day);
    }}

    function presentDayKeys() {{
      return dayKeys.filter((day) => !daysData[day].absent);
    }}

    function avgPresent(field) {{
      const days = presentDayKeys();
      if (!days.length) return 0;
      return days.reduce((sum, day) => sum + daysData[day].totals[field], 0) / days.length;
    }}

    function updatePresentSummary() {{
      const days = presentDayKeys();
      const el = document.getElementById('presentSummary');
      if (!days.length) {{
        el.textContent = '';
        return;
      }}
      el.textContent =
        'Ø anwesend (' + days.length + ' Tage): Netzbezug ' + avgPresent('grid').toFixed(2) +
        ' kWh · PV ' + avgPresent('pv').toFixed(2) +
        ' kWh · Haus ' + avgPresent('house').toFixed(2) + ' kWh';
    }}

    function barFill(day, metric) {{
      const absent = daysData[day].absent;
      const selected = day === currentDay;
      if (metric === 'grid') {{
        if (selected) return absent ? '#94a3b8' : '#fb923c';
        return absent ? 'rgba(148,163,184,0.35)' : '#f97316';
      }}
      if (selected) return absent ? '#4ade80' : '#4ade80';
      return absent ? 'rgba(34,197,94,0.25)' : '#22c55e';
    }}

    function dailyBarMeta() {{
      return {{
        backgroundColor: [
          dayKeys.map((d) => barFill(d, 'grid')),
          dayKeys.map((d) => barFill(d, 'pv')),
        ],
        borderColor: dayKeys.map((d) => (d === currentDay ? '#38bdf8' : 'transparent')),
        borderWidth: dayKeys.map((d) => (d === currentDay ? 2 : 0)),
      }};
    }}

    function isMobile() {{
      return window.innerWidth < 640;
    }}

    function chartScales(mobile) {{
      return {{
        x: {{
          ticks: {{
            maxTicksLimit: mobile ? 8 : 24,
            maxRotation: mobile ? 0 : 45,
            minRotation: 0,
            font: {{ size: mobile ? 10 : 12 }},
          }},
        }},
        y: {{
          ticks: {{ font: {{ size: mobile ? 10 : 12 }} }},
        }},
      }};
    }}

    function legendOpts(mobile) {{
      return {{
        position: 'bottom',
        labels: {{
          boxWidth: mobile ? 10 : 40,
          padding: mobile ? 8 : 12,
          font: {{ size: mobile ? 11 : 12 }},
        }},
      }};
    }}

    function makeChartOpts(spans) {{
      const mobile = isMobile();
      return {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        scales: chartScales(mobile),
        plugins: {{
          legend: legendOpts(mobile),
          zeroBezugHighlight: {{ spans }},
        }},
      }};
    }}

    function dailyChartOpts() {{
      const mobile = isMobile();
      const meta = dailyBarMeta();
      return {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: true }},
        onHover: (event, elements) => {{
          event.native.target.style.cursor = elements.length ? 'pointer' : 'default';
        }},
        onClick: (_event, elements) => {{
          if (!elements.length) return;
          selectDay(dayKeys[elements[0].index], {{ scrollToTop: true }});
        }},
        scales: {{
          x: {{
            ticks: {{
              maxRotation: mobile ? 45 : 0,
              minRotation: mobile ? 45 : 0,
              font: {{ size: mobile ? 9 : 12 }},
            }},
          }},
          y: {{
            ticks: {{ font: {{ size: mobile ? 10 : 12 }} }},
          }},
        }},
        plugins: {{ legend: legendOpts(mobile) }},
      }};
    }}

    function applyResponsiveCharts() {{
      const mobile = isMobile();
      const spans = daysData[currentDay].zeroBezugSpans || [];
      [powerChart, intervalChart].forEach((chart) => {{
        chart.options.scales = chartScales(mobile);
        chart.options.plugins.legend = legendOpts(mobile);
        chart.options.plugins.zeroBezugHighlight = {{ spans }};
        chart.update();
      }});
      dailyChart.options = dailyChartOpts();
      dailyChart.update();
    }}

    {ZERO_BEZUG_CHART_JS}

    function initCharts() {{
      const meta = dailyBarMeta();
      powerChart = new Chart(document.getElementById('powerChart'), {{
        type: 'line',
        data: {{ labels: [], datasets: [
          {{ label: 'Netzbezug (W)', data: [], borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV Erzeugung (W)', data: [], borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Hausverbrauch (W)', data: [], borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ]}},
        options: makeChartOpts([]),
      }});
      intervalChart = new Chart(document.getElementById('intervalChart'), {{
        type: 'line',
        data: {{ labels: [], datasets: [
          {{ label: 'Bezug (kWh)', data: [], borderColor: '#f97316', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'PV (kWh)', data: [], borderColor: '#22c55e', tension: 0.2, spanGaps: true, pointRadius: 0 }},
          {{ label: 'Haus (kWh)', data: [], borderColor: '#38bdf8', tension: 0.2, spanGaps: true, pointRadius: 0 }},
        ]}},
        options: makeChartOpts([]),
      }});
      dailyChart = new Chart(document.getElementById('dailyChart'), {{
        type: 'bar',
        data: {{
          labels: dayKeys.map((d) => d.slice(5)),
          datasets: [
            {{ label: 'Bezug kWh', data: dayKeys.map((d) => daysData[d].totals.grid), backgroundColor: meta.backgroundColor[0], borderColor: meta.borderColor, borderWidth: meta.borderWidth }},
            {{ label: 'PV kWh', data: dayKeys.map((d) => daysData[d].totals.pv), backgroundColor: meta.backgroundColor[1], borderColor: meta.borderColor, borderWidth: meta.borderWidth }},
          ],
        }},
        options: dailyChartOpts(),
      }});
    }}

    document.getElementById('dailyScroll').style.setProperty('--day-count', dayKeys.length);

    function updateDailyHighlight() {{
      const meta = dailyBarMeta();
      dailyChart.data.datasets[0].backgroundColor = meta.backgroundColor[0];
      dailyChart.data.datasets[1].backgroundColor = meta.backgroundColor[1];
      dailyChart.data.datasets.forEach((dataset) => {{
        dataset.borderColor = meta.borderColor;
        dataset.borderWidth = meta.borderWidth;
      }});
      dailyChart.update();
    }}

    function selectDay(day, {{ scrollToTop = false }} = {{}}) {{
      if (!daysData[day]) return;
      if (day !== currentDay) {{
        currentDay = day;
        history.replaceState(null, '', '#' + day);
        showDay(day);
        updateDailyHighlight();
        updateFallbackNav();
        window.__luluNotifyDayChange?.();
      }}
      if (scrollToTop) {{
        document.getElementById('title').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }}

    window.selectDay = selectDay;
    window.__luluGetPickerState = () => ({{
      dayKeys,
      daysData,
      currentDay,
      onSelectDay: (day) => selectDay(day),
    }});

    function showDay(day) {{
      const d = daysData[day];
      const absent = !!d.absent;
      document.getElementById('title').textContent = 'House Lulu — ' + day + (absent ? ' (abwesend)' : '');
      document.getElementById('meta').textContent =
        'SmartVisio Bezug + Hoymiles Erzeugung · ' + d.totals.intervals + ' Intervalle (15 min)';
      document.getElementById('absentBanner').hidden = !absent;
      document.getElementById('totalGrid').textContent = d.totals.grid.toFixed(2) + ' kWh';
      document.getElementById('totalPv').textContent = d.totals.pv.toFixed(2) + ' kWh';
      document.getElementById('totalHouse').textContent = d.totals.house.toFixed(2) + ' kWh';
      document.getElementById('totalSelf').textContent = d.totals.selfUsePct + ' %';
      document.getElementById('totalZeroBezug').textContent = d.totals.zeroBezugPct + ' %';
      document.getElementById('zeroBezugLegend').innerHTML =
        '<span></span>Bezug ≈ 0 bei PV — ' + d.totals.zeroBezugPct +
        '% der PV-Intervalle (evtl. Einspeisung)';

      const spans = d.zeroBezugSpans || [];
      powerChart.options.plugins.zeroBezugHighlight.spans = spans;
      intervalChart.options.plugins.zeroBezugHighlight.spans = spans;

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
    }}

    function updateFallbackNav() {{
      const idx = dayIndex(currentDay);
      const label = document.getElementById('fallbackLabel');
      const prev = document.getElementById('fallbackPrev');
      const next = document.getElementById('fallbackNext');
      if (!label || !prev || !next) return;
      label.textContent = currentDay + (daysData[currentDay]?.absent ? ' ✈' : '');
      prev.disabled = idx <= 0;
      next.disabled = idx >= dayKeys.length - 1;
    }}

    function mountDatePickerWidget() {{
      const el = document.getElementById('lulu-date-picker');
      const err = document.getElementById('pickerError');
      if (!el) return;

      const script = document.createElement('script');
      script.src = './assets/date-picker.js';
      script.onload = () => {{
        try {{
          const picker = window.LuluDatePicker ?? globalThis.LuluDatePicker;
          if (!picker?.mountDatePicker) {{
            throw new Error('LuluDatePicker global missing');
          }}
          const fallback = document.getElementById('lulu-date-fallback');
          if (fallback) fallback.remove();
          window.__luluNotifyDayChange = picker.notifyDayChange;
          picker.mountDatePicker(el, () => window.__luluGetPickerState());
        }} catch (error) {{
          if (err) {{
            err.hidden = false;
            err.textContent = 'Kalender konnte nicht laden: ' + error.message;
          }}
          console.error(error);
        }}
      }};
      script.onerror = () => {{
        if (err) {{
          err.hidden = false;
          err.textContent = 'Kalender-Script nicht gefunden (./assets/date-picker.js). merge-all.sh erneut ausführen.';
        }}
      }};
      document.body.appendChild(script);
    }}

    document.getElementById('fallbackPrev')?.addEventListener('click', () => {{
      const idx = dayIndex(currentDay);
      if (idx > 0) selectDay(dayKeys[idx - 1]);
    }});
    document.getElementById('fallbackNext')?.addEventListener('click', () => {{
      const idx = dayIndex(currentDay);
      if (idx < dayKeys.length - 1) selectDay(dayKeys[idx + 1]);
    }});

    window.addEventListener('keydown', (event) => {{
      if (event.target.closest('select, input, textarea, button')) return;
      const idx = dayIndex(currentDay);
      if (event.key === 'ArrowLeft' && idx > 0) {{
        event.preventDefault();
        selectDay(dayKeys[idx - 1]);
      }} else if (event.key === 'ArrowRight' && idx < dayKeys.length - 1) {{
        event.preventDefault();
        selectDay(dayKeys[idx + 1]);
      }}
    }});

    window.addEventListener('hashchange', () => {{
      const day = location.hash.slice(1);
      if (daysData[day]) selectDay(day);
    }});

    initCharts();
    updatePresentSummary();
    history.replaceState(null, '', '#' + currentDay);
    showDay(currentDay);
    updateDailyHighlight();
    updateFallbackNav();
    mountDatePickerWidget();

    let resizeTimer;
    window.addEventListener('resize', () => {{
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(applyResponsiveCharts, 150);
    }});
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


def _write_day_csvs(days_map: dict[str, list[Interval]]) -> None:
    for day, intervals in days_map.items():
        out_dir = OUTPUT_ROOT / day
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "merged-energy.csv"
        write_csv(csv_path, intervals)
        print(f"wrote {csv_path} ({len(intervals)} intervals)")


def _build_date_picker_assets() -> None:
    if not (VIEWER_DIR / "package.json").is_file():
        raise SystemExit(
            "missing viewer/package.json — run: cd viewer && npm install && npm run build"
        )
    node_modules = VIEWER_DIR / "node_modules"
    if not node_modules.is_dir():
        subprocess.run(["npm", "install"], cwd=VIEWER_DIR, check=True)
    subprocess.run(["npm", "run", "build"], cwd=VIEWER_DIR, check=True)


def _sync_date_picker_assets() -> None:
    if not DATE_PICKER_ASSETS.is_dir():
        return
    for target in (OUTPUT_ROOT, PAGES_INDEX.parent):
        dest = target / "assets"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(DATE_PICKER_ASSETS, dest)


def refresh_viewer(imports_root: Path = IMPORTS_ROOT) -> Path | None:
    days_map = collect_day_intervals(imports_root)
    if not days_map:
        return None
    absent_days = load_absent_days(imports_root)
    days_data: dict[str, dict] = {}
    for day, intervals in days_map.items():
        payload = intervals_payload(intervals)
        payload["absent"] = day in absent_days
        days_data[day] = payload
    viewer_path = OUTPUT_ROOT / "energy-report.html"
    _build_date_picker_assets()
    write_viewer_html(viewer_path, days_data)
    write_viewer_html(PAGES_INDEX, days_data)
    _sync_date_picker_assets()
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
    days_map = collect_day_intervals(imports_root)
    if not days_map:
        raise SystemExit(f"no import days/weeks found in {imports_root}")

    _write_day_csvs(days_map)

    for name in discover_import_dirs(imports_root):
        if not WEEK_DIR_RE.fullmatch(name):
            continue
        intervals = merge_day_intervals(name, imports_root)
        out_dir = OUTPUT_ROOT / name
        csv_path = out_dir / "merged-energy.csv"
        html_path = out_dir / "energy-report.html"
        write_csv(csv_path, intervals)
        write_html(html_path, intervals, f"House Lulu — {name}")
        print(f"wrote {csv_path} ({len(intervals)} intervals)")

    viewer = refresh_viewer(imports_root)
    if viewer:
        print(f"wrote {viewer} ({len(days_map)} days)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--day",
        help="YYYY-MM-DD or YYYY-week-WW → imports/<name>/ → output + refresh viewer",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="merge all import days/weeks + output/energy-report.html viewer",
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
        intervals = run_merge(
            smartvisio,
            hoymiles,
            out_dir,
            title,
            refresh_viewer_after=True,
            imports_root=args.imports_root,
        )
        if WEEK_DIR_RE.fullmatch(args.day):
            day_dirs = set(discover_days(args.imports_root))
            extra = {
                day: ivals
                for day, ivals in split_by_day(intervals).items()
                if day not in day_dirs
            }
            _write_day_csvs(extra)
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

