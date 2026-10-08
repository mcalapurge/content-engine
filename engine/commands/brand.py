"""brands: one folder per client in brands/<name>/ (guide, effects, grade, style, b-roll).

usage:
  python -m engine brand list                              every brand and what it has
  python -m engine brand new <name> [--style editorial]    start a new brand from brands/_template/,
                                                           its look copied from a style in assets/styles/
  python -m engine brand show <name>                       where each of a brand's files lives
"""
import argparse
import re
import shutil

from engine.core.brand import Brand, brand_names, get_brand
from engine.core.common import ROOT, die, load_json
from engine.core.paths import BRAND_TEMPLATE_DIR, BRANDS_DIR, STYLES_DIR


def cmd_list():
    names = brand_names()
    if not names:
        print("[engine] no brands yet. start one: python -m engine brand new <name>")
        return
    for n in names:
        b = Brand(n)
        clips = len(load_json(b.library)["clips"]) if b.library.exists() else 0
        missing = [f.name for f in (b.guide, b.effects, b.grade_file, b.style_file) if not f.exists()]
        print(f"  {n:16} {clips:3} b-roll clip(s)" + (f"  missing: {', '.join(missing)}" if missing else ""))


def cmd_show(name):
    b = get_brand(name)
    for label, p in (("guide", b.guide), ("effects", b.effects), ("grade", b.grade_file),
                     ("style", b.style_file), ("styles", b.styles_dir), ("b-roll", b.broll_dir),
                     ("library", b.library)):
        print(f"  {label:8} {p.relative_to(ROOT).as_posix()}{'' if p.exists() else '  (not there yet)'}")


def cmd_new(name, style):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name or ""):
        die("brand names are lowercase letters, numbers, - and _ (eg mia, wornbybeth)")
    dest = BRANDS_DIR / name
    if dest.exists():
        die(f"brands/{name}/ already exists")
    src_style = STYLES_DIR / f"{style}.json"
    if not src_style.exists():
        die(f"no style template '{style}'. options: {', '.join(p.stem for p in STYLES_DIR.glob('*.json'))}")
    shutil.copytree(BRAND_TEMPLATE_DIR, dest)
    shutil.copy(src_style, dest / "style.json")
    print(f"[engine] made brands/{name}/ (look copied from {style}). fill in brands/{name}/brand.md next")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show")
    s.add_argument("name")
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--style", default="editorial", help="generic look to start from (assets/styles/)")
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "show":
        cmd_show(a.name)
    else:
        cmd_new(a.name, a.style)


if __name__ == "__main__":
    main()
