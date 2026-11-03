"""Command line: sheetwrap build | stations | datum"""
import argparse
import csv
import sys
from pathlib import Path

import pymupdf

from . import config, holes as holes_mod, tbc, wrap
from .alignment import Alignment, format_station


def resolve_sheets(cfg, n_source_pages):
    """Per-sheet values: config "pages" entries, auto-filled from the
    alignment and hole data when the job provides them."""
    pages = cfg.get("pages") or [{"source_page": i + 1} for i in range(n_source_pages)]
    pages = [dict(p, source_page=p.get("source_page", i + 1)) for i, p in enumerate(pages)]
    rxl = config.path_of(cfg, "alignment")
    csvs = cfg.get("holes_csv") or []
    csvs = [config.resolve(cfg, c) for c in ([csvs] if isinstance(csvs, str) else csvs)]
    if rxl and csvs:
        al = Alignment.from_rxl(rxl)
        if al.closure_error > 0.005:
            print(f"warning: alignment integration misses element ends by {al.closure_error * 1000:.1f} mm")
        hs = holes_mod.locate([h for c in csvs for h in holes_mod.read_check_csv(c)], al)
        for p in pages:
            if p.get("holes"):
                auto = holes_mod.sheet_values(hs, p["holes"], al, cfg.get("row_labels", ()),
                                              cfg.get("station_decimals", 2), p.get("increase", "auto"))
                p.update({k: v for k, v in auto.items() if k not in p or k == "holes"})
    order = cfg.get("page_order", "auto")
    if order == "auto":
        if all("_sort" in p for p in pages):
            pages.sort(key=lambda p: p["_sort"])
    elif order:
        pages = [pages[[p["source_page"] for p in pages].index(n)] for n in order]
    return pages


def cmd_build(args):
    cfg = config.load(args.job)
    if not cfg.get("datum") and config.path_of(cfg, "datum_from_tbc_report"):
        cfg["datum"] = tbc.datum_from_report(config.path_of(cfg, "datum_from_tbc_report"))
    if cfg.get("input"):
        src = pymupdf.open(config.path_of(cfg, "input"))
    else:  # build the source from per-page image files
        pages = cfg.get("pages") or []
        if not pages or not all(p.get("images") for p in pages):
            print("error: job needs \"input\" or \"images\" on every page", file=sys.stderr)
            return 2
        src = wrap.compose_images([[config.resolve(cfg, im) for im in p["images"]] for p in pages])
        cfg.setdefault("sheet_size", [1224, 792])
    logo = None
    logo_path = config.path_of(cfg, "logo")
    if logo_path and logo_path.is_file():
        logo = wrap.open_logo(logo_path)
    elif cfg.get("logo"):
        print(f"note: logo not found ({cfg['logo']}); using company text row")
    sheets = resolve_sheets(cfg, src.page_count)
    # PDF input: image bytes are copied, so compare raw streams. Image-file
    # input: streams are recompressed on save, so compare decoded pixels.
    digests = wrap.image_digests if cfg.get("input") else wrap.pixel_digests
    before = digests(src)
    out = wrap.build(src, sheets, cfg, logo)
    out_path = config.path_of(cfg, "output")
    out.save(out_path, garbage=3, deflate=True)
    after = digests(pymupdf.open(out_path))
    print(f"wrote {out_path}")
    print(f"source images: {len(before)}  identical {'bytes' if cfg.get('input') else 'pixels'} "
          f"in output: {len(before & after)}")
    for i, p in enumerate(sheets, 1):
        print(f"  sheet {i}: source page {p['source_page']}  {p.get('wall_name', '')}  {p.get('station', '')}")
    return 0 if before <= after else 1


def cmd_stations(args):
    al = Alignment.from_rxl(args.rxl)
    print(f"alignment: {al.name}  (closure {al.closure_error * 1000:.2f} mm)", file=sys.stderr)
    hs = holes_mod.locate(holes_mod.read_check_csv(args.csv), al)
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["Point ID", "Station", "Offset", "Elevation", "Wall offset", "Hole to wall (mm)"])
    for h in hs:
        w.writerow([h.id, format_station(h.sta, 3), f"{h.off:.3f}", f"{h.z:.3f}", f"{h.wall_off:.3f}",
                    f"{h.dist:.0f}"])
    return 0


def cmd_datum(args):
    print(tbc.datum_from_report(args.report))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sheetwrap", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="wrap a report PDF in title block sheets")
    b.add_argument("job", type=Path, help="job JSON")
    b.set_defaults(func=cmd_build)
    s = sub.add_parser("stations", help="station/offset of each hole in a TBC check CSV")
    s.add_argument("rxl", type=Path)
    s.add_argument("csv", type=Path)
    s.set_defaults(func=cmd_stations)
    d = sub.add_parser("datum", help="datum line from a TBC Project Computation Report (.html)")
    d.add_argument("report", type=Path)
    d.set_defaults(func=cmd_datum)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
