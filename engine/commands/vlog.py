"""b-roll / vlog edits: a folder of clips -> a ~30s edit with a quick-fire teaser, best bits of
each clip, transitions, natural sound kept, cut to the beat of a music track if there is one.

usage:
  python -m engine vlog analyse inputs/vlog/<folder>                    measure every clip + frame sheets
  python -m engine vlog plan inputs/vlog/<folder> [--music assets/music/x.mp3] [--length 30]
  python -m engine vlog render inputs/vlog/<folder> [--draft] [--no-grade]

analyse writes work/vlog-<folder>/clips.json and sheets/ (8 frames per clip, so claude can see
them). plan picks the best 1-3s of each clip and lays out teaser + shots in plan.json, which
claude then edits by eye (order, which moment, transitions). render builds the video.
"""
import argparse
import re
import subprocess
from pathlib import Path

import numpy as np

from engine.core.brand import add_brand_arg, get_brand
from engine.core.common import (h264, vin, ROOT, SFX_DIR, VIDEO_EXTS, die, find_bin, input_subfolders, job_dir,
                                load_json, output_folder, probe, run, save_json, sdr_filter)
from engine.core.grade import grade_filter, has_huesaturation, load_grade

W, H, FPS = 1080, 1920, 30
MEASURE_FPS = 5


# ---------- analyse ----------

def clips_in(folder):
    clips = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if not clips:
        die(f"no video clips in {folder}")
    return clips


def measure(clip):
    """per-frame sharpness, brightness and movement at 5 frames a second."""
    res = run([find_bin("ffmpeg"), "-v", "error", *vin(clip), "-an", "-vf",
               f"fps={MEASURE_FPS},scale=360:-2,signalstats,blurdetect,metadata=mode=print:file=-",
               "-f", "null", "-"])
    frames, cur = [], None
    for line in res.stdout.splitlines():
        m = re.match(r"frame:\d+\s+pts:\d+\s+pts_time:([\d.]+)", line)
        if m:
            cur = {"t": float(m.group(1))}
            frames.append(cur)
        elif cur is not None and "=" in line:
            k, v = line.split("=", 1)
            if k.endswith(("YAVG", "YDIF")) or k == "lavfi.blur":
                cur[k.split(".")[-1].lower()] = float(v)
    return frames


def frame_score(f):
    sharp = min(max((8.0 - f.get("blur", 8.0)) / 6.0, 0.0), 1.0)
    y = f.get("yavg", 128)
    expo = 1.0 if 45 <= y <= 205 else max(0.0, 1 - min(abs(y - 45), abs(y - 205)) / 40)
    d = f.get("ydif", 0)
    move = min(d / 4.0, 1.0) * (1.0 if d < 15 else max(0.0, 1 - (d - 15) / 15))   # too much = shaky
    return 0.45 * sharp + 0.25 * expo + 0.30 * move


def best_windows(frames, dur, length=2.5, count=1):
    """the strongest stretches of a clip (sharp, well lit, something happening, not shaky)."""
    if not frames:
        return []
    t = np.array([f["t"] for f in frames])
    s = np.array([frame_score(f) for f in frames])
    length = min(length, max(0.5, dur - 0.4))
    picks = []
    for _ in range(count):
        best = None
        for a in np.arange(0.2, max(0.21, dur - length - 0.2), 0.2):
            if any(a < p["start"] + p["length"] and p["start"] < a + length for p in picks):
                continue
            sel = s[(t >= a) & (t < a + length)]
            if len(sel) and (best is None or sel.mean() > best[1]):
                best = (float(a), float(sel.mean()))
        if not best:
            break
        a = best[0]
        inside = [(sc, tt) for sc, tt in zip(s, t) if a <= tt < a + length]
        peak = max(inside)[1] if inside else a
        picks.append({"start": round(a, 2), "length": round(length, 2), "score": round(best[1], 3),
                      "peak": round(float(peak), 2)})
    return picks


def contact_sheet(clip, dur, out):
    n = 8
    ts = [dur * (k + 0.5) / n for k in range(n)]
    ins = []
    for t in ts:
        ins += vin(clip, "-ss", f"{t:.2f}")
    sdr = sdr_filter(clip)
    fc = "".join(f"[{k}:v]{sdr}scale=-2:300,trim=end_frame=1,drawtext=text='{ts[k]:.1f}s':x=6:y=6:"
                 f"fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.6[f{k}];" for k in range(n))
    fc += "".join(f"[f{k}]" for k in range(n)) + f"hstack=inputs={n}[o]"
    run([find_bin("ffmpeg"), "-y", *ins, "-filter_complex", fc, "-map", "[o]", "-frames:v", "1",
         "-q:v", "4", str(out)])


def cmd_analyse(folder, wd, args):
    (wd / "sheets").mkdir(parents=True, exist_ok=True)
    out = []
    for clip in clips_in(folder):
        info = probe(clip)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        dur = float(info["format"].get("duration", 0))
        frames = measure(clip)
        wins = best_windows(frames, dur, count=max(1, min(4, int(dur // 4))))
        sheet = wd / "sheets" / f"{clip.stem}.jpg"
        contact_sheet(clip, dur, sheet)
        out.append({"file": str(clip.relative_to(ROOT)), "duration": round(dur, 2),
                    "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
                    "created": (info["format"].get("tags") or {}).get("creation_time", ""),
                    "hdr": v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
                    "windows": wins, "sheet": str(sheet.relative_to(ROOT)), "description": ""})
        w = wins[0] if wins else {}
        print(f"  {clip.name:40} {dur:5.1f}s  best {w.get('start', 0):5.1f}s  score {w.get('score', 0):.2f}")
    save_json(wd / "clips.json", {"folder": str(Path(folder)), "clips": out})
    print(f"\n[engine] {len(out)} clips measured. frame sheets in {(wd / 'sheets').relative_to(ROOT)}/")


# ---------- music ----------

def detect_beats(path):
    """tempo + beat times from the music's energy (spectral flux + autocorrelation)."""
    sr, hop, n = 22050, 512, 2048
    raw = subprocess.run([find_bin("ffmpeg"), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < n * 4:
        die("music track is too short")
    count = 1 + (len(x) - n) // hop
    win = np.hanning(n).astype(np.float32)
    env = np.zeros(count, np.float32)
    prev = None
    for k in range(count):     # frame by frame keeps memory small for long tracks
        mag = np.log1p(10 * np.abs(np.fft.rfft(x[k * hop:k * hop + n] * win)))
        if prev is not None:
            env[k] = np.maximum(0, mag - prev).sum()
        prev = mag
    rate = sr / hop
    smooth = np.convolve(env, np.ones(int(rate * 0.5)) / int(rate * 0.5), "same")
    env = np.maximum(0, env - smooth)
    env /= env.max() or 1
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    lags = np.arange(int(rate * 60 / 180), int(rate * 60 / 70) + 1)
    bpms = 60 * rate / lags
    weight = np.exp(-0.5 * (np.log2(bpms / 120) / 0.9) ** 2)    # favour sensible tempos
    k = int(np.argmax(ac[lags] * weight))
    lag = float(lags[k])
    if 0 < k < len(lags) - 1:
        y0, y1, y2 = ac[lags[k - 1]], ac[lags[k]], ac[lags[k + 1]]
        den = y0 - 2 * y1 + y2
        lag += 0.5 * (y0 - y2) / den if den else 0
    phases = np.arange(0, lag, 0.5)
    pos = lambda ph: np.arange(ph, len(env) - 1, lag)
    phase = max(phases, key=lambda ph: np.interp(pos(ph), np.arange(len(env)), env).sum())
    lagfix = (n - hop / 2) / sr      # a frame "hears" an onset once it enters its window
    beats = [round(float(b / rate + lagfix), 3) for b in pos(phase)]
    return round(60 * rate / lag, 1), beats


# ---------- plan ----------

def cmd_plan(folder, wd, args):
    cp = wd / "clips.json"
    if not cp.exists():
        die("run 'python -m engine vlog analyse' first")
    clips = load_json(cp)["clips"]
    cands = [{"clip": c["file"], "dur": c["duration"], **w} for c in clips for w in c["windows"]]
    if not cands:
        die("couldn't find usable moments in these clips")
    target = args.length

    music, bpm, beats = None, None, []
    if args.music:
        music = str(Path(args.music))
        bpm, beats = detect_beats(ROOT / music if not Path(music).is_absolute() else music)
        print(f"[engine] music: {bpm} bpm, first beat at {beats[0]:.2f}s")
    beat = 60 / bpm if bpm else None

    # rhythm: teaser snaps of ~0.3s, then shots of 2-4 beats (or 1.6-2.4s without music)
    if beat:
        unit = beat if beat <= 0.45 else beat / 2
        mult = 2 if beat < 0.4 else 1
        pattern = [b * beat * mult for b in (4, 2, 2, 4, 4, 2, 2, 4)]
    else:
        unit = 4 / FPS          # 4-frame snaps
        pattern = [2.4, 1.6, 1.6, 2.4, 2.0, 1.6, 1.8, 2.4]
    n_teaser = int(min(16, max(6, round(2.1 / unit))))

    # main shots: strongest moments, one per clip first, then second windows from long clips
    first = sorted([c for c in cands if c is max((x for x in cands if x["clip"] == c["clip"]),
                                                    key=lambda x: x["score"])], key=lambda c: -c["score"])
    extra = sorted([c for c in cands if c not in first], key=lambda c: -c["score"])
    pool = first + extra
    shots, total, k = [], n_teaser * unit, 0
    while total < target - 0.5 and k < len(pool):
        d = pattern[len(shots) % len(pattern)]
        shots.append({**pool[k], "out": d})
        total += d
        k += 1
    # not enough footage for the target length: let the shots run longer (still on the beat)
    main_len = sum(s["out"] for s in shots)
    room = target - n_teaser * unit
    if shots and main_len < room - 0.5:
        step = beat if beat else 0.1
        for s in shots:
            s["out"] = max(step, round(s["out"] * room / main_len / step) * step)
    # engaging order: open on the best, close on the second best, alternate energy in between
    if len(shots) > 2:
        mid = shots[2:]
        mid = mid[::2] + mid[1::2][::-1]
        shots = [shots[0]] + mid + [shots[1]]
    for i in range(1, len(shots)):      # never the same clip twice in a row
        if shots[i]["clip"] == shots[i - 1]["clip"]:
            j = next((j for j in range(i + 1, len(shots)) if shots[j]["clip"] != shots[i - 1]["clip"]
                      and (j + 1 >= len(shots) or shots[j + 1]["clip"] != shots[i]["clip"])), None)
            if j:
                shots[i], shots[j] = shots[j], shots[i]

    def piece(c, out, kind, speed=1.0, transition="cut", push=False, at=None):
        need = out * speed
        start = at if at is not None else c["start"] + (c["length"] - need) / 2
        if need > c["dur"] - 0.1:            # clip too short: slow it down a touch
            speed = max(0.5, (c["dur"] - 0.2) / out)
            need = out * speed
        start = round(min(max(0.0, start), max(0.0, c["dur"] - need - 0.05)), 2)
        return {"kind": kind, "clip": c["clip"], "start": start, "dur": round(out, 3), "speed": round(speed, 2),
                "ramp": False, "transition": transition, "push": push, "freeze": 0, "nat": True, "note": ""}

    teaser_src = [shots[(i * 7) % len(shots)] for i in range(min(n_teaser, len(shots)))]
    while len(teaser_src) < n_teaser:
        teaser_src.append(shots[len(teaser_src) % len(shots)])
    teaser = [piece(s, unit, "teaser", at=s["peak"] - unit / 2) for s in teaser_src]
    main = []
    for i, s in enumerate(shots):
        # default: no transitions. alternate slow zooms with jump cuts (same clip, skip, tighter frame)
        if i % 2 and s["out"] >= 1.6 and s["dur"] >= s["out"] + 0.3:
            half = round(s["out"] / 2, 2)
            a = piece(s, half, "shot")
            b = piece(s, half, "shot", at=a["start"] + half + 0.25)
            a["zoom"], b["zoom"] = (1.0, 1.15) if i % 4 == 1 else (1.15, 1.0)
            main += [a, b]
        else:
            main.append(piece(s, s["out"], "shot", push=True))
    # no speed ramps by default (footage stays at real speed). set "ramp" by hand if asked

    plan = {"brand": get_brand(args.brand).name, "folder": str(Path(folder)), "music": music, "music_start": beats[0] if beats else 0,
            "bpm": bpm, "music_volume": 0.8, "nat_volume": 0.5 if music else 1.0, "teaser_nat": not music,
            "pieces": teaser + main}
    save_json(wd / "plan.json", plan)
    write_table(plan, wd)
    storyboard(plan, wd)
    print((wd / "plan.md").read_text())
    print(f"[engine] storyboard: {(wd / 'storyboard.jpg').relative_to(ROOT)}")


def write_table(plan, wd):
    rows = ["| # | part | clip | from | length | speed | transition | note |", "|---|---|---|---|---|---|---|---|"]
    t = 0.0
    for i, p in enumerate(plan["pieces"], 1):
        sp = "ramp" if p["ramp"] else (f"{p['speed']}x" if p["speed"] != 1 else "")
        rows.append(f"| {i} | {p['kind']} | {Path(p['clip']).name} | {p['start']}s | {p['dur']:.2f}s | {sp} | "
                    f"{p['transition'] if p['transition'] != 'cut' else ''}{' +push' if p['push'] else ''}"
                    f"{' +freeze' if p['freeze'] else ''}{' tight' if p.get('zoom', 1) > 1 else ''} | {p['note']} |")
        t += p["dur"]
    head = (f"# b-roll edit - {Path(plan['folder']).name}\n\n"
            f"length **{t:.1f}s**, {sum(p['kind'] == 'teaser' for p in plan['pieces'])} teaser snaps, "
            f"{sum(p['kind'] == 'shot' for p in plan['pieces'])} shots, "
            f"music: {Path(plan['music']).name + ' (' + str(plan['bpm']) + ' bpm)' if plan['music'] else 'none'}\n")
    (wd / "plan.md").write_text(head + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def storyboard(plan, wd):
    """one frame per piece, in order, so the edit can be checked at a glance."""
    pieces = plan["pieces"]
    ins, fc = [], ""
    for k, p in enumerate(pieces):
        mid = p["start"] + p["dur"] * p["speed"] / 2
        clip = ROOT / p["clip"]
        ins += vin(clip, "-ss", f"{mid:.2f}")
        fc += (f"[{k}:v]{sdr_filter(clip)}scale=180:320:force_original_aspect_ratio=increase,crop=180:320,"
               f"format=yuv420p,trim=end_frame=1,drawtext=text='{k + 1}':x=6:y=6:fontsize=24:fontcolor=yellow:box=1:"
               f"boxcolor=black@0.6[f{k}];")
    per_row = 8
    rows = [list(range(r, min(r + per_row, len(pieces)))) for r in range(0, len(pieces), per_row)]
    for r, idx in enumerate(rows):
        tiles = "".join(f"[f{k}]" for k in idx)
        for j in range(per_row - len(idx)):      # pad short rows with black tiles
            fc += f"color=c=black:s=180x320:d=1,format=yuv420p,trim=end_frame=1[p{r}_{j}];"
            tiles += f"[p{r}_{j}]"
        fc += f"{tiles}hstack=inputs={per_row}[r{r}];"
    fc += "".join(f"[r{r}]" for r in range(len(rows))) + (f"vstack=inputs={len(rows)}[o]" if len(rows) > 1 else "null[o]")
    run([find_bin("ffmpeg"), "-y", *ins, "-filter_complex", fc, "-map", "[o]", "-frames:v", "1",
         "-q:v", "4", str(wd / "storyboard.jpg")])


# ---------- render ----------

def video_chain(k, p, frames, grade):
    """one piece: speed, 9:16 framing (+ optional slow push), grade, transition looks."""
    clip = ROOT / p["clip"]
    push = p["push"]
    z = float(p.get("zoom", 1.0))      # static framing: 1.15 = tighter (jump cut look)
    if push:   # slow zoom in, starting from the shot's framing
        fit = (f"scale={2 * W}:{2 * H}:force_original_aspect_ratio=increase,crop={2 * W}:{2 * H},setsar=1,fps={FPS},"
               f"zoompan=z='{z}+0.07*on/{frames}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS}")
    else:
        zw, zh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
        fit = f"scale={zw}:{zh}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    freeze = int(round(p.get("freeze", 0) * FPS))
    moving = max(1, frames - freeze)
    if p["ramp"]:      # fast into the moment, then slow on it
        a = max(1, int(moving * 0.4))
        b = moving - a
        src_a, src_b = a / FPS * 2.5, b / FPS * 0.5
        chain = (f"[{k}:v]{sdr_filter(clip)}split[ra{k}][rb{k}];"
                 f"[ra{k}]trim=0:{src_a:.3f},setpts=(PTS-STARTPTS)/2.5,{fit},trim=end_frame={a}[rA{k}];"
                 f"[rb{k}]trim={src_a:.3f}:{src_a + src_b:.3f},setpts=(PTS-STARTPTS)/0.5,{fit},trim=end_frame={b}[rB{k}];"
                 f"[rA{k}][rB{k}]concat=n=2:v=1:a=0,setpts=PTS-STARTPTS")
    else:
        chain = (f"[{k}:v]{sdr_filter(clip)}setpts=(PTS-STARTPTS)/{p['speed']},{fit},"
                 f"trim=end_frame={moving},setpts=PTS-STARTPTS")
    if freeze:
        chain += f",tpad=stop_mode=clone:stop={freeze}"
    if grade:
        chain += "," + grade
    tr = p["transition"]
    if tr == "flash":
        chain += ",fade=t=in:st=0:d=0.15:color=white"
    elif tr == "dip":
        chain += ",fade=t=in:st=0:d=0.25"
    elif tr == "whip":
        chain += ",gblur=sigma=40:sigmaV=1:enable='lt(t,0.1)'"
    return chain + f",trim=end_frame={frames},setpts=PTS-STARTPTS,format=yuv420p"


def source_span(p):
    if p["ramp"]:
        moving = p["dur"] - p.get("freeze", 0)
        return moving * 0.4 * 2.5 + moving * 0.6 * 0.5
    return (p["dur"] - p.get("freeze", 0)) * p["speed"]


def cmd_render(folder, wd, args):
    plan = load_json(wd / "plan.json")
    pieces = plan["pieces"]
    brand = get_brand(args.brand, plan)
    grade = "" if args.no_grade else grade_filter(load_grade(brand), has_huesaturation())
    music = plan.get("music")
    nat_vol = plan.get("nat_volume", 1.0)

    # frame-exact cut points so the edit stays locked to the beat
    edges, t = [0], 0.0
    for p in pieces:
        t += p["dur"]
        edges.append(int(round(t * FPS)))
    total = edges[-1] / FPS

    inputs, f, vl, al = [], [], [], []
    for k, p in enumerate(pieces):
        frames = edges[k + 1] - edges[k]
        span = source_span(p) + 0.3
        inputs += vin(ROOT / p["clip"], "-ss", f"{p['start']:.3f}", "-t", f"{span:.3f}")
        vc = video_chain(k, p, frames, grade)
        # whip: blur the end of the shot before too, so the cut reads as one fast swipe
        if k + 1 < len(pieces) and pieces[k + 1]["transition"] == "whip":
            vc += f",gblur=sigma=40:sigmaV=1:enable='gt(t,{frames / FPS - 0.1:.3f})'"
        f.append(vc + f"[v{k}];")
        vl.append(f"[v{k}]")
        d = frames / FPS
        has_a = any(s["codec_type"] == "audio" for s in probe(ROOT / p["clip"])["streams"])
        keep = p.get("nat", True) and has_a and (p["kind"] != "teaser" or plan.get("teaser_nat", False))
        if keep and not p["ramp"] and 0.5 <= p["speed"] <= 2.0:
            tempo = f"atempo={p['speed']}," if p["speed"] != 1 else ""
            f.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,{tempo}"
                     f"atrim=0:{d:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={d:.3f},"
                     f"afade=t=in:d=0.03,afade=t=out:st={max(0, d - 0.05):.3f}:d=0.05[a{k}];")
        else:
            f.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.3f}[a{k}];")
        al.append(f"[a{k}]")
    f.append("".join(v + a for v, a in zip(vl, al)) + f"concat=n={len(pieces)}:v=1:a=1[vout][nat];")

    # whoosh on whips, quietly
    sfx, n_in = [], len(pieces)
    whoosh = SFX_DIR / "whoosh.wav"
    for k, p in enumerate(pieces):
        if p["transition"] == "whip" and whoosh.exists():
            inputs += ["-i", str(whoosh)]
            ms = max(0, int(edges[k] / FPS * 1000) - 120)
            f.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.35,"
                     f"adelay={ms}|{ms}[fx{len(sfx)}];")
            sfx.append(f"[fx{len(sfx)}]")
            n_in += 1

    outs = []
    # this render's own folder: output/<brand>/vlog/<date>_<time>_<folder>/
    base = output_folder(brand.name, "vlog", wd.name.removeprefix("vlog-")) / f"{wd.name}{'_draft' if args.draft else ''}"
    f.append(f"[nat]volume={nat_vol}[natv];")
    if music:
        inputs += ["-ss", f"{plan.get('music_start', 0):.3f}", "-i", str(ROOT / music)]
        f.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.3f},"
                 f"asetpts=PTS-STARTPTS,volume={plan.get('music_volume', 0.8)},"
                 f"afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus];")
        f.append("[natv]asplit=2[nat1][nat2];")
        mix_in = "[nat1][mus]" + "".join(sfx)
        f.append(f"{mix_in}amix=inputs={2 + len(sfx)}:duration=first:normalize=0,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aout];")
        f.append(f"[nat2]loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aclean];")
        f.append("[vout]split=2[vo1][vo2];")
        outs = [(base.with_name(base.name + ".mp4"), "[vo1]", "[aout]"),
                (base.with_name(base.name + "_no_music.mp4"), "[vo2]", "[aclean]")]
    else:
        mix_in = "[natv]" + "".join(sfx)
        f.append(f"{mix_in}amix=inputs={1 + len(sfx)}:duration=first:normalize=0,"
                 f"loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aout];")
        outs = [(base.with_name(base.name + ".mp4"), "[vout]", "[aout]")]

    script = wd / "filter.txt"
    script.write_text("\n".join(f).rstrip(";\n"), encoding="utf-8")
    cmd = [find_bin("ffmpeg"), "-y", *inputs, "-/filter_complex", str(script)]
    for path, v, a in outs:
        cmd += ["-map", v, "-map", a, *h264(args.draft), "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(path)]
    print(f"[engine] rendering {len(pieces)} pieces, {total:.1f}s{', with music' if music else ''}...")
    run(cmd)
    for path, _, _ in outs:
        print(f"[engine] rendered {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["analyse", "plan", "render", "table"])
    ap.add_argument("folder")
    ap.add_argument("--music", default=None)
    ap.add_argument("--length", type=float, default=30)
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--no-grade", action="store_true")
    add_brand_arg(ap)
    args = ap.parse_args()
    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = (ROOT / folder) if (ROOT / folder).exists() else folder
    if not folder.is_dir():
        die(f"can't find the folder '{args.folder}'")
    def owns(work):
        clips = work / "clips.json"
        return clips.exists() and Path(load_json(clips).get("folder", "")).resolve() == folder.resolve()

    # subfolders are part of the name (inputs/vlog/mia/trip -> work/vlog-mia-trip) so brands never share one
    wd = job_dir("vlog-" + "-".join(input_subfolders(folder) + [folder.name]), "vlog-" + folder.name, owns)
    if args.action == "table":       # reprint after hand edits to plan.json
        plan = load_json(wd / "plan.json")
        write_table(plan, wd)
        storyboard(plan, wd)
        print((wd / "plan.md").read_text())
        return
    {"analyse": cmd_analyse, "plan": cmd_plan, "render": cmd_render}[args.action](folder, wd, args)


if __name__ == "__main__":
    main()
