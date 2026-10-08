"""decide which clips a job uses. every content skill runs this first, so they all behave the same.

usage: python engine/inputs.py <input folder> [subfolder] [--newest]
  eg   python engine/inputs.py input_vlog sunday-reset
       python engine/inputs.py input --newest            (talking head: just the newest added clip)

rules:
  1. subfolder given           -> the clips in input_x/<subfolder> (--newest: just the newest added one)
  2. no subfolder, folders exist -> prints ASK + the folder names: ask her which one
  3. no subfolder, no folders  -> every clip in input_x/ (--newest: just the newest added one)
"newest" means newest ADDED to the folder (mac "date added"), not the date it was filmed.
"""
import argparse
import sys
from pathlib import Path

from common import ROOT, VIDEO_EXTS, date_added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--newest", action="store_true")
    ap.add_argument("--sheets", action="store_true", help="also list spreadsheets (trial reels)")
    args = ap.parse_args()

    base = Path(args.base)
    base = base if base.is_absolute() else ROOT / base
    if not base.is_dir():
        sys.exit(f"no folder called {args.base}")
    subs = sorted(d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith((".", "_")))

    if args.folder:
        target = base / args.folder
        if not target.is_dir():
            sys.exit(f"no folder called '{args.folder}' in {base.name}/. folders: {', '.join(subs) or 'none'}")
    elif subs:
        print("ASK")
        print(f"folders in {base.name}/: " + ", ".join(subs))
        return
    else:
        target = base

    clips = [p for p in target.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    sheets = [p for p in target.iterdir() if p.is_file() and p.suffix.lower() in (".xlsx", ".csv")] if args.sheets else []
    if not clips and not sheets:
        sys.exit(f"nothing to use in {target.relative_to(ROOT)}/ (no clips{' or spreadsheets' if args.sheets else ''})")
    clips.sort(key=date_added)
    if args.newest:
        clips = clips[-1:]
    print(f"FOLDER {target.relative_to(ROOT)}")
    for sh in sheets:
        print(f"SHEET {sh.relative_to(ROOT)}")
    for c in clips:
        print(c.relative_to(ROOT))


if __name__ == "__main__":
    main()
