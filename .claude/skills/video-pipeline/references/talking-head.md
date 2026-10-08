# talking head edit (one clip of her talking to camera)

Prefix engine commands with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ` and run from the project root.

## 1. transcribe

```
.venv/bin/python engine/transcribe.py input/<clip>            # no name = newest file in input/
.venv/bin/python engine/transcribe.py <clip> --model medium   # much more accurate, slower. use for batches, compilations, or when small mishears a lot
```

Writes `work/<clip>/transcript.json` (`words`: text, start, end, prob). iPhone HDR footage is handled automatically everywhere (converted to normal colour), nothing to do.

## 2. rough cut

```
.venv/bin/python engine/plan.py <clip> --style beth            # talking reels
.venv/bin/python engine/plan.py <clip> --style beth --no-text  # captions only: no hook card, stat pops or step badges (shop videos)
```

Groups repeated takes, cuts fillers / dead air / earlier takes, assigns motion. Prints a beat table (`work/<clip>/plan.md`).

Then read every line with word indexes and fix things before showing her:

```
.venv/bin/python - <<'EOF'
import json
w=json.load(open("work/<clip>/transcript.json"))["words"]; p=json.load(open("work/<clip>/plan.json"))
for l in p["lines"]:
    print(l["id"], "" if l["keep"] else "[CUT "+l["reason"]+"]", l["takes"], " ".join(f"{i}:{w[i]['text']}"+("?" if w[i].get("prob",1)<0.5 else "") for i in l["words"]))
EOF
```

Check for:
- **misheard words** (low prob `?`). fix the text in transcript.json (not plan.json). brand/product names get misheard a lot (eg "these two love trousers" = "these Halara trousers", "white calf" = "wide-calf", "buried amount" = "varied amount"). if you're guessing, tell her the guess and ask her to confirm.
- **wrongly grouped retakes**: the planner can group two different lines that start with the same words ("I feel like..."). un-group: set `keep: true`, `takes: []`.
- **stumbles / false starts** inside a line: add word indexes to that line's `cut_words`.
- **the last line repeating the next video's hook** (in batches): cut it.
- **filler "like"s**: trim the obvious ones, keep ones that sound natural.
- **numbers written as two words** (eg "5" + "'2"): set the first word's text to `5'2"` and the second word's text to `""`. a blank word is merged into the one before it in captions; its audio stays.
- after editing, rebuild each line's `text` from its kept words so the table matches.

## 3. best takes (if lines were filmed more than once)

```
.venv/bin/python engine/takes.py <clip>
```

Look at `work/<clip>/takes/line_<id>.jpg` (3 frames per take). Her rules (brand.md): no mistakes first, then most confident and sincere; the 1st or 3rd take is usually best; if equal, keep the last. Swap `keep` so the winner is kept. One line each on why.

## 4. plan.json fields (per line)

| field | values |
|---|---|
| `keep` | true / false |
| `cut_words` | word indexes to drop |
| `motion` | `slow` (slow zoom in), `jump` (jump cut zoom), `punch` (punch-in), `none` |
| `treatment` | `none`, `hook`, `stat pop` (+`stat`), `step` (+`step`), `takeover` (+`takeover_text` list of cards) |
| `broll` | `{"file": "broll/...", "start": <sec>, "mode": "full"}` or null. extra: `"grade": true` (raw footage that needs her grade, eg from the same source file), `"continue": true` (keep playing the previous line's b-roll as one unbroken shot) |
| `keywords` | word indexes to highlight (overrides automatic: numbers/money + the style's keyword list) |
| `sfx` / `sfx_volume` | sound name from sfx/ at the line start, `"none"` to silence auto sounds; volume is a multiplier |
| `notes` | act on it, then clear it |

Top level: `hook_text` (punchy, max ~8 words, appears at 0s; suggest a better one if hers is weak, eg the question her viewer is asking), `style`, `sound` (`sfx`, `sfx_volume`, `music`, `music_volume`).

Her defaults to apply every time:
- first kept line: `"sfx": "click", "sfx_volume": 0.6`
- motion: first line `slow`, then alternate `jump` / `slow`; `punch` on 1-3 key lines (the answer, the money line, the opinion). avoid `none`
- `keywords`: about one per line (numbers first, then the key term)
- reprint: `.venv/bin/python engine/plan.py <clip> --table-only`

## 5. b-roll

```
.venv/bin/python engine/broll.py match <clip>    # keyword suggestions. NOTE: this writes suggestions into plan.json, review them
```

Then use judgement: read each kept line and `broll/library.json` descriptions; place b-roll where it shows what she's saying (products for brand deals, the action she describes). Keep the hook on camera, max ~40% of lines, don't reuse a clip in one video, keep key opinion lines and the ending on camera. Always `"mode": "full"` (she doesn't like picture-in-picture). Pick `start` from the clip's preview (`broll/_previews/`).

New b-roll: `.venv/bin/python engine/broll.py index`, then open each preview it lists and fill `description` (one specific sentence), `tags`, `good_for` in `broll/library.json`. Flag duplicates and black/blurry sections. Clips get removed from `broll/` sometimes: always check files exist before using them.

## 6. review + approval

```
.venv/bin/python engine/review.py <clip>     # opens a page: delete/restore, zoom, treatment, notes, "copy instructions"
```

Show her a short summary (hook, punch-ins, b-roll, cuts) plus anything you guessed. Wait for "go".

## 7a. trouble spots: render them for her to judge

You can't hear, and the transcriber drops or smears words where she stumbles (eg a take that really starts "...one *thing* but getting" transcribed as "one but getting", so the cut lands before "thing" and it plays twice). So when a video is hard (she says she struggled, lots of retakes) or any of these happen, list the trouble spots and render just those:
- a join between two takes (a line spliced from take 1 + take 2, or a retake that starts mid-sentence)
- `cut_words` in the middle of a line (a stumble or restart removed)
- a word whose timing you moved by hand, low-confidence words (`?`) next to a cut, a long word (>0.8s) or a pause inside a line
- anything she points at ("around 0:08 I say thing twice")

```
.venv/bin/python engine/render.py <clip> --spot 7.9,41.5 --pad 2              # full size, ~2s either side of each time in the FINISHED reel
.venv/bin/python engine/render.py <clip> --plan work/<clip>/plan_b.json --spot 7.5   # try a fix without touching plan.json
```

Spot times are finished-reel seconds: get them from `edl.json` `segments` (`new_start` of the piece after the join) or from `--cuts` labels. Output: `output/<clip>_spot.mp4` (or `_spot_<plan name>.mp4`).

How to fix one:
1. find what's really there: print the loudness every 20-40ms around the join (ffmpeg `-f s16le` piped into a small rms loop) and match the syllables to the words. silence dips between words show where a missed word sits
2. where it's a real choice (splice two takes vs keep one whole take), make `plan_a.json` / `plan_b.json` and render a spot of each. transcript fixes that differ per option: back up `transcript.json`, render A, swap, render B, then keep the one she picks
3. send her the spot file(s) with a one-line "A = ..., B = ..." and let her pick by ear
4. apply the winner to `plan.json` / `transcript.json`, delete the spare plan/transcript copies, re-check the spot, then the full render

## 7. check the cuts, then render + qc

**Check the cuts first** (fast, no full render). Renders only ~1.5s either side of every cut (shot changes + b-roll in/out) at half size, scans each one for stray frames, and joins them into `output/<clip>_cuts_preview.mp4` with "cut N at Xs" labels:

```
.venv/bin/python engine/render.py <clip> --cuts                 # all cuts. prints "clean" or "FLASH at ..." per cut
.venv/bin/python engine/render.py <clip> --cuts --only 3,7      # re-check just these after a fix
.venv/bin/python engine/render.py <clip> --cuts --pad 2         # more context either side
```

Fix anything flagged (plan.json `start` / `cut_words` / b-roll `start`), re-check only those cuts, and use the preview when fine-tuning cuts with her. Then one full render:

```
.venv/bin/python engine/render.py <clip>               # --draft quick preview, --no-grade, --cover, --capcut, --music <track>
.venv/bin/python engine/qc.py <clip>                    # FAIL = fix it. explain warnings in one line
```

Output: `output/<clip>_beth.mp4`. Then do the visual checks in checks.md (frames at b-roll moments, hook frame, flash scan).

What render does automatically (don't redo by hand):
- snaps every cut to the real audio (silence map), so words aren't clipped and the first word starts on frame 1; holds ~0.35s after the last word
- keeps one shot while speech runs on: framing only changes where time was cut out, or for a punch-in
- never lets a shot run across a cut that's already inside the footage (compilations)
- b-roll starts/ends exactly on nearby cuts (no 1-frame flash); consecutive b-roll merges seamlessly
- grade on talking-head only (b-roll ungraded unless `"grade": true`)
- captions: lowercase + brand caps from `keep_caps` in beth.json, "I" capitalised, keyword colour, line never wraps (max ~22 chars), phrases like "TikTok Shop" never split

Before rendering, `render.py` stops if any boxed text (hook box, step badge, takeover) is under 4.5:1 contrast. `qc.py` reports it as "text contrast".

## 8. hand over

Send the file, a one-line summary of what changed, the qc result, and anything she should check by ear (you can't hear it). Offer the post caption.

## feedback she's given before (already in the defaults, don't undo)

- "gap at the start" → first word on frame 1, hook text at 0s
- "text outlined" → no outline, soft shadow
- "letters closer" → spacing is applied inline (`\fsp`), style-level spacing is ignored by the renderer
- "hook in capitals, lines closer" → `hook_uppercase`, `hook_line_height`, `hook_chars: 20` (2 lines)
- "I should be capital" → done in captions
- "no small overlay" → b-roll always full screen
- "don't grade the b-roll" → grade before b-roll is laid on
- "Playfair Display" → dropped, keywords are colour only
- "last word cuts off" / "no words cut off" → audio snapping + tail
- "glitchy" → framing changes only at real cuts; no shot straddles a built-in cut
- "noise reduction" → engine has none; it's the DJI mic's NC setting
