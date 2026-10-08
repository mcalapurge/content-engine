"""break down someone else's reel so you can learn what's working (not copy it).

usage:
  python -m engine analyse https://www.instagram.com/reel/XXXX/
  python -m engine analyse https://... --browser chrome   # if instagram asks for a login
  python -m engine analyse path/to/screen-recording.mp4    # if the download won't work

saves to references/<name>/: the video, transcript, contact sheets (one frame per second)
and stats.json (cuts, pacing, speaking speed, when the first word lands).
for your own study only - don't repost other people's videos.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from engine.core.common import vin, REF_DIR, die, find_bin, run, save_json, video_info


def download(url, browser):
    REF_DIR.mkdir(exist_ok=True)
    tmp = REF_DIR / "_download"
    tmp.mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "yt_dlp", "-o", str(tmp / "%(uploader)s_%(id)s.%(ext)s"),
           "-f", "mp4/best", "--no-playlist", url]
    if browser:
        cmd[3:3] = ["--cookies-from-browser", browser]
    res = subprocess.run(cmd, capture_output=True, text=True)
    files = list(tmp.glob("*.mp4")) or list(tmp.glob("*.*"))
    if res.returncode != 0 or not files:
        die("couldn't download that reel. try again with --browser chrome (or safari / edge), "
            "or screen-record it and pass the file instead.\n" + res.stderr[-600:])
    return files[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="reel link or a video file")
    ap.add_argument("--browser", default=None, help="chrome / safari / edge / firefox")
    ap.add_argument("--model", default="parakeet", help="parakeet, or a whisper size (needs faster-whisper)")
    args = ap.parse_args()

    if re.match(r"https?://", args.source):
        src = download(args.source, args.browser)
    else:
        src = Path(args.source).resolve()
        if not src.exists():
            die(f"can't find {args.source}")
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", src.stem).strip("-")[:60] or "reel"
    out = REF_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    video = out / f"video{src.suffix}"
    if src != video:
        shutil.move(str(src), video) if REF_DIR in src.parents else shutil.copy(src, video)
    info = video_info(video)
    dur = info["duration"]
    print(f"[engine] analysing {name} ({dur:.1f}s)")

    # cuts
    res = run([find_bin("ffmpeg"), *vin(video), "-vf", "select='gt(scene,0.3)',showinfo",
               "-f", "null", "-"])
    cuts = [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", res.stderr)]

    # contact sheets: one frame a second, 10 per sheet
    sheets = []
    per = 10
    for k in range(0, int(dur) + 1, per):
        sheet = out / f"frames_{k:03d}-{min(k + per, int(dur)):03d}s.jpg"
        run([find_bin("ffmpeg"), "-y", *vin(video, "-ss", str(k), "-t", str(per)), "-vf",
             f"fps=1,scale=-2:420,tile={per}x1", "-frames:v", "1", "-q:v", "4", str(sheet)])
        sheets.append(sheet.name)

    stats = {"duration": round(dur, 1), "cuts": len(cuts), "cut_times": cuts,
             "avg_shot_seconds": round(dur / (len(cuts) + 1), 2),
             "cuts_per_10s": round(len(cuts) / dur * 10, 1) if dur else 0,
             "contact_sheets": sheets}
    if info["has_audio"]:
        from engine.commands.transcribe import transcribe_file
        tr = transcribe_file(video, out, args.model)
        words = tr["words"]
        if words:
            speech = words[-1]["end"] - words[0]["start"]
            text = " ".join(w["text"] for w in words)
            first = re.split(r"(?<=[.?!])\s", text, maxsplit=1)[0]
            stats.update({"first_word_at": words[0]["start"], "words": len(words),
                          "words_per_second": round(len(words) / speech, 2) if speech else 0,
                          "opening_line": first, "transcript": text})
    save_json(out / "stats.json", stats)
    print(f"[engine] {len(cuts)} cuts (one every {stats['avg_shot_seconds']}s), "
          f"{stats.get('words_per_second', 0)} words/sec, first word at {stats.get('first_word_at', '-')}s")
    print(f"[engine] look at the contact sheets in {out}")


if __name__ == "__main__":
    main()
