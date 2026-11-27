"""Synthetic fixtures - no project data in the repo."""
import math


def rxl(elements, name="TEST CL"):
    """RoadXML text from (tag, fields) pairs; fields hold StartStation,
    StartAzimuth, Length, start/end coords and curve params."""
    parts = []
    for tag, f in elements:
        body = "".join(f"<{k}>{v}</{k}>" for k, v in f.items() if k not in ("start", "end"))
        body += f"<StartCoordinate><North>{f['start'][1]}</North><East>{f['start'][0]}</East></StartCoordinate>"
        body += f"<EndCoordinate><North>{f['end'][1]}</North><East>{f['end'][0]}</East></EndCoordinate>"
        parts.append(f"<{tag}>{body}</{tag}>")
    return (f'<?xml version="1.0"?><TrimbleRoad><Name>{name}</Name>'
            f"<HorizontalAlignment>{''.join(parts)}</HorizontalAlignment></TrimbleRoad>")


def straight_arc_spiral(e0=1000.0, n0=5000.0, az_deg=30.0):
    """Straight 50 m, then entry spiral 40 m into a left arc R=100 of 30 m.
    End coordinates computed analytically, independent of the integrator."""
    az = math.radians(az_deg)
    els = []
    e1, n1 = e0 + 50 * math.sin(az), n0 + 50 * math.cos(az)
    els.append(("Straight", dict(StartStation=0, StartAzimuth=az_deg, Length=50, start=(e0, n0), end=(e1, n1))))
    # clothoid series in local frame (x along tangent, y to the left)
    L, R = 40.0, 100.0
    x = L - L ** 3 / (40 * R ** 2) + L ** 5 / (3456 * R ** 4)
    y = L ** 2 / (6 * R) - L ** 4 / (336 * R ** 3)
    e2 = e1 + x * math.sin(az) - y * math.cos(az)
    n2 = n1 + x * math.cos(az) + y * math.sin(az)
    els.append(("EntrySpiral", dict(StartStation=50, StartAzimuth=az_deg, Length=L, Direction="Left",
                                    StartRadius="", EndRadius=R, start=(e1, n1), end=(e2, n2))))
    az2 = az - L / (2 * R)
    # left arc: centre is 90 deg left of the tangent
    ce, cn = e2 - R * math.cos(az2), n2 + R * math.sin(az2)
    sweep = 30 / R
    a_end = az2 - sweep
    e3, n3 = ce + R * math.cos(a_end), cn - R * math.sin(a_end)
    els.append(("Arc", dict(StartStation=90, StartAzimuth=math.degrees(az2), Length=30, Direction="Left",
                            Radius=R, start=(e2, n2), end=(e3, n3))))
    return els
