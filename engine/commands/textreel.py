"""text-over-b-roll reels (trial reels): 3 lines of on-screen text over b-roll, with music.

usage:
  python -m engine textreel music                      tempo + energy of every track in assets/music/ (cached)
  python -m engine textreel import <sheet.xlsx> <name> --brand <brand>  read a trial-reels sheet into work/<name>/plan.json
  python -m engine textreel render <name> [--only 1,2,3] [--draft]

plan.json: {"reels": [{"id", "beats": [hook, middle, cta], "broll_type", "caption", "carousel",
            "shots": [{"file", "start"}, ...one per beat], "music", "music_start" (null = auto)}]}
claude fills in shots + music by eye, then renders. outputs land in output/<name>/.
"""
import argparse
import html
import re
import subprocess
import zipfile
from pathlib import Path

import numpy as np

from engine.core.brand import add_brand_arg, get_brand, load_style
from engine.core.common import (h264, vin, FONTS_DIR, MUSIC_DIR, ROOT, WORK_DIR, die, find_bin, in_parallel,
                                load_json, output_folder, run, save_json, sdr_filter)
from engine.commands.vlog import detect_beats

W, H, FPS = 1080, 1920, 30
TEXT_Y = 0.50          # text block centred in the frame
TEXT_SIZE = 92
LINE_GAP = 0.84        # line spacing as a fraction of the font size (tight)
LINE_CHARS = 22        # max characters per line before wrapping


# ---------- music ----------

def music_info(path):
    """bpm, beats and a loudness curve for a track, cached."""
    path = Path(path)
    cache = WORK_DIR / "_music" / f"{path.stem}.json"
    st = path.stat()
    stamp = f"{st.st_size}-{int(st.st_mtime)}"
    if cache.exists():
        c = load_json(cache)
        if c.get("stamp") == stamp:
            return c
    bpm, beats = detect_beats(path)
    raw = subprocess.run([find_bin("ffmpeg"), "-v", "error", "-i", str(path), "-ac", "1", "-ar", "4000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    rms = [float(np.sqrt(np.mean(x[i:i + 2000] ** 2)) if len(x[i:i + 2000]) else 0) for i in range(0, len(x), 2000)]
    info = {"stamp": stamp, "bpm": bpm, "beats": beats, "rms_half_sec": [round(r, 4) for r in rms],
            "duration": round(len(x) / 4000, 2)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    save_json(cache, info)
    return info


def best_start(info, length):
    """a beat to start on where the track is already full and energetic (skip quiet intros)."""
    rms = np.array(info["rms_half_sec"]) if info["rms_half_sec"] else np.zeros(1)
    n = max(1, int(length * 2))
    cands = [b for b in info["beats"] if 4 <= b <= max(4.5, info["duration"] * 0.6 - length)]
    if not cands:
        return info["beats"][0] if info["beats"] else 0.0
    score = lambda b: rms[int(b * 2):int(b * 2) + n].mean() if int(b * 2) < len(rms) else 0
    top = max(score(b) for b in cands)
    # earliest beat that's nearly as strong as the strongest stretch (keeps the build-up feel)
    return next(b for b in cands if score(b) >= 0.9 * top)


def cmd_music(args):
    tracks = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac"))
    for p in tracks:
        i = music_info(p)
        rms = np.array(i["rms_half_sec"])
        energy = float(np.percentile(rms, 75)) if len(rms) else 0
        print(f"  {i['bpm']:6.1f} bpm  energy {energy:.3f}  {i['duration']:6.1f}s  {p.name}")


# ---------- sheet import ----------

def read_xlsx(path):
    z = zipfile.ZipFile(path)
    tag = lambda t: rf"<(?:\w+:)?{t}[^>]*>(.*?)</(?:\w+:)?{t}>"
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in re.findall(tag("si"), z.read("xl/sharedStrings.xml").decode(), re.S):
            ss.append(html.unescape("".join(re.findall(tag("t"), si, re.S))))
    sheet = next(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
    rows = []
    for row in re.findall(tag("row"), z.read(sheet).decode(), re.S):
        cells = []
        for attrs, body in re.findall(r"<(?:\w+:)?c ([^>]*?)>(.*?)</(?:\w+:)?c>", row, re.S):
            v = re.search(tag("v"), body, re.S)
            val = html.unescape(v.group(1)) if v else html.unescape("".join(re.findall(tag("t"), body, re.S)))
            if re.search(r't="s"', attrs):
                val = ss[int(val)]
            cells.append(val.strip())
        rows.append(cells)
    head = [h.lower() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if any(r)]


def cmd_import(args):
    rows = read_xlsx(args.sheet)
    reels = []
    for r in rows:
        beats = [r.get(k, "") for k in head_keys(r)]
        reels.append({"id": int(float(r.get("#", len(reels) + 1))), "type": r.get("type", ""),
                      "beats": [b for b in beats if b], "broll_type": r.get("b-roll", ""),
                      "caption": r.get("caption", ""), "carousel": r.get("carousel it points to", ""),
                      "shots": [], "music": None, "music_start": None})
    wd = WORK_DIR / args.name
    wd.mkdir(parents=True, exist_ok=True)
    save_json(wd / "plan.json", {"brand": get_brand(args.brand).name, "reels": reels, "music_volume": 0.9})
    print(f"[engine] {len(reels)} reels imported to {(wd / 'plan.json').relative_to(ROOT)}")


def head_keys(r):
    return [k for k in r if k.startswith("beat")]


# ---------- render ----------

def beat_lengths(beats, bpm=None):
    """reading time per line: ~0.3s a word + a beat to take it in. snapped to the music."""
    out = []
    for i, text in enumerate(beats):
        words = len(text.split())
        d = min(max(0.3 * words + (1.2 if i == 0 else 1.0), 2.4 if i == 0 else 2.0), 3.8)
        if bpm:
            beat = 60 / bpm
            d = max(beat, round(d / beat) * beat)
        out.append(d)
    return out


def ass_text(text, st):
    """white bold text, numbers / money / SHOUTY words in the accent colour."""
    acc = st.get("keyword_colour", st["highlight_colour"]).lstrip("#")
    acc = f"&H00{acc[4:6]}{acc[2:4]}{acc[0:2]}&"
    out = []
    for w in text.split():
        bare = re.sub(r"[^\w£$%+,.]", "", w)
        hot = re.search(r"[£$]\d|\d", w) or (len(re.sub(r"[^A-Za-z]", "", w)) >= 3 and re.sub(r"[^A-Za-z]", "", w).isupper())
        w = w.replace("{", "(").replace("}", ")")
        out.append(f"{{\\c{acc}}}{w}{{\\c&H00FFFFFF&}}" if hot and bare else w)
    return " ".join(out)


def wrap(text):
    """balanced lines of at most ~LINE_CHARS (we place each line ourselves to control spacing)."""
    words = []
    for w in text.split():      # keep "£150 + £700" style pairs on one line
        if words and (w in ("+", "&", "vs") or words[-1].endswith((" +", " &", " vs"))):
            words[-1] += " " + w
        else:
            words.append(w)
    from functools import lru_cache
    n = max(1, -(-len(text) // LINE_CHARS))

    @lru_cache(None)
    def best(i, k):
        """split words[i:] into k lines, keeping the longest line as short as possible."""
        if k == 1:
            return (len(" ".join(words[i:])), (" ".join(words[i:]),))
        opts = []
        for j in range(i + 1, len(words) - k + 2):
            head = " ".join(words[i:j])
            worst, rest = best(j, k - 1)
            opts.append((max(len(head), worst), (head,) + rest))
        return min(opts) if opts else (len(" ".join(words[i:])), (" ".join(words[i:]),))

    while n < len(words) and best(0, n)[0] > LINE_CHARS:
        n += 1
    return list(best(0, min(n, len(words)))[1])


def write_ass(path, lines, st):
    sp = st.get("spacing", -2)
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: T,{st['font']},{TEXT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,{sp},0,1,0,3,5,110,110,0,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ts = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    gap = TEXT_SIZE * LINE_GAP
    cy = int(H * TEXT_Y)
    rows = max(len(wrap(t)) for _, _, t in lines)
    bh = int(rows * gap + 220)
    # soft dark band behind the text (no outline): keeps white text readable on bright shots
    band = (f"{{\\pos(0,{cy - bh // 2})\\an7\\p1\\c&H000000&\\alpha&HA8&\\blur40\\bord0\\shad0}}"
            f"m 0 0 l {W} 0 {W} {bh} 0 {bh}{{\\p0}}")
    ev = [f"Dialogue: 0,{ts(0)},{ts(lines[-1][1])},T,,0,0,0,,{band}"]
    for a, b, t in lines:
        parts = wrap(t)
        top = cy - (len(parts) - 1) * gap / 2          # block centred on the middle of the frame
        for k, part in enumerate(parts):
            ev.append(f"Dialogue: 1,{ts(a)},{ts(b)},T,,0,0,0,,"
                      f"{{\\an5\\pos({W // 2},{top + k * gap:.0f})\\fsp{sp}}}{ass_text(part, st)}")
    path.write_text("\n".join(head + ev) + "\n", encoding="utf-8")


def render_reel(reel, wd, out_dir, st, vol, draft):
    if len(reel["shots"]) < len(reel["beats"]):
        die(f"reel {reel['id']} needs {len(reel['beats'])} shots, has {len(reel['shots'])}")
    music = reel.get("music")
    info = music_info(ROOT / music) if music else None
    lens = beat_lengths(reel["beats"], info["bpm"] if info else None)
    total = sum(lens)
    edges = [0]
    for d in lens:
        edges.append(edges[-1] + d)
    frames = [round(edges[i + 1] * FPS) - round(edges[i] * FPS) for i in range(len(lens))]

    inputs, f = [], []
    for k, (shot, n) in enumerate(zip(reel["shots"], frames)):
        clip = ROOT / shot["file"]
        inputs += vin(clip, "-ss", f"{float(shot.get('start', 0)):.3f}", "-t", f"{n / FPS + 0.4:.3f}")
        z0 = 1.0 if k % 2 == 0 else 1.04
        # frames picked (30 fps) and counted (a short clip holds its last frame) before any picture work
        f.append(f"[{k}:v]fps={FPS},tpad=stop_mode=clone:stop_duration=4,trim=end_frame={n},"
                 f"{sdr_filter(clip)}scale={2 * W}:{2 * H}:force_original_aspect_ratio=increase,"
                 f"crop={2 * W}:{2 * H},setsar=1,"
                 f"zoompan=z='{z0}+0.06*on/{n}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS},"
                 f"setpts=PTS-STARTPTS,format=yuv420p[v{k}];")
    lines = [(edges[i], edges[i + 1], t) for i, t in enumerate(reel["beats"])]
    ass = wd / f"text_{reel['id']:02d}.ass"
    write_ass(ass, lines, st)
    f.append("".join(f"[v{k}]" for k in range(len(lens))) + f"concat=n={len(lens)}:v=1:a=0,"
             f"subtitles={ass.name}:fontsdir={FONTS_DIR}[vout];")
    if music:
        start = reel.get("music_start")
        if start is None:
            start = best_start(info, total)
        inputs += ["-ss", f"{start:.3f}", "-i", str(ROOT / music)]
        f.append(f"[{len(lens)}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.3f},"
                 f"asetpts=PTS-STARTPTS,volume={vol},afade=t=in:d=0.04,"
                 f"afade=t=out:st={max(0, total - 0.8):.3f}:d=0.8,loudnorm=I=-14:TP=-1.5:LRA=11,"
                 f"atrim=0:{total:.3f}[aout]")
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    else:
        f[-1] = f[-1].rstrip(";")
        amap = []
    script = f"filter_{reel['id']:02d}.txt"      # one per reel: three render at once
    (wd / script).write_text("\n".join(f), encoding="utf-8")
    out = out_dir / f"{wd.name}_{reel['id']:02d}{'_draft' if draft else ''}.mp4"
    run([find_bin("ffmpeg"), "-y", *inputs, "-/filter_complex", script, "-map", "[vout]", *amap,
         *h264(draft), "-r", str(FPS), "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)], cwd=wd)
    return out, total


def cmd_render(args):
    wd = WORK_DIR / args.name
    plan = load_json(wd / "plan.json")
    brand = get_brand(args.brand, plan)
    st = load_style(plan.get("style") or brand.name, brand)
    only = {int(x) for x in args.only.split(",")} if args.only else None
    out_dir = output_folder(brand.name, "trial", args.name)     # output/<brand>/trial/<date>_<time>_<set>/
    reels = [reel for reel in plan["reels"] if not only or reel["id"] in only]
    for music in sorted({reel["music"] for reel in reels if reel.get("music")}):
        music_info(ROOT / music)            # measured (and cached) once, before reels sharing it run at once
    print(f"[engine] rendering {len(reels)} reel(s), three at a time...")
    done = in_parallel(lambda reel: render_reel(reel, wd, out_dir, st, plan.get("music_volume", 0.9), args.draft),
                       reels)
    caps = []
    for reel, (out, total) in zip(reels, done):
        print(f"[engine] reel {reel['id']:2}: {total:4.1f}s  {out.relative_to(ROOT)}")
        caps.append(f"## {reel['id']}. {reel['beats'][0]}\n\n{reel['caption']}\n\n(carousel: {reel['carousel']})\n")
    if not only:
        (out_dir / "captions.md").write_text("\n".join(caps), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["music", "import", "render"])
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--only", default=None)
    ap.add_argument("--draft", action="store_true")
    add_brand_arg(ap)
    args = ap.parse_args()
    if args.action == "music":
        cmd_music(args)
    elif args.action == "import":
        if not (args.a and args.b):
            die("usage: python -m engine textreel import <sheet.xlsx> <name> --brand <brand>")
        args.sheet, args.name = args.a, args.b
        cmd_import(args)
    else:
        if not args.a:
            die("usage: python -m engine textreel render <name>")
        args.name = args.a
        cmd_render(args)


if __name__ == "__main__":
    main()
