#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["huggingface_hub", "torch", "transformers"]
# ///
"""Single local store for the model weights this skill uses.

All weights live in ONE plain folder, so the same model is never downloaded twice and never
depends on the HuggingFace hub cache (whose snapshot symlinks read as empty files on some
Windows setups -- if that happens the hub copy is unusable even though the blobs exist).

  GEO_MODELS_DIR   override the store location (default: ~/.workbuddy/models)
  GEO_ALLOW_DOWNLOAD=1   allow network access; without it every script runs fully offline

Commands:
  status                    where each model is, how big, how many copies + whether the
                            offline wiring is still present in sat_scan.py / match.py
  fetch [name ...]          download/refresh into the store; add --update to replace existing
  verify                    load every model from the store (offline) and report params
  restore [--dry-run]       re-apply the wiring after a skill update overwrote the scripts

Second line of defence, independent of these scripts: the user-level environment variables
`HF_HUB_OFFLINE=1` (nothing downloads; a missing model errors out) and `GEO_CLIP_ID` /
`GEO_DINO_ID` (even an untouched upstream sat_scan.py then uses the shared store). A skill
update cannot remove those, because they live outside the skill folder.

Resolution used by sat_scan.py / match.py: GEO_<MODEL>_ID env var -> the store -> the skill's
legacy .models/ folder -> the HuggingFace hub id (download only if GEO_ALLOW_DOWNLOAD=1).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

MODELS_ROOT = Path(os.environ.get("GEO_MODELS_DIR") or (Path.home() / ".workbuddy" / "models"))
LEGACY_DIR = Path(__file__).resolve().parent.parent / ".models"
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
# Wired copies of the scripts that carry local additions, kept OUTSIDE the skill folder so a skill
# update cannot remove them together with the scripts they are meant to restore.
# Override the location with GEO_WIRED_BACKUP.
BACKUP_DIR = Path(os.environ.get("GEO_WIRED_BACKUP")
                  or (Path.home() / ".workbuddy" / "backups" / "geo-sleuth-wired"))

# name -> (hub repo, allow_patterns or None for "everything except IGNORE")
REGISTRY: dict[str, tuple[str, list[str] | None]] = {
    "clip-vit-base-patch32": ("openai/clip-vit-base-patch32", None),
    "dinov2-small": ("facebook/dinov2-small",
                     ["config.json", "preprocessor_config.json", "model.safetensors"]),
}
IGNORE = ["*.msgpack", "*.h5", "flax_model*", "tf_model*", "*.onnx", "*.pth", "*.ot"]


def enforce_offline() -> None:
    """Run offline unless the caller explicitly opts in via GEO_ALLOW_DOWNLOAD=1.

    A missing model then fails loudly instead of silently downloading hundreds of megabytes
    into some cache directory.
    """
    if os.environ.get("GEO_ALLOW_DOWNLOAD") == "1":
        return
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def resolve(local_name: str, hub_id: str) -> str:
    """Store -> legacy skill folder -> hub id. A folder only counts if it holds a config.json."""
    for root in (MODELS_ROOT, LEGACY_DIR):
        d = root / local_name
        if (d / "config.json").exists():
            return str(d)
    return hub_id


def dirsize(p: Path) -> int:
    total = 0
    for dp, _, fs in os.walk(p):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


WIRED = ["sat_scan.py", "match.py"]


def check_wiring() -> list[tuple[str, str]]:
    """A skill update can overwrite sat_scan.py / match.py and silently undo the offline wiring.

    Comparing environment variables proves nothing about that, so inspect the files directly:
    each script must both import from models and actually call enforce_offline().
    """
    here = Path(__file__).resolve().parent
    rows = []
    for name in WIRED:
        p = here / name
        if not p.exists():
            rows.append((name, "FILE MISSING"))
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        # 用宽松判据：接线是 try/except 包裹的（缺 models.py 时优雅降级），所以不必匹配 "from models import"
        ok = ("import models" in src) and ("enforce_offline(" in src)
        rows.append((name, "wired" if ok else "UNWIRED - fell back to hub cache"))
    return rows


def cmd_status(_args) -> int:
    print(f"store      : {MODELS_ROOT}  ({'exists' if MODELS_ROOT.is_dir() else 'MISSING'})")
    print(f"legacy dir : {LEGACY_DIR}  ({'exists' if LEGACY_DIR.is_dir() else 'absent'})")
    print(f"this run   : {'GEO_ALLOW_DOWNLOAD=1 - network allowed' if os.environ.get('GEO_ALLOW_DOWNLOAD') == '1' else 'offline (downloads disabled)'}")
    print()
    print("model                    where                                        size     files")
    print("-" * 88)
    for name, (repo, _) in REGISTRY.items():
        rows = [(MODELS_ROOT / name, "store"), (LEGACY_DIR / name, "legacy"), (HF_CACHE / ("models--" + repo.replace("/", "--")), "hf-cache")]
        for p, label in rows:
            if p.is_dir():
                n = sum(len(fs) for _, _, fs in os.walk(p))
                print(f"{name:<24} {label:<12} {str(p)[:40]:<40} {dirsize(p)/1e6:8.1f} MB  {n}")
    print()
    print("script wiring (a skill update can overwrite these):")
    unwired = False
    for name, state in check_wiring():
        if state != "wired":
            unwired = True
        print(f"  {name:<16} {state}")
    if unwired:
        print("  -> offline wiring is gone: those scripts will use the hub cache and may")
        print("     download weights again. Re-apply it with:")
        print(f"       uv run {Path(__file__).resolve()} restore")
    return 0


def cmd_fetch(args) -> int:
    os.environ["GEO_ALLOW_DOWNLOAD"] = "1"
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(k, None)
    from huggingface_hub import snapshot_download
    import shutil

    names = args.names or list(REGISTRY)
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name in names:
        if name not in REGISTRY:
            print(f"unknown model: {name} (known: {', '.join(REGISTRY)})")
            rc = 2
            continue
        repo, allow = REGISTRY[name]
        dst = MODELS_ROOT / name
        if args.update and dst.exists():
            print(f"removing existing {dst}")
            shutil.rmtree(dst, ignore_errors=True)
        print(f"fetching {repo} -> {dst}")
        try:
            snapshot_download(repo_id=repo, local_dir=str(dst),
                              allow_patterns=allow, ignore_patterns=None if allow else IGNORE)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {str(e)[:300]}")
            rc = 1
            continue
        print(f"  done  {dirsize(dst)/1e6:.1f} MB")
    return rc


def cmd_verify(_args) -> int:
    enforce_offline()
    import torch
    from transformers import AutoModel, CLIPModel

    print(f"offline mode: HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')} "
          f"TRANSFORMERS_OFFLINE={os.environ.get('TRANSFORMERS_OFFLINE')}")
    rc = 0
    for name in REGISTRY:
        d = MODELS_ROOT / name
        if not (d / "config.json").exists():
            print(f"MISSING  {name}")
            rc = 1
            continue
        t0 = time.time()
        try:
            cls = CLIPModel if name.startswith("clip") else AutoModel
            m = cls.from_pretrained(str(d)).eval()
            n = sum(p.numel() for p in m.parameters())
            print(f"OK       {name:<24} {n/1e6:7.1f}M params  {time.time()-t0:5.1f}s  <- {d}")
        except Exception as e:  # noqa: BLE001
            print(f"FAILED   {name}: {str(e)[:240]}")
            rc = 1
    return rc


def sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_restore(args) -> int:
    """Re-apply the offline wiring after a skill update overwrote the scripts.

    Restores only files that actually differ from the backup, so a newer upstream script that
    already carries the wiring is left untouched.
    """
    import shutil

    here = Path(__file__).resolve().parent
    skill = here.parent
    targets = {
        "sat_scan.py": here / "sat_scan.py",
        "match.py": here / "match.py",
        "models.py": here / "models.py",
        # These do not feed the models, but they carry local additions (extra imagery sources, the
        # conclusion-card builder) and can be lost to a skill update just as easily.
        "tiles.py": here / "tiles.py",
        "conclusion.py": here / "conclusion.py",
        "SKILL.md": skill / "SKILL.md",
    }
    if not BACKUP_DIR.is_dir():
        print(f"backup folder missing: {BACKUP_DIR}")
        return 2

    rc = 0
    for name, dst in targets.items():
        src = BACKUP_DIR / name
        if not src.exists():
            print(f"  {name:<16} no backup copy, skipped")
            rc = 1
            continue
        if dst.exists() and sha256(src) == sha256(dst):
            print(f"  {name:<16} already up to date")
            continue
        state = "missing" if not dst.exists() else "overwritten by an update"
        if args.dry_run:
            print(f"  {name:<16} WOULD restore ({state})")
            continue
        shutil.copy2(src, dst)
        print(f"  {name:<16} restored ({state})")
    if not args.dry_run:
        print("\nre-check with: models.py status")
    return rc


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Local model store: one copy, offline by default.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="where each model is and how big")
    f = sub.add_parser("fetch", help="download/refresh into the store (needs network)")
    f.add_argument("names", nargs="*")
    f.add_argument("--update", action="store_true", help="replace existing folders")
    sub.add_parser("verify", help="load every model from the store, offline")
    r = sub.add_parser("restore", help="re-apply the offline wiring after a skill update overwrote it")
    r.add_argument("--dry-run", action="store_true", help="report what would change, touch nothing")
    args = ap.parse_args()
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "restore":
        return cmd_restore(args)
    return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
