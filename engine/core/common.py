"""shared helpers for the reels engine."""
import functools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from engine.core.paths import (ASSETS_DIR, BRANDS_DIR, ENV_FILE, FONTS_DIR, INPUT_DIR, INPUTS_DIR,  # noqa: F401
                               MUSIC_DIR, OUTPUT_DIR, REF_DIR, ROOT, SFX_DIR, SHOP_DIR, STYLES_DIR, TRIAL_DIR,
                               VLOG_DIR, WORK_DIR)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

FILLERS = {"um", "umm", "ummm", "uh", "uhh", "uhm", "er", "erm", "errm", "ah", "ahh",
           "hmm", "hm", "mm", "mmm", "eh"}


def die(msg):
    print(f"\n[engine] problem: {msg}\n", file=sys.stderr)
    sys.exit(1)


def find_bin(name):
    path = shutil.which(name)
    if not path:
        die(f"couldn't find '{name}'. run: python -m engine check_setup")
    return path


# ---------- hardware video (the mac's media engine) ----------
HW = sys.platform == "darwin"
FINAL_BITRATE = "10M"      # finished videos: h.264 at 10 Mbps, what instagram/tiktok like best
DRAFT_BITRATE = "4M"       # drafts, cut/spot previews


def vin(path, *pre):
    """input args for one file. video files are decoded on the media engine (videotoolbox).
    `pre` = input options like -ss/-t/-loop that go before -i."""
    hw = ["-hwaccel", "videotoolbox"] if HW and Path(path).suffix.lower() in VIDEO_EXTS else []
    return [*hw, *pre, "-i", str(path)]


def h264(draft=False, rate=None):
    """video encoder args for anything that gets watched or uploaded: h.264 high, 8-bit 4:2:0, bt709,
    hardware encoded at a set bitrate. add -r and the audio/mp4 flags yourself."""
    rate = rate or (DRAFT_BITRATE if draft else FINAL_BITRATE)
    mbps = float(rate.rstrip("Mm"))
    colour = ["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    if HW:
        return ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-b:v", rate,
                "-maxrate", f"{mbps * 1.2:g}M", "-bufsize", f"{mbps * 2:g}M",
                "-prio_speed", "1" if draft else "0", "-tag:v", "avc1", *colour]
    return ["-c:v", "libx264", "-preset", "veryfast" if draft else "medium", "-b:v", rate,
            "-maxrate", f"{mbps * 1.2:g}M", "-bufsize", f"{mbps * 2:g}M", *colour]


def hevc(rate, software=False):
    """video encoder args for the size-capped tiktok shop upload (see encode_under): h.265 main, 8-bit
    4:2:0, bt709, tagged hvc1 so tiktok and apple players read it. the media engine on a mac; libx265 when
    software=True or off a mac. add -r and the audio/mp4 flags yourself."""
    colour = ["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    if HW and not software:
        return ["-c:v", "hevc_videotoolbox", "-profile:v", "main", "-b:v", rate, "-prio_speed", "0",
                "-tag:v", "hvc1", *colour]
    return ["-c:v", "libx265", "-preset", "medium", "-b:v", rate, "-tag:v", "hvc1", *colour]


# ---------- size-capped upload (tiktok shop, --max-mb) ----------
SMALL_AUDIO_BPS = 128_000  # aac for the capped file: plenty for a voice + music
SIZE_AIM = 0.95            # aim this far under the cap: the mp4 wrapper and encoder overshoot need room
SMALL_MIN_BPS = 150_000    # below this the picture falls apart: too long to fit, say so instead
HW_TRIES, SOFT_TRIES = 3, 3


def small_rate(limit_bytes, secs, aim=SIZE_AIM):
    """video bits a second that fill `aim` of the cap once the sound is in. never above the normal finals' rate."""
    rate = limit_bytes * 8 * aim / max(secs, 0.1) - SMALL_AUDIO_BPS
    return int(min(rate, float(FINAL_BITRATE.rstrip("Mm")) * 1_000_000))


def encode_under(master, out, max_mb, fps, cwd):
    """re-encode a finished video as h.265 that is guaranteed to be at most max_mb (1 MB = 1,000,000 bytes,
    the strictest reading). media engine first (fast); every try that lands over the cap is redone at a
    proportionally lower rate, and if the media engine can't get under, two-pass x265 takes over (it hits a
    size much more exactly). a file over the cap is never left behind. returns (size in bytes, tries)."""
    limit = int(max_mb * 1_000_000)
    secs = float(probe(master)["format"]["duration"])
    full_rate = small_rate(limit, secs)
    if full_rate < SMALL_MIN_BPS:
        die(f"{secs:.0f}s won't fit in {max_mb:g}MB and still look ok. cut it shorter or raise --max-mb")
    head = [find_bin("ffmpeg"), "-y", *vin(master), "-map", "0:v:0"]
    audio = ["-map", "0:a:0?", "-c:a", "aac", "-b:a", str(SMALL_AUDIO_BPS), "-ar", "48000"]
    attempts = ([False] * HW_TRIES if HW else []) + [True] * SOFT_TRIES
    rate = full_rate
    try:
        for tries, software in enumerate(attempts, 1):
            if software and (tries == 1 or not attempts[tries - 2]):
                rate = full_rate            # x265 hits its target closely: start again from the full budget
            if rate < SMALL_MIN_BPS:
                break
            video = hevc(str(rate), software)
            if software:    # two passes: the first only measures, so the second spends the bits where they count
                run(head + [*video, "-x265-params", "pass=1:stats=x265_stats.log:log-level=error",
                            "-r", str(fps), "-an", "-f", "null", "-"], cwd=cwd)
                video += ["-x265-params", "pass=2:stats=x265_stats.log:log-level=error"]
            run(head + [*video, "-r", str(fps), *audio, "-movflags", "+faststart", str(out)], cwd=cwd)
            size = Path(out).stat().st_size
            if size <= limit:
                return size, tries
            print(f"[engine] {size / 1e6:.3f}MB is over {max_mb:g}MB, encoding again a bit lower", file=sys.stderr)
            rate = int(rate * limit * SIZE_AIM / size)
    finally:
        for leftover in Path(cwd).glob("x265_stats.log*"):
            leftover.unlink()
    if Path(out).exists():
        Path(out).unlink()
    die(f"couldn't get this under {max_mb:g}MB without it falling apart. cut it shorter or raise --max-mb")


# ---------- jobs at once ----------
JOBS = 3                   # ffmpeg runs at a time for sets: more just fight over the performance cores


def in_parallel(fn, items, jobs=JOBS):
    """fn(item) for every item, `jobs` at a time (each one runs its own ffmpeg). results in item order.
    a failure (die) stops the lot once the running jobs finish."""
    items = list(items)
    if jobs <= 1 or len(items) <= 1:
        return [fn(item) for item in items]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(jobs, len(items))) as pool:
        return list(pool.map(fn, items))


def _strip_hwaccel(cmd):
    out, skip = [], False
    for c in cmd:
        if skip:
            skip = False
        elif c == "-hwaccel":
            skip = True
        else:
            out.append(c)
    return out


def run(cmd, cwd=None, quiet=True):
    """run a command, raising a readable error if it fails. if hardware decoding was the problem
    (an odd clip the media engine won't read), it retries once with normal decoding."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0 and "-hwaccel" in cmd:
        print("[engine] note: hardware decoding failed on a clip, retrying without it", file=sys.stderr)
        cmd = _strip_hwaccel(cmd)
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-25:])
        die(f"command failed: {' '.join(str(c) for c in cmd[:6])} ...\n{tail}")
    if not quiet:
        print(res.stdout)
    return res


def probe(path):
    res = run([find_bin("ffprobe"), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", str(path)])
    return json.loads(res.stdout)


@functools.lru_cache(maxsize=None)
def sdr_filter(path):
    """filter prefix that turns phone hdr video into normal video ("" for normal clips).
    iphone hlg keeps its brightness and only has its wide hdr colours mapped into normal range,
    which looks most like the phone. done in float so skin tones don't band."""
    v = next((s for s in probe(path)["streams"] if s["codec_type"] == "video"), {})
    trc = v.get("color_transfer", "")
    to_float = "zscale=m=bt709:min=bt2020nc:r=pc,format=gbrpf32le,"
    to_sdr = "zscale=pin=bt2020:p=bt709,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
    if trc == "arib-std-b67":
        return to_float + "zscale=tin=bt709:t=linear," + to_sdr
    if trc == "smpte2084":
        return to_float + "zscale=tin=smpte2084:t=linear:npl=100,tonemap=hable," + to_sdr
    return ""


def video_info(path):
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        die(f"{path} has no video stream")
    w, h = int(v["width"]), int(v["height"])
    # phones often store portrait video as landscape + a rotation flag
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "tags" in v and "rotate" in v["tags"]:
        rot = int(v["tags"]["rotate"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return {
        "width": w,
        "height": h,
        "duration": float(info["format"].get("duration", 0)),
        "has_audio": a is not None,
    }


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")


def input_subfolders(path):
    """the subfolders between inputs/<type>/ and path, eg ["mia"] for inputs/talking-head/mia/clip.mov.
    empty when path sits straight in inputs/<type>/ or outside inputs/ altogether."""
    try:
        rel = Path(path).resolve().relative_to(INPUTS_DIR.resolve())
    except ValueError:
        return []
    return list(rel.parts[1:-1])


def job_dir(name, legacy_name, owns):
    """work/<name>/, created if needed. jobs started before subfolders were part of the name live
    in work/<legacy_name>/: that one is reused when owns(folder) says it belongs to this input."""
    d = WORK_DIR / (safe_name(name) or "clip")
    legacy = WORK_DIR / (safe_name(legacy_name) or "clip")
    if d != legacy and not d.exists() and legacy.is_dir() and owns(legacy):
        return legacy
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_dir_for(video_path):
    """work/<clip>/ for a video. clips in a subfolder of an input folder (eg one per brand) get the
    subfolder in the name, work/<subfolder>-<clip>/, so two clips with the same name never share one."""
    path = Path(video_path)

    def owns(folder):
        tr = folder / "transcript.json"
        return tr.exists() and load_json(tr).get("source") == str(path.resolve())

    return job_dir("-".join(input_subfolders(path) + [path.stem]), path.stem, owns)


# ---------- output folders ----------
# every render gets its own folder: output/<brand>/<type>/<date>_<time>_<job>/, so a re-render never
# overwrites the last one and each brand's videos stay together.
OUTPUT_TYPES = ("talking-head", "shop", "vlog", "trial", "previews", "grade")


def content_type(source):
    """what kind of job a source clip or folder is, from where it sits: the inputs/ folder it's in
    (talking-head, shop, vlog, trial), or shop for parts cut from a batch take in work/<video>/.
    anything else (a clip passed by path from elsewhere) counts as talking-head."""
    path = Path(source).resolve()
    for base, pick in ((INPUTS_DIR, lambda parts: parts[0]),
                       (WORK_DIR, lambda parts: "shop" if len(parts) > 2 and parts[1] in ("parts", "videos") else None)):
        try:
            parts = path.relative_to(Path(base).resolve()).parts
        except ValueError:
            continue
        kind = pick(parts) if parts else None
        if kind in OUTPUT_TYPES:
            return kind
    return "talking-head"


def output_folder(brand_name, kind, job):
    """a new output/<brand>/<type>/<YYYY-MM-DD_HHMM>_<job>/ folder (-2, -3... if that minute is taken)."""
    from datetime import datetime
    base = OUTPUT_DIR / brand_name / kind
    name = f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_{safe_name(job) or 'job'}"
    folder, n = base / name, 2
    while folder.exists():
        folder, n = base / f"{name}-{n}", n + 1
    folder.mkdir(parents=True)
    return folder


def date_added(p):
    """when the file landed in its folder (finder's "date added"), not when it was filmed.
    falls back to the file's change time off a mac."""
    from datetime import datetime
    try:
        out = subprocess.run(["mdls", "-raw", "-name", "kMDItemDateAdded", str(p)],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if out and out != "(null)":
            return datetime.strptime(out[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        pass
    return Path(p).stat().st_ctime


def latest_input():
    clips = [p for p in INPUT_DIR.iterdir() if p.suffix.lower() in VIDEO_EXTS]
    if not clips:
        die("no video found in the inputs/talking-head/ folder. drop a clip in there first.")
    return max(clips, key=date_added)


def resolve_video(arg):
    if not arg:
        return latest_input()
    p = Path(arg)
    if not p.exists():
        p = INPUT_DIR / arg
    if not p.exists():
        die(f"can't find the video '{arg}'")
    return p.resolve()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def norm(word):
    return re.sub(r"[^\w%£$€']+", "", word.lower())
