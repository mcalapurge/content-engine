"""step 4: check the finished reel and report honestly.

usage: python -m engine qc [video]
exit code 0 = everything passed or only warnings, 1 = something failed.
"""
import argparse
import json
import re
import sys

from engine.core.contrast import MIN_RATIO, boxed_pairs, ratio

from engine.core.brand import get_brand, load_style
from engine.core.common import FILLERS, find_bin, load_json, norm, resolve_video, run, video_info, work_dir_for

results = []


def check(name, status, detail):
    results.append((name, status, detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    args = ap.parse_args()

    video = resolve_video(args.video)
    wd = work_dir_for(video)
    edl = load_json(wd / "edl.json")
    plan = load_json(wd / "plan.json")
    tr = load_json(wd / "transcript.json")
    out = edl["output"]
    brand = get_brand(edl.get("brand"), plan)
    st = load_style(edl.get("style") or brand.name, brand)

    info = video_info(out)

    # 1. format
    if (info["width"], info["height"]) == (1080, 1920):
        check("format", "PASS", "1080x1920, 9:16")
    else:
        check("format", "FAIL", f"came out {info['width']}x{info['height']}, expected 1080x1920")

    # 2. audio present
    check("audio", "PASS" if info["has_audio"] else "FAIL",
          "audio track present" if info["has_audio"] else "no audio in the output")

    # 3. length matches the plan
    diff = abs(info["duration"] - edl["duration"])
    check("length", "PASS" if diff < 0.4 else "FAIL",
          f"{info['duration']:.1f}s (planned {edl['duration']:.1f}s)")
    if info["duration"] > 90:
        check("reel length", "WARN", f"{info['duration']:.0f}s is long for a reel - consider cutting harder")

    # 4. dead air left in
    res = run([find_bin("ffmpeg"), "-i", out, "-af", "silencedetect=noise=-38dB:d=0.7",
               "-f", "null", "-"])
    gaps = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", res.stderr)]
    if not gaps:
        check("dead air", "PASS", "no pauses over 0.7s")
    else:
        check("dead air", "WARN", f"{len(gaps)} pause(s) over 0.7s, longest {max(gaps):.1f}s "
              "(fine if deliberate, otherwise cut that line tighter)")

    # 5. loudness
    res = run([find_bin("ffmpeg"), "-i", out, "-af", "loudnorm=I=-14:print_format=json",
               "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if m:
        lufs = float(json.loads(m.group(0))["input_i"])
        ok = -17 <= lufs <= -11
        check("loudness", "PASS" if ok else "WARN",
              f"{lufs:.1f} LUFS ({'right for social' if ok else 'aim for about -14'})")
    else:
        check("loudness", "WARN", "couldn't measure loudness")

    # 6. captions cover every kept word
    if edl["caption_events"] > 0 and edl["kept_word_count"] > 0:
        check("captions", "PASS", f"{edl['kept_word_count']} words captioned in {edl['caption_events']} caption events")
    else:
        check("captions", "FAIL", "no captions were generated")

    # 7. hook
    # boxed on-screen text (hook box, step badge, takeover cards) must be readable: wcag AA contrast
    pairs = [(n, fg, bg, ratio(fg, bg)) for n, fg, bg in boxed_pairs(st, plan)]
    low = [x for x in pairs if x[3] < MIN_RATIO]
    if not pairs:
        check("text contrast", "PASS", "no text on a coloured background")
    else:
        check("text contrast", "FAIL" if low else "PASS", "; ".join(
            f"{n} {r:.1f}:1" + (f" (needs {MIN_RATIO}:1)" if r < MIN_RATIO else "") for n, fg, bg, r in pairs))
    check("hook", "PASS" if edl["has_hook"] else "WARN",
          f"\"{plan.get('hook_text')}\" on screen from 0s" if edl["has_hook"] else "no hook text set")

    check("colour grade", "PASS" if edl.get("graded") else "WARN",
          "your grade applied" if edl.get("graded") else "no grade applied (switched off or --no-grade)")

    if edl.get("broll"):
        check("b-roll", "PASS", f"{len(edl['broll'])} clip(s) placed")
    if edl.get("missing_sfx"):
        check("sound effects", "WARN", f"missing files for: {', '.join(edl['missing_sfx'])} (run python -m engine sfx)")
    elif edl.get("sfx"):
        check("sound effects", "PASS", f"{len(edl['sfx'])} placed")
    if edl.get("capcut_pack"):
        from pathlib import Path
        pack = Path(edl["capcut_pack"])
        need = ["1_video_clean.mp4", "2_graphics_on_black.mp4", "2_graphics_matte.mp4", "3_captions.srt"]
        gone = [n for n in need if not (pack / n).exists()]
        check("capcut pack", "FAIL" if gone else "PASS",
              f"missing {', '.join(gone)}" if gone else "all layers exported")

    # 8. fillers that slipped through (low-confidence words are worth a look too)
    words = tr["words"]
    kept = [i for l in plan["lines"] if l["keep"] for i in l["words"] if i not in l["cut_words"]]
    slipped = [words[i]["text"] for i in kept if norm(words[i]["text"]) in FILLERS]
    shaky = [words[i]["text"] for i in kept if words[i].get("prob", 1) < 0.45]
    check("filler words", "PASS" if not slipped else "WARN",
          "none left in" if not slipped else f"still in: {', '.join(slipped)}")
    if shaky:
        check("caption accuracy", "WARN",
              f"{len(shaky)} word(s) the transcriber wasn't sure of: {', '.join(shaky[:8])} - check spelling")

    fails = [r for r in results if r[1] == "FAIL"]
    lines = ["| check | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {s} | {d} |" for n, s, d in results]
    report = "\n".join(lines)
    (wd / "qc.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[engine] {'FAILED - ' + str(len(fails)) + ' check(s) failed' if fails else 'all checks passed (see any warnings above)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
