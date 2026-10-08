"""checks everything the engine needs is installed.

usage: python -m engine check_setup
"""
import platform
import shutil
import subprocess
import sys

from engine.core.common import ROOT

ok = True


def line(good, name, detail):
    global ok
    ok = ok and good
    print(f"  {'OK ' if good else 'MISSING'}  {name} - {detail}")


def main():
    print(f"\nreels engine setup check ({platform.system()} {platform.machine()})\n")

    line(sys.version_info >= (3, 9), "python", platform.python_version() + (" (need 3.9+)" if sys.version_info < (3, 9) else ""))

    ff = shutil.which("ffmpeg")
    if ff:
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        line(" subtitles " in filters, "ffmpeg", "found, with caption support" if " subtitles " in filters
             else "found, but built without libass (captions won't burn in) - install the full build")
    else:
        line(False, "ffmpeg", "not found. mac: brew install ffmpeg | windows: winget install Gyan.FFmpeg")

    line(shutil.which("ffprobe") is not None, "ffprobe", "comes with ffmpeg")
    if ff:
        good = " huesaturation " in filters and " zoompan " in filters
        line(good, "ffmpeg version", "new enough for your colour grade + zooms" if good
             else "too old for the HSL part of your grade - update ffmpeg (brew upgrade ffmpeg / winget upgrade Gyan.FFmpeg)")

    try:
        import faster_whisper  # noqa
        line(True, "faster-whisper", "installed")
    except ImportError:
        line(False, "faster-whisper", "run: pip install -r requirements.txt")

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
