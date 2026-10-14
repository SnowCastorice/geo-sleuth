#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Point coordinates -> official address (Tianditu reverse geocoding; server key required).

Why: when a candidate camera position (or any point) has to be decided as "on the street" or
"inside which building", the official address database answers it directly, while satellite
imagery can be ambiguous — a street buried in building shadow, or pavement that looks exactly
like a plaza or a roof deck. A point that reverse-geocodes to a shop or an entrance
("... 7号门" = gate 7) sits inside that building, not on the road.

Coordinates: Tianditu is CGCS2000, which aligns with WGS84 at this scale — pass WGS84 as-is
(NOT the GCJ-02 used by Amap / Tencent).

Key: --tk, or the GEO_TIANDITU_KEY environment variable (server-type key; an empty IP
allow-list is fine). Same key as `tiles.py --source tianditu`.

Examples:
  revgeo.py 31.23680,121.47025
  revgeo.py 31.23680,121.47025 --out rev.json
  revgeo.py --points candidates.json --out rev.json    # {name: [lat, lon]} in; addresses appended
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _net import fetch_bytes  # noqa: E402


def lookup(lat: float, lon: float, tk: str, proxy: str | None = None) -> dict:
    body = json.dumps({"lon": lon, "lat": lat, "ver": 1})
    query = urllib.parse.urlencode({"postStr": body, "type": "geocode", "tk": tk})
    url = "http://api.tianditu.gov.cn/geocoder?" + query
    raw = fetch_bytes(url, proxy=proxy, timeout=20)
    data = json.loads(raw.decode("utf-8", "replace"))
    return data.get("result") or {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="*", help="lat,lon pairs")
    ap.add_argument("--points", type=Path, help="JSON {name: [lat, lon]} (poi.py / tiles.py style)")
    ap.add_argument("--tk", default=os.environ.get("GEO_TIANDITU_KEY", ""),
                    help="Tianditu server key (default: $GEO_TIANDITU_KEY)")
    ap.add_argument("--proxy", help="proxy URL or 'direct'")
    ap.add_argument("--out", type=Path, help="write the results as JSON")
    args = ap.parse_args()
    if not args.tk:
        print("no key: pass --tk or set GEO_TIANDITU_KEY", file=sys.stderr)
        return 2

    items: list[tuple[str, float, float]] = []
    if args.points:
        for name, ll in json.loads(args.points.read_text(encoding="utf-8")).items():
            items.append((str(name), float(ll[0]), float(ll[1])))
    for pair in args.pairs:
        lat_s, lon_s = pair.split(",")
        items.append((pair, float(lat_s), float(lon_s)))
    if not items:
        print("nothing to look up: pass lat,lon pairs or --points <file>", file=sys.stderr)
        return 2

    out: dict[str, dict] = {}
    for name, lat, lon in items:
        try:
            res = lookup(lat, lon, args.tk, args.proxy)
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: ERROR {exc}")
            continue
        addr = res.get("formatted_address", "")
        out[name] = {"lat": lat, "lon": lon, "address": addr,
                     "component": res.get("addressComponent") or {}}
        print(f"{name} ({lat},{lon}) -> {addr}")
    if args.out and out:
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
