import math

import pytest

from sheetwrap.alignment import Alignment
from sheetwrap.holes import Hole, locate, select, sheet_values

from helpers import rxl, straight_arc_spiral


@pytest.fixture
def al(tmp_path):
    p = tmp_path / "cl.rxl"
    p.write_text(rxl(straight_arc_spiral()))
    return Alignment.from_rxl(p)


def at(sta, off, az_deg=30):
    az = math.radians(az_deg)
    return (1000 + sta * math.sin(az) + off * math.cos(az),
            5000 + sta * math.cos(az) - off * math.sin(az))


def wall_holes(side):
    """Left (side=-1) or right wall 6 m from CL: toes 0.3 m behind the face
    at EL 100, collars 0.3 m in front at EL 108, stations 5..15."""
    hs = []
    for i, sta in enumerate(range(5, 16)):
        for prefix, z, d in (("T1", 100.0, 6.3), ("T2", 108.0, 5.7)):
            e, n = at(sta, side * d)
            we, wn = at(sta, side * 6.0)
            hs.append(Hole(f"{prefix}{i:02d}", e, n, z, 300, we, wn))
    return hs


def test_select_range():
    hs = wall_holes(-1)
    assert [h.id for h in select(hs, "T100-T102")] == ["T100", "T101", "T102"]
    with pytest.raises(ValueError):
        select(hs, "X1-X2")


def test_left_wall_values(al):
    hs = locate(wall_holes(-1), al)
    v = sheet_values(hs, ["T100-T110", "T200-T210"], al, ("TOE", "COLLAR"))
    assert v["wall_name"] == "WEST (LEFT) WALL" or "(LEFT) WALL" in v["wall_name"]
    assert v["offset"] == "LT 6.0 m"
    assert v["elevation"] == "COLLAR 108.000 / TOE 100.000"
    assert v["station"] == "0+005.0 TO 0+015.0"
    # left wall seen from the CL: stations increase to the right
    assert v["ends"]["left"][0].startswith("T100 (TOE)  STA 0+005.00  LT 6.30")
    assert v["ends"]["right"][1].startswith("T210 (COLLAR)  STA 0+015.00  LT 5.70")


def test_right_wall_ends_flip(al):
    hs = locate(wall_holes(1), al)
    v = sheet_values(hs, ["T100-T110", "T200-T210"], al, ("TOE", "COLLAR"))
    assert v["offset"] == "RT 6.0 m"
    assert v["ends"]["left"][0].startswith("T110 (TOE)  STA 0+015.00")
    assert v["_sort"][0] == 1
