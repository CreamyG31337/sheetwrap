# sheetwrap

Wrap an existing PDF report (e.g. a Bluebeam/TBC screenshot report) in a
title block sheet, without regenerating it in CAD.

- Each source page is placed on the new sheet as a vector Form XObject, so
  embedded images are **copied byte-for-byte** — no resampling or
  recompression. Every build verifies this and reports it.
- Pages with two views (ortho over plan) are split and stacked at one
  common scale and horizontal alignment, each with a view title, so a
  station grid marked up afterwards lines up through both.
- With an alignment (`.rxl`) and a TBC point-to-surface check CSV, the
  station range, wall side/offset, elevations, end-of-view station
  references and sheet order are computed rather than typed.

## Install

On the survey PC it is already installed (editable) in the shared `C:\Projects\.venv`. Run it with
`C:\Projects\.venv\Scripts\python.exe -m sheetwrap ...` (see `C:\Projects\TOOLS.md`). Elsewhere:

```powershell
uv venv .venv
uv pip install --python .venv -e ".[dev]"
```

Set the logo once per machine (SVG/PDF/AI are placed as vectors):

```powershell
[Environment]::SetEnvironmentVariable("SHEETWRAP_LOGO", "C:\path\to\logo.svg", "User")
```

Without it the title block shows a COMPANY text row instead.

## Use

```powershell
sheetwrap build job.json                 # write the title-blocked PDF
sheetwrap stations channel.rxl check.csv # station/offset of every hole, as CSV
sheetwrap datum computation_report.html  # datum line from a TBC report
```

Where application control blocks the generated `sheetwrap.exe` launcher, use
`.venv\Scripts\python.exe -m sheetwrap ...` instead.

Keep each job's JSON next to its data, **not** in this repo.

## Job file

```jsonc
{
  "extends": ["company", "shear_check"],   // built-in templates or relative paths
  "input": "report.pdf",
  "output": "report - TB.pdf",

  "project": "1234 - SOME PROJECT",
  "title": "SHEAR BENCH 100 - DRILL HOLE OFFSET CHECK\nSTA 0+000 TO 0+030",
  "drawing_no": "0000001", "revision": "0", "date": "2026-01-01",
  "drawn_by": "AB", "checked_by": "CD",
  "datum": "...",                          // or "datum_from_tbc_report": "report.html"

  "alignment": "channel.rxl",              // optional: enables computed values
  "holes_csv": "check.csv",
  "job_notes": ["HOLE IDs: ...", "WALL DESIGN SURFACE: ..."],

  "pages": [                               // one per output sheet
    {"source_page": 2, "holes": ["T100-T127", "T200-T229"]},
    {"source_page": 1, "holes": ["T127-T173", "T227-T273"]}
  ]
}
```

**Screenshots instead of a PDF:** omit `input` and give each page its
image files, top view first. They are stacked at one width and placed on an
11x17 sheet (`"sheet_size": [1224, 792]` to change). PNG pixels are kept
exactly; the build checks decoded pixels rather than stream bytes.

```jsonc
"pages": [{"images": ["ortho.png", "plan.png"], "holes": ["AW510-AW1000"]}]
```

`holes_csv` may be a list of CSVs. `Distance` is read as mm, or as m when
every value is under 20.

Any key in a `pages` entry overrides the computed or document-wide value for
that sheet (`wall_name`, `station`, `offset`, `elevation`, `ends`, `layout`, ...).
`layout` is `"right"` (default right-hand strip), `"bottom"` (full-width bottom
info/title band + slim right legend strip — better for wide, shallow views such
as unrolled wall scans), or `"auto"` (picks whichever gives the larger view
scale; `"right"` also prints a hint when `"bottom"` would be at least 5% larger).
`holes_label` renames the HOLES field in the location block (e.g. `"SCAN"` for a
cut/fill map). `page_order` is `"auto"` (left wall first, then by station), a list of
source page numbers, or `null` to keep the `pages` order.

Values still in `[brackets]` print in red as unfilled placeholders.

### Computed values

For each sheet's hole ranges, against the alignment:

| field | from |
|---|---|
| `wall_name` | side of CL (compass + LEFT/RIGHT) |
| `station` | min/max hole station |
| `offset` | CL offset of the wall points in the CSV |
| `elevation` | mean elevation per range, labelled by `row_labels` (ascending) |
| `ends` | first/last hole of each range by station; a left wall is assumed viewed from the CL, so stations run left-to-right (`"increase": "left"/"right"` to override) |

### Legend symbols

`fill`, `gradient`, `line`, `hole`, `text` (with `sample`), `scalebar`, and `colorbar`: one
stacked bar in TBC cut/fill style.

```jsonc
{"kind": "colorbar", "top": "FILLS", "bottom": "CUTS",
 "bands": [{"color": "#4f8fd6", "text": "0.5 m2"}, ...],   // top to bottom
 "breaks": ["0.200 F", ...]}                                // between bands, len(bands) - 1
```

## Excel tables

`sheetwrap.xlsx.write_xlsx` writes styled report tables (needs `openpyxl`: `pip install sheetwrap[xlsx]`).
Stations are stored as numbers and shown as station text with an Excel number format, so `-5.81` shows
`-0+005.81`, sorts correctly and keeps its sign (a CSV opened in Excel loses it). Station text in the rows
(`"1+005.81"`) is converted.

```python
from sheetwrap.xlsx import Col, write_xlsx
write_xlsx("check.xlsx", {"Points": {
    "title": "Pre-pour check", "subtitle": "local grid",
    "columns": ["Point", Col("Station", "station"), Col("Offset", "0.000"), Col("dZ", "signed"),
                Col("Result", "status")],          # status: PASS/OK green, FAIL/OUT red, CHECK/WARN amber
    "rows": rows,                                   # lists in column order or dicts by column name
    "notes": ["dZ = field - design; + = high."]}})
```

Column kinds: `station` (`dec`, `unit=100` for `901+25.00` highway stationing), `status`, `signed`
(`+0.000`), `volume`/`area` (`#,##0.0`), `int`, `date`, `percent`, `text`, or any Excel format string.
Every sheet gets a frozen, filterable header, widths from the content, notes under the table, and landscape
fit-to-width printing with the header repeated.

## Notes

- Bluebeam writes image wrappers with an unpainted path (`re q`). It is
  invisible on the original page but leaks once the page is nested, so the
  build ends those paths (`re n q`). Only Form XObject operators change.
- The view split uses the page's two largest images; a page with one image is
  placed whole.
- Defender Controlled Folder Access may block Python from writing into
  Documents/OneDrive (event 1123). Point `output` at an unprotected folder.
- Licensed under GNU AGPL-3.0 (matching PyMuPDF). See `LICENSE`.
