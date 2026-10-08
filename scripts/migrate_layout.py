"""move an install from the old flat layout to the current one. run it once, by hand, from the
project root. it shows what it would do first; nothing changes without --apply.

  python scripts/migrate_layout.py --brand beth            # dry run: list every move
  python scripts/migrate_layout.py --brand beth --apply    # do it

why it's needed: footage, b-roll, music and work files aren't tracked by git, so pulling the new
layout leaves them in the old folders. this moves them and points saved plans at the new paths.

old                    new
input/                 inputs/talking-head/
input_shop/            inputs/shop/
input_vlog/            inputs/vlog/
input_trial/           inputs/trial/
brand/                 brands/<brand>/   (brand.md, effects.md, grade.json)
styles/<brand>.json    brands/<brand>/style.json
styles/, fonts/, music/, sfx/   assets/...
broll/                 brands/<brand>/broll/

files are moved, never copied or deleted. a file already at its new place is left alone and reported.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def moves(brand):
    b = f"brands/{brand}"
    return [
        ("input", "inputs/talking-head"), ("input_shop", "inputs/shop"), ("input_vlog", "inputs/vlog"),
        ("input_trial", "inputs/trial"),
        (f"styles/{brand}.json", f"{b}/style.json"), ("styles", "assets/styles"),
        ("brand", b), ("broll", f"{b}/broll"),
        ("fonts", "assets/fonts"), ("music", "assets/music"), ("sfx", "assets/sfx"),
    ]


# path prefixes saved inside json files (plan.json, clips.json, library.json)
def prefixes(brand):
    b = f"brands/{brand}"
    return [("input/", "inputs/talking-head/"), ("input_shop/", "inputs/shop/"), ("input_vlog/", "inputs/vlog/"),
            ("input_trial/", "inputs/trial/"), ("broll/", f"{b}/broll/"), ("assets/broll/", f"{b}/broll/"),
            ("music/", "assets/music/"), ("sfx/", "assets/sfx/")]


def plan_moves(src, dst, out):
    """every file under src that should end up under dst."""
    if src.is_file():
        out.append((src, dst))
        return
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.name not in (".DS_Store",):
            out.append((p, dst / p.relative_to(src)))


def fix_paths(value, pairs):
    if isinstance(value, str):
        for old, new in pairs:
            if value.startswith(old):
                return new + value[len(old):]
        return value
    if isinstance(value, list):
        return [fix_paths(v, pairs) for v in value]
    if isinstance(value, dict):
        return {k: fix_paths(v, pairs) for k, v in value.items()}
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True, help="the brand the old brand/, broll/ and style belong to (eg beth)")
    ap.add_argument("--apply", action="store_true", help="actually move things (default: just show)")
    args = ap.parse_args()

    todo, skipped = [], []
    for old, new in moves(args.brand):
        src = ROOT / old
        if src.exists():
            plan_moves(src, ROOT / new, todo)
    seen = set()
    final = []
    for src, dst in todo:
        if src in seen:
            continue
        seen.add(src)
        if dst.exists():
            skipped.append((src, dst))
        else:
            final.append((src, dst))

    pairs = prefixes(args.brand)
    json_fixes = []
    for p in list((ROOT / "work").rglob("*.json")) + list((ROOT / "brands").glob("*/broll/library.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        new = fix_paths(data, pairs)
        if new != data:
            json_fixes.append((p, new))

    rel = lambda p: p.relative_to(ROOT).as_posix()
    for src, dst in final:
        print(f"  move  {rel(src)}  ->  {rel(dst)}")
    for src, dst in skipped:
        print(f"  skip  {rel(src)}  (already at {rel(dst)})")
    for p, _ in json_fixes:
        print(f"  paths {rel(p)}")
    if not (final or json_fixes):
        print("nothing to move, the layout is already up to date")
        return
    if not args.apply:
        print(f"\n{len(final)} file(s) to move, {len(json_fixes)} json file(s) to update. "
              "run again with --apply to do it")
        return

    for src, dst in final:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    for p, data in json_fixes:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmoved {len(final)} file(s), updated {len(json_fixes)} json file(s).")
    leftovers = [old for old, _ in moves(args.brand) if (ROOT / old).is_dir()
                 and not any(p.is_file() for p in (ROOT / old).rglob("*") if p.name != ".DS_Store")]
    if leftovers:
        print("these old folders are now empty and can be deleted: " + ", ".join(leftovers))
    if skipped:
        print("some files were skipped because something is already at the new path: check them by hand")
        sys.exit(1)


if __name__ == "__main__":
    main()
