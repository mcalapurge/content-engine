# text reels: on-screen text over b-roll, with music

Short (~8-11s) reels: 3 lines of text (hook, middle, call to action) over 3 b-roll shots, with music. No talking. Built by `engine/textreel.py`. Prefix commands with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && `.

## the look (built into textreel.py, don't redo by hand)

- each text beat gets its own b-roll shot with a slow zoom; no transitions, no speed changes
- text exactly as she wrote it (her lowercase, her CAPS for emphasis), Helvetica Neue bold, white, tight letters
- text block **centred in the frame** (both ways), **tight line spacing** (0.84 x font size), balanced line breaks (max ~22 chars a line, no orphan word, "£150 + £700" kept together)
- soft dark band behind the text for readability (no outline, no box)
- numbers, money and CAPS words (3+ letters) in the accent colour (pale pink: see the open issue in SKILL.md)
- reading time per line ≈ 0.3s a word + 1s (hook 2.4-3.8s, others 2-3.8s), snapped to the music's beat so text changes land on a beat
- music: starts at a full, energetic part of the track (skips quiet intros), fades out over the last 0.8s, levelled for social
- no grade (b-roll is already edited). a clip shorter than its beat holds its last frame instead of running out
- settings live at the top of textreel.py: `TEXT_Y`, `TEXT_SIZE`, `LINE_GAP`, `LINE_CHARS`

## steps

1. **import** her spreadsheet (columns: `#`, `type`, `beat 1 (hook)`, `beat 2`, `beat 3`, `b-roll`, `caption`, `carousel it points to`):
   ```
   .venv/bin/python engine/textreel.py import "<path to .xlsx>" <name>      # eg trial
   ```
   → `work/<name>/plan.json`. (the reader handles namespaced xlsx files, which normal parsers miss)
2. **music** (cached, fast):
   ```
   .venv/bin/python engine/textreel.py music      # bpm, energy, length of every track in music/
   ```
   Very quiet/ambient tracks (low energy) suit calm brand-facing reels only.
3. **b-roll pool**: everything in `broll/` and `input_vlog/`. Get best moments:
   ```
   .venv/bin/python engine/vlog.py analyse broll
   .venv/bin/python engine/vlog.py analyse input_vlog          # slow for raw iPhone clips: run in background
   ```
   Read `work/vlog-broll/clips.json` + `broll/library.json` descriptions, and `work/vlog-input_vlog/clips.json` + sheets. **Check files still exist**: she removes clips sometimes.
4. **fill each reel** in plan.json: `shots` = one `{"file", "start"}` per text beat (3 different clips; the first matches the `b-roll` column; the others are related creator-life shots), `music` = `music/<file>`, `music_start` = null (auto) or a beat time. Vary clips and tracks across the set so reels don't look alike. Starting map by reel type:

   | type | tracks (in music/) |
   |---|---|
   | number reveal | my-chapters, move, feels-so-right, think-straight, girl-in-the-southeast, do-my-thing |
   | hot take | look-at-me, splurge, washing-up, sex-and-money, melons |
   | I thought / actually | coffee-drips, last-call, the-waves |
   | mistake | stokerville, undercover, teal, fountains, do-my-thing, sex-and-money |
   | pov | melons, washing-up, still-waters, look-at-me |
   | brand-facing | leaders-greenhouse, nota-bene, wabisabi, fall-night-drift |
   | list tease | move, odyssey, my-chapters |

   b-roll types → closest footage she has (verify files exist and look at the preview):

   | b-roll type | use |
   |---|---|
   | typing an email | cafe laptop typing clips (BR004-1, BR004-8, b-roll 23rd, b-roll 2, trail reels-3, b-roll 3) |
   | laptop + matcha at café | BR004-8, b-roll 2, b-roll 23rd, BR004-9, BR004-1, trail reels-2 |
   | walking in manchester with coffee | BR004-11, BR004-12, b-roll-1, vlog street coffee clips |
   | filming setup with ring light | BR004-2 (home studio), BR004-3 (Alex photographing her), vlog studio clips |
   | desk flat lay with notebook | trail reels-4 (flat lay), vlog jewellery flat lay, BR004-7 |
   | filming product close up / getting ready / skincare | copy_6C2F... (skincare), trail reels-1 (lip product), vlog makeup close-up |
   | pr packages / unboxing | vlog ring box flat lay, b-roll event, vlog pr event |
   | packing camera bag | trail reels-4, vlog Alex with camera |
   | **invoice / banking app screen** | **no real footage yet.** stand-in: cafe laptop / phone shots. tell her |
   | **editing in capcut** | **no real footage yet.** stand-in: BR004-5 (laptop screen with her on a call), b-roll 3. tell her |
   | **sat on sofa with phone** | **no real footage yet.** stand-in: BR004-4, vlog in-bed-with-mug. tell her |

   Suggest she screen-records her banking app (numbers blurred) and CapCut for those reels.
5. **samples first** for a new set or a changed look: render 3 different types, show her, wait for approval:
   ```
   .venv/bin/python engine/textreel.py render <name> --only 1,3,6
   ```
6. **render all** (background, a few minutes for 30):
   ```
   .venv/bin/python engine/textreel.py render <name>
   ```
   Outputs `output/<name>/<name>_01.mp4` ... plus `output/<name>/captions.md` (each reel's post caption + the carousel it points to, ready to paste; only written on a full render).
7. **check** (checks.md): a hook-frame contact sheet of every reel (is the text readable, centred, on a sensible shot?), flash scan, audio present.

## feedback history (already the defaults)

- text was hard to read on bright shots → soft dark band, bigger text
- "line spacing much smaller, make sure it's in the centre" → lines placed individually at 0.84 spacing, block centred
