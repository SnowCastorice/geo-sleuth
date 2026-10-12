#!/usr/bin/env python3
"""Deploy skills/geo-sleuth into the agent's skills directory under an independent name.

Why a separate deploy step at all: the client only loads skills from
`~/.workbuddy/skills/<folder>/`, and it is the client that overwrites
market-installed skills. A folder that came from the marketplace gets replaced
wholesale (modified files reverted, files the market package does not contain
deleted). Deploying under a different folder name, with a different `name:` in
the frontmatter, keeps this copy out of the marketplace's sync scope.

The sync is a mirror: files that no longer exist in the repo are deleted from the
target, so nothing stale is left behind.

Usage:
  python tools/deploy.py                 # deploy to ~/.workbuddy/skills/geo-sleuth-custom
  python tools/deploy.py --name my-fork  # deploy under another folder name
  python tools/deploy.py --dry-run       # report what would change, change nothing
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "skills" / "geo-sleuth"
SKILLS_DIR = Path.home() / ".workbuddy" / "skills"

DISPLAY = "照片地点识别（本地增强版）"

# Shipped by the marketplace install, not part of the repo's skill folder: keep them so the
# deployed copy still carries its licence notice and icon.
KEEP = {"LICENSE", "NOTICE.md", "_icon.png"}


def _skip(p: Path) -> bool:
    """Byte-code caches and editor leftovers never belong in the deployed skill."""
    return "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}


def _relabel_text(text: str, name: str) -> str:
    """Frontmatter as it should read in the deployed copy."""
    new = re.sub(r"^name:\s*geo-sleuth\s*$", f"name: {name}", text, count=1, flags=re.M)
    if not re.search(r"^display_name:", new, re.M):
        new = re.sub(r"^(name: .*)$", rf"\1\ndisplay_name: \"{DISPLAY}\"", new, count=1, flags=re.M)
    return new


def _deployed_bytes(src_file: Path, rel: Path, name: str) -> bytes:
    """What this file should look like in the target — SKILL.md differs by the relabel."""
    data = src_file.read_bytes()
    if rel.name == "SKILL.md":
        return _relabel_text(data.decode("utf-8"), name).encode("utf-8")
    return data


def mirror(src: Path, dst: Path, name: str, dry: bool) -> tuple[list[str], list[str]]:
    """Copy every changed file, delete files that are gone from the source."""
    copied: list[str] = []
    removed: list[str] = []
    src_files = {p.relative_to(src) for p in src.rglob("*") if p.is_file() and not _skip(p)}
    if dst.exists():
        for p in sorted(dst.rglob("*"), reverse=True):
            if p.is_dir() or _skip(p):
                continue
            if p.relative_to(dst) not in src_files and str(p.relative_to(dst)) not in KEEP:
                removed.append(str(p.relative_to(dst)))
                if not dry:
                    p.unlink()
    for rel in sorted(src_files):
        s, d = src / rel, dst / rel
        want = _deployed_bytes(s, rel, name)
        if d.exists() and d.read_bytes() == want:
            continue
        copied.append(str(rel))
        if not dry:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(want)
    for cache in list(dst.rglob("__pycache__")) if dst.exists() else []:
        if not dry:
            shutil.rmtree(cache, ignore_errors=True)
    return copied, removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="geo-sleuth-custom", help="folder name under the skills directory")
    ap.add_argument("--target", type=Path, help="full target path (overrides --name)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dst = args.target or (SKILLS_DIR / args.name)
    if not SRC.is_dir():
        print(f"source missing: {SRC}", file=sys.stderr)
        return 2

    copied, removed = mirror(SRC, dst, args.name, args.dry_run)

    verb = "would " if args.dry_run else ""
    print(f"source : {SRC}")
    print(f"target : {dst}")
    print(f"{verb}copied  {len(copied)} file(s)" + (": " + ", ".join(copied[:8]) + (" …" if len(copied) > 8 else "") if copied else ""))
    print(f"{verb}removed {len(removed)} stale file(s)" + (": " + ", ".join(removed[:8]) if removed else ""))
    if not copied and not removed:
        print("already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
