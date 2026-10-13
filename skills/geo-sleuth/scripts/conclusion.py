#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Render the conclusion card: one self-contained image carrying the answer, the coordinates,
the evidence chain and the confidence line.

The card is what you hand the user, so build it in the language the answer is written in and
show it together with the answer.

Usage:
  conclusion.py spec.json --out conclusion.jpg

spec.json — only "title" is required, everything else is optional:
{
  "title":      "Where this photo was taken",
  "subtitle":   "Xi'an Bell Tower · camera on the north-west side, facing south-east",
  "answer":     "One-sentence conclusion, shown in a highlighted box.",
  "facts":      ["Key fact, one per line", "..."],
  "photo":      "annotated_photo.jpg",      # left panel
  "photo_caption": "What that panel shows",
  "map":        "map_annotated.jpg",        # right panel
  "map_caption": "...",
  "chain": [                                # reasoning chain, in investigation order
    {"text": "what was seen → what it was checked against → what it established",
     "basis": "source of the check: gazetteer / street view + date / your own pixel measurement",
     "image": "card/step1.jpg"}
  ],
  "coords":     [{"label": "WGS84", "value": "34.26204, 108.94216"}],
  "confidence": [{"level": "City", "grade": "high", "why": "unique anchor"}],
  "footer":     "Anything the reader must know before trusting the number.",
  "width":      1200,
  "lang":       "zh"
}

Chain thumbnails are drawn at most 230×140 px and the text column narrows by the thumbnail
width, so keep one short line per item. A thumbnail must be a real artefact of the step it sits
next to — a decorative stand-in is fabrication; leave "image" out instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from baidu_pano import _font  # noqa: E402  CJK-capable font lookup, honours GEO_FONT

BG = (255, 255, 255)
INK = (28, 32, 38)
MUTED = (108, 114, 124)
ACCENT = (168, 32, 32)
RULE = (223, 227, 233)
BOX = (243, 245, 248)
THUMB = (230, 140)

LABELS = {
    "en": {"facts": "Key facts", "chain": "How each step was established", "coords": "Coordinates",
           "confidence": "Confidence", "answer": "Conclusion", "basis": "basis"},
    "zh": {"facts": "关键事实", "chain": "推理链（每步：观察 → 依据 → 推断）", "coords": "坐标",
           "confidence": "置信度", "answer": "结论", "basis": "依据"},
}


def wrap(draw: ImageDraw.ImageDraw, text: str, font, maxw: float) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > maxw and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def panel(base: Path, name: str | None, box: tuple[int, int]) -> Image.Image | None:
    if not name:
        return None
    p = base / name
    if not p.exists():
        print(f"panel not found, skipped: {p}", file=sys.stderr)
        return None
    im = Image.open(p).convert("RGB")
    im.thumbnail(box)
    return im


def build(spec: dict, base: Path, out: Path) -> None:
    W = int(spec.get("width", 1200))
    pad = int(W * 0.04)
    lab = LABELS.get(spec.get("lang", "en"), LABELS["en"])
    F_TITLE = _font(int(W * 0.040))
    F_SUB = _font(int(W * 0.020))
    F_H = _font(int(W * 0.023))
    F_B = _font(int(W * 0.018))
    F_S = _font(int(W * 0.015))
    inner = W - 2 * pad
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    blocks: list[tuple[int, callable]] = []

    def text_block(text: str, font, fill, lead: float, top: int = 0, bottom: int = 0):
        lines = wrap(probe, text, font, inner)
        h = int(top + len(lines) * lead + bottom)

        def draw(d, y, lines=lines, font=font, fill=fill, lead=lead, top=top, h=h):
            for i, ln in enumerate(lines):
                d.text((pad, y + top + i * lead), ln, font=font, fill=fill)
            return y + h
        blocks.append((h, draw))

    if spec.get("title"):
        text_block(spec["title"], F_TITLE, INK, F_TITLE.size * 1.32, bottom=6)
    if spec.get("subtitle"):
        text_block(spec["subtitle"], F_SUB, MUTED, F_SUB.size * 1.5, bottom=14)

    if spec.get("answer"):
        lead = F_B.size * 1.6
        lines = wrap(probe, spec["answer"], F_B, inner - 40)
        h = int(20 + 28 + len(lines) * lead + 18)

        def draw_answer(d, y, lines=lines, lead=lead, h=h):
            d.rectangle([pad, y, W - pad, y + h], fill=BOX, outline=RULE, width=1)
            d.rectangle([pad, y, pad + 5, y + h], fill=ACCENT)
            d.text((pad + 20, y + 12), lab["answer"], font=F_S, fill=ACCENT)
            for i, ln in enumerate(lines):
                d.text((pad + 20, y + 42 + i * lead), ln, font=F_B, fill=INK)
            return y + h + 22
        blocks.append((h + 22, draw_answer))

    pim = panel(base, spec.get("photo"), (int(inner * 0.52), int(W * 0.42)))
    mim = panel(base, spec.get("map"), (int(inner * 0.44), int(W * 0.42)))
    if pim or mim:
        gap = int(W * 0.02)
        ph = max([im.height for im in (pim, mim) if im] or [0])
        capt = bool(spec.get("photo_caption") or spec.get("map_caption"))
        cap_h = 34 if capt else 8

        def draw_panels(d, y, pim=pim, mim=mim, gap=gap, ph=ph, cap_h=cap_h):
            y = int(y)
            x = pad
            for im, cap in ((pim, spec.get("photo_caption")), (mim, spec.get("map_caption"))):
                if not im:
                    continue
                d.rectangle([x - 1, y - 1, x + im.width, y + im.height], outline=RULE, width=1)
                canvas.paste(im, (x, y))
                if cap:
                    for i, ln in enumerate(wrap(probe, cap, F_S, im.width)[:2]):
                        d.text((x, y + im.height + 6 + i * F_S.size * 1.3), ln, font=F_S, fill=MUTED)
                x += im.width + gap
            return y + ph + cap_h
        blocks.append((ph + cap_h, draw_panels))

    if spec.get("facts"):
        lead = F_B.size * 1.55
        packed = [(f, wrap(probe, "· " + f, F_B, inner)) for f in spec["facts"]]
        h = int(F_H.size * 1.9 + sum(len(ls) * lead + 6 for _, ls in packed) + 14)

        def draw_facts(d, y, packed=packed, lead=lead, h=h):
            d.text((pad, y), lab["facts"], font=F_H, fill=ACCENT)
            y += F_H.size * 1.9
            for _, lines in packed:
                for i, ln in enumerate(lines):
                    d.text((pad, y + i * lead), ln, font=F_B, fill=INK)
                y += len(lines) * lead + 6
            return y + 14
        blocks.append((h, draw_facts))

    if spec.get("chain"):
        items = []
        for it in spec["chain"]:
            txt = it.get("text", "") if isinstance(it, dict) else str(it)
            basis = it.get("basis", "") if isinstance(it, dict) else ""
            img = it.get("image") if isinstance(it, dict) else None
            thumb = panel(base, img, THUMB) if img else None
            colw = inner - (thumb.width + 16 if thumb else 0)
            lines = wrap(probe, txt, F_B, colw)
            b_lines = wrap(probe, f"{lab['basis']}：{basis}", F_S, colw - 8) if basis else []
            hh = int(max(THUMB[1] if thumb else 0,
                         len(lines) * F_B.size * 1.5 + (len(b_lines) * F_S.size * 1.45 + 4 if b_lines else 0)))
            items.append((thumb, lines, b_lines, hh))
        h = int(F_H.size * 1.9 + sum(hh + 16 for _, _, _, hh in items) + 6)

        def draw_chain(d, y, items=items, h=h):
            y = int(y)
            d.text((pad, y), lab["chain"], font=F_H, fill=ACCENT)
            y += F_H.size * 1.9
            for thumb, lines, b_lines, hh in items:
                y = int(y)
                if thumb:
                    d.rectangle([pad - 1, y - 1, pad + thumb.width, y + thumb.height], outline=RULE, width=1)
                    canvas.paste(thumb, (pad, y))
                tx = pad + (thumb.width + 16 if thumb else 0)
                ty = y
                for i, ln in enumerate(lines):
                    d.text((tx, ty + i * F_B.size * 1.5), ln, font=F_B, fill=INK)
                ty = int(ty + len(lines) * F_B.size * 1.5 + 2)
                for i, ln in enumerate(b_lines):          # 依据：灰色小字，单独成行
                    d.text((tx + 8, ty + i * F_S.size * 1.45), ln, font=F_S, fill=MUTED)
                if b_lines:
                    d.line([(tx, ty + 2), (tx, ty + int(len(b_lines) * F_S.size * 1.45))], fill=ACCENT, width=2)
                y += hh + 16
            return y + 6
        blocks.append((h, draw_chain))

    coords = spec.get("coords") or []
    conf = spec.get("confidence") or []
    if coords or conf:
        lead = F_B.size * 1.6
        h = int(F_H.size * 1.9 + len(coords) * lead + (10 + F_H.size * 1.9 + len(conf) * lead if conf else 0) + 12)

        def draw_meta(d, y, coords=coords, conf=conf, lead=lead, h=h):
            if coords:
                d.text((pad, y), lab["coords"], font=F_H, fill=ACCENT)
                y += F_H.size * 1.9
                for c in coords:
                    d.text((pad, y), str(c.get("label", "")), font=F_B, fill=MUTED)
                    d.text((pad + int(inner * 0.18), y), str(c.get("value", "")), font=F_B, fill=INK)
                    y += lead
            if conf:
                y += 10
                d.text((pad, y), lab["confidence"], font=F_H, fill=ACCENT)
                y += F_H.size * 1.9
                for c in conf:
                    d.text((pad, y), f"{c.get('level', '')}  {c.get('grade', '')}".strip(), font=F_B, fill=INK)
                    if c.get("why"):
                        d.text((pad + int(inner * 0.30), y), str(c["why"]), font=F_S, fill=MUTED)
                    y += lead
            return y + 12
        blocks.append((h, draw_meta))

    footer = spec.get("footer")
    total = sum(h for h, _ in blocks)
    foot_lines = wrap(probe, footer, F_S, inner) if footer else []
    if foot_lines:
        total += int(len(foot_lines) * F_S.size * 1.45 + 22)

    canvas = Image.new("RGB", (W, pad + total + pad), BG)
    d = ImageDraw.Draw(canvas)
    y = pad
    for _, fn in blocks:
        y = int(fn(d, y))          # keep the cursor integral: PIL paste/rectangle reject floats
    if foot_lines:
        d.line([(pad, y + 6), (W - pad, y + 6)], fill=RULE, width=1)
        for i, ln in enumerate(foot_lines):
            d.text((pad, y + 20 + i * F_S.size * 1.45), ln, font=F_S, fill=MUTED)

    canvas.save(out, quality=92)
    print(f"{out}  {canvas.size[0]}x{canvas.size[1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path, help="JSON describing the card")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", type=Path, help="directory the panel paths are relative to (default: the spec's folder)")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    build(spec, args.base or args.spec.parent, args.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
