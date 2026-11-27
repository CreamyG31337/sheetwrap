"""write_xlsx: numeric stations shown as station text, status colours, layout (synthetic data)."""
import datetime as dt

import numpy as np
import pytest
from openpyxl import load_workbook

from sheetwrap.xlsx import Col, station_format, write_xlsx


def test_station_format():
    assert station_format() == '0"+"000.00;-0"+"000.00'
    assert station_format(0) == '0"+"000;-0"+"000'
    assert station_format(2, unit=100) == '0"+"00.00;-0"+"00.00'


def test_write_xlsx_tables(tmp_path):
    rows = [
        ["P1", -5.81, np.float64(-0.012), 0.0123, "PASS", dt.date(2026, 11, 27)],
        ["P2", "1+005.81", 2.5, np.nan, "FAIL (high)", None],
        {"Point": "P3", "Station": "0+050", "Result": "check"},
    ]
    path = write_xlsx(tmp_path / "check.xlsx", {
        "Tolerance check: pre-pour": {
            "title": "Synthetic footing check",
            "subtitle": "N 1000 / E 2000 local grid",
            "columns": ["Point", Col("Station", "station"), Col("Offset", "0.000"), Col("dZ", "signed"),
                        Col("Result", "status"), "Date"],
            "rows": rows,
            "notes": ["dZ = field - design; + = high."],
        },
        "Summary": {"columns": ["Item", Col("Volume (m3)", "volume")], "rows": [["Fill", 114.66]]},
    })
    wb = load_workbook(path)
    assert wb.sheetnames == ["Tolerance check- pre-pour", "Summary"]   # ':' is not allowed in sheet names
    ws = wb["Tolerance check- pre-pour"]
    assert ws["A1"].value == "Synthetic footing check"
    hdr = 4                                            # title, subtitle, blank, header
    assert [c.value for c in ws[hdr]] == ["Point", "Station", "Offset", "dZ", "Result", "Date"]
    assert ws.freeze_panes == f"A{hdr + 1}"
    assert ws.auto_filter.ref == f"A{hdr}:F{hdr + 3}"
    assert ws.print_title_rows == f"${hdr}:${hdr}"

    # stations: numbers (sortable, sign kept) with a station display format; text input parsed
    sta = [ws.cell(hdr + i, 2) for i in (1, 2, 3)]
    assert [c.value for c in sta] == [pytest.approx(-5.81), pytest.approx(1005.81), pytest.approx(50.0)]
    assert all(c.number_format == '0"+"000.00;-0"+"000.00' for c in sta)

    assert ws.cell(hdr + 1, 3).value == pytest.approx(-0.012)          # numpy scalar -> float
    assert ws.cell(hdr + 2, 4).value is None                            # NaN -> blank
    assert ws.cell(hdr + 1, 4).number_format == "+0.000;-0.000;0.000"
    assert ws.cell(hdr + 1, 6).number_format == "yyyy-mm-dd"

    fills = [ws.cell(hdr + i, 5).fill.fgColor.rgb[-6:] for i in (1, 2, 3)]
    assert fills == ["D4EDDA", "F8D7DA", "FFF3CD"]                      # pass / fail / check
    assert ws.cell(hdr + 5, 1).value.startswith("dZ = field")           # notes under the table

    ws2 = wb["Summary"]
    assert ws2.freeze_panes == "A2" and ws2["B2"].number_format == "#,##0.0"


def test_write_xlsx_rejects_long_rows(tmp_path):
    with pytest.raises(ValueError, match="3 values for 2 columns"):
        write_xlsx(tmp_path / "x.xlsx", {"S": {"columns": ["A", "B"], "rows": [[1, 2, 3]]}})
