"""step 3: render the approved plan into a finished, graded 9:16 reel.

usage: python -m engine render [video] [--brand <name>] [--style <style>] [--music track.mp3] [--draft] [--no-grade]
(brand and style default to the ones saved in plan.json)

how a render is put together:
  1. timeline   the kept words become segments of the source clip, snapped to the real audio
  2. framing    each segment gets its zoom (slow push, jump cut, punch-in) and is cropped to 9:16
  3. text       captions and graphics (hook, stat pops, badges, takeovers) are written as .ass files
  4. b-roll     laid over the edit on its lines, after the grade
  5. sound      speech, ducked music and sound effects, levelled for social
  6. encode     one ffmpeg run reads a filter script (filter.txt) and writes the reel
"""
import argparse
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from engine.core.brand import add_brand_arg, get_brand, load_style
from engine.core.common import (IMAGE_EXTS, OUTPUT_DIR, ROOT, SFX_DIR, WORK_DIR, die, find_bin, h264, load_json,
                                norm, resolve_video, run, save_json, sdr_filter, vin, work_dir_for)
from engine.core.contrast import MIN_RATIO, badge_colours, problems as contrast_problems, takeover_colours
from engine.core.grade import grade_filter, has_huesaturation, load_grade

# ---------- output ----------
FRAME_W, FRAME_H = 1080, 1920   # 9:16. cut previews swap in half size, see half_size_frames()
FPS = 30
SAMPLE_RATE = 48000
FONTS_FROM_WORK_DIR = "../../assets/fonts"           # ffmpeg runs inside work/<clip>/
FONTS_FROM_PREVIEW_DIR = "../../../assets/fonts"     # ...or inside work/<clip>/<x>_previews/

# ---------- timeline ----------
JOIN_GAP = 0.30          # pauses shorter than this stay in (natural breathing)
PAD_BEFORE = 0.06        # extra source kept before a segment's first word
PAD_AFTER = 0.14         # ...and after its last word
TAIL = 0.35              # extra hold after the very last word
SNAP_BACK_MAX = 0.25     # how far a cut may back up to the silence before a word
SNAP_ON_MAX = 0.5        # how far a cut may run on to the silence after a word
SNAP_ON_DEFAULT = 0.25   # run-on when no silence is close enough
WORD_EDGE = 0.05         # tolerance at a word's edges (timing noise in the transcript)
SCENE_NUDGE = 0.01       # how far past a built-in scene cut a segment is moved
SOURCE_READ_EXTRA = 0.3  # each segment reads this much spare source past its end
SEGMENT_FADE = 0.012     # tiny audio fade on every cut, so joins don't click

# ---------- framing ----------
FACE_Y = 0.42            # crop a little above centre, where faces usually are
SLOW_ZOOM = 1.07         # defaults when the style doesn't set them
JUMP_ZOOM = 1.12
PUNCH_ZOOM = 1.25

# ---------- captions + graphics ----------
CAPTION_HOLD = 0.25      # a caption stays this long after its last word (unless the next one starts)
CAPTION_MIN = 0.12       # shortest a caption is ever on screen
BUILD_STEP_MIN = 0.04    # shortest step of a build-up caption
GRAPHIC_HOLD = 0.2       # graphics stay this long after a line's last word
HOOK_TOP = 230           # y of the hook's first line
HOOK_SECS = 3.0          # hook on screen for the first line, between these limits
HOOK_MIN_SECS, HOOK_MAX_SECS = 2.0, 3.5
STAT_POS = "{\\pos(540,700)}"
STAT_COUNT_STEPS = 8     # big numbers count up in this many steps...
STAT_COUNT_STEP_SECS = 0.06   # ...this long each, then pop
STAT_LEAD = 0.1          # stat lands just before its number is said
SRT_WORDS_MIN = 3        # capcut captions: at least this many words each
SRT_MIN_SECS = 0.2

# ---------- b-roll ----------
BROLL_LEAD = 0.05        # b-roll starts this long before the line's first word...
BROLL_TAIL = 0.15        # ...and ends this long after its last word
SNAP_TO_CUT = 0.2        # b-roll edges this close to a cut move onto it
BROLL_JOIN_GAP = 0.6     # b-roll this close together runs straight through
BROLL_SCENE_SKIP = 1.5   # a built-in scene cut this soon after the b-roll start: start after it
BROLL_SCENE_NUDGE = 0.04
BROLL_READ_EXTRA = 0.5
BROLL_PUSH = 0.05        # gentle push so stills and static shots don't look dead
PIP_W, PIP_H = 420, 560
PIP_PLACE = "x=W-w-40:y=140"   # ffmpeg overlay expression: top right, 40px in

# ---------- sound ----------
SFX_EXTS = (".wav", ".mp3", ".m4a", ".aif", ".aiff")
SFX_LEAD = 0.05          # a line's own sound effect plays just before it
WHOOSH_LEAD = 0.15
SWOOSH_LEAD = 0.1
SFX_NEAR = 0.3           # no automatic swoosh within this of another sound
MUSIC_VOLUME = 0.12
SFX_VOLUME = 0.5
MUSIC_FADE_OUT = 1.2
MUSIC_DUCK = "threshold=0.02:ratio=6:attack=15:release=350"
LOUDNESS = "I=-14:TP=-1.5:LRA=11"     # what instagram / tiktok play back at
STEREO = f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo"

# ---------- checks ----------
SCENE_DETECT = "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time"
FLASH_GAP = 0.4          # two picture changes closer than this = a stray frame
SILENCE_DETECT = "silencedetect=noise=-35dB:d=0.08"


# ---------- timeline ----------

def snap_to_audio(segments, words, silences):
    """the transcriber's word times are often a little short. move each cut out to where the
    voice really stops/starts, so no word gets clipped, without reaching into a neighbouring word."""
    def silence_at(time):
        return next(((start, end) for start, end in silences if start <= time <= end), None)

    for seg in segments:
        first_word, last_word = seg["words"][0], seg["words"][-1]
        earliest = words[first_word - 1]["end"] if first_word > 0 else 0.0
        latest = words[last_word + 1]["start"] if last_word + 1 < len(words) else float("inf")
        silence = silence_at(seg["start"])
        if silence:             # "word" starts in silence: start on the voice instead
            if silence[1] < words[first_word]["end"] - WORD_EDGE:
                seg["start"] = silence[1]
        else:                   # starts mid-sound: back up to the silence just before it
            before = [end for start, end in silences if end <= seg["start"] and seg["start"] - end <= SNAP_BACK_MAX]
            if before:
                seg["start"] = max(before[-1], earliest)
        if not silence_at(seg["end"]):   # ends mid-sound: run on until the voice stops
            after = [start for start, end in silences if start >= seg["end"] and start - seg["end"] <= SNAP_ON_MAX]
            seg["end"] = min(after[0] if after else seg["end"] + SNAP_ON_DEFAULT, max(latest, seg["end"]))
        if silence:
            words[first_word]["start"] = seg["start"]


def same_shot(a, b):
    """two pieces stay one shot unless a punch-in starts or ends between them."""
    return a["line"] == b["line"] or "punch" not in (a["motion"], b["motion"])


def build_segments(plan, words, silences=None, scenes=None):
    """the kept words -> segments of the source clip, plus each word's (start, end) on the new timeline."""
    kept = []
    for line in plan["lines"]:
        if line["keep"]:
            cut = set(line["cut_words"])
            kept += [(word_id, line) for word_id in line["words"] if word_id not in cut]
    segments, current = [], None
    for word_id, line in kept:
        word = words[word_id]
        # keep one shot while the speech runs on: only change framing where something was cut,
        # or for a deliberate punch-in. (zooming mid-sentence with no cut looks like a glitch)
        if (current and same_shot(current, {"line": line["id"], "motion": line.get("motion")})
                and word_id == current["last"] + 1
                and word["start"] - words[current["last"]]["end"] <= JOIN_GAP):
            current.update(end=word["end"], last=word_id)
            current["words"].append(word_id)
        else:
            current = {"start": word["start"], "end": word["end"], "last": word_id, "line": line["id"],
                       "motion": line.get("motion", "none"), "words": [word_id]}
            segments.append(current)
    if silences:
        snap_to_audio(segments, words, silences)
        # pieces that now run straight on in the source are one shot, not a cut
        merged = [segments[0]] if segments else []
        for seg in segments[1:]:
            previous = merged[-1]
            if seg["start"] - previous["end"] <= JOIN_GAP and same_shot(previous, seg):
                previous.update(end=max(previous["end"], seg["end"]), last=seg["last"])
                previous["words"] += seg["words"]
            else:
                merged.append(seg)
        segments = merged
    segments[-1]["end"] += TAIL if segments else 0   # let the last word ring out before the reel ends
    for index, seg in enumerate(segments):
        seg["start"] = max(0.0, seg["start"] - PAD_BEFORE)
        seg["end"] += PAD_AFTER
        # never straddle a cut that's already in the footage (a flash of another scene looks glitchy)
        for scene_cut in scenes or []:
            if seg["start"] < scene_cut < seg["end"]:
                first = words[seg["words"][0]]["start"]
                last = words[seg["words"][-1]]["end"]
                if scene_cut <= first + WORD_EDGE:
                    seg["start"] = scene_cut + SCENE_NUDGE
                elif scene_cut >= last - WORD_EDGE:
                    seg["end"] = scene_cut - SCENE_NUDGE
        if index and seg["start"] < segments[index - 1]["end"]:
            mid = (seg["start"] + segments[index - 1]["end"]) / 2
            segments[index - 1]["end"] = seg["start"] = mid
    position, timed = 0.0, {}
    for seg in segments:
        # whole frames only, so the real cut points match the timeline (b-roll ends exactly on them)
        seg["frames"] = max(1, round((seg["end"] - seg["start"]) * FPS))
        seg["end"] = seg["start"] + seg["frames"] / FPS
        seg["new_start"] = position
        for word_id in seg["words"]:
            timed[word_id] = (position + words[word_id]["start"] - seg["start"],
                              position + words[word_id]["end"] - seg["start"])
        position += seg["end"] - seg["start"]
        seg["new_end"] = position
    return segments, timed


def assign_zoom(segments, style):
    """work out the zoom for every cut (z0 at its start, z1 at its end).
    slow zooms span the whole line, not each cut."""
    line_spans = {}
    for seg in segments:
        start, end = line_spans.get(seg["line"], (seg["new_start"], seg["new_end"]))
        line_spans[seg["line"]] = (min(start, seg["new_start"]), max(end, seg["new_end"]))
    jump_in = False
    for seg in segments:
        motion = seg["motion"]
        if motion == "slow":
            line_start, line_end = line_spans[seg["line"]]
            span = max(line_end - line_start, 0.01)
            final_zoom = style.get("slow_zoom", SLOW_ZOOM)
            seg["z0"] = 1 + (final_zoom - 1) * (seg["new_start"] - line_start) / span
            seg["z1"] = 1 + (final_zoom - 1) * (seg["new_end"] - line_start) / span
        elif motion == "jump":
            jump_in = not jump_in
            seg["z0"] = seg["z1"] = style.get("jump_zoom", JUMP_ZOOM) if jump_in else 1.0
        elif motion == "punch":
            seg["z0"] = seg["z1"] = style.get("punch_zoom", PUNCH_ZOOM)
        else:
            seg["z0"] = seg["z1"] = 1.0


def frame_filter(seg, src_w, src_h):
    """cover-fit to 9:16 and zoom down to the output size.
    still framing (jump cuts, punch-ins, no zoom): crop the exact same window straight from the
    source and scale once. ~6x less work than going via a 2x copy, identical framing.
    slow push: cover-fit at 2x, then zoompan, so the moving crop lands on half pixels and doesn't judder."""
    if abs(seg["z1"] - seg["z0"]) < 1e-4:
        scale = max(FRAME_W / src_w, FRAME_H / src_h) * seg["z0"]
        crop_w, crop_h = min(src_w, FRAME_W / scale), min(src_h, FRAME_H / scale)
        return (f"crop={crop_w:.2f}:{crop_h:.2f}:{(src_w - crop_w) / 2:.2f}:{(src_h - crop_h) * FACE_Y:.2f},"
                f"scale={FRAME_W}:{FRAME_H},setsar=1,fps={FPS}")
    scale = max(2 * FRAME_W / src_w, 2 * FRAME_H / src_h)
    big_w, big_h = int(src_w * scale) // 2 * 2, int(src_h * scale) // 2 * 2
    base = (f"scale={big_w}:{big_h},crop={2 * FRAME_W}:{2 * FRAME_H}:(iw-{2 * FRAME_W})/2:(ih-{2 * FRAME_H})*{FACE_Y},"
            f"setsar=1,fps={FPS}")
    frames = max(1, round((seg["end"] - seg["start"]) * FPS))
    zoom = f"{seg['z0']:.5f}+{seg['z1'] - seg['z0']:.5f}*on/{frames}"
    return (base + f",zoompan=z='{zoom}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*{FACE_Y}'"
            f":d=1:s={FRAME_W}x{FRAME_H}:fps={FPS}")


@contextmanager
def half_size_frames():
    """cut previews render at half size: plenty to spot glitches, ~4x faster. every filter and
    caption file reads FRAME_W / FRAME_H when it's built, so they're swapped while this is open."""
    global FRAME_W, FRAME_H
    full_size = FRAME_W, FRAME_H
    FRAME_W, FRAME_H = FRAME_W // 2, FRAME_H // 2
    try:
        yield
    finally:
        FRAME_W, FRAME_H = full_size


# ---------- captions + overlays (ASS) ----------

def ass_colour(hex_colour, alpha=0):
    rgb = hex_colour.lstrip("#")
    return f"&H{alpha:02X}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def ass_time(secs):
    secs = max(0.0, secs)
    return f"{int(secs // 3600)}:{int(secs % 3600 // 60):02d}:{secs % 60:05.2f}"


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def ass_header(style):
    colour = ass_colour
    bold = -1 if style.get("bold") else 0
    italic_hook = -1 if style.get("italic_hook") else 0
    caption_margin = int(FRAME_H * (1 - style["caption_position"]))
    takeover_text, takeover_bg = takeover_colours(style)
    badge_text, badge_bg = badge_colours(style)
    spacing = style.get("spacing", 0)
    if style.get("hook_box", True):
        hook_look = (f"{colour(style['hook_box_colour'])},{colour(style['hook_box_colour'])},-1,{italic_hook},0,0,100,100,"
                     f"{spacing},0,3,18,0")
    else:      # bold text straight on the video, soft dark edge so it reads on any background
        hook_look = (f"{colour(style['outline_colour'])},&H80000000,-1,{italic_hook},0,0,100,100,"
                     f"{style.get('hook_spacing', spacing)},0,1,{style['outline']},{style['shadow']}")
    fields = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
              "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
              "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {FRAME_W}", f"PlayResY: {FRAME_H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]", fields,
        f"Style: Caption,{style['font']},{style['font_size']},{colour(style['text_colour'])},"
        f"{colour(style['highlight_colour'])},{colour(style['outline_colour'])},&H80000000,{bold},0,0,0,100,100,"
        f"{spacing},0,1,{style['outline']},{style['shadow']},2,90,90,{caption_margin},1",
        f"Style: Hook,{style['hook_font']},{style['hook_size']},{colour(style['hook_text_colour'])},"
        f"{colour(style['hook_text_colour'])},{hook_look},8,80,80,230,1",
        f"Style: Stat,{style['hook_font']},230,{colour(style['stat_colour'])},{colour(style['stat_colour'])},"
        f"{colour(style['outline_colour'])},&H00000000,-1,0,0,0,100,100,0,0,1,8,0,5,60,60,0,1",
        f"Style: Badge,{style['hook_font']},64,{colour(badge_text)},{colour(badge_text)},"
        f"{colour(badge_bg)},{colour(badge_bg)},-1,0,0,0,100,100,0,0,3,14,0,8,80,80,430,1",
        f"Style: TakeBox,Arial,10,{colour(takeover_bg)},{colour(takeover_bg)},{colour(takeover_bg)},"
        f"{colour(takeover_bg)},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: TakeText,{style['hook_font']},{style.get('takeover_size', 125)},{colour(takeover_text)},"
        f"{colour(takeover_text)},{colour(takeover_bg)},{colour(takeover_bg)},-1,0,0,0,100,100,0,0,1,0,0,5,90,90,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", ""])


def _match_key(word):
    return norm(word.replace("’", "'")).replace("'", "")


def _phrase_hits(word_ids, words, phrases):
    """word ids covered by any phrase (longest first), mapped to the phrase word they match,
    plus the ids that must stay on screen with the word after them."""
    tokens = [_match_key(words[word_id]["text"]) for word_id in word_ids]
    hits, glue = {}, set()
    for phrase in sorted(phrases, key=lambda p: -len(p.split())):
        parts = phrase.split()
        keys = [_match_key(part) for part in parts]
        size = len(keys)
        for pos in range(len(word_ids) - size + 1):
            if tokens[pos:pos + size] == keys and not any(word_ids[pos + j] in hits for j in range(size)):
                for offset, part in enumerate(parts):
                    hits[word_ids[pos + offset]] = part
                glue |= {word_ids[pos + offset] for offset in range(size - 1)}
    return hits, glue


def cased_words(line, word_ids, words, style, strip_punct):
    """display text per word id after case rules + brand capitals, the set of keyword ids, and
    the ids glued to the next word (brand names and keyword phrases never split across captions)."""
    shown = {}
    for word_id in word_ids:
        text = words[word_id]["text"].strip().replace("’", "'")
        if strip_punct:
            text = text.strip(",.")
        if style.get("uppercase"):
            text = text.upper()
        elif style.get("lowercase"):
            text = text.lower()
            if re.fullmatch(r"i('(m|d|ve|ll))?\W*", text):     # "i", "i'm" etc stay capital
                text = "I" + text[1:]
        shown[word_id] = text
    capitals, glue = _phrase_hits(word_ids, words, style.get("keep_caps", []))
    for word_id, proper in capitals.items():
        shown[word_id] = re.sub(r"[\w'£$€%-]+", lambda _: proper, shown[word_id], count=1)
    for name in style.get("keep_caps", []):      # one-word names inside a longer word, eg "UK 16"
        if " " not in name:
            for word_id in word_ids:
                shown[word_id] = re.sub(rf"(?i)(?<![\w']){re.escape(name)}(?![\w'])", name, shown[word_id])
    keyword_hits, keyword_glue = _phrase_hits(word_ids, words, style.get("keywords", []))
    keywords = set(line.get("keywords") or [])
    if not keywords:        # automatic: numbers/money + the style's keyword list
        keywords = {word_id for word_id in word_ids if re.search(r"[\d£$€%]", words[word_id]["text"])}
        keywords |= set(keyword_hits)
    return shown, keywords & set(word_ids), glue | keyword_glue


def chunked(word_ids, per_caption, glue, shown=None, max_chars=0):
    """split a line into captions of ~per_caption words (and at most max_chars, so a caption never
    wraps onto two rows) without breaking a glued phrase."""
    captions, current = [], []
    for word_id in word_ids:
        if (max_chars and current and current[-1] not in glue
                and len(" ".join(shown[other] for other in current + [word_id])) > max_chars):
            captions.append(current)
            current = []
        current.append(word_id)
        if len(current) >= per_caption and word_id not in glue:
            captions.append(current)
            current = []
    if current:
        captions.append(current)
    # don't leave one word hanging on its own: borrow the last word of the caption before
    if len(captions) > 1 and len(captions[-1]) == 1 and len(captions[-2]) > 2 and captions[-2][-2] not in glue:
        captions[-1].insert(0, captions[-2].pop())
    return captions


def caption_events(plan, words, timed, style, total):
    """(start, end, style name, text) for every caption, in the style's caption mode."""
    events = []
    highlight = ass_colour(style["highlight_colour"])
    mode = style["caption_mode"]
    per_caption = 1 if mode == "word" else max(1, int(style["words_per_caption"]))
    word_order = sorted(timed)
    spacing_tag = f"\\fsp{style['spacing']}" if style.get("spacing") else ""
    keyword_tag = ""
    if style.get("keyword_font") or style.get("keyword_colour"):
        keyword_tag = (f"\\fn{style.get('keyword_font', style['font'])}"
                       f"\\c{ass_colour(style.get('keyword_colour', style['text_colour']))}"
                       f"\\fs{style.get('keyword_size', style['font_size'])}"
                       f"\\fsp{style.get('keyword_spacing', style.get('spacing', 0))}"
                       f"\\bord{style.get('keyword_outline', style['outline'])}")

    for line in plan["lines"]:
        if not line["keep"] or line["treatment"] == "takeover":
            continue
        # a blank word = merged into the word before it (eg "5" + "'2" shown as 5'2")
        word_ids = [word_id for word_id in line["words"] if word_id in timed and words[word_id]["text"].strip()]
        shown, keywords, glue = cased_words(line, word_ids, words, style, strip_punct=mode != "line")

        def styled(word_id, extra=""):
            # every word starts with \r so a keyword's look never leaks onto the next word.
            # spacing goes inline too: libass ignores the style's spacing value
            tags = spacing_tag + (keyword_tag if word_id in keywords else "") + extra
            return f"{{\\r{tags}}}{ass_escape(shown[word_id])}"

        for caption in chunked(word_ids, per_caption, glue, shown, style.get("caption_chars", 0)):
            start = timed[caption[0]][0]
            next_word = next((word_id for word_id in word_order if word_id > caption[-1]), None)
            end = min(timed[caption[-1]][1] + CAPTION_HOLD, timed[next_word][0] if next_word is not None else total)
            end = max(end, start + CAPTION_MIN)
            if mode == "karaoke":
                for pos, word_id in enumerate(caption):
                    word_end = timed[caption[pos + 1]][0] if pos + 1 < len(caption) else end
                    parts = [styled(other, f"\\c{highlight}") + "{\\r}" if other == word_id else styled(other)
                             for other in caption]
                    events.append((timed[word_id][0], word_end, "Caption", " ".join(parts)))
            elif mode == "build":
                # the whole line is laid out from the start (unsaid words invisible) so nothing
                # shifts sideways as words appear
                step = max(1, int(style.get("build_step", 1)))
                for pos in range(0, len(caption), step):
                    step_start = timed[caption[pos]][0]
                    step_end = timed[caption[pos + step]][0] if pos + step < len(caption) else end
                    parts = [styled(other) if other_pos < pos + step else styled(other, "\\alpha&HFF&")
                             for other_pos, other in enumerate(caption)]
                    events.append((step_start, max(step_end, step_start + BUILD_STEP_MIN), "Caption", " ".join(parts)))
            elif mode == "word":
                events.append((start, end, "Caption",
                               "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" + styled(caption[0])))
            else:
                events.append((start, end, "Caption", " ".join(styled(word_id) for word_id in caption)))
    return events


def hook_lines(text, style):
    """split the hook into short lines so line spacing can be set (ass has no line height)."""
    if style.get("hook_uppercase"):
        text = text.upper()
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > style.get("hook_chars", 18):
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return lines + [current] if current else lines


def hook_events(plan, kept, timed, total, style):
    """the hook card, on screen from 0s for about the first line."""
    hook = (plan.get("hook_text") or "").strip()
    if not hook or (kept and kept[0]["treatment"] == "takeover"):
        return []
    end = HOOK_SECS
    first_line = [word_id for word_id in kept[0]["words"] if word_id in timed] if kept else []
    if first_line:
        end = max(HOOK_MIN_SECS, min(HOOK_MAX_SECS, timed[first_line[-1]][1]))
    end = min(end, total)
    if not style.get("hook_line_height"):
        return [(0.0, end, "Hook", "{\\fad(0,150)}" + ass_escape(hook))]
    line_gap = style["hook_size"] * style["hook_line_height"]
    return [(0.0, end, "Hook",
             f"{{\\an8\\pos({FRAME_W // 2},{HOOK_TOP + row * line_gap:.0f})\\fsp{style.get('hook_spacing', 0)}"
             f"\\fad(0,150)}}" + ass_escape(text))
            for row, text in enumerate(hook_lines(hook, style))]


def stat_events(line, word_ids, words, timed, end):
    """a big number that lands on the word it's said on. numbers 10+ count up first."""
    number_word = next((word_id for word_id in word_ids if re.search(r"\d", words[word_id]["text"])), word_ids[0])
    start = max(0.0, timed[number_word][0] - STAT_LEAD)
    stat = ass_escape(str(line["stat"]))
    match = re.fullmatch(r"([£$€]?)(\d[\d,]*)(.*)", stat)
    number = int(match.group(2).replace(",", "")) if match else 0
    if not (match and number >= 10):
        return [(start, end, "Stat", STAT_POS + "{\\fscx40\\fscy40\\t(0,180,\\fscx112\\fscy112)"
                 "\\t(180,300,\\fscx100\\fscy100)}" + stat)]
    currency, _, suffix = match.groups()
    events = []
    for step in range(STAT_COUNT_STEPS):
        step_start = start + STAT_COUNT_STEP_SECS * step
        value = int(number * (step + 1) / STAT_COUNT_STEPS)
        events.append((step_start, step_start + STAT_COUNT_STEP_SECS, "Stat", STAT_POS + f"{currency}{value:,}{suffix}"))
    pop_start = start + STAT_COUNT_STEP_SECS * STAT_COUNT_STEPS
    events.append((pop_start, end, "Stat", STAT_POS + "{\\fscx112\\fscy112\\t(0,160,\\fscx100\\fscy100)}" + stat))
    return events


def takeover_events(line, start, end):
    """a full-screen brand-colour card (or several in turn) with big text."""
    cards = line.get("takeover_text") or line["text"]
    if isinstance(cards, str):
        cards = [cards]
    events = [(start, end, "TakeBox",
               f"{{\\pos(0,0)\\p1}}m 0 0 l {FRAME_W} 0 {FRAME_W} {FRAME_H} 0 {FRAME_H}{{\\p0}}")]
    card_secs = (end - start) / len(cards)
    for index, card in enumerate(cards):
        card_start = start + index * card_secs
        text = ass_escape(card.strip()).replace("\\n", "\\N")
        events.append((card_start, card_start + card_secs, "TakeText",
                       "{\\fscx92\\fscy92\\t(0,140,\\fscx100\\fscy100)}" + text))
    return events


def overlay_events(plan, words, timed, total, style):
    """(start, end, style name, text) for every graphic: hook, stat pops, step badges, takeovers."""
    kept = [line for line in plan["lines"] if line["keep"]]
    events = hook_events(plan, kept, timed, total, style)
    for line in kept:
        word_ids = [word_id for word_id in line["words"] if word_id in timed]
        if not word_ids:
            continue
        start, end = timed[word_ids[0]][0], min(total, timed[word_ids[-1]][1] + GRAPHIC_HOLD)
        treatment = line["treatment"]
        if treatment == "stat pop" and line.get("stat"):
            events += stat_events(line, word_ids, words, timed, end)
        elif treatment == "step" and line.get("step"):
            events.append((start, end, "Badge", "{\\fad(100,100)}" + f"step {line['step']}"))
        elif treatment == "takeover":
            events += takeover_events(line, start, end)
    return events


def write_ass(path, style, events):
    layer = {"Caption": 0, "TakeBox": 2, "TakeText": 3}     # everything else sits on layer 1
    lines = [ass_header(style)]
    for start, end, style_name, text in sorted(events, key=lambda event: (event[0], layer.get(event[2], 1))):
        lines.append(f"Dialogue: {layer.get(style_name, 1)},{ass_time(start)},{ass_time(end)},{style_name},,0,0,0,,{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- b-roll ----------

def broll_windows(plan, timed, total, cuts=()):
    """lines with b-roll -> (start, end, spec) on the new timeline. spec is the line's "broll"
    settings plus "path", the resolved file."""
    windows = []
    for line in plan["lines"]:
        spec = line.get("broll")
        if not line["keep"] or not spec or not spec.get("file"):
            continue
        word_ids = [word_id for word_id in line["words"] if word_id in timed]
        if not word_ids:
            continue
        start = max(0.0, timed[word_ids[0]][0] - BROLL_LEAD)
        end = min(total, timed[word_ids[-1]][1] + BROLL_TAIL)
        # start/end exactly on a nearby cut, or a frame of the talking shot flashes up
        start = next((cut for cut in cuts if abs(cut - start) < SNAP_TO_CUT), start)
        end = next((cut for cut in cuts if abs(cut - end) < SNAP_TO_CUT), end)
        path = Path(spec["file"])
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            die(f"b-roll file not found: {spec['file']}")
        if (windows and spec.get("continue") and windows[-1][2]["path"] == path
                and start - windows[-1][1] < BROLL_JOIN_GAP):
            # "continue": true = keep playing the previous b-roll as one unbroken shot
            windows[-1] = (windows[-1][0], end, windows[-1][2])
            continue
        windows.append((start, end, {**spec, "path": path}))
    # back-to-back b-roll runs straight through (no flash of the talking shot between lines)
    for index in range(len(windows) - 1):
        if windows[index + 1][0] - windows[index][1] < BROLL_JOIN_GAP:
            windows[index] = (windows[index][0], windows[index + 1][0], windows[index][2])
    # b-roll that would run across a cut already in that footage: start after the cut
    for index, (start, end, spec) in enumerate(windows):
        if spec["path"].suffix.lower() in IMAGE_EXTS:
            continue
        clip_start = float(spec.get("start", 0))
        for scene_cut in scene_cuts(spec["path"]):
            if clip_start < scene_cut < clip_start + (end - start):
                if scene_cut - clip_start < BROLL_SCENE_SKIP:
                    spec = {**spec, "start": round(scene_cut + BROLL_SCENE_NUDGE, 3)}
                    clip_start = spec["start"]
                else:
                    print(f"[engine] note: b-roll {spec['path'].name} from {clip_start:.1f}s runs into "
                          f"a scene change at {scene_cut:.1f}s")
        windows[index] = (start, end, spec)
    return windows


def broll_input(spec, start, end):
    """ffmpeg input args for a b-roll window: a still loops, a clip reads from its start time."""
    length = f"{end - start + BROLL_READ_EXTRA:.3f}"
    if spec["path"].suffix.lower() in IMAGE_EXTS:
        return ["-loop", "1", "-t", length, "-i", str(spec["path"])]
    return vin(spec["path"], "-ss", f"{float(spec.get('start', 0)):.3f}", "-t", length)


def broll_filter(input_index, start, end, spec, grade=""):
    frames = max(1, round((end - start) * FPS))
    pip = spec.get("mode") == "pip"
    box_w, box_h = (PIP_W, PIP_H) if pip else (FRAME_W, FRAME_H)
    chain = (f"[{input_index}:v]{sdr_filter(spec['path'])}scale={box_w * 2}:{box_h * 2}:force_original_aspect_ratio=increase,"
             f"crop={box_w * 2}:{box_h * 2},setsar=1,fps={FPS},"
             f"zoompan=z='1+{BROLL_PUSH}*on/{frames}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={box_w}x{box_h}:fps={FPS},"
             # a few spare frames: the start time rounds down to a whole frame, and if the b-roll runs out
             # before its slot ends a frame of the talking shot flashes up. the overlay's enable ends it on time
             f"tpad=stop_mode=clone:stop_duration=0.3,"
             f"trim=end_frame={frames + 4},format=yuv420p,setpts=PTS-STARTPTS+{start:.3f}/TB")
    if grade and spec.get("grade"):   # "grade": true = raw footage that needs your grade too
        chain += "," + grade
    if pip:
        chain += ",pad=iw+16:ih+16:8:8:white"
    return chain


# ---------- sound ----------

def sfx_cues(plan, words, timed, windows):
    """automatic sound effects + per-line overrides. returns [(time, name, volume)]
    (volume is a multiplier on sfx_volume, set per line with "sfx_volume")"""
    sound = plan.get("sound", {})
    auto = sound.get("sfx", True)
    cues = []
    for line in plan["lines"]:
        if not line["keep"]:
            continue
        word_ids = [word_id for word_id in line["words"] if word_id in timed]
        if not word_ids:
            continue
        start = timed[word_ids[0]][0]
        if line.get("sfx"):
            if line["sfx"] != "none":
                cues.append((max(0.0, start - SFX_LEAD), line["sfx"], line.get("sfx_volume", 1.0)))
            continue
        if not auto:
            continue
        treatment = line["treatment"]
        if treatment == "takeover":
            cues.append((max(0.0, start - WHOOSH_LEAD), "whoosh", 1.0))
        elif treatment == "stat pop":
            number_word = next((word_id for word_id in word_ids if re.search(r"\d", words[word_id]["text"])), word_ids[0])
            cues.append((max(0.0, timed[number_word][0] - STAT_LEAD), "pop", 1.0))
        elif treatment == "step":
            cues.append((start, "click", 1.0))
    if auto:
        for window_start, _, _ in windows:
            if not any(abs(cue[0] - window_start) < SFX_NEAR for cue in cues):
                cues.append((max(0.0, window_start - SWOOSH_LEAD), "swoosh", 1.0))
    return sorted(cues)


def find_sfx(name):
    for ext in SFX_EXTS:
        path = SFX_DIR / f"{name}{ext}"
        if path.exists():
            return path
    return None


def mix(labels, out_label, total, with_speech=True, loud=True):
    """mix the speech (label "sp") and the given sound labels into one track."""
    sources = (["sp"] if with_speech else []) + labels
    if not sources:
        return f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=0:{total:.3f}[{out_label}]"
    chain = "".join(f"[{label}]" for label in sources)
    if len(sources) == 1:
        chain += STEREO
    else:
        chain += f"amix=inputs={len(sources)}:duration=first:normalize=0"
    if loud:
        chain += f",loudnorm={LOUDNESS}"
    return chain + f",atrim=0:{total:.3f}[{out_label}]"


# ---------- source analysis ----------

def detect_scene_changes(video):
    """picture-change times in a video file (ffmpeg scdet)."""
    result = run([find_bin("ffmpeg"), "-hide_banner", *vin(video), "-an", "-vf", SCENE_DETECT, "-f", "null", "-"])
    return [float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", result.stdout + result.stderr)]


def scene_cuts(video):
    """times of hard cuts already inside the footage (eg a compilation). cached per file."""
    stat = Path(video).stat()
    cache = WORK_DIR / "_scenes" / f"{stat.st_ino}.json"     # by file identity, so linked copies share it
    stamp = f"{stat.st_size}-{int(stat.st_mtime)}"
    if cache.exists():
        cached = load_json(cache)
        if cached.get("stamp") == stamp:
            return cached["cuts"]
    cuts = detect_scene_changes(video)
    cache.parent.mkdir(parents=True, exist_ok=True)
    save_json(cache, {"stamp": stamp, "cuts": cuts})
    return cuts


def silence_map(video):
    """[(start, end)] of every quiet stretch in the clip's audio."""
    result = run([find_bin("ffmpeg"), "-hide_banner", "-i", str(video), "-map", "0:a:0",
                  "-af", SILENCE_DETECT, "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", result.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", result.stderr)]
    return [(max(0.0, start), end) for start, end in zip(starts, ends + [float("inf")])]


# ---------- build ----------

@dataclass
class Edit:
    """everything a render needs, worked out once and shared by the full render, the cut / spot
    previews and the capcut export."""
    inputs: list          # ffmpeg input args, one list per input
    filters: list         # filter script lines up to [graded] (picture) and [sp] (speech) + sound labels
    segments: list        # source segments in order (see build_segments)
    timed: dict           # word id -> (start, end) on the new timeline
    total: float          # finished length in seconds
    captions: list        # caption events
    graphics: list        # graphics events
    windows: list         # b-roll (start, end, spec)
    cues: list            # sound effects (time, name, volume)
    missing_sfx: list     # sound effect names with no file
    sound_labels: list    # filter labels of the music + sound effect tracks
    music: object         # the music track used, or None


def build(video, work_dir, plan, transcript, style, opts):
    """work out the edit and write its caption / graphics files. returns an Edit."""
    words = [dict(word) for word in transcript["words"]]
    # cuts follow the real audio: hook lands instantly and no word gets clipped
    segments, timed = build_segments(plan, words, silence_map(video), scene_cuts(video))
    if not segments:
        die("every line is marked as cut - nothing left to render")
    assign_zoom(segments, style)
    total = segments[-1]["new_end"]

    captions = caption_events(plan, words, timed, style, total)
    graphics = overlay_events(plan, words, timed, total, style)
    write_ass(work_dir / "captions.ass", style, captions)
    write_ass(work_dir / "graphics.ass", style, graphics)
    windows = broll_windows(plan, timed, total, [seg["new_start"] for seg in segments] + [total])

    # each shot reads only its own stretch of the source (no decoding the whole file)
    inputs = [vin(video, "-ss", f"{seg['start']:.3f}", "-t", f"{seg['end'] - seg['start'] + SOURCE_READ_EXTRA:.3f}")
              for seg in segments]
    filters = []
    for index, seg in enumerate(segments):
        length = seg["end"] - seg["start"]
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS,"
                       f"{sdr_filter(video)}{frame_filter(seg, transcript['width'], transcript['height'])},"
                       f"tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={seg['frames']}[v{index}];")
        fade_out_at = max(0.0, length - SEGMENT_FADE)
        filters.append(f"[{index}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,"
                       f"afade=t=in:d={SEGMENT_FADE},afade=t=out:st={fade_out_at:.3f}:d={SEGMENT_FADE}[a{index}];")
    filters.append("".join(f"[v{index}][a{index}]" for index in range(len(segments))) +
                   f"concat=n={len(segments)}:v=1:a=1[vc][speech];")

    # grade the talking head only. b-roll goes on after, untouched (it's already edited)
    grade = opts["grade"]
    filters.append(f"[vc]{grade if grade else 'null'}[vcg];")

    # b-roll on top of the edit, under the text
    picture = "vcg"
    for number, (start, end, spec) in enumerate(windows):
        input_index = len(inputs)
        inputs.append(broll_input(spec, start, end))
        filters.append(broll_filter(input_index, start, end, spec, grade) + f"[br{number}];")
        place = PIP_PLACE if spec.get("mode") == "pip" else "x=0:y=0"
        filters.append(f"[{picture}][br{number}]overlay={place}:enable='between(t,{start:.3f},{end:.3f})'"
                       f":eof_action=pass[vb{number}];")
        picture = f"vb{number}"
    filters.append(f"[{picture}]null[graded];")

    # ---- audio: speech, ducked music, sound effects
    sound = plan.get("sound", {})
    music = opts.get("music") or sound.get("music")
    sound_labels = []
    if music:
        music_path = Path(music)
        if not music_path.is_absolute():
            music_path = ROOT / music_path
        if not music_path.exists():
            die(f"can't find the music file {music}")
        input_index = len(inputs)
        inputs.append(["-stream_loop", "-1", "-i", str(music_path)])
        volume = opts.get("music_volume") or sound.get("music_volume", MUSIC_VOLUME)
        # speech splits three ways: the mix, the music's ducking key, and a spare to sink
        filters.append("[speech]asplit=3[sp][sc][spx];")
        filters.append(f"[{input_index}:a]{STEREO},volume={volume},"
                       f"atrim=0:{total:.3f},afade=t=out:st={max(0, total - MUSIC_FADE_OUT):.3f}:d={MUSIC_FADE_OUT}[mraw];")
        filters.append(f"[sc]{STEREO}[scs];")
        filters.append(f"[mraw][scs]sidechaincompress={MUSIC_DUCK}[music];")
        sound_labels.append("music")
    else:
        filters.append("[speech]asplit=2[sp][spx];")
    cues = sfx_cues(plan, words, timed, windows)
    missing = set()
    sfx_volume = sound.get("sfx_volume", SFX_VOLUME)
    for number, (time, name, volume) in enumerate(cues):
        path = find_sfx(name)
        if not path:
            missing.add(name)
            continue
        input_index = len(inputs)
        inputs.append(["-i", str(path)])
        delay_ms = int(time * 1000)
        filters.append(f"[{input_index}:a]{STEREO},volume={sfx_volume * volume:.3f},"
                       f"adelay={delay_ms}|{delay_ms}[fx{number}];")
        sound_labels.append(f"fx{number}")
    filters.append("[spx]anullsink;")
    return Edit(inputs=inputs, filters=filters, segments=segments, timed=timed, total=total,
                captions=captions, graphics=graphics, windows=windows, cues=cues,
                missing_sfx=sorted(missing), sound_labels=sound_labels, music=music)


def ffmpeg_with_inputs(inputs):
    cmd = [find_bin("ffmpeg"), "-y"]
    for input_args in inputs:
        cmd += input_args
    return cmd


def encode(inputs, filters, maps, out, work_dir, draft, video_codec=None):
    (work_dir / "filter.txt").write_text("\n".join(filters), encoding="utf-8")
    cmd = ffmpeg_with_inputs(inputs) + ["-/filter_complex", "filter.txt"] + maps
    cmd += video_codec or [*h264(draft), "-r", str(FPS)]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE), "-movflags", "+faststart", str(out)]
    run(cmd, cwd=work_dir)


def srt_time(secs):
    ms = int(round(secs * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, plan, words, timed, style, total):
    """captions as a plain .srt (for capcut): same words and casing, a few words a caption."""
    per_caption = max(SRT_WORDS_MIN, int(style.get("words_per_caption", 3)))
    word_order = sorted(timed)
    entries = []
    for line in plan["lines"]:
        if not line["keep"] or line["treatment"] == "takeover":
            continue
        word_ids = [word_id for word_id in line["words"] if word_id in timed and words[word_id]["text"].strip()]
        shown, _, glue = cased_words(line, word_ids, words, style, strip_punct=False)
        for caption in chunked(word_ids, per_caption, glue):
            start = timed[caption[0]][0]
            next_word = next((word_id for word_id in word_order if word_id > caption[-1]), None)
            end = min(timed[caption[-1]][1] + CAPTION_HOLD, timed[next_word][0] if next_word is not None else total)
            text = " ".join(shown[word_id] for word_id in caption)
            entries.append(f"{len(entries) + 1}\n{srt_time(start)} --> {srt_time(max(end, start + SRT_MIN_SECS))}\n{text}\n")
    path.write_text("\n".join(entries), encoding="utf-8")


# ---------- cut / spot previews: render only a moment either side of each point ----------

def _shift_events(events, window_start, window_end):
    """caption/graphic events inside [window_start, window_end], moved so window_start = 0."""
    shifted = []
    for start, end, style_name, text in events:
        if end > window_start and start < window_end:
            shifted.append((max(start, window_start) - window_start, min(end, window_end) - window_start,
                            style_name, text))
    return shifted


def preview_windows(points, pad, total):
    """(start, end, [points]) around each point, merging points that sit close together."""
    windows = []
    for point in points:
        start, end = max(0.0, point - pad), min(total, point + pad)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], end, windows[-1][2] + [point])
        else:
            windows.append((start, end, [point]))
    return windows


def flash_times(video, offset):
    """stray-frame check: two picture changes < FLASH_GAP apart = a flash. times + offset."""
    changes = detect_scene_changes(video)
    return [round(offset + first, 2) for first, second in zip(changes, changes[1:]) if second - first < FLASH_GAP]


def _render_windows(video, windows, edit, transcript, grade, style, preview_dir, kind="cut"):
    """render each window of the finished edit as its own labelled clip. returns
    (clips, report) where report is [(number, label, flash times)]."""
    clips, report = [], []
    fonts = FONTS_FROM_PREVIEW_DIR
    for number, (window_start, window_end, points) in enumerate(windows, 1):
        window_len = window_end - window_start
        inputs, filters, video_labels, audio_labels = [], [], [], []
        # the talking-head pieces that fall inside this window
        for seg in edit.segments:
            if seg["new_end"] <= window_start or seg["new_start"] >= window_end:
                continue
            trim_front = max(0.0, window_start - seg["new_start"])
            trim_back = max(0.0, seg["new_end"] - window_end)
            length = seg["end"] - seg["start"]
            piece = dict(seg)
            piece["start"], piece["end"] = seg["start"] + trim_front, seg["end"] - trim_back

            def zoom_at(secs, seg=seg, length=length):
                return seg["z0"] + (seg["z1"] - seg["z0"]) * (secs / length if length else 0)

            piece["z0"], piece["z1"] = zoom_at(trim_front), zoom_at(length - trim_back)
            frames = max(1, round((piece["end"] - piece["start"]) * FPS))
            index = len(video_labels)
            inputs.append(vin(video, "-ss", f"{piece['start']:.3f}",
                              "-t", f"{piece['end'] - piece['start'] + SOURCE_READ_EXTRA:.3f}"))
            filters.append(f"[{index}:v]setpts=PTS-STARTPTS,"
                           f"{sdr_filter(video)}{frame_filter(piece, transcript['width'], transcript['height'])},"
                           f"tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={frames}[v{index}];")
            filters.append(f"[{index}:a]atrim=0:{piece['end'] - piece['start']:.3f},asetpts=PTS-STARTPTS[a{index}];")
            video_labels.append(f"[v{index}]")
            audio_labels.append(f"[a{index}]")
        filters.append("".join(v + a for v, a in zip(video_labels, audio_labels)) +
                       f"concat=n={len(video_labels)}:v=1:a=1[vc][speech];")
        filters.append(f"[vc]{grade if grade else 'null'}[vcg];")
        picture = "vcg"
        for broll_number, (start, end, spec) in enumerate(edit.windows):
            if end <= window_start or start >= window_end:
                continue
            local_start, local_end = max(start, window_start) - window_start, min(end, window_end) - window_start
            local_spec = {**spec, "start": float(spec.get("start", 0)) + max(0.0, window_start - start)}
            input_index = len(inputs)
            inputs.append(broll_input(local_spec, local_start, local_end))
            filters.append(broll_filter(input_index, local_start, local_end, local_spec, grade) + f"[br{broll_number}];")
            filters.append(f"[{picture}][br{broll_number}]overlay=0:0:enable='between(t,{local_start:.3f},"
                           f"{local_end:.3f})':eof_action=pass[vb{broll_number}];")
            picture = f"vb{broll_number}"
        write_ass(preview_dir / f"cap_{number}.ass", style, _shift_events(edit.captions, window_start, window_end))
        write_ass(preview_dir / f"gfx_{number}.ass", style, _shift_events(edit.graphics, window_start, window_end))
        label = " + ".join(f"{point:.1f}s" for point in points)
        filters.append(f"[{picture}]subtitles=gfx_{number}.ass:fontsdir={fonts},subtitles=cap_{number}.ass:fontsdir={fonts},"
                       f"drawtext=text='{kind} {number} at {label}':x=30:y=40:fontsize=24:fontcolor=yellow:box=1:boxcolor=black@0.6,"
                       f"format=yuv420p[vout];")
        filters.append(f"[speech]{STEREO},"
                       f"apad=whole_dur={window_len:.3f},atrim=0:{window_len:.3f}[aout]")
        (preview_dir / "filter.txt").write_text("\n".join(filters), encoding="utf-8")
        out = preview_dir / f"{kind}_{number:02d}.mp4"
        run(ffmpeg_with_inputs(inputs) + ["-/filter_complex", "filter.txt", "-map", "[vout]", "-map", "[aout]",
                                          *h264(draft=True), "-r", str(FPS),
                                          "-c:a", "aac", "-b:a", "128k", "-t", f"{window_len:.3f}", str(out)],
            cwd=preview_dir)
        report.append((number, label, flash_times(out, window_start)))
        clips.append(out)
    return clips, report


def join_clips(clips, preview_dir, joined):
    clip_list = preview_dir / "list.txt"
    clip_list.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
    run([find_bin("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(joined)],
        cwd=preview_dir)


def fresh_preview_dir(work_dir, name):
    preview_dir = work_dir / name
    preview_dir.mkdir(exist_ok=True)
    for old in preview_dir.glob("*.mp4"):
        old.unlink()
    return preview_dir


def print_report(kind, report):
    for number, label, flashes in report:
        print(f"  {kind} {number:2} at {label:>14}: " + (f"FLASH at {flashes}" if flashes else "clean"))


def preview_cuts(video, work_dir, transcript, style, edit, grade, pad=1.5, only=None):
    """same edit as the full render, but only ~pad seconds either side of every cut
    (shot changes + b-roll in/out). each window is checked for stray frames, then all
    windows are joined into one labelled preview. much faster than a full render."""
    total = edit.total
    points = [seg["new_start"] for seg in edit.segments[1:]]
    for start, end, _ in edit.windows:
        points += [start, end]
    points = sorted(point for point in set(round(point, 3) for point in points) if 0 < point < total - 0.05)
    windows = preview_windows(points, pad, total)
    if only:
        windows = [window for number, window in enumerate(windows, 1) if number in only]
    if not windows:
        print("[engine] no cuts to preview")
        return None
    preview_dir = fresh_preview_dir(work_dir, "cut_previews")
    with half_size_frames():
        clips, report = _render_windows(video, windows, edit, transcript, grade, dict(style), preview_dir)
    joined = OUTPUT_DIR / f"{work_dir.name}_cuts_preview.mp4"
    join_clips(clips, preview_dir, joined)
    print(f"[engine] cut preview: {len(clips)} cuts, {sum(end - start for start, end, _ in windows):.1f}s of "
          f"{total:.1f}s rendered -> {joined.relative_to(ROOT)}")
    print_report("cut", report)
    return joined


def preview_spots(video, work_dir, transcript, style, edit, grade, spots, pad=1.5, name="spot"):
    """full-size render of just the trouble spots: `pad` seconds either side of each time
    (finished-reel time), labelled, joined into output/<clip>_<name>.mp4 for the client to judge by ear."""
    windows = preview_windows(sorted(spots), pad, edit.total)
    preview_dir = fresh_preview_dir(work_dir, f"{name}_previews")
    clips, report = _render_windows(video, windows, edit, transcript, grade, dict(style), preview_dir, kind="spot")
    joined = OUTPUT_DIR / f"{work_dir.name}_{name}.mp4"
    join_clips(clips, preview_dir, joined)
    print(f"[engine] spot preview: {len(clips)} spot(s) -> {joined.relative_to(ROOT)}")
    print_report("spot", report)
    return joined


# ---------- finished reel, cover, capcut pack ----------

def render_reel(edit, work_dir, out, style_name, grade, draft):
    filters = list(edit.filters)
    filters.append(f"[graded]subtitles=graphics.ass:fontsdir={FONTS_FROM_WORK_DIR},"
                   f"subtitles=captions.ass:fontsdir={FONTS_FROM_WORK_DIR}[vout];")
    filters.append(mix(edit.sound_labels, "aout", edit.total))
    print(f"[engine] rendering {len(edit.segments)} cuts, {edit.total:.1f}s, style '{style_name}'"
          f"{', graded' if grade else ''}, {len(edit.windows)} b-roll, {len(edit.cues)} sound fx"
          f"{', music' if edit.music else ''}...")
    encode(edit.inputs, filters, ["-map", "[vout]", "-map", "[aout]"], out, work_dir, draft)
    if edit.missing_sfx:
        print(f"[engine] note: no sound file for {', '.join(edit.missing_sfx)} in assets/sfx/ - "
              "run python -m engine sfx to make the defaults")


def save_cover(reel, cover, total):
    run([find_bin("ffmpeg"), "-y", *vin(reel, "-ss", f"{min(1.0, total / 2):.2f}"),
         "-frames:v", "1", "-q:v", "2", str(cover)])


def export_capcut(edit, work_dir, pack, plan, transcript, style):
    """a layer pack to finish in capcut: clean video, graphics + matte, captions, music + sfx."""
    pack.mkdir(exist_ok=True)
    total = edit.total
    print("[engine] exporting capcut layers...")
    # 1. clean video: edit + zooms + b-roll + grade, your voice only, no text
    filters = list(edit.filters)
    filters.append("[graded]null[vout];")
    filters += [f"[{label}]anullsink;" for label in edit.sound_labels]
    filters.append(mix([], "aout", total))
    encode(edit.inputs, filters, ["-map", "[vout]", "-map", "[aout]"], pack / "1_video_clean.mp4", work_dir, False)
    # 2. graphics: hook, stat pops, badges, takeovers on a transparent background
    matte = re.sub(r"&H[0-9A-Fa-f]{8}", "&H00FFFFFF", (work_dir / "graphics.ass").read_text(encoding="utf-8"))
    matte = re.sub(r"\\(1?c)&H[0-9A-Fa-f]{6,8}&?", r"\\1c&HFFFFFF&", matte)
    (work_dir / "graphics_matte.ass").write_text(matte, encoding="utf-8")
    # h.264 can't hold transparency, so: the graphics on black + a black/white matte (white = show)
    run([find_bin("ffmpeg"), "-y", "-f", "lavfi", "-i",
         f"color=c=black:s={FRAME_W}x{FRAME_H}:r={FPS}:d={total:.3f}", "-filter_complex",
         f"[0:v]split[a][b];[a]subtitles=graphics.ass:fontsdir={FONTS_FROM_WORK_DIR}[rgb];"
         f"[b]subtitles=graphics_matte.ass:fontsdir={FONTS_FROM_WORK_DIR}[m]",
         "-map", "[rgb]", *h264(), "-r", str(FPS), "-movflags", "+faststart", str(pack / "2_graphics_on_black.mp4"),
         "-map", "[m]", *h264(), "-r", str(FPS), "-movflags", "+faststart", str(pack / "2_graphics_matte.mp4")],
        cwd=work_dir)
    # 3. captions as editable text
    write_srt(pack / "3_captions.srt", plan, transcript["words"], edit.timed, style, total)
    # 4. music + sound effects without your voice
    if edit.sound_labels:
        filters = list(edit.filters)
        filters.append("[graded]nullsink;[sp]anullsink;")
        filters.append(mix(edit.sound_labels, "aout", total, with_speech=False, loud=False))
        (work_dir / "filter.txt").write_text("\n".join(filters), encoding="utf-8")
        run(ffmpeg_with_inputs(edit.inputs) + ["-/filter_complex", "filter.txt", "-map", "[aout]",
                                               "-c:a", "pcm_s16le", str(pack / "4_music_and_sfx.wav")], cwd=work_dir)
    (pack / "HOW_TO_OPEN_IN_CAPCUT.txt").write_text(CAPCUT_HELP, encoding="utf-8")


def save_edl(work_dir, plan, edit, brand, style_name, grade, out, cover, pack):
    """edl.json: what was rendered, for qc and for later fixes."""
    kept_words = [word_id for line in plan["lines"] if line["keep"] and line["treatment"] != "takeover"
                  for word_id in line["words"] if word_id in edit.timed]
    save_json(work_dir / "edl.json", {
        "output": str(out), "cover": str(cover) if cover else None, "capcut_pack": str(pack) if pack else None,
        "brand": brand.name, "style": style_name, "duration": edit.total, "graded": bool(grade),
        "music": bool(edit.music),
        "broll": [{"start": start, "end": end, "file": str(spec["file"])} for start, end, spec in edit.windows],
        "sfx": [{"time": time, "name": name, "volume": volume} for time, name, volume in edit.cues],
        "missing_sfx": edit.missing_sfx,
        "segments": [{key: seg[key] for key in ("start", "end", "new_start", "new_end", "line", "motion", "z0", "z1")}
                     for seg in edit.segments],
        "kept_word_count": len(kept_words),
        "caption_events": sum(1 for event in edit.captions if event[2] == "Caption"),
        "has_hook": bool(plan.get("hook_text")),
    })


# ---------- main ----------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="?")
    parser.add_argument("--style", default=None, help="override the style in plan.json")
    add_brand_arg(parser)
    parser.add_argument("--music", default=None, help="override the music track in plan.json")
    parser.add_argument("--music-volume", type=float, default=None)
    parser.add_argument("--draft", action="store_true", help="quick low-quality preview")
    parser.add_argument("--no-grade", action="store_true", help="skip the colour grade")
    parser.add_argument("--cover", action="store_true", help="also save a cover image")
    parser.add_argument("--capcut", action="store_true",
                        help="also export a layer pack to finish in capcut")
    parser.add_argument("--cuts", action="store_true",
                        help="only render ~1.5s either side of every cut, check each for stray frames")
    parser.add_argument("--pad", type=float, default=1.5, help="seconds either side of a cut for --cuts")
    parser.add_argument("--only", default=None, help="with --cuts: just these cut numbers, eg 3,7")
    parser.add_argument("--spot", default=None,
                        help="only render around these times in the finished reel (secs), eg 8 or 8,41.5")
    parser.add_argument("--plan", default=None,
                        help="use another plan file (eg work/<clip>/plan_b.json) to try a fix without touching plan.json")
    return parser.parse_args()


def check_contrast(style, plan):
    """stop before rendering if any boxed text would be too hard to read."""
    bad = contrast_problems(style, plan)
    if bad:
        die("on-screen text too hard to read (needs at least "
            f"{MIN_RATIO}:1 contrast against its background):\n" + "\n".join(
                f"  {name}: {text} on {bg} = {ratio:.1f}:1" for name, text, bg, ratio in bad)
            + "\nfix the colours in the style (badge_text_colour / badge_bg, takeover_text_colour / "
              "takeover_bg, hook_text_colour / hook_box_colour) and render again")


def main():
    args = parse_args()
    video = resolve_video(args.video)
    work_dir = work_dir_for(video)
    transcript = load_json(work_dir / "transcript.json")
    plan_path = Path(args.plan) if args.plan else work_dir / "plan.json"
    plan = load_json(plan_path)
    brand = get_brand(args.brand, plan)
    style_name = args.style or plan.get("style") or brand.name
    style = load_style(style_name, brand)
    grade = "" if args.no_grade else grade_filter(load_grade(brand), has_huesaturation())
    check_contrast(style, plan)
    edit = build(video, work_dir, plan, transcript, style,
                 {"grade": grade, "music": args.music, "music_volume": args.music_volume})
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.spot:
        spots = [float(x) for x in args.spot.split(",")]
        name = "spot" + ("" if plan_path.name == "plan.json" else "_" + plan_path.stem)
        preview_spots(video, work_dir, transcript, style, edit, grade, spots, args.pad, name)
        return
    if args.cuts:
        only = {int(x) for x in args.only.split(",")} if args.only else None
        preview_cuts(video, work_dir, transcript, style, edit, grade, args.pad, only)
        return

    out = OUTPUT_DIR / f"{work_dir.name}_{style_name}{'_draft' if args.draft else ''}.mp4"
    render_reel(edit, work_dir, out, style_name, grade, args.draft)
    cover = None
    if args.cover:
        cover = OUTPUT_DIR / f"{work_dir.name}_{style_name}_cover.jpg"
        save_cover(out, cover, edit.total)
    pack = None
    if args.capcut:
        pack = OUTPUT_DIR / f"{work_dir.name}_capcut"
        export_capcut(edit, work_dir, pack, plan, transcript, style)
    save_edl(work_dir, plan, edit, brand, style_name, grade, out, cover, pack)
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
