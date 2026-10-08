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

files are moved, never copied or deleted. a file whose exact copy is already at its new place (eg a
readme that git already moved) is left where it is, and so are the old folders' own placeholder files
(README.txt, .gitkeep) when the new folder has its own. a different file already at a new place is a
collision: the script lists them and changes nothing until they're sorted by hand.
jobs in work/ get their paths updated and are stamped with --brand (the old layout had one brand).
"""
import filecmp
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


PLACEHOLDERS = ("README.txt", ".gitkeep")


def placeholder(src, folder):
    """an old folder's own readme / .gitkeep: part of the old layout, not someone's file."""
    return src.name in PLACEHOLDERS and src.parent == folder


def plan_moves(src, dst, out):
    """every file under src that should end up under dst."""
    if src.is_file():
        out.append((src, dst))
        return
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.name not in (".DS_Store",):
            out.append((p, dst / p.relative_to(src)))


def stamp_brand(data, brand):
    """plans from the old layout belong to its one brand. without this, old vlog / text reel plans
    (which never saved a brand) can't be opened once a second brand exists."""
    if isinstance(data, dict) and ("lines" in data or "pieces" in data or "reels" in data) and not data.get("brand"):
        return {"brand": brand, **data}
    return data


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

    todo, already, collisions = [], [], []
    old_folders = set()
    for old, new in moves(args.brand):
        src = ROOT / old
        if src.exists():
            plan_moves(src, ROOT / new, todo)
            old_folders.add(src)
    seen = set()
    final = []
    for src, dst in todo:
        if src in seen:
            continue
        seen.add(src)
        if not dst.exists():
            final.append((src, dst))
        elif filecmp.cmp(src, dst, shallow=False) or any(placeholder(src, folder) for folder in old_folders):
            already.append((src, dst))
        else:
            collisions.append((src, dst))

    pairs = prefixes(args.brand)
    json_fixes = []
    for p in list((ROOT / "work").rglob("*.json")) + list((ROOT / "brands").glob("*/broll/library.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        new = fix_paths(data, pairs)
        if p.parent.parent == ROOT / "work":
            new = stamp_brand(new, args.brand)
        if new != data:
            json_fixes.append((p, new))

    rel = lambda p: p.relative_to(ROOT).as_posix()
    for src, dst in final:
        print(f"  move  {rel(src)}  ->  {rel(dst)}")
    for src, dst in already:
        print(f"  same  {rel(src)}  (already at {rel(dst)}, nothing to do)")
    for p, _ in json_fixes:
        print(f"  json  {rel(p)}  (paths and brand)")
    if collisions:
        print("\nthese files already exist at their new place with different contents:")
        for src, dst in collisions:
            print(f"  CLASH {rel(src)}  vs  {rel(dst)}")
        print("nothing was changed. compare each pair, keep the right one, move or delete the other, "
              "then run this again.")
        sys.exit(1)
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
    copies = {src for src, _ in already}
    leftovers = [old for old, _ in moves(args.brand) if (ROOT / old).is_dir()
                 and all(f in copies for f in (ROOT / old).rglob("*") if f.is_file() and f.name != ".DS_Store")]
    if leftovers:
        print("these old folders now only hold copies of files already in the new layout, "
              "so they can be deleted: " + ", ".join(leftovers))


if __name__ == "__main__":
    main()
