"""Wrap each page of an existing PDF in a title block sheet.

The original page is placed as a Form XObject (show_pdf_page), so embedded
images are copied unchanged - no resampling or recompression.

Each source page is split into its top and bottom view (by its two largest
images), placed at one common scale and horizontal alignment with a title
above each.
"""
import hashlib
import re

import pymupdf

from . import sheet
from .sheet import BLACK, GREY, field, text

PT = 72  # points per inch
MARGIN = 0.25 * PT
STRIP_W = 3.25 * PT  # right-hand title block strip
LEGEND_W = 2.15 * PT  # slim right-hand legend strip for bottom layout
BOTTOM_H = 124        # bottom info/title band height for bottom layout
GAP = 0.1 * PT
VIEW_TITLE_H = 24
END_REF_H = 20


def end_dangling_paths(stream):
    """Bluebeam writes image wrappers as '... re q ... Do Q' - a path that is
    never painted or ended. Harmless on its own page, but once nested in a new
    page the open path leaks and gets stroked by the next drawing op. Add the
    missing 'n' (end path, no paint)."""
    return re.sub(rb"\bre(\s+)q\b", rb"re n\1q", stream)


def fix_dangling_paths(doc):
    """Apply end_dangling_paths to every Form XObject. Image streams are not
    touched."""
    for xref in range(1, doc.xref_length()):
        if doc.xref_get_key(xref, "Subtype")[1] != "/Form":
            continue
        s = doc.xref_stream(xref)
        fixed = end_dangling_paths(s)
        if fixed != s:
            doc.update_stream(xref, fixed)


def split_views(sp):
    """Source clip rects for the page's views, top to bottom, split between
    the two largest images. One view if the page has fewer images."""
    boxes = [pymupdf.Rect(b[1]) & sp.rect for b in sp.get_bboxlog()]
    boxes = [b for b in boxes if not b.is_empty]
    imgs = sorted((pymupdf.Rect(i["bbox"]) for i in sp.get_image_info()),
                  key=lambda r: -r.get_area())[:2]
    if len(imgs) < 2:
        whole = pymupdf.Rect()
        for b in boxes:
            whole |= b
        return [whole if not whole.is_empty else sp.rect]
    upper, lower = sorted(imgs, key=lambda r: r.y0)
    # if the images overlap, the upper one is drawn over the lower one -
    # split at its bottom edge so neither view shows a sliver of the other
    split = upper.y1 if upper.y1 > lower.y0 else (upper.y1 + lower.y0) / 2
    top, bottom = pymupdf.Rect(), pymupdf.Rect()
    for b in boxes:
        if (b.y0 + b.y1) / 2 < split:
            top |= b
        else:
            bottom |= b
    top.y1 = min(top.y1, split)
    bottom.y0 = max(bottom.y0, split)
    return [top, bottom]


def place_views(page, src, pno, area, clips, views, ends=None):
    """Stack the clipped views in `area` at one common scale, keeping their
    original horizontal alignment, with a title above each. `ends` holds
    optional reference lines drawn under the last view at its left/right ends."""
    ux0 = min(c.x0 for c in clips)
    ux1 = max(c.x1 for c in clips)
    titles_h = VIEW_TITLE_H * len(clips) + (END_REF_H if ends else 0)
    gaps_h = GAP * 2 * (len(clips) - 1)
    s = min(area.width / (ux1 - ux0),
            (area.height - titles_h - gaps_h) / sum(c.height for c in clips))
    used_h = s * sum(c.height for c in clips) + titles_h + gaps_h
    ax = area.x0 + (area.width - s * (ux1 - ux0)) / 2
    y = area.y0 + (area.height - used_h) / 2
    for i, clip in enumerate(clips):
        v = views[i] if i < len(views) else {}
        if v.get("title"):
            page.insert_text((ax, y + 11), v["title"], fontsize=10, fontname="hebo", color=BLACK)
            tw = pymupdf.get_text_length(v["title"], fontname="hebo", fontsize=10)
            page.draw_line((ax, y + 13), (ax + tw, y + 13), color=BLACK, width=0.8)
            if v.get("subtitle"):
                page.insert_text((ax, y + 21), v["subtitle"], fontsize=6.5, fontname="helv", color=GREY)
        y += VIEW_TITLE_H
        r = pymupdf.Rect(ax + s * (clip.x0 - ux0), y, ax + s * (clip.x1 - ux0), y + s * clip.height)
        page.show_pdf_page(r, src, pno, clip=clip, keep_proportion=False)
        y = r.y1 + GAP * 2
    if ends:
        right = ax + s * (ux1 - ux0)
        for side, align in (("left", 0), ("right", 2)):
            if ends.get(side):
                text(page, pymupdf.Rect(ax, y, right, y + END_REF_H), "\n".join(ends[side]),
                     size=6.5, align=align)


def _draw_rows(page, x0, w, rows):
    for ry, rh, cells in rows:
        cx = x0
        for label, value, frac in cells:
            cw = w * frac
            field(page, pymupdf.Rect(cx, ry, cx + cw, ry + rh), label, value,
                  size=9 if label in ("TITLE", "DRAWING No.") else 8)
            cx += cw


def _draw_location(page, rect, pc):
    """Draw the 4-row scan/location metadata block inside `rect`."""
    x0, x1, w = rect.x0, rect.x1, rect.width
    rh = rect.height / 4
    page.draw_rect(rect, color=BLACK, width=1.2)
    rows = [
        (rect.y0, rh, [("WALL", pc.get("wall_name", "[WALL]"), 0.45),
                       (pc.get("holes_label", "HOLES"), pc.get("holes", "[HOLES]"), 0.55)]),
        (rect.y0 + rh, rh, [("STATION", pc.get("station", "[STATION]"), 0.5),
                            ("WALL FACE OFFSET FROM CL", pc.get("offset", "[OFFSET]"), 0.5)]),
        (rect.y0 + 2 * rh, rh, [("ELEVATION", pc.get("elevation", "[ELEVATION]"), 1.0)]),
        (rect.y0 + 3 * rh, rh, [("DATUM", pc.get("datum", "[DATUM]"), 1.0)]),
    ]
    _draw_rows(page, x0, w, rows)


def draw_strip(page, strip, pc, logo, sheet_no, n_sheets):
    x0, x1 = strip.x0, strip.x1
    w = strip.width

    # title block at the bottom, with an optional logo row on top
    logo_h = 44 if logo else 0
    tb = pymupdf.Rect(x0, strip.y1 - 128 - logo_h, x1, strip.y1)
    if logo:
        cell = pymupdf.Rect(x0, tb.y0, x1, tb.y0 + logo_h)
        page.draw_rect(cell, color=BLACK, width=0.5)
        page.show_pdf_page(cell + (8, 6, -8, -6), logo, 0)
    ty = tb.y0 + logo_h
    rows = [
        (ty, 22, [("PROJECT", pc.get("project", "[PROJECT]"), 1.0)]),
        (ty + 22, 34, [("TITLE", pc.get("title", "[TITLE]"), 1.0)]),
        (ty + 56, 22, [("DRAWN", pc.get("drawn_by", "[INITIALS]"), 0.25),
                       ("CHECKED", pc.get("checked_by", "[INITIALS]"), 0.25),
                       ("SCALE", pc.get("scale", "AS SHOWN"), 0.5)]),
        (ty + 78, 26, [("DRAWING No.", pc.get("drawing_no", "[No.]"), 0.5),
                       ("REV", pc.get("revision", "0"), 0.2),
                       ("SHEET", f"{sheet_no} OF {n_sheets}", 0.3)]),
        (ty + 104, 24, [("DATE", pc.get("date", "[YYYY-MM-DD]"), 1.0)]),
    ]
    if not logo:
        tb.y0 -= 22
        rows.insert(0, (tb.y0, 22, [("COMPANY", pc.get("company", "[COMPANY]"), 1.0)]))
    page.draw_rect(tb, color=BLACK, width=1.2)
    _draw_rows(page, x0, w, rows)

    # location block
    loc = pymupdf.Rect(x0, tb.y0 - GAP - 4 * 22, x1, tb.y0 - GAP)
    _draw_location(page, loc, pc)

    # legend / sign convention / notes fill the remaining space top-down
    entries = pc.get("legend", [])
    r = pymupdf.Rect(x0, strip.y0, x1, strip.y0 + sheet.legend_height(entries))
    sheet.legend(page, sheet.section(page, r, "LEGEND"), entries)
    sc = pc.get("sign_convention", [])
    if sc:
        r = pymupdf.Rect(x0, r.y1 + GAP, x1, r.y1 + GAP + sheet.bullets_height(sc, w))
        sheet.bullets(page, sheet.section(page, r, "SIGN CONVENTION"), sc)
    notes = pc.get("job_notes", []) + pc.get("notes", [])
    if notes:
        r = pymupdf.Rect(x0, r.y1 + GAP, x1, loc.y0 - GAP)
        sheet.bullets(page, sheet.section(page, r, "NOTES"),
                      [f"{i}. {s}" for i, s in enumerate(notes, 1)])


def draw_bottom_band(page, legend_strip, bottom, pc, logo, sheet_no, n_sheets):
    """Alternate layout: slim right legend strip + full-width bottom info/title band."""
    entries = pc.get("legend", [])
    lr = pymupdf.Rect(legend_strip.x0, legend_strip.y0, legend_strip.x1,
                      min(legend_strip.y1, legend_strip.y0 + sheet.legend_height(entries)))
    sheet.legend(page, sheet.section(page, lr, "LEGEND"), entries)

    # Bottom band: [NOTES + SIGN CONVENTION] | [LOCATION] | [LOGO + TITLE BLOCK]
    tb_w = 360
    loc_w = 260
    tb = pymupdf.Rect(bottom.x1 - tb_w, bottom.y0, bottom.x1, bottom.y1)
    loc = pymupdf.Rect(tb.x0 - GAP - loc_w, bottom.y0, tb.x0 - GAP, bottom.y1)
    info = pymupdf.Rect(bottom.x0, bottom.y0, loc.x0 - GAP, bottom.y1)

    # Title block (4 rows inside BOTTOM_H = 124: 34 + 36 + 26 + 28)
    y0 = tb.y0
    logo_w = 144
    if logo:
        cell = pymupdf.Rect(tb.x0, y0, tb.x0 + logo_w, y0 + 34)
        page.draw_rect(cell, color=BLACK, width=0.5)
        page.show_pdf_page(cell + (5, 4, -5, -4), logo, 0)
        field(page, pymupdf.Rect(tb.x0 + logo_w, y0, tb.x1, y0 + 34),
              "PROJECT", pc.get("project", "[PROJECT]"), size=8)
    else:
        _draw_rows(page, tb.x0, tb_w, [(y0, 34, [
            ("COMPANY", pc.get("company", "[COMPANY]"), 0.4),
            ("PROJECT", pc.get("project", "[PROJECT]"), 0.6),
        ])])
    _draw_rows(page, tb.x0, tb_w, [
        (y0 + 34, 36, [("TITLE", pc.get("title", "[TITLE]"), 1.0)]),
        (y0 + 70, 26, [("DRAWN", pc.get("drawn_by", "[INITIALS]"), 0.25),
                       ("CHECKED", pc.get("checked_by", "[INITIALS]"), 0.25),
                       ("SCALE", pc.get("scale", "AS SHOWN"), 0.5)]),
        (y0 + 96, 28, [("DRAWING No.", pc.get("drawing_no", "[No.]"), 0.38),
                       ("REV", pc.get("revision", "0"), 0.14),
                       ("SHEET", f"{sheet_no} OF {n_sheets}", 0.22),
                       ("DATE", pc.get("date", "[YYYY-MM-DD]"), 0.26)]),
    ])
    page.draw_rect(tb, color=BLACK, width=1.2)

    _draw_location(page, loc, pc)

    sc = pc.get("sign_convention", [])
    notes = pc.get("job_notes", []) + pc.get("notes", [])
    if sc and notes:
        sc_w = min(225, info.width * 0.42)
        sc_r = pymupdf.Rect(info.x0, info.y0, info.x0 + sc_w, info.y1)
        nt_r = pymupdf.Rect(sc_r.x1 + GAP, info.y0, info.x1, info.y1)
        sheet.bullets(page, sheet.section(page, sc_r, "SIGN CONVENTION"), sc, size=6.0, line_h=8.0)
        sheet.bullets(page, sheet.section(page, nt_r, "NOTES"),
                      [f"{i}. {s}" for i, s in enumerate(notes, 1)], size=6.0, line_h=8.0)
    elif sc:
        sheet.bullets(page, sheet.section(page, info, "SIGN CONVENTION"), sc, size=6.0, line_h=8.0)
    elif notes:
        sheet.bullets(page, sheet.section(page, info, "NOTES"),
                      [f"{i}. {s}" for i, s in enumerate(notes, 1)], size=6.0, line_h=8.0)


def open_logo(path):
    """Logo as a vector PDF page: SVG/PDF/AI opened as a document."""
    logo = pymupdf.open(path)
    return logo if logo.is_pdf else pymupdf.open("pdf", logo.convert_to_pdf())


def compose_images(pages, width=1000, gap=20):
    """Source document built from image files: one page per entry in `pages`
    (each a list of image paths, top to bottom), the images stacked at a common
    width. Images are embedded losslessly (PNG pixels are kept as-is; JPEG is
    copied unchanged), so split_views/place_views treat them like a report."""
    doc = pymupdf.open()
    for paths in pages:
        sizes = []
        for p in paths:
            pix = pymupdf.Pixmap(str(p))
            sizes.append(width * pix.height / pix.width)
        page = doc.new_page(width=width, height=sum(sizes) + gap * (len(sizes) - 1))
        y = 0
        for p, h in zip(paths, sizes):
            page.insert_image(pymupdf.Rect(0, y, width, y + h), filename=str(p))
            y += h + gap
    return doc


def build(src, sheets, cfg, logo=None):
    """Return a new document with one title-blocked sheet per entry in
    `sheets`; each is a dict of per-sheet values with "source_page" (1-based)
    that overrides the document-wide `cfg`. Sheets are the source page size
    unless cfg has "sheet_size" [width, height] in points."""
    fix_dangling_paths(src)
    out = pymupdf.open()
    for i, sh in enumerate(sheets):
        pno = sh["source_page"] - 1
        pc = {**cfg, **sh}
        sp = src[pno]
        W, H = pc.get("sheet_size") or (sp.rect.width, sp.rect.height)
        page = out.new_page(width=W, height=H)
        border = pymupdf.Rect(MARGIN, MARGIN, W - MARGIN, H - MARGIN)
        page.draw_rect(border, color=BLACK, width=1.5)
        if pc.get("layout") == "bottom":
            bottom = pymupdf.Rect(border.x0, border.y1 - BOTTOM_H, border.x1, border.y1)
            legend_strip = pymupdf.Rect(border.x1 - LEGEND_W, border.y0, border.x1, bottom.y0 - GAP)
            area = pymupdf.Rect(border.x0 + GAP, border.y0 + GAP, legend_strip.x0 - GAP, bottom.y0 - GAP)
            place_views(page, src, pno, area, split_views(sp), pc.get("views", []), pc.get("ends"))
            draw_bottom_band(page, legend_strip, bottom, pc, logo, i + 1, len(sheets))
        else:
            strip = pymupdf.Rect(border.x1 - STRIP_W, border.y0, border.x1, border.y1)
            area = pymupdf.Rect(border.x0 + GAP, border.y0 + GAP, strip.x0 - GAP, border.y1 - GAP)
            place_views(page, src, pno, area, split_views(sp), pc.get("views", []), pc.get("ends"))
            draw_strip(page, strip, pc, logo, i + 1, len(sheets))
    return out


def image_digests(doc):
    """Raw image stream digests - equal only if the bytes were copied."""
    return {hashlib.sha1(doc.xref_stream_raw(x[0])).hexdigest()
            for p in doc for x in p.get_images(full=True)}


def pixel_digests(doc):
    """Decoded pixel digests - for images embedded from PNG files, whose
    streams are recompressed on save but whose pixels must not change."""
    out = set()
    for p in doc:
        for x in p.get_images(full=True):
            pix = pymupdf.Pixmap(doc, x[0])
            out.add((pix.width, pix.height, hashlib.sha1(pix.samples).hexdigest()))
    return out
