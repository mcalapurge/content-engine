"""split a batch-filmed video (several tiktok shop videos in one long take) into separate clips.

usage:
  python -m engine batch split inputs/shop/<video> [--gap 1.5] [--count 6]   find where each video is
  python -m engine batch cut inputs/shop/<video>                              save each one as a clip

split transcribes the whole file (if needed), then splits at the big pauses between videos.
--count forces exactly that many videos (uses the biggest pauses). cut saves each video to
work/<video>/parts/ - the original is never touched - ready for the normal edit steps. the picture is
copied, not re-encoded, so a part can start a moment early (on the keyframe in the pause before it).
"""
import argparse
import math
import sys

from engine.core.common import (vin, die, find_bin, in_parallel, load_json, probe, resolve_video, run, save_json,
                                work_dir_for)
from engine.commands.transcribe import transcribe_file


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


def keyframe_before(video, t):
    """time (from the file's start, as -ss counts) of the last keyframe at or before t."""
    start = float(probe(video)["format"].get("start_time", 0) or 0)
    res = run([find_bin("ffprobe"), "-v", "error", "-select_streams", "v:0",
               "-read_intervals", f"{max(0.0, start + t - 20):.3f}%{start + t + 0.1:.3f}",
               "-show_entries", "packet=pts_time,flags",
               "-of", "csv=p=0", str(video)])
    keys = []
    for line in res.stdout.splitlines():
        pts, _, flags = line.partition(",")
        if "K" in flags and pts not in ("", "N/A"):
            keys.append(float(pts) - start)
    return max((k for k in keys if k <= t + 0.001), default=0.0)


def cmd_cut(video, wd, args):
    bp = wd / "batch.json"
    if not bp.exists():
        die("run 'python -m engine batch split' first")
    sections = load_json(bp)["sections"]
    words = load_json(wd / "transcript.json")["words"] if (wd / "transcript.json").exists() else []
    v = next(s for s in probe(video)["streams"] if s["codec_type"] == "video")
    # re-encode settings, only for a part whose keyframe would reach back into the video before it.
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
    copy = ["-c:v", "copy", *(["-tag:v", "hvc1"] if v.get("codec_name") == "hevc" else [])]
    parts = wd / "parts"
    parts.mkdir(exist_ok=True)
    stem = wd.name

    def cut(job):
        n, s = job
        out = parts / f"{stem}_{n:02d}.mp4"
        # copy the picture as it is (no re-encode: instant, and the edit works from the camera's own
        # frames). a copy has to start on a keyframe, so a part can begin a moment early, inside the
        # pause before its hook. if that keyframe is back in the previous video's speech, re-encode instead
        said_before = max((w["end"] for w in words if w["end"] <= s["start"]), default=0.0)
        key = keyframe_before(video, s["start"]) if s["start"] > 0 else 0.0
        exact = key < said_before - 0.05
        # a copy keeps everything from the keyframe at or before the cut, and the sound starts at the cut
        # itself: cut a hair (under 1ms) after the keyframe, so picture and sound start together
        start = s["start"] if exact else math.floor(key * 1000) / 1000 + 0.001 if key > 0 else 0.0
        run([find_bin("ffmpeg"), "-y", *vin(video, "-ss", f"{start:.3f}", "-to", f"{s['end']:.3f}"),
             "-map", "0:v:0", "-map", "0:a:0", *(codec + colour if exact else copy),
             "-c:a", "aac", "-b:a", "256k", "-avoid_negative_ts", "make_zero", str(out)])
        return out, start, exact

    for n, (out, start, exact) in enumerate(in_parallel(cut, list(enumerate(sections, 1))), 1):
        how = "re-encoded (no keyframe in the pause before it)" if exact else \
            f"copied from {mmss(start)}" if start < sections[n - 1]["start"] - 0.01 else "copied"
        print(f"[engine] video {n}: {out.relative_to(wd.parent.parent)}  {how}")


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
