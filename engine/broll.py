"""your b-roll library: index it once, then it gets matched to lines automatically.

usage:
  python engine/broll.py index            # scan broll/, make preview sheets, update library.json
  python engine/broll.py match [video]    # suggest b-roll for each line of a reel's plan
  python engine/broll.py list             # show what's in the library

broll/ can have subfolders (eg broll/hairburst/, broll/lifestyle/, broll/products/).
folder names and file names become tags, so "hairburst/pouring-gummies.mp4" is tagged
hairburst, pouring, gummies. claude adds a proper description by looking at each preview.
"""
import argparse
import re

from common import (vin, BROLL_DIR, IMAGE_EXTS, ROOT, VIDEO_EXTS, find_bin, load_json, norm, probe,
                    resolve_video, run, save_json, work_dir_for)

LIB = BROLL_DIR / "library.json"
PREVIEWS = BROLL_DIR / "_previews"
STOP = set("""a an the and or but so to of in on at for with from by is are was were be been it its
this that these those i im i'm you your my me we our they them he she his her just like really very
about what when how why if then than there here do does did doing have has had not no yes can will
would should could get got go going gonna one thing things know think say said make made up out
some all any more most much many also too as into over now well okay ok um uh erm""".split())


def tokens(text):
    out = set()
    for w in re.split(r"[^a-z0-9£$%']+", text.lower()):
        w = w.strip("'")
        if len(w) < 3 or w in STOP:
            continue
        for suf in ("ing", "es", "s", "ed"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def load_lib():
    return load_json(LIB) if LIB.exists() else {"clips": []}


def cmd_index():
    BROLL_DIR.mkdir(exist_ok=True)
    PREVIEWS.mkdir(exist_ok=True)
    lib = load_lib()
    known = {c["file"]: c for c in lib["clips"]}
    clips = []
    for p in sorted(BROLL_DIR.rglob("*")):
        if PREVIEWS in p.parents or p.suffix.lower() not in VIDEO_EXTS | IMAGE_EXTS:
            continue
        rel = p.relative_to(ROOT).as_posix()
        entry = known.get(rel, {"file": rel, "description": "", "tags": [], "good_for": ""})
        stat_key = f"{p.stat().st_size}-{int(p.stat().st_mtime)}"
        prev = PREVIEWS / (re.sub(r"[^A-Za-z0-9_-]+", "_", p.relative_to(BROLL_DIR).as_posix()) + ".jpg")
        if entry.get("_stamp") != stat_key or not prev.exists():
            if p.suffix.lower() in IMAGE_EXTS:
                entry["kind"], entry["duration"] = "image", None
                run([find_bin("ffmpeg"), "-y", "-i", str(p), "-vf", "scale=-2:400", "-frames:v", "1",
                     str(prev)])
            else:
                info = probe(p)
                v = next(s for s in info["streams"] if s["codec_type"] == "video")
                dur = float(info["format"].get("duration", 0))
                entry["kind"], entry["duration"] = "video", round(dur, 1)
                entry["orientation"] = "portrait" if int(v["height"]) >= int(v["width"]) else "landscape"
                inputs = []
                for f in (0.15, 0.5, 0.85):
                    inputs += vin(p, "-ss", f"{dur * f:.2f}")
                fc = "".join(f"[{k}:v]scale=-2:400,trim=end_frame=1[f{k}];" for k in range(3))
                run([find_bin("ffmpeg"), "-y", *inputs, "-filter_complex",
                     fc + "[f0][f1][f2]hstack=inputs=3", "-frames:v", "1", "-q:v", "4", str(prev)])
            entry["_stamp"] = stat_key
        entry["preview"] = prev.relative_to(ROOT).as_posix()
        auto = tokens(" ".join(p.relative_to(BROLL_DIR).with_suffix("").parts).replace("-", " ").replace("_", " "))
        entry["tags"] = sorted(set(entry.get("tags", [])) | auto)
        clips.append(entry)
    lib["clips"] = clips
    save_json(LIB, lib)
    todo = [c for c in clips if not c.get("description")]
    print(f"[engine] {len(clips)} clip(s) in the library, {len(todo)} need a description")
    for c in todo:
        print(f"  needs description: {c['file']}  (preview: {c['preview']})")


def cmd_list():
    for c in load_lib()["clips"]:
        dur = f"{c['duration']}s" if c.get("duration") else "still"
        print(f"  {c['file']:50s} {dur:>7s}  {c.get('description', '')[:60]}")


def cmd_match(video_arg, max_share):
    video = resolve_video(video_arg)
    wd = work_dir_for(video)
    plan = load_json(wd / "plan.json")
    clips = load_lib()["clips"]
    if not clips:
        print("[engine] broll/ is empty - add clips and run: broll.py index")
        return
    kept = [l for l in plan["lines"] if l["keep"]]
    budget = max(1, int(len(kept) * max_share))
    scored = []
    for l in kept:
        if l["treatment"] in ("hook", "takeover") or l.get("broll"):
            continue
        lt = tokens(l["text"])
        best, best_s = None, 0
        for c in clips:
            ct = set(c.get("tags", [])) | tokens(c.get("description", "") + " " + c.get("good_for", ""))
            s = len(lt & ct)
            if s > best_s:
                best, best_s = c, s
        if best:
            scored.append((best_s, l, best))
    scored.sort(key=lambda x: -x[0])
    used, last_line, chosen = set(), None, []
    for s, l, c in scored:
        if len(chosen) >= budget or c["file"] in used:
            continue
        l["broll"] = {"file": c["file"], "start": 0, "mode": "full"}
        used.add(c["file"])
        chosen.append((l["id"], c["file"], s))
    save_json(wd / "plan.json", plan)
    if not chosen:
        print("[engine] no keyword matches. claude can still pick by meaning - ask it to")
    for lid, f, s in sorted(chosen):
        print(f"  line {lid}: {f}  (match score {s})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    sub.add_parser("list")
    m = sub.add_parser("match")
    m.add_argument("video", nargs="?")
    m.add_argument("--max-share", type=float, default=0.4,
                   help="most of the reel that can be covered by b-roll (0.4 = 40%% of lines)")
    a = ap.parse_args()
    {"index": cmd_index, "list": cmd_list}.get(a.cmd, lambda: cmd_match(a.video, a.max_share))()


if __name__ == "__main__":
    main()
