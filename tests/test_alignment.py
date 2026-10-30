import math

import pytest

from sheetwrap.alignment import Alignment, format_station

from helpers import rxl, straight_arc_spiral


@pytest.fixture
def al(tmp_path):
    p = tmp_path / "cl.rxl"
    p.write_text(rxl(straight_arc_spiral()))
    return Alignment.from_rxl(p)


def test_integration_closes_on_element_ends(al):
    assert al.closure_error < 0.001  # 1 mm against analytic end coordinates


def test_station_offset_on_straight(al):
    az = math.radians(30)
    # 10 m up-station, 5 m right
    e = 1000 + 10 * math.sin(az) + 5 * math.cos(az)
    n = 5000 + 10 * math.cos(az) - 5 * math.sin(az)
    sta, off = al.station_offset(e, n)
    assert sta == pytest.approx(10, abs=0.005)
    assert off == pytest.approx(5, abs=0.005)


def test_station_offset_left_is_negative(al):
    az = math.radians(30)
    e = 1000 + 20 * math.sin(az) - 3 * math.cos(az)
    n = 5000 + 20 * math.cos(az) + 3 * math.sin(az)
    assert al.station_offset(e, n)[1] == pytest.approx(-3, abs=0.005)


def test_points_on_curve_round_trip(al):
    for sta, e, n, _ in al.pts[::500]:
        s, o = al.station_offset(e, n)
        assert s == pytest.approx(sta, abs=0.005)
        assert o == pytest.approx(0, abs=0.005)


@pytest.mark.parametrize("s,dec,expected", [
    (-33.974, 2, "-0+033.97"), (5.0, 1, "0+005.0"), (1234.567, 2, "1+234.57"), (-0.001, 2, "0+000.00"),
])
def test_format_station(s, dec, expected):
    assert format_station(s, dec) == expected
