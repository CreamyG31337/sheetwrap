"""Drill hole check data (TBC point-to-surface CSV) and the per-sheet values
derived from it against an alignment."""
import csv
import re
from dataclasses import dataclass

from .alignment import format_station

COMPASS = ["NORTH", "EAST", "SOUTH", "WEST"]


@dataclass
class Hole:
    id: str
    e: float
    n: float
    z: float
    dist: float  # hole to wall, mm
    wall_e: float
    wall_n: float
    sta: float = 0.0
    off: float = 0.0
    wall_off: float = 0.0


def read_check_csv(path):
    """TBC export with columns: Point ID, Pt East, Pt North, Pt Elevation,
    Distance, East, North, Elevation (the last three are the wall point)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [Hole(r["Point ID"], float(r["Pt East"]), float(r["Pt North"]), float(r["Pt Elevation"]),
                     float(r["Distance"]), float(r["East"]), float(r["North"]))
                for r in csv.DictReader(f)]


def locate(holes, alignment):
    for h in holes:
        h.sta, h.off = alignment.station_offset(h.e, h.n)
        h.wall_off = alignment.station_offset(h.wall_e, h.wall_n)[1]
    return holes


def select(holes, rng):
    """Holes in an ID range like 'T100-T127' (same prefix, numeric part)."""
    m = re.fullmatch(r"\s*([A-Za-z]*)(\d+)\s*-\s*([A-Za-z]*)(\d+)\s*", rng)
    if not m:
        raise ValueError(f"bad hole range: {rng!r}")
    prefix, lo, hi = m[1], int(m[2]), int(m[4])
    out = []
    for h in holes:
        hm = re.fullmatch(r"([A-Za-z]*)(\d+)", h.id)
        if hm and hm[1] == prefix and lo <= int(hm[2]) <= hi:
            out.append(h)
    if not out:
        raise ValueError(f"no holes in range {rng}")
    return out


def _side(off):
    return "LT" if off < 0 else "RT"


def _range_text(vals, unit):
    lo, hi = round(min(vals), 1), round(max(vals), 1)
    return f"{lo:.1f} {unit}" if lo == hi else f"{lo:.1f} TO {hi:.1f} {unit}"


def sheet_values(holes, ranges, alignment, row_labels=(), decimals=2, increase="auto"):
    """Title block values for one sheet showing the holes in `ranges`.

    row_labels name the ranges in ascending elevation order (e.g. TOE,
    COLLAR) when there is one label per range. `increase` is the direction
    stations run across the page; "auto" assumes the wall is viewed from the
    alignment side, so stations run left-to-right on a left wall."""
    rows = [select(holes, r) for r in ranges]
    order = sorted(range(len(rows)), key=lambda i: sum(h.z for h in rows[i]) / len(rows[i]))
    labels = {}
    if len(row_labels) == len(rows):
        labels = {i: row_labels[rank] for rank, i in enumerate(order)}
    allh = [h for r in rows for h in r]
    mean_wall_off = sum(h.wall_off for h in allh) / len(allh)
    side = _side(mean_wall_off)
    mid_sta = sum(h.sta for h in allh) / len(allh)
    normal = (alignment.azimuth_at(mid_sta) + (-90 if side == "LT" else 90)) % 360
    compass = COMPASS[int((normal + 45) // 90) % 4]
    if increase == "auto":
        increase = "right" if side == "LT" else "left"

    def ref(h, i):
        tag = f" ({labels[i]})" if i in labels else ""
        return f"{h.id}{tag}  STA {format_station(h.sta, decimals)}  {_side(h.off)} {abs(h.off):.2f} m"

    lo_end = [ref(min(rows[i], key=lambda h: h.sta), i) for i in order]
    hi_end = [ref(max(rows[i], key=lambda h: h.sta), i) for i in order]
    elev = [(sum(h.z for h in rows[i]) / len(rows[i]), labels.get(i, ranges[i])) for i in order]
    stas = [h.sta for h in allh]
    return {
        "wall_name": f"{compass} ({'LEFT' if side == 'LT' else 'RIGHT'}) WALL",
        "holes": " / ".join(ranges),
        "station": f"{format_station(min(stas), 1)} TO {format_station(max(stas), 1)}",
        "offset": f"{side} " + _range_text([abs(h.wall_off) for h in allh], "m"),
        "elevation": " / ".join(f"{lab} {z:.3f}" for z, lab in sorted(elev, reverse=True)),
        "ends": {"left": lo_end if increase == "right" else hi_end,
                 "right": hi_end if increase == "right" else lo_end},
        "_sort": (0 if side == "LT" else 1, min(stas)),
    }
