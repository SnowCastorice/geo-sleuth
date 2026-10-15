#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Offline smoke tests for the local additions: roadmap.py, revgeo.py, amap_road.py, conclusion.py.
Run: uv run --with pytest pytest skills/geo-sleuth/tests/test_offline_tools.py -q
No network and no API key: the network calls are patched out, so only the pure logic and the
file output are checked."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import amap_road  # noqa: E402
import conclusion  # noqa: E402
import revgeo  # noqa: E402
import roadmap  # noqa: E402


class RoadmapTests(unittest.TestCase):
    def test_tile_url_and_web_mercator_index(self):
        url = roadmap.tile_url("KEY", "vec_w", 17, 105198, 52244)
        for fragment in ("vec_w_w/wmts", "LAYER=vec_w", "TILEMATRIX=17", "TILEROW=52244",
                         "TILECOL=105198", "tk=KEY"):
            self.assertIn(fragment, url)
        # Web Mercator anchors: the world at z=0 is one tile whose centre is (0.5, 0.5); at z=1
        # lon +/-180 land on x 0/2 and the projection's limit +/-85.051129 on y 2/0.
        self.assertAlmostEqual(roadmap.tile_xy(0.0, 0.0, 0)[0], 0.5, places=9)
        self.assertAlmostEqual(roadmap.tile_xy(0.0, 0.0, 0)[1], 0.5, places=9)
        self.assertAlmostEqual(roadmap.tile_xy(0.0, -180.0, 1)[0], 0.0, places=6)
        self.assertAlmostEqual(roadmap.tile_xy(0.0, 180.0, 1)[0], 2.0, places=6)
        self.assertAlmostEqual(roadmap.tile_xy(-85.05112878, 0.0, 1)[1], 2.0, places=4)
        self.assertAlmostEqual(roadmap.tile_xy(85.05112878, 0.0, 1)[1], 0.0, places=4)


class RevgeoTests(unittest.TestCase):
    def test_lookup_builds_the_request_and_returns_result(self):
        seen = {}

        def fake_fetch(url, proxy=None, timeout=20, **kw):
            seen["url"] = url
            return json.dumps({"result": {"formatted_address": "陕西省西安市碑林区南大街1号"}}).encode()

        with patch.object(revgeo, "fetch_bytes", fake_fetch):
            out = revgeo.lookup(34.2530, 108.9416, "KEY")
        self.assertIn("api.tianditu.gov.cn/geocoder", seen["url"])
        self.assertIn("type=geocode", seen["url"])
        self.assertEqual(out["formatted_address"], "陕西省西安市碑林区南大街1号")


class AmapRoadTests(unittest.TestCase):
    def test_fetch_road_writes_a_mosaic_and_a_gcj_sidecar(self):
        with patch.object(amap_road, "_tile", lambda z, x, y, style: Image.new("RGB", (256, 256), (200, 200, 200))):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "road.jpg"
                amap_road.fetch_road("34.2530,108.9416", 17, 1, 8, out)
                meta = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
                self.assertTrue(out.exists())
        self.assertEqual(meta["crs"], "gcj")          # tiles.py mark then converts WGS84 points itself
        self.assertEqual(meta["zoom"], 17)
        self.assertEqual(meta["size"], [768, 768])    # (2*radius+1) tiles of 256 px


class ConclusionTests(unittest.TestCase):
    def test_build_writes_a_card_from_a_minimal_spec(self):
        spec = {"title": "T", "subtitle": "S", "answer": "A", "facts": [], "chain": [],
                "photo": "photo.jpg", "width": 400, "lang": "en"}
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            Image.new("RGB", (320, 240), (120, 160, 200)).save(base / "photo.jpg")
            out = base / "card.jpg"
            conclusion.build(spec, base, out)
            self.assertTrue(out.exists() and out.stat().st_size > 0)
            with Image.open(out) as im:
                self.assertGreater(im.size[0], 100)


if __name__ == "__main__":
    unittest.main()
