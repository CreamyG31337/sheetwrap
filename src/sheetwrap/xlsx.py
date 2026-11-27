"""Excel report tables: one call writes styled, print-ready .xlsx sheets from rows.

    from sheetwrap.xlsx import Col, write_xlsx
    write_xlsx("check.xlsx", {"Points": {
        "title": "Footing pre-pour check", "subtitle": "Field CSV 26-329, design rev 2",
        "columns": ["Point", Col("Station", "station"), Col("Offset", "0.000"), Col("dZ", "signed"),
                    Col("Result", "status")],
        "rows": rows,                       # lists in column order, or dicts keyed by column name
        "notes": ["dZ = field - design; + = high."]}})

Stations are written as *numbers* shown as station text (``0"+"000.00``): 1005.81 shows ``1+005.81`` and
-5.81 shows ``-0+005.81``, and the column still sorts and works in formulas. (A CSV opened in Excel loses
the minus sign or turns stations into text.) Every sheet gets a frozen, filterable header, column widths
from the content, PASS/FAIL colours on ``status`` columns, and landscape fit-to-width printing with the
header repeated on each page.
"""
import datetime as _dt
import math
import re
from dataclasses import dataclass

NAVY, NAVY_TEXT = "1B365D", "FFFFFF"
STATUS_FILLS = (  # (prefixes, fill, font colour); matched on the upper-cased cell text
    (("PASS", "OK", "IN TOL", "WITHIN", "GOOD"), "D4EDDA", "155724"),
    (("FAIL", "OUT", "NG", "REJECT", "CLASH"), "F8D7DA", "721C24"),
    (("WARN", "CHECK", "REVIEW", "MISSING", "DRAFT"), "FFF3CD", "856404"),
)
FORMATS = {
    "text": "@",
    "int": "#,##0",
    "date": "yyyy-mm-dd",
    "datetime": "yyyy-mm-dd hh:mm",
    "percent": "0.0%",
    "signed": "+0.000;-0.000;0.000",
    "volume": "#,##0.0",
    "area": "#,##0.0",
}


@dataclass
class Col:
    """A column: ``fmt`` is a kind (``"station"``, ``"status"``, ``"signed"``, ``"volume"``, ``"date"``,
    ``"percent"``, ``"int"``, ``"text"``) or any Excel number format (``"0.000"``). ``dec``/``unit`` apply to
    stations (``unit=100`` for 100 m highway stationing ``901+25.00``). ``width`` overrides auto width."""
    name: str
    fmt: str | None = None
    width: float | None = None
    dec: int = 2
    unit: int = 1000


def station_format(dec=2, unit=1000):
    """Excel number format showing a numeric station as station text: ``0"+"000.00;-0"+"000.00``."""
    pos = f'0"+"{"0" * len(str(unit - 1))}' + (f".{'0' * dec}" if dec > 0 else "")
    return f"{pos};-{pos}"


_STA = re.compile(r"^\s*([+-]?)\s*(\d+)\s*\+\s*(\d+(?:\.\d*)?)\s*$")


def _station_value(v, unit):
    """Number for a station cell; accepts numbers and station text ('-0+005.81')."""
    if isinstance(v, str):
        m = _STA.match(v.replace(",", ""))
        if m:
            sign, blocks, rem = m.groups()
            x = int(blocks) * unit + float(rem)
            return -x if sign == "-" else x
        try:
            return float(v)
        except ValueError:
            return v                      # leave unparseable text as is
    return v


def _clean(v):
    """Plain Python value for openpyxl: numpy scalars -> int/float, NaN/inf -> blank."""
    if v is None:
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):   # numpy scalar
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _status_style(text):
    t = str(text).strip().upper()
    for prefixes, fill, font in STATUS_FILLS:
        if any(t == p or t.startswith(p + " ") or t.startswith(p + ":") or t.startswith(p + "(") for p in prefixes):
            return fill, font
    return None


def _shown_len(v, fmt):
    if v is None:
        return 0
    if isinstance(v, (_dt.date, _dt.datetime)):
        return 16 if isinstance(v, _dt.datetime) else 10
    if isinstance(v, float):
        return len(f"{v:,.3f}")
    return max(len(s) for s in str(v).split("\n"))


def write_xlsx(path, sheets, *, landscape=True):
    """Write ``sheets`` (``{sheet name: spec}``) to ``path`` and return the path.

    Each spec is a dict with ``columns`` (names or ``Col``), ``rows`` (lists in column order or dicts by
    column name) and optional ``title``, ``subtitle``, ``notes`` (list of lines under the table) and
    ``freeze`` (default True). Sheet names are trimmed to Excel's 31 characters.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if not sheets:
        raise ValueError("no sheets to write")
    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor=NAVY)
    hdr_font = Font(bold=True, color=NAVY_TEXT)
    used_names = set()

    for sheet_name, spec in sheets.items():
        name = re.sub(r"[\[\]:*?/\\]", "-", str(sheet_name))[:31] or "Sheet"
        base, k = name, 2
        while name.lower() in used_names:
            name = f"{base[:28]}-{k}"
            k += 1
        used_names.add(name.lower())
        ws = wb.create_sheet(name)
        cols = [c if isinstance(c, Col) else Col(str(c)) for c in spec["columns"]]
        if not cols:
            raise ValueError(f"sheet {sheet_name!r}: no columns")
        ncol = len(cols)
        last = get_column_letter(ncol)

        r = 1
        for key, font in (("title", Font(bold=True, size=13)), ("subtitle", Font(italic=True, color="555555"))):
            if spec.get(key):
                ws.cell(r, 1, spec[key]).font = font
                if ncol > 1:
                    ws.merge_cells(f"A{r}:{last}{r}")
                r += 1
        if r > 1:
            r += 1                              # blank line between titles and the table
        hdr_row = r
        for j, c in enumerate(cols, 1):
            cell = ws.cell(r, j, c.name)
            cell.fill, cell.font, cell.border = hdr_fill, hdr_font, border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        widths = [len(c.name) for c in cols]
        for row in spec.get("rows", []):
            r += 1
            if isinstance(row, dict):
                vals = [row.get(c.name) for c in cols]
            else:
                vals = list(row)
                if len(vals) > ncol:
                    raise ValueError(f"sheet {sheet_name!r}: row has {len(vals)} values for {ncol} columns")
                vals += [None] * (ncol - len(vals))
            for j, (c, v) in enumerate(zip(cols, vals), 1):
                v = _clean(v)
                fmt = c.fmt
                if fmt == "station":
                    v = _station_value(v, c.unit)
                cell = ws.cell(r, j, v)
                cell.border = border
                if fmt == "station":
                    if isinstance(v, (int, float)):
                        cell.number_format = station_format(c.dec, c.unit)
                        cell.alignment = Alignment(horizontal="right")
                    shown = len(str(int(abs(v) // c.unit))) + len(str(c.unit - 1)) + c.dec + 3 \
                        if isinstance(v, (int, float)) else _shown_len(v, fmt)
                elif fmt == "status":
                    st = _status_style(v) if v is not None else None
                    if st:
                        cell.fill = PatternFill("solid", fgColor=st[0])
                        cell.font = Font(bold=True, color=st[1])
                    cell.alignment = Alignment(horizontal="center")
                    shown = _shown_len(v, fmt)
                else:
                    if fmt:
                        cell.number_format = FORMATS.get(fmt, fmt)
                    elif isinstance(v, _dt.datetime):
                        cell.number_format = FORMATS["datetime"]
                    elif isinstance(v, _dt.date):
                        cell.number_format = FORMATS["date"]
                    shown = _shown_len(v, fmt)
                widths[j - 1] = max(widths[j - 1], shown)

        if spec.get("freeze", True):
            ws.freeze_panes = ws.cell(hdr_row + 1, 1)
        ws.auto_filter.ref = f"A{hdr_row}:{last}{max(r, hdr_row)}"
        for j, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(j)].width = c.width or min(60, max(8, widths[j - 1] + 2))

        notes = spec.get("notes") or []
        if notes:
            r += 2
            for line in notes:
                cell = ws.cell(r, 1, line)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if ncol > 1:
                    ws.merge_cells(f"A{r}:{last}{r}")
                total_w = sum(ws.column_dimensions[get_column_letter(j)].width for j in range(1, ncol + 1))
                ws.row_dimensions[r].height = 15 * max(1, math.ceil(len(str(line)) * 1.1 / max(total_w, 1)))
                r += 1

        ws.print_title_rows = f"{hdr_row}:{hdr_row}"
        ws.page_setup.orientation = "landscape" if landscape else "portrait"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    wb.save(path)
    return path
