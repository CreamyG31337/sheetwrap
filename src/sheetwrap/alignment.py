"""Horizontal alignment from a Trimble RoadXML (.rxl) file, with
station/offset lookup for arbitrary points."""
import math
import xml.etree.ElementTree as ET

ELEMENTS = ("Straight", "Arc", "EntrySpiral", "ExitSpiral")


class Alignment:
    def __init__(self, name, pts, closure_error):
        self.name = name
        self.pts = pts  # (station, E, N, azimuth rad), densified
        self.closure_error = closure_error  # worst element end mismatch, m
        self._coarse = list(range(0, len(pts), _COARSE))

    @classmethod
    def from_rxl(cls, path, step=0.01):
        root = ET.parse(path).getroot()
        return cls.from_elements(root.findtext("Name", "").strip(), root.find("HorizontalAlignment"), step)

    @classmethod
    def from_elements(cls, name, ha, step=0.01):
        """Integrate each element with curvature varying linearly along it
        (exact for straights and arcs, clothoid for spirals)."""
        pts, worst = [], 0.0
        for el in ha:
            if el.tag not in ELEMENTS:
                continue
            g = el.findtext
            sta0, length = float(g("StartStation")), float(g("Length"))
            az = math.radians(float(g("StartAzimuth")))
            sc = el.find("StartCoordinate")
            e, n = float(sc.findtext("East")), float(sc.findtext("North"))
            sgn = -1 if g("Direction") == "Left" else 1

            def k(r):
                r = (r or "").strip()
                return sgn / float(r) if r else 0.0

            if el.tag == "Straight":
                k0 = k1 = 0.0
            elif el.tag == "Arc":
                k0 = k1 = k(g("Radius"))
            else:
                k0, k1 = k(g("StartRadius")), k(g("EndRadius"))
            steps = max(1, int(length / step))
            ds = length / steps
            for i in range(steps):
                pts.append((sta0 + i * ds, e, n, az))
                kk = k0 + (k1 - k0) * (i + 0.5) / steps
                a_mid = az + kk * ds / 2
                e += ds * math.sin(a_mid)
                n += ds * math.cos(a_mid)
                az += kk * ds
            ec = el.find("EndCoordinate")
            if ec is not None:
                worst = max(worst, math.hypot(e - float(ec.findtext("East")), n - float(ec.findtext("North"))))
            pts.append((sta0 + length, e, n, az))
        if not pts:
            raise ValueError("no horizontal alignment elements found")
        return cls(name, pts, worst)

    def _nearest(self, e, n):
        d2 = lambda i: (e - self.pts[i][1]) ** 2 + (n - self.pts[i][2]) ** 2
        c = min(self._coarse, key=d2)
        lo, hi = max(0, c - 2 * _COARSE), min(len(self.pts), c + 2 * _COARSE)
        return min(range(lo, hi), key=d2)

    def station_offset(self, e, n):
        """(station, offset) of a point; offset is + right / - left of the
        alignment looking up-station."""
        sta, pe, pn, az = self.pts[self._nearest(e, n)]
        de, dn = e - pe, n - pn
        return (sta + de * math.sin(az) + dn * math.cos(az),
                de * math.cos(az) - dn * math.sin(az))

    def azimuth_at(self, station):
        """Azimuth in degrees at the densified point nearest `station`."""
        p = min(self.pts, key=lambda p: abs(p[0] - station))
        return math.degrees(p[3]) % 360


_COARSE = 100


def format_station(s, decimals=2):
    """-33.97 -> '-0+033.97'"""
    v = round(abs(s), decimals)
    km, m = int(v // 1000), v - (v // 1000) * 1000
    width = 3 + (decimals + 1 if decimals else 0)
    return f"{'-' if s < 0 and v else ''}{km}+{m:0{width}.{decimals}f}"
