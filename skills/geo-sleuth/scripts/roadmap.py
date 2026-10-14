#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Tianditu vector road base (no shadow) with candidate points / a view sector drawn on it.

Why: satellite imagery hides streets — strong building shadow, or pavement indistinguishable
from a plaza / roof deck (two real runs went tens of metres wrong this way). The vector base
draws roads *as roads* and the label layer prints road names, so "is this point on the street /
which side of the road is this block on" becomes readable at a glance. `revgeo.py` answers the
same question with the official address database; use both, then let the satellite image display.

Layers: `vec_w` (roads / water / green) under `cva_w` (labels: road names, POIs) — the label
layer is what makes e.g. "南京东路" visible on the map.

Key: --tk or GEO_TIANDITU_KEY (server-type key, same as `tiles.py --source tianditu`).
Tianditu is CGCS2000 (≈WGS84 at this scale), so no coordinate conversion is involved.

Examples:
  roadmap.py --center 31.2372,121.4704 --zoom 18 --tiles 2 --out road.jpg
  roadmap.py --center 31.2372,121.4704 --tiles 2 --points cands.json --out road.jpg
  roadmap.py --center 31.2372,121.4704 --tiles 2 --points cands.json \
             --sector 31.23680,121.47025,90,50,120 --out road.jpg
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from _net import fetch_bytes  # noqa: E402

TILE = 256


def tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def tile_center_ll(tx: float, ty: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    lon = (tx + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2.0 * (ty + 0.5) / n))))
    return lat, lon


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("C:/Windows/Fonts/msyh.ttc",
                      "/System/Library/Fonts/PingFang.ttc",
                      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:  # noqa: BLE001
                pass
    return ImageFont.load_default()


def tile_url(tk: str, layer: str, z: int, x: int, y: int) -> str:
    return (f"https://t0.tianditu.gov.cn/{layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile"
            f"&VERSION=1.0.0&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
            f"&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={tk}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--center", required=True, help="lat,lon")
    ap.add_argument("--zoom", type=int, default=18)
    ap.add_argument("--tiles", type=int, default=2, help="tile radius N; the image is (2N+1)^2 tiles")
    ap.add_argument("--points", type=Path, help="JSON {name: [lat, lon]} — drawn as rings")
    ap.add_argument("--sector", help="lat,lon,heading_deg,spread_deg,radius_m — draw a view sector")
    ap.add_argument("--tk", default=os.environ.get("GEO_TIANDITU_KEY", ""),
                    help="Tianditu server key (default: $GEO_TIANDITU_KEY)")
    ap.add_argument("--proxy", help="proxy URL or 'direct'")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if not args.tk:
        print("no key: pass --tk or set GEO_TIANDITU_KEY", file=sys.stderr)
        return 2

    clat, clon = (float(v) for v in args.center.split(","))
    z, n = args.zoom, args.tiles
    cx, cy = tile_xy(clat, clon, z)
    tx0, ty0 = int(cx) - n, int(cy) - n
    span = 2 * n + 1
    size = span * TILE
    m_per_px = 156543.03392 * math.cos(math.radians(clat)) / (2 ** z)

    base = Image.new("RGB", (size, size), (238, 238, 238))
    missing = 0
    for layer in ("vec", "cva"):
        for i in range(span):
            for j in range(span):
                x, y = tx0 + i, ty0 + j
                try:
                    raw = fetch_bytes(tile_url(args.tk, layer, z, x, y), proxy=args.proxy, timeout=20)
                    tim = Image.open(io.BytesIO(raw)).convert("RGBA")
                    if layer == "cva":
                        base.paste(tim, (i * TILE, j * TILE), tim)
                    else:
                        base.paste(tim.convert("RGB"), (i * TILE, j * TILE))
                except Exception:  # noqa: BLE001
                    missing += 1

    def ll_to_px(lat: float, lon: float) -> tuple[float, float]:
        gx, gy = tile_xy(lat, lon, z)
        return (gx - tx0) * TILE, (gy - ty0) * TILE

    d = ImageDraw.Draw(base, "RGBA")
    font = load_font(20)

    if args.sector:
        slat, slon, heading, spread, radius_m = (float(v) for v in args.sector.split(","))
        px, py = ll_to_px(slat, slon)
        r_px = radius_m / m_per_px
        azimuths = [heading - spread / 2.0 + spread * k / 24.0 for k in range(25)]
        poly = [(px, py)] + [(px + r_px * math.sin(math.radians(a)),
                              py - r_px * math.cos(math.radians(a))) for a in azimuths]
        d.polygon(poly, fill=(255, 210, 0, 70), outline=(230, 140, 0, 235))
        d.line([(px, py), poly[1]], fill=(230, 140, 0, 235), width=3)
        d.line([(px, py), poly[-1]], fill=(230, 140, 0, 235), width=3)

    if args.points:
        palette = [(230, 0, 0), (0, 90, 220), (0, 150, 0), (150, 0, 200), (255, 130, 0), (0, 160, 160)]
        for i, (name, ll) in enumerate(json.loads(args.points.read_text(encoding="utf-8")).items()):
            lat, lon = float(ll[0]), float(ll[1])
            x, y = ll_to_px(lat, lon)
            col = palette[i % len(palette)]
            d.ellipse([x - 8, y - 8, x + 8, y + 8], outline=col, width=3)
            d.text((x + 11, y - 12), str(name), font=font, fill=col)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    base.save(args.out, quality=92)
    center_ll = tile_center_ll(tx0 + n, ty0 + n, z)
    meta = {"zoom": z, "origin_tile": [tx0, ty0], "center": [center_ll[0], center_ll[1]],
            "source": "tianditu-vec", "crs": "wgs", "size": [size, size],
            "m_per_px": m_per_px, "failed_tiles": missing}
    args.out.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    print(f"{args.out}  {size}x{size}  (missing {missing} tile(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
