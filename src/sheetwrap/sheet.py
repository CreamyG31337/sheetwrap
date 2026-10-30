"""Drawing primitives for the title block strip: fields, legend, notes."""
import pymupdf

BLACK = (0, 0, 0)
GREY = (0.45, 0.45, 0.45)
RED = (0.85, 0.1, 0.1)
LEGEND_ROW_H = 24


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def colour_for(value):
    """Values still in [brackets] are unfilled placeholders - show in red."""
    return RED if str(value).startswith("[") else BLACK


def text(page, rect, s, size=7, bold=False, align=0, colour=None):
    """Text box that shrinks to fit rather than silently dropping text."""
    font = "hebo" if bold else "helv"
    colour = colour or colour_for(s)
    while size > 4 and page.insert_textbox(rect, s, fontsize=size, fontname=font,
                                           color=colour, align=align) < 0:
        size -= 0.5
    if size <= 4:
        page.insert_textbox(rect, s, fontsize=4, fontname=font, color=colour, align=align)


def text_height(s, width, size, line_h):
    """Estimated wrapped height of `s` in a box `width` wide."""
    lines = 0
    for para in s.split("\n"):
        w = pymupdf.get_text_length(para, fontname="helv", fontsize=size)
        lines += max(1, int(w / (width * 0.95)) + 1)
    return lines * line_h


def section(page, rect, heading):
    """Box with a heading bar; returns the inner rect below the heading."""
    page.draw_rect(rect, color=BLACK, width=0.75)
    bar = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + 12)
    page.draw_rect(bar, color=BLACK, fill=(0.88, 0.88, 0.88), width=0.75)
    text(page, bar + (3, 1.5, -3, 0), heading, size=7, bold=True, colour=BLACK)
    return pymupdf.Rect(rect.x0 + 4, bar.y1 + 3, rect.x1 - 4, rect.y1 - 3)


def field(page, rect, label, value, size=8):
    page.draw_rect(rect, color=BLACK, width=0.5)
    text(page, pymupdf.Rect(rect.x0 + 2, rect.y0 + 1, rect.x1 - 2, rect.y0 + 9),
         label, size=5, colour=GREY)
    text(page, pymupdf.Rect(rect.x0 + 2, rect.y0 + 8, rect.x1 - 2, rect.y1 - 1),
         value, size=size, bold=True)


def legend_symbol(page, sym, e):
    kind = e.get("kind")
    c = hex_rgb(e["color"]) if "color" in e else BLACK
    mid = (sym.y0 + sym.y1) / 2
    if kind == "fill":
        page.draw_rect(sym, color=BLACK, fill=c, width=0.4)
    elif kind == "gradient":
        cols = [hex_rgb(h) for h in e["colors"]]
        steps = int(sym.width)
        for i in range(steps):
            t = i / (steps - 1) * (len(cols) - 1)
            a, b = cols[int(t)], cols[min(int(t) + 1, len(cols) - 1)]
            f = t - int(t)
            rgb = tuple(a[k] + (b[k] - a[k]) * f for k in range(3))
            page.draw_rect(pymupdf.Rect(sym.x0 + i, sym.y0, sym.x0 + i + 1.2, sym.y1),
                           color=None, fill=rgb, width=0)
        page.draw_rect(sym, color=BLACK, width=0.4)
    elif kind == "line":
        page.draw_line((sym.x0, mid), (sym.x1, mid), color=c, width=e.get("width", 2))
    elif kind == "hole":
        # open circle with a short offset line, as drawn in the views
        page.draw_circle((sym.x0 + 8, mid), 2, color=c, width=0.6)
        page.draw_line((sym.x0 + 10, mid), (sym.x1 - 4, mid),
                       color=hex_rgb(e.get("line_color", "#d9363e")), width=0.8)
    elif kind == "scalebar":
        # grey bar with left tick, red north line from the left end, length label
        base = sym.y1 - 1
        page.draw_line((sym.x0 + 2, base), (sym.x1, base), color=GREY, width=0.6)
        page.draw_line((sym.x0 + 2, base), (sym.x0 + 2, base - 3), color=GREY, width=0.6)
        page.draw_line((sym.x0 + 2, base), (sym.x0 + 14, base - 4.5), color=c, width=1.2)
        page.insert_text((sym.x0 + 3, base - 6), e.get("sample", "1 m"), fontsize=5, fontname="helv",
                         color=BLACK)
    elif kind == "text":
        text(page, sym, e.get("sample", ""), size=6, colour=c, align=1)


def legend(page, inner, entries):
    y = inner.y0
    for e in entries:
        legend_symbol(page, pymupdf.Rect(inner.x0, y + 1, inner.x0 + 34, y + 15), e)
        text(page, pymupdf.Rect(inner.x0 + 39, y + 1, inner.x1, y + LEGEND_ROW_H), e["label"], size=6)
        y += LEGEND_ROW_H


def legend_height(entries):
    return 18 + LEGEND_ROW_H * len(entries)


def bullets(page, inner, lines, size=6.5, line_h=9):
    y = inner.y0
    for s in lines:
        h = text_height(s, inner.width, size, line_h)
        text(page, pymupdf.Rect(inner.x0, y, inner.x1, y + h + 2), s, size=size)
        y += h + 2


def bullets_height(lines, width, size=6.5, line_h=9):
    return 20 + sum(text_height(s, width - 8, size, line_h) + 2 for s in lines)
