"""measurements of a source file the edit is built around: built-in scene cuts and quiet stretches.
both are cached per file (by identity, size and change time), so a reel's cut preview, spot previews and
final render, and every b-roll clip after it's indexed, only ever scan once."""
import re
from pathlib import Path

from engine.core import common
from engine.core.common import find_bin, load_json, run, save_json, vin

SCENE_DETECT = "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time"
SILENCE_DETECT = "silencedetect=noise=-35dB:d=0.08"


def _cached(video, folder, recipe, measure):
    """measure(video), or the saved answer from the last time this exact file was measured with this recipe."""
    stat = Path(video).stat()
    cache = common.WORK_DIR / folder / f"{stat.st_ino}.json"     # by file identity, so linked copies share it
    stamp = f"{stat.st_size}-{int(stat.st_mtime)}"
    if cache.exists():
        cached = load_json(cache)
        if cached.get("stamp") == stamp and cached.get("recipe", recipe) == recipe:
            return cached["result"] if "result" in cached else cached["cuts"]
    result = measure(video)
    cache.parent.mkdir(parents=True, exist_ok=True)
    save_json(cache, {"stamp": stamp, "recipe": recipe, "result": result})
    return result


def detect_scene_changes(video):
    """picture-change times in a video file (ffmpeg scdet)."""
    result = run([find_bin("ffmpeg"), "-hide_banner", *vin(video), "-an", "-vf", SCENE_DETECT, "-f", "null", "-"])
    return [float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", result.stdout + result.stderr)]


def scene_cuts(video):
    """times of hard cuts already inside the footage (eg a compilation). cached per file."""
    return _cached(video, "_scenes", SCENE_DETECT, detect_scene_changes)


def detect_silences(video):
    result = run([find_bin("ffmpeg"), "-hide_banner", "-i", str(video), "-map", "0:a:0",
                  "-af", SILENCE_DETECT, "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", result.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", result.stderr)]
    # json has no infinity: a silence still running at the end of the file is saved as null
    return [[max(0.0, start), end] for start, end in zip(starts, ends + [None])]


def silence_map(video):
    """[(start, end)] of every quiet stretch in the clip's audio. cached per file."""
    return [(start, float("inf") if end is None else end)
            for start, end in _cached(video, "_silence", SILENCE_DETECT, detect_silences)]
