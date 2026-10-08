"""split a batch-filmed video (several tiktok shop videos in one long take) into separate clips.

usage:
  python engine/batch.py split input_shop/<video> [--gap 1.5] [--count 6]   find where each video is
  python engine/batch.py cut input_shop/<video>                              save each one as a clip

split transcribes the whole file (if needed), then splits at the big pauses between videos.
--count forces exactly that many videos (uses the biggest pauses). cut saves each video to
work/<video>/parts/ - the original is never touched - ready for the normal edit steps.
"""
import argparse
import sys

from common import vin, die, find_bin, load_json, probe, resolve_video, run, save_json, work_dir_for
from transcribe import transcribe_file


def find_sections(words, gap, count):
    gaps = [(words[k + 1]["start"] - words[k]["end"], k) for k in range(len(words) - 1)]
    if count:
        breaks = sorted(k for _, k in sorted(gaps, reverse=True)[:max(0, count - 1)])
    else:
        breaks = [k for g, k in gaps if g >= gap]
    edges = [-1] + breaks + [len(words) - 1]
    return [(edges[n] + 1, edges[n + 1]) for n in range(len(edges) - 1)]


def cmd_split(video, wd, args):
    tp = wd / "transcript.json"
    if tp.exists():
        tr = load_json(tp)
    else:
        print(f"[engine] transcribing the whole batch ({video.name})...")
        tr = transcribe_file(video, wd)
    words = tr["words"]
    if not words:
        die("no speech found in this video")
    sections = []
    for a, b in find_sections(words, args.gap, args.count):
        prev_end = words[a - 1]["end"] if a else 0.0
        next_start = words[b + 1]["start"] if b + 1 < len(words) else tr["duration"]
        sections.append({
            "start": round((prev_end + words[a]["start"]) / 2, 3) if a else 0.0,
            "end": round((words[b]["end"] + next_start) / 2, 3) if b + 1 < len(words) else tr["duration"],
            "gap_before": round(words[a]["start"] - prev_end, 1) if a else None,
            "hook": " ".join(w["text"] for w in words[a:a + 14]),
        })
    save_json(wd / "batch.json", {"source": str(video), "sections": sections})
    print(f"\n# {video.name}: found {len(sections)} video(s)\n")
    print("| # | from | to | length | pause before | starts with |")
    print("|---|---|---|---|---|---|")
    for n, s in enumerate(sections, 1):
        gb = f"{s['gap_before']}s" if s["gap_before"] is not None else "-"
        print(f"| {n} | {mmss(s['start'])} | {mmss(s['end'])} | {s['end'] - s['start']:.0f}s | {gb} | "
              f"{s['hook'].replace('|', '/')}... |")


def cmd_cut(video, wd, args):
    bp = wd / "batch.json"
    if not bp.exists():
        die("run 'batch.py split' first")
    sections = load_json(bp)["sections"]
    v = next(s for s in probe(video)["streams"] if s["codec_type"] == "video")
    # keep the colour info (hdr stays hdr) so the edit treats each part like the original
    colour = []
    for opt, key in (("-color_primaries", "color_primaries"), ("-color_trc", "color_transfer"),
                     ("-colorspace", "color_space")):
        if v.get(key):
            colour += [opt, v[key]]
    if sys.platform == "darwin":       # hardware encoder: fast, keeps 10-bit
        codec = ["-c:v", "hevc_videotoolbox", "-q:v", "80", "-tag:v", "hvc1"]
        if "10" in v.get("pix_fmt", ""):
            codec += ["-profile:v", "main10"]
    else:
        codec = ["-c:v", "libx264", "-crf", "14", "-preset", "fast"]
    parts = wd / "parts"
    parts.mkdir(exist_ok=True)
    stem = wd.name
    for n, s in enumerate(sections, 1):
        out = parts / f"{stem}_{n:02d}.mp4"
        run([find_bin("ffmpeg"), "-y", *vin(video, "-ss", f"{s['start']:.3f}", "-to", f"{s['end']:.3f}"), "-map", "0:v:0", "-map", "0:a:0", *codec, *colour,
             "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out)])
        print(f"[engine] video {n}: {out.relative_to(wd.parent.parent)}")


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["split", "cut"])
    ap.add_argument("video")
    ap.add_argument("--gap", type=float, default=1.5, help="pause (seconds) that counts as a new video")
    ap.add_argument("--count", type=int, default=0, help="force exactly this many videos")
    args = ap.parse_args()
    video = resolve_video(args.video)
    wd = work_dir_for(video)
    (cmd_split if args.action == "split" else cmd_cut)(video, wd, args)


if __name__ == "__main__":
    main()
