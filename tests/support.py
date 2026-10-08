"""shared helpers for the tests: a sandbox of folders inside the project, a way to run engine
commands in it, synthetic clips and transcripts, an ffmpeg capability check and golden files.

the sandbox lives in work/_tests/<name>/ (git-ignored) and is removed afterwards, so the tests
never touch real footage, jobs, outputs or brands.
"""
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "golden"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"

# every filter the engine uses somewhere. a build without one of these can't run the media tests
NEEDED_FILTERS = ("subtitles", "zscale", "lut3d", "huesaturation", "zoompan", "scdet", "drawtext",
                  "sidechaincompress", "loudnorm", "blurdetect", "signalstats", "silencedetect")


@functools.lru_cache(maxsize=None)
def ffmpeg_problem():
    """None when ffmpeg can run every engine feature, else why not (used to skip media tests)."""
    if os.environ.get("REELS_SKIP_MEDIA") == "1":
        return "REELS_SKIP_MEDIA=1"
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not (ffmpeg and ffprobe):
        return "ffmpeg / ffprobe not on PATH"
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    major = re.search(r"version n?(\d+)\.", version)
    if major and int(major.group(1)) < 7:
        return f"ffmpeg 7+ needed (-/filter_complex), found: {version}"
    filters = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    missing = [f for f in NEEDED_FILTERS if f" {f} " not in filters]
    if missing:
        return f"ffmpeg is missing filters: {', '.join(missing)}"
    return None


def needs_ffmpeg(test):
    return unittest.skipIf(ffmpeg_problem() is not None, ffmpeg_problem() or "")(test)


class Sandbox:
    """work/_tests/<name>/ with its own inputs/, brands/ (a copy of the real ones), work/ and output/."""

    def __init__(self, name, copy_brands=True):
        self.dir = ROOT / "work" / "_tests" / name
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.inputs = self.dir / "inputs"
        self.brands = self.dir / "brands"
        self.work = self.dir / "work"
        self.output = self.dir / "output"
        for folder in ("talking-head", "shop", "vlog", "trial", "brand-guides"):
            (self.inputs / folder).mkdir(parents=True)
        if copy_brands:
            shutil.copytree(ROOT / "brands", self.brands)
        else:
            self.brands.mkdir(parents=True)
        self.work.mkdir()
        self.output.mkdir()

    def env(self):
        env = dict(os.environ, REELS_INPUTS_DIR=str(self.inputs), REELS_BRANDS_DIR=str(self.brands),
                   REELS_WORK_DIR=str(self.work), REELS_OUTPUT_DIR=str(self.output),
                   PYTHONIOENCODING="utf-8")
        return env

    def engine(self, *args, check=True, timeout=900):
        """run python -m engine <args> in the sandbox. returns the CompletedProcess."""
        res = subprocess.run([sys.executable, "-m", "engine", *map(str, args)], cwd=ROOT, env=self.env(),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        if check and res.returncode != 0:
            raise AssertionError(f"engine {' '.join(map(str, args))} failed ({res.returncode}):\n"
                                 f"{res.stdout[-3000:]}\n{res.stderr[-3000:]}")
        return res

    def remove(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        parent = self.dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def make_clip(path, secs, size="540x960", pattern="testsrc2", tone=300, audio=True):
    """a synthetic clip: a moving test pattern + a steady tone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-f", "lavfi", "-i", f"{pattern}=size={size}:rate=30"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency={tone}", "-c:a", "aac"]
    ffmpeg(*args, "-t", secs, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path)
    return path


def fake_transcript(work_dir, video, text, size=(540, 960), duration=None, word_secs=0.22, step=0.27, pause=1.2,
                    unsure=()):
    """write work/<clip>/transcript.json as if the transcriber had heard `text`. "|" in the text = a pause."""
    words, t = [], 0.2
    for token in text.split():
        if token == "|":
            t += pause
            continue
        words.append({"text": token, "start": round(t, 3), "end": round(t + word_secs, 3),
                      "prob": 0.3 if token in unsure else 0.95})
        t += step
    work_dir.mkdir(parents=True, exist_ok=True)
    data = {"source": str(Path(video).resolve()), "duration": duration or round(t + 0.5, 2), "width": size[0],
            "height": size[1], "language": "en", "words": words}
    (work_dir / "transcript.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def normalise(text, sandbox=None):
    """machine-specific paths out of a generated file, so it can be compared with a golden copy."""
    if sandbox is not None:
        text = text.replace(str(sandbox.dir), "<SANDBOX>").replace(sandbox.dir.as_posix(), "<SANDBOX>")
    return text.replace(str(ROOT), "<ROOT>").replace(ROOT.as_posix(), "<ROOT>")


def assert_golden(test, name, actual):
    """compare with tests/golden/<name>. UPDATE_GOLDEN=1 writes the current output as the new golden copy."""
    path = GOLDEN_DIR / name
    if UPDATE_GOLDEN or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        if not UPDATE_GOLDEN:
            test.fail(f"no golden copy of {name} yet: wrote one, check it in and rerun")
        return
    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        import difflib
        diff = "".join(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True),
                                            f"golden/{name}", "now", n=1))
        test.fail(f"{name} changed (if that's intended, rerun with UPDATE_GOLDEN=1):\n{diff[:4000]}")


def words(text):
    """[{"text", "start", "end"}] for in-process tests, one word every 0.3s, "|" = a 1.2s pause."""
    out, t = [], 0.0
    for token in text.split():
        if token == "|":
            t += 1.2
            continue
        out.append({"text": token, "start": round(t, 3), "end": round(t + 0.25, 3), "prob": 0.95})
        t += 0.3
    return out
