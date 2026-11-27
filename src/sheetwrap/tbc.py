"""Read bits of Trimble Business Center HTML reports."""
import html
import re
from pathlib import Path


def _cells(text):
    """{label: value} from '<td>Label:</td><td>Value</td>' pairs."""
    pairs = re.findall(r"<td[^>]*>\s*([^<:]+?):\s*</td>\s*<td[^>]*>([^<]*)</td>", text, re.I)
    out = {}
    for k, v in pairs:
        out.setdefault(html.unescape(k).strip(), html.unescape(v).strip())
    return out


def datum_from_report(path):
    """Datum line from a TBC Project Computation Report, e.g.
    'NAD83(CSRS)v7 UTM ZONE 10N / VERT: CVD28 (HT2_1997)'."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # skip the "Project File Data" block, whose Name: is the project file path
    c = _cells(text.split("Coordinate System", 1)[-1])
    datum = re.sub(r"-\d{4}$", "", c.get("Datum", "")).strip()
    system = c.get("Name", "").split("/")[-1].strip().upper()
    zone = c.get("Zone", "")
    zm = re.match(r"(\d+)\s*(North|South)", zone, re.I)
    zone = f"{zm[1]}{zm[2][0].upper()}" if zm else zone.upper()
    vert = c.get("Vertical datum", "").upper()
    geoid = c.get("Geoid", "").split()[-1] if c.get("Geoid") else ""
    s = " ".join(p for p in (datum, system, f"ZONE {zone}" if zone else "") if p)
    if vert:
        s += f" / VERT: {vert}" + (f" ({geoid})" if geoid else "")
    return s
