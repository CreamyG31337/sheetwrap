import pymupdf

from sheetwrap import wrap


def two_view_pdf():
    """17x11 page with a large 'ortho' image over a smaller 'plan' image,
    overlapping by a few points like the Bluebeam reports."""
    doc = pymupdf.open()
    page = doc.new_page(width=1224, height=792)
    for rect, colour in (((60, 30, 1140, 570), (200, 120, 60)), ((70, 565, 1120, 765), (250, 250, 250))):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 100), False)
        pix.set_rect(pix.irect, colour)
        page.insert_image(pymupdf.Rect(rect), pixmap=pix, keep_proportion=False)
    return doc


def test_compose_images_keeps_pixels(tmp_path):
    paths = []
    for i, size in enumerate(((300, 100), (200, 50))):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, *size), False)
        pix.set_rect(pix.irect, (10 * i, 120, 200))
        p = tmp_path / f"v{i}.png"
        pix.save(p)
        paths.append(p)
    src = wrap.compose_images([paths])
    top, bottom = wrap.split_views(src[0])
    assert top.y1 <= bottom.y0 and abs(top.width - bottom.width) < 0.01
    out = wrap.build(src, [{"source_page": 1}], {"sheet_size": [1224, 792]})
    out = pymupdf.open("pdf", out.tobytes(garbage=3, deflate=True))
    assert out[0].rect.width == 1224
    got = {pymupdf.Pixmap(out, x[0]).samples for x in out[0].get_images(full=True)}
    assert all(pymupdf.Pixmap(str(p)).samples in got for p in paths)


def test_end_dangling_paths():
    s = b"1 0 0 RG 0 w 60 229 1078 530 re q 1078 0 0 530 60 229 cm /Image Do Q"
    assert b"re n q" in wrap.end_dangling_paths(s)
    painted = b"0 0 10 10 re f q Q"
    assert wrap.end_dangling_paths(painted) == painted


def test_split_views_does_not_overlap():
    src = two_view_pdf()
    top, bottom = wrap.split_views(src[0])
    assert top.y1 <= bottom.y0
    assert top.y1 == 570  # overlapping images: split at the upper image's bottom


def test_build_keeps_images_identical():
    src = two_view_pdf()
    before = wrap.image_digests(src)
    cfg = {"views": [{"title": "ORTHOGRAPHIC VIEW"}, {"title": "PLAN VIEW"}], "project": "TEST",
           "legend": [{"kind": "scalebar", "color": "#ff0000", "label": "SCALE"}]}
    out = wrap.build(src, [{"source_page": 1, "ends": {"left": ["A"], "right": ["B"]}}], cfg)
    out = pymupdf.open("pdf", out.tobytes())
    assert out.page_count == 1
    assert before <= wrap.image_digests(out)
    words = out[0].get_text()
    assert "ORTHOGRAPHIC VIEW" in words and "PLAN VIEW" in words and "1 OF 1" in words
