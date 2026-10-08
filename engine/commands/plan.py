"""step 2: turn a transcript into an edit plan + beat table for approval.

usage: python -m engine plan [video] --brand <name> [--style <style>]

writes work/<clip>/plan.json (claude edits this when you ask for changes)
and work/<clip>/plan.md (the beat table you approve).
"""
import argparse
import re
from difflib import SequenceMatcher

from engine.core.brand import add_brand_arg, get_brand, load_style
from engine.core.common import FILLERS, load_json, norm, resolve_video, save_json, work_dir_for

LINE_BREAK_GAP = 0.7      # a pause this long starts a new line
MAX_LINE_WORDS = 16
SLOW_LINE_SECS = 6.0      # lines longer than this get flagged (viewers drop off)
STEP_WORDS = ("first", "firstly", "second", "secondly", "third", "thirdly", "next", "finally",
              "lastly", "step", "number")
MOTIONS = {"slow": "slow zoom in", "jump": "jump cut zoom", "punch": "punch-in", "none": "static"}


def split_lines(words):
    lines, cur = [], []
    for i, w in enumerate(words):
        if cur:
            gap = w["start"] - words[cur[-1]]["end"]
            sentence_end = words[cur[-1]]["text"].endswith((".", "?", "!")) and len(cur) >= 3
            if gap > LINE_BREAK_GAP or sentence_end or len(cur) >= MAX_LINE_WORDS:
                lines.append(cur)
                cur = []
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def clean_tokens(words, idxs):
    return [norm(words[i]["text"]) for i in idxs if norm(words[i]["text"]) not in FILLERS]


def is_retake(a, b):
    """True if line a looks like another attempt at line b."""
    if not a or not b:
        return False
    k = min(3, len(a), len(b))
    if k >= 2 and a[:k] == b[:k]:
        return True
    prefix = " ".join(b[:len(a) + 2])
    return len(a) >= 3 and SequenceMatcher(None, " ".join(a), prefix).ratio() >= 0.72


def find_stat(text):
    m = re.search(r"([£$€]?\d[\d,.]*\s?(%|percent|k|x|million|thousand)?)", text, re.I)
    if m:
        return m.group(1).strip().rstrip(".,").replace(" percent", "%").replace("percent", "%")
    return None


def short_hook(text, max_words=8):
    t = re.sub(r"\b(um+|uh+|erm|er|so|okay|ok)\b,?\s*", "", text, flags=re.I).strip()
    w = t.split()
    out = " ".join(w[:max_words])
    if len(w) > max_words:
        out = out.rstrip(",.") + "..."
    return out[:1].upper() + out[1:]


def first_sentence(kept):
    out = []
    for l in kept[:3]:
        out.append(l["text"])
        if l["text"].rstrip().endswith((".", "?", "!")):
            break
    return " ".join(out)


def beat_table(plan, video_name, raw_duration):
    lines = plan["lines"]
    kept = [l for l in lines if l["keep"]]
    total = sum(l["end"] - l["start"] for l in kept)
    groups = {tuple(l["takes"]) for l in lines if l["takes"]}
    snd = plan.get("sound", {})
    music = snd.get("music")
    out = [f"# edit plan - {video_name}", "",
           f"brand: **{plan.get('brand', '?')}**  |  style: **{plan['style']}**  |  hook on screen: **\"{plan['hook_text']}\"**",
           f"raw {raw_duration:.1f}s -> about **{total:.1f}s** after cuts",
           (f"{len(groups)} line(s) filmed more than once - picked the last take by default. "
            "run python -m engine takes to choose by expression" if groups else "no repeated takes found"),
           f"sound: {'sound effects on' if snd.get('sfx', True) else 'no sound effects'}, "
           f"{'music: ' + str(music).replace(chr(92), '/').split('/')[-1] if music else 'no music yet'}",
           "", "| # | keep? | secs | what you say | what's on screen |", "|---|---|---|---|---|"]
    for l in lines:
        if not l["keep"]:
            screen = f"cut ({l['reason']})"
        else:
            bits = []
            t = l["treatment"]
            if t == "hook":
                bits.append("hook card")
            elif t == "stat pop":
                bits.append(f"stat pop **{l['stat']}**")
            elif t == "step":
                bits.append(f"step badge **{l['step']}**")
            elif t == "takeover":
                bits.append("full screen takeover")
            bits.append(MOTIONS.get(l["motion"], l["motion"]))
            if l["cut_words"]:
                bits.append(f"{len(l['cut_words'])} filler trimmed")
            if l["takes"]:
                bits.append(f"take {l['takes'].index(l['id']) + 1} of {len(l['takes'])}")
            if l.get("broll"):
                bits.append(f"b-roll: {l['broll']['file'].split('/')[-1]}"
                            f"{' (picture in picture)' if l['broll'].get('mode') == 'pip' else ''}")
            if l.get("sfx"):
                bits.append(f"sound: {l['sfx']}")
            if l.get("notes"):
                bits.append(f"note: {l['notes']}")
            screen = ", ".join(bits)
        flag = " (slow)" if l["keep"] and l["seconds"] > SLOW_LINE_SECS else ""
        out.append(f"| {l['id']} | {'yes' if l['keep'] else 'no'} | {l['seconds']}{flag} | "
                   f"{l['text'].replace('|', '/')} | {screen} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    add_brand_arg(ap)
    ap.add_argument("--style", default=None, help="default: the brand's own style")
    ap.add_argument("--no-text", action="store_true",
                    help="captions only: no hook card, stat pops or step badges (eg tiktok shop)")
    ap.add_argument("--table-only", action="store_true",
                    help="just reprint the beat table from the existing plan.json")
    args = ap.parse_args()

    video = resolve_video(args.video)
    wd = work_dir_for(video)
    tr = load_json(wd / "transcript.json")

    if args.table_only:
        plan = load_json(wd / "plan.json")
        md = beat_table(plan, video.name, tr["duration"])
        (wd / "plan.md").write_text(md, encoding="utf-8")
        print(md)
        return

    brand = get_brand(args.brand)
    style = args.style or brand.name
    load_style(style, brand)          # stop now if the style doesn't exist, not at render time
    words = tr["words"]
    if not words:
        print("[engine] no speech found in this clip.")
        return

    raw_lines = split_lines(words)
    tokens = [clean_tokens(words, l) for l in raw_lines]

    # group repeated takes of the same line (say a line as many times as you like)
    take_of = list(range(len(raw_lines)))
    for n in range(len(raw_lines)):
        for m in range(n + 1, min(n + 5, len(raw_lines))):
            if is_retake(tokens[n], tokens[m]):
                take_of[m] = take_of[n]
                break

    lines = []
    for n, idxs in enumerate(raw_lines):
        group = [k for k in range(len(raw_lines)) if take_of[k] == take_of[n]]
        keep, reason = True, ""
        if not tokens[n]:
            keep, reason = False, "just filler / noise"
        elif len(group) > 1 and n != group[-1]:
            keep, reason = False, f"earlier take - keeping line {group[-1] + 1}"
        lines.append({
            "id": n + 1,
            "start": words[idxs[0]]["start"],
            "end": words[idxs[-1]]["end"],
            "seconds": round(words[idxs[-1]]["end"] - words[idxs[0]]["start"], 1),
            "text": " ".join(words[i]["text"] for i in idxs).strip(),
            "keep": keep,
            "reason": reason,
            "takes": [k + 1 for k in group] if len(group) > 1 else [],
            "words": idxs,
            "cut_words": [i for i in idxs if norm(words[i]["text"]) in FILLERS],
            "treatment": "none",
            "motion": "none",
            "stat": None,
            "step": None,
            "takeover_text": None,
            "broll": None,
            "sfx": None,
            "notes": "",
        })

    # treatments + camera motion. rhythm keeps it moving without being seasick
    kept = [l for l in lines if l["keep"]]
    rhythm = ["jump", "slow", "jump", "none"]
    step_n = r = 0
    for k, l in enumerate(kept):
        first = norm(l["text"].split()[0]) if l["text"] else ""
        stat = find_stat(l["text"])
        if args.no_text:
            l["motion"] = "slow" if k == 0 else rhythm[r % len(rhythm)]
            r += k > 0
        elif k == 0:
            l["treatment"], l["motion"] = "hook", "slow"
        elif stat:
            l["treatment"], l["stat"], l["motion"] = "stat pop", stat, "punch"
        elif first in STEP_WORDS:
            step_n += 1
            l["treatment"], l["step"], l["motion"] = "step", step_n, "jump"
        else:
            l["motion"] = rhythm[r % len(rhythm)]
            r += 1
        if k == len(kept) - 1 and k > 0 and l["motion"] == "none":
            l["motion"] = "slow"   # land the ending

    hook = short_hook(first_sentence(kept)) if kept and not args.no_text else ""
    plan = {"brand": brand.name, "style": style, "hook_text": hook,
            "sound": {"sfx": True, "sfx_volume": 0.5, "music": None, "music_volume": 0.12},
            "lines": lines}
    save_json(wd / "plan.json", plan)
    md = beat_table(plan, video.name, tr["duration"])
    (wd / "plan.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
