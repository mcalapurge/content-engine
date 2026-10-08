"""background music: your own library, or ai-generated tracks via elevenlabs.

usage:
  python engine/music.py list
  python engine/music.py generate "warm lo-fi, soft keys, gentle beat, no vocals" --seconds 45 --name calm-keys
  python engine/music.py use [video] music/calm-keys.mp3 [--volume 0.12]

library: drop tracks you have the rights to into music/ (eg named by mood: upbeat-pop.mp3).
ai music needs an elevenlabs api key in a file called .env in this folder:
  ELEVENLABS_API_KEY=your-key-here
check your elevenlabs plan allows commercial use before using ai tracks in paid brand content.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request

from common import MUSIC_DIR, ROOT, die, load_json, probe, resolve_video, save_json, work_dir_for

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg"}


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ELEVENLABS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key


def cmd_list():
    MUSIC_DIR.mkdir(exist_ok=True)
    tracks = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if not tracks:
        print("[engine] music/ is empty. drop in tracks you have rights to, or generate one.")
    for t in tracks:
        try:
            dur = float(probe(t)["format"]["duration"])
        except Exception:
            dur = 0
        print(f"  {t.name:40s} {dur:5.0f}s")
    print(f"\nai generation: {'ready (key found)' if api_key() else 'no elevenlabs key in .env'}")


def cmd_generate(prompt, seconds, name):
    key = api_key()
    if not key:
        die("no ELEVENLABS_API_KEY found. add it to a .env file in this folder")
    seconds = min(max(seconds, 10), 300)
    body = json.dumps({"prompt": prompt, "music_length_ms": int(seconds * 1000),
                       "force_instrumental": True}).encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/music", data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    print(f"[engine] composing {seconds:.0f}s of music...")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        die(f"elevenlabs said no ({e.code}): {e.read().decode(errors='replace')[:400]}")
    MUSIC_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or prompt[:40]).lower()).strip("-")
    out = MUSIC_DIR / f"{slug}.mp3"
    out.write_bytes(audio)
    meta = MUSIC_DIR / "ai_tracks.json"
    log = load_json(meta) if meta.exists() else []
    log.append({"file": out.name, "prompt": prompt, "seconds": seconds})
    save_json(meta, log)
    print(f"[engine] saved {out}")


def cmd_use(video_arg, track, volume):
    video = resolve_video(video_arg)
    wd = work_dir_for(video)
    plan = load_json(wd / "plan.json")
    p = (ROOT / track) if not os.path.isabs(track) else track
    if not os.path.exists(p):
        p = MUSIC_DIR / track
    if not os.path.exists(p):
        die(f"can't find {track}")
    snd = plan.setdefault("sound", {})
    snd["music"] = os.path.relpath(p, ROOT).replace("\\", "/")
    if volume is not None:
        snd["music_volume"] = volume
    save_json(wd / "plan.json", plan)
    print(f"[engine] {video.name} will use {snd['music']} at volume {snd.get('music_volume', 0.12)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("generate")
    g.add_argument("prompt")
    g.add_argument("--seconds", type=float, default=45)
    g.add_argument("--name", default=None)
    u = sub.add_parser("use")
    u.add_argument("video", nargs="?")
    u.add_argument("track")
    u.add_argument("--volume", type=float, default=None)
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "generate":
        cmd_generate(a.prompt, a.seconds, a.name)
    else:
        cmd_use(a.video, a.track, a.volume)


if __name__ == "__main__":
    main()
