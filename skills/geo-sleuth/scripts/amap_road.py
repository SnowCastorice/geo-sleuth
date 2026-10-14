#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""AMap 2D road-map base (with POI labels) for camera points / a view sector.

Why: a satellite mosaic hides what a *map* states outright. On the AMap road base you can read
label text that pins a spot far more precisely than pixels do — in the Xi'an city-wall run the
labels "22号敌楼" (watchtower no. 22), "永宁门城楼 / 永宁门瓮城 / 月城咖啡屋 / 城墙故事文创店 / 吊桥"
and the hotel name all landed exactly on the points that had been deduced from the photo, which
turned a soft reading into a checkable one. Use it with the Tianditu vector base (`roadmap.py`),
the official address (`revgeo.py`) and the satellite mosaic (`tiles.py`): draw the conclusion on
the map base *and* the imagery, never only on the imagery.

Tiles: https://webrd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x=&y=&z=
(style=8 = road map with labels; style=7 = road map without labels). AMap tiles are cut on GCJ-02,
so the mosaic sidecar records crs="gcj" — `tiles.py mark` then converts WGS84 points internally,
the same way `tiles.py --source amap` does for imagery.

Note: `--sector lat,lon,heading,horizontalFOV,radius_m` — the 4th number is the **full** horizontal
field of view (spread), i.e. the sector spans heading ± fov/2, not ± fov. Getting this wrong once
put a landmark the photo clearly shows just outside the drawn cone.

Examples:
  amap_road.py --center 34.2531,108.9420 --zoom 18 --tiles 2 --out road.jpg
  amap_road.py --center 34.2531,108.9420 --zoom 18 --tiles 2 --points pts.json \
               --sector 34.25310,108.94200,276,70,900 --label --out road_marked.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import geo  # noqa: E402
import tiles  # noqa: E402
from _net import fetch_bytes  # noqa: E402

URL = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style={style}&x={x}&y={y}&z={z}"


def _tile(z: int, x: int, y: int, style: int) -> Image.Image | None:
    for s in ("1", "2", "3", "4"):
        try:
            data = fetch_bytes(URL.format(s=s, style=style, x=x, y=y, z=z),
                               headers={"Referer": "https://www.amap.com/"})
            if len(data) > 500:
                return Image.open(BytesIO(data)).convert("RGB")
        except Exception:
            continue
    return None


def fetch_road(center: str, zoom: int, radius: int, style: int, out: Path) -> None:
    lat, lon = (float(v) for v in center.split(","))
    glat, glon = geo.wgs2gcj(lat, lon)
    cx, cy = geo.ll2px(zoom, glat, glon)
    ox, oy = int(cx // 256) - radius, int(cy // 256) - radius
    n = 2 * radius + 1
    sheet = Image.new("RGB", (n * 256, n * 256), (240, 240, 240))
    jobs = [(ox + i, oy + j) for i in range(n) for j in range(n)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        imgs = list(ex.map(lambda p: _tile(zoom, p[0], p[1], style), jobs))
    missing = 0
    for (tx, ty), im in zip(jobs, imgs):
        if im is None:
            missing += 1
            continue
        sheet.paste(im, ((tx - ox) * 256, (ty - oy) * 256))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)
    meta = {"zoom": zoom, "origin_tile": [ox, oy], "center": [lat, lon], "source": "amap-road",
            "style": style, "crs": "gcj", "size": list(sheet.size),
            "m_per_px": geo.meters_per_px(zoom, lat)}
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"{out}  {sheet.size[0]}x{sheet.size[1]}  (missing {missing} tile(s))")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--center", required=True, help="lat,lon (WGS84)")
    ap.add_argument("--zoom", type=int, default=18)
    ap.add_argument("--tiles", type=int, default=2, help="tile radius N → (2N+1)² tiles")
    ap.add_argument("--style", type=int, default=8, help="8 = road map with labels, 7 = without")
    ap.add_argument("--points", help="JSON {name: [lat, lon]} drawn as rings")
    ap.add_argument("--sector", action="append",
                    help="lat,lon,heading,horizontalFOV,radius_m — FOV is the full spread (heading ± fov/2)")
    ap.add_argument("--label", action="store_true", help="write each point's name next to it")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    out = Path(a.out)
    base = out if not (a.points or a.sector) else out.with_name(out.stem + "_base.jpg")
    fetch_road(a.center, a.zoom, a.tiles, a.style, base)
    if a.points or a.sector:
        pts = json.loads(Path(a.points).read_text(encoding="utf-8")) if a.points else {}
        tiles.mark(base, pts, out, a.label, None, a.sector)
        print(f"{out}  (base {base})")


if __name__ == "__main__":
    main()
