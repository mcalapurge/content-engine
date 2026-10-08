"""checks everything the engine needs is installed.

usage: python -m engine check_setup
"""
import platform
import re
import shutil
import subprocess
import sys

from engine.core.common import ROOT, which_bin

ok = True


def line(good, name, detail):
    global ok
    ok = ok and good
    print(f"  {'OK ' if good else 'MISSING'}  {name} - {detail}")


def ffmpeg_major(version_line):
    """the major version from `ffmpeg -version`'s first line ("ffmpeg version 7.1.1 ...", "n7.0.2"),
    or None for a build straight from ffmpeg's latest code ("N-127233-g..."), which is newer than any release."""
    m = re.search(r"version n?(\d+)\.", version_line)
    return int(m.group(1)) if m else None


def main():
    print(f"\nreels engine setup check ({platform.system()} {platform.machine()})\n")

    line(sys.version_info >= (3, 10), "python", platform.python_version() + (" (need 3.10+)" if sys.version_info < (3, 10) else ""))

    ff = which_bin("ffmpeg")
    if ff:
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        line(" subtitles " in filters, "ffmpeg", "found, with caption support" if " subtitles " in filters
             else "found, but built without captions - mac: brew install ffmpeg-full | windows: winget install Gyan.FFmpeg")
    else:
        line(False, "ffmpeg", "not found. mac: bash scripts/setup_mac.sh (or brew install ffmpeg-full) | windows: winget install Gyan.FFmpeg")

    line(which_bin("ffprobe") is not None, "ffprobe", "comes with ffmpeg")
    if ff:
        version = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        major = ffmpeg_major(version)
        # the engine hands ffmpeg its filter script with -/filter_complex, which arrived in ffmpeg 7
        good = (major is None or major >= 7) and " huesaturation " in filters and " zoompan " in filters
        line(good, "ffmpeg version", f"{major or 'latest'}: new enough for renders, your colour grade + zooms" if good
             else f"{major}: too old, renders need ffmpeg 7 or newer - update ffmpeg "
                  "(brew upgrade ffmpeg-full / winget upgrade Gyan.FFmpeg)")

    try:
        import onnx_asr  # noqa
        line(True, "parakeet (onnx-asr)", "installed. the speech model downloads on the first transcribe")
    except ImportError:
        line(False, "parakeet (onnx-asr)", "run: pip install -r requirements.txt")

    try:
        import yt_dlp  # noqa
        line(True, "yt-dlp", "installed (for breaking down other reels)")
    except ImportError:
        line(False, "yt-dlp", "run: pip install -r requirements.txt")

    free_gb = shutil.disk_usage(ROOT).free / 1e9
    line(free_gb > 5, "disk space", f"{free_gb:.0f} GB free (want 5+)")

    print("\nall good - drop a clip in inputs/talking-head/ and say 'edit this reel'\n" if ok
          else "\nfix the MISSING items above, then run this again\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
