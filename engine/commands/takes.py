"""pull frames from every take of a repeated line so claude can pick the best one by eye.

usage: python -m engine takes [video]
saves work/<clip>/takes/line_<id>.jpg (3 frames across each take, side by side)
and prints the groups with timing + how clearly each take was spoken.
"""
import argparse

from engine.core.common import vin, find_bin, load_json, resolve_video, run, sdr_filter, work_dir_for


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    args = ap.parse_args()
    video = resolve_video(args.video)
    wd = work_dir_for(video)
    plan = load_json(wd / "plan.json")
    words = load_json(wd / "transcript.json")["words"]
    out_dir = wd / "takes"
    out_dir.mkdir(exist_ok=True)

    by_id = {l["id"]: l for l in plan["lines"]}
    groups = []
    for l in plan["lines"]:
        if l["takes"] and l["takes"] not in groups:
            groups.append(l["takes"])
    if not groups:
        print("[engine] no repeated takes in this clip")
        return

    for g in groups:
        print(f"\nline filmed {len(g)} times:")
        for lid in g:
            l = by_id[lid]
            dur = l["end"] - l["start"]
            stamps = [l["start"] + dur * f for f in (0.2, 0.5, 0.8)]
            img = out_dir / f"line_{lid:02d}.jpg"
            inputs = []
            for t in stamps:
                inputs += vin(video, "-ss", f"{t:.2f}")
            fc = "".join(f"[{k}:v]{sdr_filter(video)}scale=-2:480,trim=end_frame=1[f{k}];" for k in range(3))
            fc += "[f0][f1][f2]hstack=inputs=3"
            run([find_bin("ffmpeg"), "-y", *inputs, "-filter_complex", fc,
                 "-frames:v", "1", "-q:v", "3", str(img)])
            probs = [words[i].get("prob", 1) for i in l["words"]]
            clarity = sum(probs) / len(probs) if probs else 0
            wps = len(l["words"]) / dur if dur else 0
            mark = "KEPT" if l["keep"] else "    "
            print(f"  {mark} line {lid}: {dur:.1f}s, {wps:.1f} words/sec, clarity {clarity:.2f} "
                  f"-> {img.name}\n        \"{l['text']}\"")
    print(f"\n[engine] frames saved in {out_dir}")


if __name__ == "__main__":
    main()
