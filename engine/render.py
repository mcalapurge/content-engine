"""step 3: render the approved plan into a finished, graded 9:16 reel.

usage: python engine/render.py [video] [--style beth] [--music track.mp3] [--draft] [--no-grade]
"""
import argparse
import re
from pathlib import Path

from common import (IMAGE_EXTS, OUTPUT_DIR, ROOT, SFX_DIR, WORK_DIR, die, find_bin, h264, load_json, load_style,
                    norm, resolve_video, run, save_json, sdr_filter, vin, work_dir_for)
from contrast import MIN_RATIO, badge_colours, problems as contrast_problems, takeover_colours
from grade import grade_filter, has_huesaturation, load_grade

W, H = 1080, 1920
FPS = 30
JOIN_GAP = 0.30      # pauses shorter than this stay in (natural breathing)
PAD_BEFORE = 0.06
PAD_AFTER = 0.14
TAIL = 0.35          # extra hold after the very last word
FACE_Y = 0.42        # crop a little above centre, where faces usually are


# ---------- timeline ----------

def snap_to_audio(segs, words, silences):
    """the transcriber's word times are often a little short. move each cut out to where the
    voice really stops/starts, so no word gets clipped, without reaching into a neighbouring word."""
    def silence_at(t):
        return next(((a, b) for a, b in silences if a <= t <= b), None)

    for s in segs:
        i0, i1 = s["words"][0], s["words"][-1]
        lo = words[i0 - 1]["end"] if i0 > 0 else 0.0
        hi = words[i1 + 1]["start"] if i1 + 1 < len(words) else float("inf")
        sil = silence_at(s["start"])
        if sil:                 # "word" starts in silence: start on the voice instead
            if sil[1] < words[i0]["end"] - 0.05:
                s["start"] = sil[1]
        else:                   # starts mid-sound: back up to the silence just before it
            before = [b for a, b in silences if b <= s["start"] and s["start"] - b <= 0.25]
            if before:
                s["start"] = max(before[-1], lo)
        if not silence_at(s["end"]):   # ends mid-sound: run on until the voice stops
            after = [a for a, b in silences if a >= s["end"] and a - s["end"] <= 0.5]
            s["end"] = min(after[0] if after else s["end"] + 0.25, max(hi, s["end"]))
        if sil:
            words[i0]["start"] = s["start"]


def build_segments(plan, words, silences=None, scenes=None):
    kept = []
    for line in plan["lines"]:
        if line["keep"]:
            cut = set(line["cut_words"])
            kept += [(i, line) for i in line["words"] if i not in cut]
    segs, cur = [], None
    for i, line in kept:
        w = words[i]
        # keep one shot while the speech runs on: only change framing where something was cut,
        # or for a deliberate punch-in. (zooming mid-sentence with no cut looks like a glitch)
        same_shot = cur and (cur["line"] == line["id"] or "punch" not in (cur["motion"], line.get("motion")))
        if (same_shot and i == cur["last"] + 1
                and w["start"] - words[cur["last"]]["end"] <= JOIN_GAP):
            cur.update(end=w["end"], last=i)
            cur["words"].append(i)
        else:
            cur = {"start": w["start"], "end": w["end"], "last": i, "line": line["id"],
                   "motion": line.get("motion", "none"), "words": [i]}
            segs.append(cur)
    if silences:
        snap_to_audio(segs, words, silences)
        # pieces that now run straight on in the source are one shot, not a cut
        merged = [segs[0]] if segs else []
        for s in segs[1:]:
            p = merged[-1]
            if s["start"] - p["end"] <= JOIN_GAP and (p["line"] == s["line"] or "punch" not in (p["motion"], s["motion"])):
                p.update(end=max(p["end"], s["end"]), last=s["last"])
                p["words"] += s["words"]
            else:
                merged.append(s)
        segs = merged
    segs[-1]["end"] += TAIL if segs else 0   # let the last word ring out before the reel ends
    for k, s in enumerate(segs):
        s["start"] = max(0.0, s["start"] - PAD_BEFORE)
        s["end"] += PAD_AFTER
        # never straddle a cut that's already in the footage (a flash of another scene looks glitchy)
        for c in scenes or []:
            if s["start"] < c < s["end"]:
                first, last = words[s["words"][0]]["start"], words[s["words"][-1]]["end"]
                if c <= first + 0.05:
                    s["start"] = c + 0.01
                elif c >= last - 0.05:
                    s["end"] = c - 0.01
        if k and s["start"] < segs[k - 1]["end"]:
            mid = (s["start"] + segs[k - 1]["end"]) / 2
            segs[k - 1]["end"] = s["start"] = mid
    t, timed = 0.0, {}
    for s in segs:
        # whole frames only, so the real cut points match the timeline (b-roll ends exactly on them)
        s["frames"] = max(1, round((s["end"] - s["start"]) * FPS))
        s["end"] = s["start"] + s["frames"] / FPS
        s["new_start"] = t
        for i in s["words"]:
            timed[i] = (t + words[i]["start"] - s["start"], t + words[i]["end"] - s["start"])
        t += s["end"] - s["start"]
        s["new_end"] = t
    return segs, timed


def assign_zoom(segs, style):
    """work out the zoom for every cut. slow zooms span the whole line, not each cut."""
    spans = {}
    for s in segs:
        a, b = spans.get(s["line"], (s["new_start"], s["new_end"]))
        spans[s["line"]] = (min(a, s["new_start"]), max(b, s["new_end"]))
    jump_on = False
    for s in segs:
        m = s["motion"]
        if m == "slow":
            a, b = spans[s["line"]]
            span = max(b - a, 0.01)
            z1 = style.get("slow_zoom", 1.07)
            s["z0"] = 1 + (z1 - 1) * (s["new_start"] - a) / span
            s["z1"] = 1 + (z1 - 1) * (s["new_end"] - a) / span
        elif m == "jump":
            jump_on = not jump_on
            s["z0"] = s["z1"] = style.get("jump_zoom", 1.12) if jump_on else 1.0
        elif m == "punch":
            s["z0"] = s["z1"] = style.get("punch_zoom", 1.25)
        else:
            s["z0"] = s["z1"] = 1.0


def frame_filter(s, src_w, src_h):
    """cover-fit to 9:16 and zoom down to 1080x1920.
    still framing (jump cuts, punch-ins, no zoom): crop the exact same window straight from the
    source and scale once. ~6x less work than going via a 2x copy, identical framing.
    slow push: cover-fit at 2x, then zoompan, so the moving crop lands on half pixels and doesn't judder."""
    if abs(s["z1"] - s["z0"]) < 1e-4:
        z = s["z0"]
        sc = max(W / src_w, H / src_h) * z
        cw, ch = min(src_w, W / sc), min(src_h, H / sc)
        return (f"crop={cw:.2f}:{ch:.2f}:{(src_w - cw) / 2:.2f}:{(src_h - ch) * FACE_Y:.2f},"
                f"scale={W}:{H},setsar=1,fps={FPS}")
    sc = max(2 * W / src_w, 2 * H / src_h)
    bw, bh = int(src_w * sc) // 2 * 2, int(src_h * sc) // 2 * 2
    base = (f"scale={bw}:{bh},crop={2 * W}:{2 * H}:(iw-{2 * W})/2:(ih-{2 * H})*{FACE_Y},"
            f"setsar=1,fps={FPS}")
    frames = max(1, round((s["end"] - s["start"]) * FPS))
    z = f"{s['z0']:.5f}+{s['z1'] - s['z0']:.5f}*on/{frames}"
    return (base + f",zoompan=z='{z}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*{FACE_Y}'"
            f":d=1:s={W}x{H}:fps={FPS}")


# ---------- captions + overlays (ASS) ----------

def ass_colour(hex_colour, alpha=0):
    h = hex_colour.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def ass_header(st):
    c = ass_colour
    bold = -1 if st.get("bold") else 0
    cap_v = int(H * (1 - st["caption_position"]))
    tk_tx, tk_bg = takeover_colours(st)
    bd_tx, bd_bg = badge_colours(st)
    sp = st.get("spacing", 0)
    if st.get("hook_box", True):
        hook_look = f"{c(st['hook_box_colour'])},{c(st['hook_box_colour'])},-1,{-1 if st.get('italic_hook') else 0},0,0,100,100,{sp},0,3,18,0"
    else:      # bold text straight on the video, soft dark edge so it reads on any background
        hook_look = (f"{c(st['outline_colour'])},&H80000000,-1,{-1 if st.get('italic_hook') else 0},0,0,100,100,"
                     f"{st.get('hook_spacing', sp)},0,1,{st['outline']},{st['shadow']}")
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
           "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]", fmt,
        f"Style: Caption,{st['font']},{st['font_size']},{c(st['text_colour'])},{c(st['highlight_colour'])},"
        f"{c(st['outline_colour'])},&H80000000,{bold},0,0,0,100,100,{sp},0,1,{st['outline']},{st['shadow']},2,90,90,{cap_v},1",
        f"Style: Hook,{st['hook_font']},{st['hook_size']},{c(st['hook_text_colour'])},{c(st['hook_text_colour'])},"
        f"{hook_look},8,80,80,230,1",
        f"Style: Stat,{st['hook_font']},230,{c(st['stat_colour'])},{c(st['stat_colour'])},"
        f"{c(st['outline_colour'])},&H00000000,-1,0,0,0,100,100,0,0,1,8,0,5,60,60,0,1",
        f"Style: Badge,{st['hook_font']},64,{c(bd_tx)},{c(bd_tx)},"
        f"{c(bd_bg)},{c(bd_bg)},-1,0,0,0,100,100,0,0,3,14,0,8,80,80,430,1",
        f"Style: TakeBox,Arial,10,{c(tk_bg)},{c(tk_bg)},{c(tk_bg)},{c(tk_bg)},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: TakeText,{st['hook_font']},{st.get('takeover_size', 125)},{c(tk_tx)},{c(tk_tx)},"
        f"{c(tk_bg)},{c(tk_bg)},-1,0,0,0,100,100,0,0,1,0,0,5,90,90,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", ""])


def _key(word):
    return norm(word.replace("’", "'")).replace("'", "")


def _phrase_hits(ids, words, phrases):
    """word ids covered by any phrase (longest first), mapped to the phrase word they match,
    plus the ids that must stay on screen with the word after them."""
    toks = [_key(words[i]["text"]) for i in ids]
    hits, glue = {}, set()
    for phrase in sorted(phrases, key=lambda p: -len(p.split())):
        parts = phrase.split()
        pk = [_key(p) for p in parts]
        for k in range(len(ids) - len(pk) + 1):
            if toks[k:k + len(pk)] == pk and not any(ids[k + j] in hits for j in range(len(pk))):
                for j, p in enumerate(parts):
                    hits[ids[k + j]] = p
                glue |= {ids[k + j] for j in range(len(pk) - 1)}
    return hits, glue


def cased_words(line, ids, words, st, strip_punct):
    """display text per word id after case rules + brand capitals, the set of keyword ids, and
    the ids glued to the next word (brand names and keyword phrases never split across captions)."""
    out = {}
    for i in ids:
        t = words[i]["text"].strip().replace("’", "'")
        if strip_punct:
            t = t.strip(",.")
        if st.get("uppercase"):
            t = t.upper()
        elif st.get("lowercase"):
            t = t.lower()
            if re.fullmatch(r"i('(m|d|ve|ll))?\W*", t):     # "i", "i'm" etc stay capital
                t = "I" + t[1:]
        out[i] = t
    caps, glue = _phrase_hits(ids, words, st.get("keep_caps", []))
    for i, proper in caps.items():
        out[i] = re.sub(r"[\w'£$€%-]+", lambda m: proper, out[i], count=1)
    for name in st.get("keep_caps", []):      # one-word names inside a longer word, eg "UK 16"
        if " " not in name:
            for i in ids:
                out[i] = re.sub(rf"(?i)(?<![\w']){re.escape(name)}(?![\w'])", name, out[i])
    kw_hits, kw_glue = _phrase_hits(ids, words, st.get("keywords", []))
    keys = set(line.get("keywords") or [])
    if not keys:        # automatic: numbers/money + the style's keyword list
        keys = {i for i in ids if re.search(r"[\d£$€%]", words[i]["text"])} | set(kw_hits)
    return out, keys & set(ids), glue | kw_glue


def chunked(ids, n, glue, shown=None, max_chars=0):
    """split a line into captions of ~n words (and at most max_chars, so a caption never wraps
    onto two rows) without breaking a glued phrase."""
    out, cur = [], []
    for i in ids:
        if (max_chars and cur and cur[-1] not in glue
                and len(" ".join(shown[j] for j in cur + [i])) > max_chars):
            out.append(cur)
            cur = []
        cur.append(i)
        if len(cur) >= n and i not in glue:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    # don't leave one word hanging on its own: borrow the last word of the caption before
    if len(out) > 1 and len(out[-1]) == 1 and len(out[-2]) > 2 and out[-2][-2] not in glue:
        out[-1].insert(0, out[-2].pop())
    return out


def caption_events(plan, words, timed, st, total):
    ev = []
    hl = ass_colour(st["highlight_colour"])
    mode = st["caption_mode"]
    n = 1 if mode == "word" else max(1, int(st["words_per_caption"]))
    order = sorted(timed)
    fsp = f"\\fsp{st['spacing']}" if st.get("spacing") else ""
    kw_tag = ""
    if st.get("keyword_font") or st.get("keyword_colour"):
        kw_tag = (f"\\fn{st.get('keyword_font', st['font'])}"
                  f"\\c{ass_colour(st.get('keyword_colour', st['text_colour']))}"
                  f"\\fs{st.get('keyword_size', st['font_size'])}"
                  f"\\fsp{st.get('keyword_spacing', st.get('spacing', 0))}"
                  f"\\bord{st.get('keyword_outline', st['outline'])}")

    for line in plan["lines"]:
        if not line["keep"] or line["treatment"] == "takeover":
            continue
        # a blank word = merged into the word before it (eg "5" + "'2" shown as 5'2")
        ids = [i for i in line["words"] if i in timed and words[i]["text"].strip()]
        shown, keys, glue = cased_words(line, ids, words, st, strip_punct=mode != "line")

        def txt(i, extra=""):
            # every word starts with \r so a keyword's look never leaks onto the next word.
            # spacing goes inline too: libass ignores the style's spacing value
            tags = fsp + (kw_tag if i in keys else "") + extra
            return f"{{\\r{tags}}}{esc(shown[i])}"

        for chunk in chunked(ids, n, glue, shown, st.get("caption_chars", 0)):
            c_start = timed[chunk[0]][0]
            nxt = next((i for i in order if i > chunk[-1]), None)
            c_end = min(timed[chunk[-1]][1] + 0.25, timed[nxt][0] if nxt is not None else total)
            c_end = max(c_end, c_start + 0.12)
            if mode == "karaoke":
                for k, i in enumerate(chunk):
                    e = timed[chunk[k + 1]][0] if k + 1 < len(chunk) else c_end
                    parts = [txt(j, f"\\c{hl}") + "{\\r}" if j == i else txt(j) for j in chunk]
                    ev.append((timed[i][0], e, "Caption", " ".join(parts)))
            elif mode == "build":
                # the whole line is laid out from the start (unsaid words invisible) so nothing
                # shifts sideways as words appear
                step = max(1, int(st.get("build_step", 1)))
                for k in range(0, len(chunk), step):
                    a = timed[chunk[k]][0]
                    e = timed[chunk[k + step]][0] if k + step < len(chunk) else c_end
                    parts = [txt(j) if p < k + step else txt(j, "\\alpha&HFF&")
                             for p, j in enumerate(chunk)]
                    ev.append((a, max(e, a + 0.04), "Caption", " ".join(parts)))
            elif mode == "word":
                ev.append((c_start, c_end, "Caption",
                           "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" + txt(chunk[0])))
            else:
                ev.append((c_start, c_end, "Caption", " ".join(txt(i) for i in chunk)))
    return ev


def hook_lines(text, st):
    """split the hook into short lines so line spacing can be set (ass has no line height)."""
    if st.get("hook_uppercase"):
        text = text.upper()
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > st.get("hook_chars", 18):
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def overlay_events(plan, words, timed, total, st):
    ev = []
    kept = [l for l in plan["lines"] if l["keep"]]
    hook = (plan.get("hook_text") or "").strip()
    if hook and not (kept and kept[0]["treatment"] == "takeover"):
        end = 3.0
        ids = [i for i in kept[0]["words"] if i in timed] if kept else []
        if ids:
            end = max(2.0, min(3.5, timed[ids[-1]][1]))
        if st.get("hook_line_height"):
            gap = st["hook_size"] * st["hook_line_height"]
            for k, ln in enumerate(hook_lines(hook, st)):
                ev.append((0.0, min(end, total), "Hook",
                           f"{{\\an8\\pos({W // 2},{230 + k * gap:.0f})\\fsp{st.get('hook_spacing', 0)}\\fad(0,150)}}" + esc(ln)))
        else:
            ev.append((0.0, min(end, total), "Hook", "{\\fad(0,150)}" + esc(hook)))

    for line in kept:
        ids = [i for i in line["words"] if i in timed]
        if not ids:
            continue
        s, e = timed[ids[0]][0], min(total, timed[ids[-1]][1] + 0.2)
        t = line["treatment"]
        if t == "stat pop" and line.get("stat"):
            num_word = next((i for i in ids if re.search(r"\d", words[i]["text"])), ids[0])
            s = max(0.0, timed[num_word][0] - 0.1)
            stat = esc(str(line["stat"]))
            m = re.fullmatch(r"([£$€]?)(\d[\d,]*)(.*)", stat)
            num = int(m.group(2).replace(",", "")) if m else 0
            pos = "{\\pos(540,700)}"
            if m and num >= 10:      # count up, then pop
                for k in range(8):
                    a = s + 0.06 * k
                    ev.append((a, a + 0.06, "Stat", pos + f"{m.group(1)}{int(num * (k + 1) / 8):,}{m.group(3)}"))
                ev.append((s + 0.48, e, "Stat", pos + "{\\fscx112\\fscy112\\t(0,160,\\fscx100\\fscy100)}" + stat))
            else:
                ev.append((s, e, "Stat", pos + "{\\fscx40\\fscy40\\t(0,180,\\fscx112\\fscy112)\\t(180,300,\\fscx100\\fscy100)}" + stat))
        elif t == "step" and line.get("step"):
            ev.append((s, e, "Badge", "{\\fad(100,100)}" + f"step {line['step']}"))
        elif t == "takeover":
            cards = line.get("takeover_text") or line["text"]
            if isinstance(cards, str):
                cards = [cards]
            ev.append((s, e, "TakeBox", f"{{\\pos(0,0)\\p1}}m 0 0 l {W} 0 {W} {H} 0 {H}{{\\p0}}"))
            step = (e - s) / len(cards)
            for k, card in enumerate(cards):
                a = s + k * step
                text = esc(card.strip()).replace("\\n", "\\N")
                ev.append((a, a + step, "TakeText",
                           "{\\fscx92\\fscy92\\t(0,140,\\fscx100\\fscy100)}" + text))
    return ev


def write_ass(path, st, events):
    layer = {"Caption": 0, "TakeBox": 2, "TakeText": 3}
    out = [ass_header(st)]
    for s, e, style, text in sorted(events, key=lambda x: (x[0], layer.get(x[2], 1))):
        out.append(f"Dialogue: {layer.get(style, 1)},{ts(s)},{ts(e)},{style},,0,0,0,,{text}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------- b-roll ----------

def broll_windows(plan, timed, total, cuts=()):
    """lines with b-roll -> (start, end, spec) on the new timeline."""
    out = []
    for line in plan["lines"]:
        spec = line.get("broll")
        if not line["keep"] or not spec or not spec.get("file"):
            continue
        ids = [i for i in line["words"] if i in timed]
        if not ids:
            continue
        a = max(0.0, timed[ids[0]][0] - 0.05)
        b = min(total, timed[ids[-1]][1] + 0.15)
        # start/end exactly on a nearby cut, or a frame of the talking shot flashes up
        a = next((c for c in cuts if abs(c - a) < 0.2), a)
        b = next((c for c in cuts if abs(c - b) < 0.2), b)
        path = Path(spec["file"])
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            die(f"b-roll file not found: {spec['file']}")
        if (out and spec.get("continue") and out[-1][2]["path"] == path and a - out[-1][1] < 0.6):
            # "continue": true = keep playing the previous b-roll as one unbroken shot
            out[-1] = (out[-1][0], b, out[-1][2])
            continue
        out.append((a, b, {**spec, "path": path}))
    # back-to-back b-roll runs straight through (no flash of the talking shot between lines)
    for k in range(len(out) - 1):
        if out[k + 1][0] - out[k][1] < 0.6:
            out[k] = (out[k][0], out[k + 1][0], out[k][2])
    # b-roll that would run across a cut already in that footage: start after the cut
    for k, (a, b, spec) in enumerate(out):
        if spec["path"].suffix.lower() in IMAGE_EXTS:
            continue
        st = float(spec.get("start", 0))
        for c in scene_cuts(spec["path"]):
            if st < c < st + (b - a):
                if c - st < 1.5:
                    spec = {**spec, "start": round(c + 0.04, 3)}
                    st = spec["start"]
                else:
                    print(f"[engine] note: b-roll {spec['path'].name} from {st:.1f}s runs into a scene change at {c:.1f}s")
        out[k] = (a, b, spec)
    return out


def broll_filter(idx, a, b, spec, grade=""):
    dur = b - a
    frames = max(1, round(dur * FPS))
    pip = spec.get("mode") == "pip"
    bw, bh = (420, 560) if pip else (W, H)
    # gentle push so stills and static shots don't look dead
    chain = (f"[{idx}:v]{sdr_filter(spec['path'])}scale={bw * 2}:{bh * 2}:force_original_aspect_ratio=increase,"
             f"crop={bw * 2}:{bh * 2},setsar=1,fps={FPS},"
             f"zoompan=z='1+0.05*on/{frames}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={bw}x{bh}:fps={FPS},"
             # a few spare frames: the start time rounds down to a whole frame, and if the b-roll runs out
             # before its slot ends a frame of the talking shot flashes up. the overlay's enable ends it on time
             f"tpad=stop_mode=clone:stop_duration=0.3,"
             f"trim=end_frame={frames + 4},format=yuv420p,setpts=PTS-STARTPTS+{a:.3f}/TB")
    if grade and spec.get("grade"):   # "grade": true = raw footage that needs your grade too
        chain += "," + grade
    if pip:
        chain += ",pad=iw+16:ih+16:8:8:white"
    return chain


# ---------- sound ----------

def sfx_cues(plan, words, timed, windows):
    """automatic sound effects + per-line overrides. returns [(time, name, volume)]
    (volume is a multiplier on sfx_volume, set per line with "sfx_volume")"""
    snd = plan.get("sound", {})
    cues = []
    for line in plan["lines"]:
        if not line["keep"]:
            continue
        ids = [i for i in line["words"] if i in timed]
        if not ids:
            continue
        s = timed[ids[0]][0]
        if line.get("sfx"):
            if line["sfx"] != "none":
                cues.append((max(0.0, s - 0.05), line["sfx"], line.get("sfx_volume", 1.0)))
            continue
        if not snd.get("sfx", True):
            continue
        t = line["treatment"]
        if t == "takeover":
            cues.append((max(0.0, s - 0.15), "whoosh", 1.0))
        elif t == "stat pop":
            num = next((i for i in ids if re.search(r"\d", words[i]["text"])), ids[0])
            cues.append((max(0.0, timed[num][0] - 0.1), "pop", 1.0))
        elif t == "step":
            cues.append((s, "click", 1.0))
    if snd.get("sfx", True):
        for a, _, spec in windows:
            if not any(abs(c[0] - a) < 0.3 for c in cues):
                cues.append((max(0.0, a - 0.1), "swoosh", 1.0))
    return sorted(cues)


def find_sfx(name):
    for ext in (".wav", ".mp3", ".m4a", ".aif", ".aiff"):
        p = SFX_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


# ---------- build ----------

def scene_cuts(video):
    """times of hard cuts already inside the footage (eg a compilation). cached per file."""
    st = Path(video).stat()
    cache = WORK_DIR / "_scenes" / f"{st.st_ino}.json"     # by file identity, so linked copies share it
    if cache.exists():
        c = load_json(cache)
        if c.get("stamp") == f"{st.st_size}-{int(st.st_mtime)}":
            return c["cuts"]
    res = run([find_bin("ffmpeg"), "-hide_banner", *vin(video), "-an", "-vf",
               "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time", "-f", "null", "-"])
    cuts = [float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", res.stdout + res.stderr)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    save_json(cache, {"stamp": f"{st.st_size}-{int(st.st_mtime)}", "cuts": cuts})
    return cuts


def silence_map(video):
    """[(start, end)] of every quiet stretch in the clip's audio."""
    res = run([find_bin("ffmpeg"), "-hide_banner", "-i", str(video), "-map", "0:a:0",
               "-af", "silencedetect=noise=-35dB:d=0.08", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    return [(max(0.0, a), b) for a, b in zip(starts, ends + [float("inf")])]


def build(video, wd, plan, tr, st, opts):
    """returns (inputs, filter_lines, labels) for ffmpeg."""
    words = [dict(w) for w in tr["words"]]
    # cuts follow the real audio: hook lands instantly and no word gets clipped
    segs, timed = build_segments(plan, words, silence_map(video), scene_cuts(video))
    if not segs:
        die("every line is marked as cut - nothing left to render")
    assign_zoom(segs, st)
    total = segs[-1]["new_end"]

    captions = caption_events(plan, words, timed, st, total)
    graphics = overlay_events(plan, words, timed, total, st)
    write_ass(wd / "captions.ass", st, captions)
    write_ass(wd / "graphics.ass", st, graphics)
    windows = broll_windows(plan, timed, total, [s["new_start"] for s in segs] + [total])

    # each shot reads only its own stretch of the source (no decoding the whole file)
    inputs = [vin(video, "-ss", f"{s['start']:.3f}", "-t", f"{s['end'] - s['start'] + 0.3:.3f}")
              for s in segs]
    f = []
    for k, s in enumerate(segs):
        f.append(f"[{k}:v]setpts=PTS-STARTPTS,"
                 f"{sdr_filter(video)}{frame_filter(s, tr['width'], tr['height'])},"
                 f"tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={s['frames']}[v{k}];")
        fo = max(0.0, s["end"] - s["start"] - 0.012)
        f.append(f"[{k}:a]atrim=0:{s['end'] - s['start']:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d=0.012,afade=t=out:st={fo:.3f}:d=0.012[a{k}];")
    f.append("".join(f"[v{k}][a{k}]" for k in range(len(segs))) +
             f"concat=n={len(segs)}:v=1:a=1[vc][speech];")

    # grade the talking head only. b-roll goes on after, untouched (it's already edited)
    grade = opts["grade"]
    f.append(f"[vc]{grade if grade else 'null'}[vcg];")

    # b-roll on top of the edit, under the text
    cur = "vcg"
    for n, (a, b, spec) in enumerate(windows):
        idx = len(inputs)
        if spec["path"].suffix.lower() in IMAGE_EXTS:
            inputs.append(["-loop", "1", "-t", f"{b - a + 0.5:.3f}", "-i", str(spec["path"])])
        else:
            inputs.append(vin(spec["path"], "-ss", f"{float(spec.get('start', 0)):.3f}", "-t", f"{b - a + 0.5:.3f}"))
        f.append(broll_filter(idx, a, b, spec, grade) + f"[br{n}];")
        pos = "x=W-w-40:y=140" if spec.get("mode") == "pip" else "x=0:y=0"
        f.append(f"[{cur}][br{n}]overlay={pos}:enable='between(t,{a:.3f},{b:.3f})':eof_action=pass[vb{n}];")
        cur = f"vb{n}"

    f.append(f"[{cur}]null[graded];")

    # ---- audio: speech, ducked music, sound effects
    snd = plan.get("sound", {})
    music = opts.get("music") or snd.get("music")
    sound_labels = []
    if music:
        mp = Path(music)
        if not mp.is_absolute():
            mp = ROOT / mp
        if not mp.exists():
            die(f"can't find the music file {music}")
        idx = len(inputs)
        inputs.append(["-stream_loop", "-1", "-i", str(mp)])
        vol = opts.get("music_volume") or snd.get("music_volume", 0.12)
        f.append("[speech]asplit=3[sp][sc][spx];")
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},"
                 f"atrim=0:{total:.3f},afade=t=out:st={max(0, total - 1.2):.3f}:d=1.2[mraw];")
        f.append("[sc]aformat=sample_rates=48000:channel_layouts=stereo[scs];")
        f.append("[mraw][scs]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[music];")
        sound_labels.append("music")
    else:
        f.append("[speech]asplit=2[sp][spx];")
    cues = sfx_cues(plan, words, timed, windows)
    missing = set()
    sv = snd.get("sfx_volume", 0.5)
    for n, (t, name, vol) in enumerate(cues):
        path = find_sfx(name)
        if not path:
            missing.add(name)
            continue
        idx = len(inputs)
        inputs.append(["-i", str(path)])
        ms = int(t * 1000)
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={sv * vol:.3f},"
                 f"adelay={ms}|{ms}[fx{n}];")
        sound_labels.append(f"fx{n}")
    f.append("[spx]anullsink;")
    return {"inputs": inputs, "filters": f, "segs": segs, "timed": timed, "total": total,
            "captions": captions, "graphics": graphics, "windows": windows, "cues": cues,
            "missing_sfx": sorted(missing), "sound_labels": sound_labels, "music": music}


def mix(labels, out_label, total, with_speech=True, loud=True):
    ins = (["sp"] if with_speech else []) + labels
    if not ins:
        return f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[{out_label}]"
    chain = "".join(f"[{l}]" for l in ins)
    if len(ins) == 1:
        chain += "aformat=sample_rates=48000:channel_layouts=stereo"
    else:
        chain += f"amix=inputs={len(ins)}:duration=first:normalize=0"
    if loud:
        chain += ",loudnorm=I=-14:TP=-1.5:LRA=11"
    return chain + f",atrim=0:{total:.3f}[{out_label}]"


def encode(cmd_inputs, filters, maps, out, wd, draft, video_codec=None):
    (wd / "filter.txt").write_text("\n".join(filters), encoding="utf-8")
    cmd = [find_bin("ffmpeg"), "-y"]
    for i in cmd_inputs:
        cmd += i
    cmd += ["-/filter_complex", "filter.txt"] + maps
    cmd += video_codec or [*h264(draft), "-r", str(FPS)]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    run(cmd, cwd=wd)


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, plan, words, timed, st, total):
    n = max(3, int(st.get("words_per_caption", 3)))
    order = sorted(timed)
    out, k = [], 1
    for line in plan["lines"]:
        if not line["keep"] or line["treatment"] == "takeover":
            continue
        ids = [i for i in line["words"] if i in timed and words[i]["text"].strip()]
        shown, _, glue = cased_words(line, ids, words, st, strip_punct=False)
        for chunk in chunked(ids, n, glue):
            a = timed[chunk[0]][0]
            nxt = next((i for i in order if i > chunk[-1]), None)
            b = min(timed[chunk[-1]][1] + 0.25, timed[nxt][0] if nxt is not None else total)
            text = " ".join(shown[i] for i in chunk)
            out.append(f"{k}\n{srt_time(a)} --> {srt_time(max(b, a + 0.2))}\n{text}\n")
            k += 1
    path.write_text("\n".join(out), encoding="utf-8")


# ---------- main ----------

# ---------- cut previews: render only a moment either side of each cut ----------

def _shift_events(events, a, b):
    """caption/graphic events inside [a, b], moved so a = 0."""
    out = []
    for s, e, style, text in events:
        if e > a and s < b:
            out.append((max(s, a) - a, min(e, b) - a, style, text))
    return out


def _render_windows(video, wins, segs, b, tr, grade, st_ass, pdir, clips, report, kind="cut"):
    for wi, (lo, hi, pts) in enumerate(wins, 1):
        inputs, f, vl, al = [], [], [], []
        # the talking-head pieces that fall inside this window
        for s in segs:
            if s["new_end"] <= lo or s["new_start"] >= hi:
                continue
            off_a = max(0.0, lo - s["new_start"])
            off_b = max(0.0, s["new_end"] - hi)
            length = s["end"] - s["start"]
            piece = dict(s)
            piece["start"], piece["end"] = s["start"] + off_a, s["end"] - off_b
            z = lambda t: s["z0"] + (s["z1"] - s["z0"]) * (t / length if length else 0)
            piece["z0"], piece["z1"] = z(off_a), z(length - off_b)
            frames = max(1, round((piece["end"] - piece["start"]) * FPS))
            k = len(vl)
            inputs.append(vin(video, "-ss", f"{piece['start']:.3f}", "-t", f"{piece['end'] - piece['start'] + 0.3:.3f}"))
            f.append(f"[{k}:v]setpts=PTS-STARTPTS,{sdr_filter(video)}{frame_filter(piece, tr['width'], tr['height'])},"
                     f"tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={frames}[v{k}];")
            f.append(f"[{k}:a]atrim=0:{piece['end'] - piece['start']:.3f},asetpts=PTS-STARTPTS[a{k}];")
            vl.append(f"[v{k}]")
            al.append(f"[a{k}]")
        n = len(vl)
        f.append("".join(v + a for v, a in zip(vl, al)) + f"concat=n={n}:v=1:a=1[vc][speech];")
        f.append(f"[vc]{grade if grade else 'null'}[vcg];")
        cur = "vcg"
        for bi, (a, e, spec) in enumerate(b["windows"]):
            if e <= lo or a >= hi:
                continue
            a2, e2 = max(a, lo) - lo, min(e, hi) - lo
            spec2 = {**spec, "start": float(spec.get("start", 0)) + max(0.0, lo - a)}
            idx = len(inputs)
            if spec["path"].suffix.lower() in IMAGE_EXTS:
                inputs.append(["-loop", "1", "-t", f"{e2 - a2 + 0.5:.3f}", "-i", str(spec["path"])])
            else:
                inputs.append(vin(spec["path"], "-ss", f"{spec2['start']:.3f}", "-t", f"{e2 - a2 + 0.5:.3f}"))
            f.append(broll_filter(idx, a2, e2, spec2, grade) + f"[br{bi}];")
            f.append(f"[{cur}][br{bi}]overlay=0:0:enable='between(t,{a2:.3f},{e2:.3f})':eof_action=pass[vb{bi}];")
            cur = f"vb{bi}"
        write_ass(pdir / f"cap_{wi}.ass", st_ass, _shift_events(b["captions"], lo, hi))
        write_ass(pdir / f"gfx_{wi}.ass", st_ass, _shift_events(b["graphics"], lo, hi))
        label = " + ".join(f"{p:.1f}s" for p in pts)
        f.append(f"[{cur}]subtitles=gfx_{wi}.ass:fontsdir=../../../fonts,subtitles=cap_{wi}.ass:fontsdir=../../../fonts,"
                 f"drawtext=text='{kind} {wi} at {label}':x=30:y=40:fontsize=24:fontcolor=yellow:box=1:boxcolor=black@0.6,"
                 f"format=yuv420p[vout];")
        f.append(f"[speech]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"apad=whole_dur={hi - lo:.3f},atrim=0:{hi - lo:.3f}[aout]")
        (pdir / "filter.txt").write_text("\n".join(f), encoding="utf-8")
        out = pdir / f"{kind}_{wi:02d}.mp4"
        cmd = [find_bin("ffmpeg"), "-y"]
        for i in inputs:
            cmd += i
        cmd += ["-/filter_complex", "filter.txt", "-map", "[vout]", "-map", "[aout]",
                *h264(draft=True), "-r", str(FPS),
                "-c:a", "aac", "-b:a", "128k", "-t", f"{hi - lo:.3f}", str(out)]
        run(cmd, cwd=pdir)
        # stray-frame check on this window: two picture changes < 0.4s apart = a flash
        r = run([find_bin("ffmpeg"), "-hide_banner", *vin(out), "-vf",
                 "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time", "-an", "-f", "null", "-"])
        det = [float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", r.stdout + r.stderr)]
        flashes = [round(lo + x, 2) for x, y in zip(det, det[1:]) if y - x < 0.4]
        report.append((wi, label, flashes))
        clips.append(out)


def preview_cuts(video, wd, plan, tr, st, b, grade, pad=1.5, only=None):
    """same edit as the full render, but only ~pad seconds either side of every cut
    (shot changes + b-roll in/out). each window is checked for stray frames, then all
    windows are joined into one labelled preview. much faster than a full render."""
    segs, total = b["segs"], b["total"]
    points = [s["new_start"] for s in segs[1:]]
    for a, e, _ in b["windows"]:
        points += [a, e]
    points = sorted(p for p in set(round(p, 3) for p in points) if 0 < p < total - 0.05)
    # one window per cut, merging cuts that sit close together
    wins = []
    for p in points:
        lo, hi = max(0.0, p - pad), min(total, p + pad)
        if wins and lo <= wins[-1][1]:
            wins[-1] = (wins[-1][0], hi, wins[-1][2] + [p])
        else:
            wins.append((lo, hi, [p]))
    if only:
        wins = [w for i, w in enumerate(wins, 1) if i in only]
    if not wins:
        print("[engine] no cuts to preview")
        return None
    pdir = wd / "cut_previews"
    pdir.mkdir(exist_ok=True)
    for old in pdir.glob("*.mp4"):
        old.unlink()
    st_ass = dict(st)
    clips, report = [], []
    global W, H
    full_wh, (W, H) = (W, H), (W // 2, H // 2)     # half size: plenty to spot glitches, ~4x faster
    try:
        _render_windows(video, wins, segs, b, tr, grade, st_ass, pdir, clips, report)
    finally:
        W, H = full_wh
    lst = pdir / "list.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    joined = OUTPUT_DIR / f"{wd.name}_cuts_preview.mp4"
    run([find_bin("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], cwd=pdir)
    print(f"[engine] cut preview: {len(clips)} cuts, {sum(h - l for l, h, _ in wins):.1f}s of "
          f"{total:.1f}s rendered -> {joined.relative_to(ROOT)}")
    for wi, label, flashes in report:
        print(f"  cut {wi:2} at {label:>14}: " + (f"FLASH at {flashes}" if flashes else "clean"))
    return joined


def preview_spots(video, wd, tr, st, b, grade, spots, pad=1.5, name="spot"):
    """full-size render of just the trouble spots: `pad` seconds either side of each time
    (finished-reel time), labelled, joined into output/<clip>_<name>.mp4 for her to judge by ear."""
    total = b["total"]
    wins = []
    for p in sorted(spots):
        lo, hi = max(0.0, p - pad), min(total, p + pad)
        if wins and lo <= wins[-1][1]:
            wins[-1] = (wins[-1][0], hi, wins[-1][2] + [p])
        else:
            wins.append((lo, hi, [p]))
    pdir = wd / f"{name}_previews"
    pdir.mkdir(exist_ok=True)
    for old in pdir.glob("*.mp4"):
        old.unlink()
    clips, report = [], []
    _render_windows(video, wins, b["segs"], b, tr, grade, dict(st), pdir, clips, report, kind="spot")
    lst = pdir / "list.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    joined = OUTPUT_DIR / f"{wd.name}_{name}.mp4"
    run([find_bin("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], cwd=pdir)
    print(f"[engine] spot preview: {len(clips)} spot(s) -> {joined.relative_to(ROOT)}")
    for wi, label, flashes in report:
        print(f"  spot {wi:2} at {label:>14}: " + (f"FLASH at {flashes}" if flashes else "clean"))
    return joined


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--style", default=None, help="override the style in plan.json")
    ap.add_argument("--music", default=None, help="override the music track in plan.json")
    ap.add_argument("--music-volume", type=float, default=None)
    ap.add_argument("--draft", action="store_true", help="quick low-quality preview")
    ap.add_argument("--no-grade", action="store_true", help="skip the colour grade")
    ap.add_argument("--cover", action="store_true", help="also save a cover image")
    ap.add_argument("--capcut", action="store_true",
                    help="also export a layer pack to finish in capcut")
    ap.add_argument("--cuts", action="store_true",
                    help="only render ~1.5s either side of every cut, check each for stray frames")
    ap.add_argument("--pad", type=float, default=1.5, help="seconds either side of a cut for --cuts")
    ap.add_argument("--only", default=None, help="with --cuts: just these cut numbers, eg 3,7")
    ap.add_argument("--spot", default=None,
                    help="only render around these times in the finished reel (secs), eg 8 or 8,41.5")
    ap.add_argument("--plan", default=None,
                    help="use another plan file (eg work/<clip>/plan_b.json) to try a fix without touching plan.json")
    args = ap.parse_args()

    video = resolve_video(args.video)
    wd = work_dir_for(video)
    tr = load_json(wd / "transcript.json")
    plan_path = Path(args.plan) if args.plan else wd / "plan.json"
    plan = load_json(plan_path)
    style_name = args.style or plan.get("style", "beth")
    st = load_style(style_name)
    grade = "" if args.no_grade else grade_filter(load_grade(), has_huesaturation())
    bad = contrast_problems(st, plan)
    if bad:
        die("on-screen text too hard to read (needs at least "
            f"{MIN_RATIO}:1 contrast against its background):\n" + "\n".join(
                f"  {n}: {fg} on {bg} = {r:.1f}:1" for n, fg, bg, r in bad)
            + "\nfix the colours in the style (badge_text_colour / badge_bg, takeover_text_colour / "
              "takeover_bg, hook_text_colour / hook_box_colour) and render again")
    b = build(video, wd, plan, tr, st, {"grade": grade, "music": args.music,
                                         "music_volume": args.music_volume})
    total = b["total"]
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.spot:
        spots = [float(x) for x in args.spot.split(",")]
        name = "spot" + ("" if plan_path.name == "plan.json" else "_" + plan_path.stem)
        preview_spots(video, wd, tr, st, b, grade, spots, args.pad, name)
        return

    if args.cuts:
        only = {int(x) for x in args.only.split(",")} if args.only else None
        preview_cuts(video, wd, plan, tr, st, b, grade, args.pad, only)
        return

    # ---- the finished reel
    f = list(b["filters"])
    f.append("[graded]subtitles=graphics.ass:fontsdir=../../fonts,"
             "subtitles=captions.ass:fontsdir=../../fonts[vout];")
    f.append(mix(b["sound_labels"], "aout", total))
    out = OUTPUT_DIR / f"{wd.name}_{style_name}{'_draft' if args.draft else ''}.mp4"
    print(f"[engine] rendering {len(b['segs'])} cuts, {total:.1f}s, style '{style_name}'"
          f"{', graded' if grade else ''}, {len(b['windows'])} b-roll, {len(b['cues'])} sound fx"
          f"{', music' if b['music'] else ''}...")
    encode(b["inputs"], f, ["-map", "[vout]", "-map", "[aout]"], out, wd, args.draft)
    if b["missing_sfx"]:
        print(f"[engine] note: no sound file for {', '.join(b['missing_sfx'])} in sfx/ - "
              "run engine/sfx.py to make the defaults")

    cover = None
    if args.cover:
        cover = OUTPUT_DIR / f"{wd.name}_{style_name}_cover.jpg"
        run([find_bin("ffmpeg"), "-y", *vin(out, "-ss", f"{min(1.0, total / 2):.2f}"),
             "-frames:v", "1", "-q:v", "2", str(cover)])

    # ---- capcut layer pack
    pack = None
    if args.capcut:
        pack = OUTPUT_DIR / f"{wd.name}_capcut"
        pack.mkdir(exist_ok=True)
        print("[engine] exporting capcut layers...")
        # 1. clean video: edit + zooms + b-roll + grade, your voice only, no text
        f = list(b["filters"])
        f.append("[graded]null[vout];")
        f += [f"[{l}]anullsink;" for l in b["sound_labels"]]
        f.append(mix([], "aout", total))
        encode(b["inputs"], f, ["-map", "[vout]", "-map", "[aout]"],
               pack / "1_video_clean.mp4", wd, False)
        # 2. graphics: hook, stat pops, badges, takeovers on a transparent background
        mat = re.sub(r"&H[0-9A-Fa-f]{8}", "&H00FFFFFF",
                     (wd / "graphics.ass").read_text(encoding="utf-8"))
        mat = re.sub(r"\\(1?c)&H[0-9A-Fa-f]{6,8}&?", r"\\1c&HFFFFFF&", mat)
        (wd / "graphics_matte.ass").write_text(mat, encoding="utf-8")
        # h.264 can't hold transparency, so: the graphics on black + a black/white matte (white = show)
        run([find_bin("ffmpeg"), "-y", "-f", "lavfi", "-i",
             f"color=c=black:s={W}x{H}:r={FPS}:d={total:.3f}", "-filter_complex",
             "[0:v]split[a][b];[a]subtitles=graphics.ass:fontsdir=../../fonts[rgb];"
             "[b]subtitles=graphics_matte.ass:fontsdir=../../fonts[m]",
             "-map", "[rgb]", *h264(), "-r", str(FPS), "-movflags", "+faststart", str(pack / "2_graphics_on_black.mp4"),
             "-map", "[m]", *h264(), "-r", str(FPS), "-movflags", "+faststart", str(pack / "2_graphics_matte.mp4")],
            cwd=wd)
        # 3. captions as editable text
        write_srt(pack / "3_captions.srt", plan, tr["words"], b["timed"], st, total)
        # 4. music + sound effects without your voice
        if b["sound_labels"]:
            f = list(b["filters"])
            f.append("[graded]nullsink;[sp]anullsink;")
            f.append(mix(b["sound_labels"], "aout", total, with_speech=False, loud=False))
            (wd / "filter.txt").write_text("\n".join(f), encoding="utf-8")
            cmd = [find_bin("ffmpeg"), "-y"]
            for i in b["inputs"]:
                cmd += i
            run(cmd + ["-/filter_complex", "filter.txt", "-map", "[aout]",
                       "-c:a", "pcm_s16le", str(pack / "4_music_and_sfx.wav")], cwd=wd)
        (pack / "HOW_TO_OPEN_IN_CAPCUT.txt").write_text(CAPCUT_HELP, encoding="utf-8")

    save_json(wd / "edl.json", {
        "output": str(out), "cover": str(cover) if cover else None, "capcut_pack": str(pack) if pack else None,
        "style": style_name, "duration": total, "graded": bool(grade), "music": bool(b["music"]),
        "broll": [{"start": a, "end": e, "file": str(s["file"])} for a, e, s in b["windows"]],
        "sfx": [{"time": t, "name": n, "volume": v} for t, n, v in b["cues"]], "missing_sfx": b["missing_sfx"],
        "segments": [{k: s[k] for k in ("start", "end", "new_start", "new_end", "line", "motion", "z0", "z1")}
                     for s in b["segs"]],
        "kept_word_count": len([i for l in plan["lines"] if l["keep"] and l["treatment"] != "takeover"
                                for i in l["words"] if i in b["timed"]]),
        "caption_events": sum(1 for e in b["captions"] if e[2] == "Caption"),
        "has_hook": bool(plan.get("hook_text")),
    })
    print(f"[engine] rendered {out}" + (f"\n[engine] cover    {cover}" if cover else ""))
    if pack:
        print(f"[engine] capcut   {pack}")


CAPCUT_HELP = """how to finish this reel in capcut (desktop)

1. new project. drag in 1_video_clean.mp4 - this is your cut, zooms, b-roll and colour grade,
   with your voice. no text on it.
2. drag 2_graphics_on_black.mp4 onto the track ABOVE the video, lined up at the start.
   it holds the hook card, stat pops, step badges and takeovers on black.
   to drop the black: drag 2_graphics_matte.mp4 above it and use it as a luma / track matte
   (white = show), or set the graphics layer's blend mode to "screen" (fine for white text,
   pale backgrounds can look washed out). or skip both and add the hook text in capcut.
3. captions: import 3_captions.srt (captions > import, if your capcut has it) and every caption
   lands as editable text you can restyle. or use capcut's auto captions instead and delete
   this file.
4. if there's a 4_music_and_sfx.wav, drag it onto an audio track at the start. it's already
   ducked under your voice. delete it if you'd rather pick music from capcut's library.
5. tweak anything, export, post.

every file starts at 0:00, so lining them up at the very start keeps everything in sync.
"""


if __name__ == "__main__":
    main()
