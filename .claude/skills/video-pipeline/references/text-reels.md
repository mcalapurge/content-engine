# text reels: on-screen text over b-roll, with music

Short (~8-11s) reels: 3 lines of text (hook, middle, call to action) over 3 b-roll shots, with music. No talking. Built by `python -m engine textreel`. Read the brand's brand.md first (its trial / text reel defaults: spreadsheet format, reel types, music by type, b-roll pool, footage it still needs). On a mac, prefix with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ` if ffmpeg isn't found.

## the look (built into textreel.py, don't redo by hand)

- each text beat gets its own b-roll shot with a slow zoom; no transitions, no speed changes
- text exactly as written in the sheet (keep their case and CAPS for emphasis)
- font, letter spacing and accent colour come from the brand's `style.json`; text is white
- text block **centred in the frame** (both ways), **tight line spacing** (0.84 x font size), balanced line breaks (max ~22 chars a line, no orphan word, "£150 + £700" kept together)
- soft dark band behind the text for readability (no outline, no box)
- numbers, money and CAPS words (3+ letters) in the brand's accent colour
- reading time per line ≈ 0.3s a word + 1s (hook 2.4-3.8s, others 2-3.8s), snapped to the music's beat so text changes land on a beat
- music: starts at a full, energetic part of the track (skips quiet intros), fades out over the last 0.8s, levelled for social
- no grade (b-roll is already edited). a clip shorter than its beat holds its last frame instead of running out
- layout settings live at the top of textreel.py: `TEXT_Y`, `TEXT_SIZE`, `LINE_GAP`, `LINE_CHARS`

## steps

1. **import** the spreadsheet (default columns: `#`, `type`, `beat 1 (hook)`, `beat 2`, `beat 3`, `b-roll`, `caption`, `carousel it points to`):
   ```
   .venv/bin/python -m engine textreel import "<path to .xlsx>" <name> --brand <brand>      # eg trial
   ```
   → `work/<name>/plan.json`. (the reader handles namespaced xlsx files, which normal parsers miss)
2. **music** (cached, fast):
   ```
   .venv/bin/python -m engine textreel music      # bpm, energy, length of every track in assets/music/
   ```
   Very quiet/ambient tracks (low energy) suit calm brand-facing reels only.
3. **b-roll pool**: the brand's library (`brands/<brand>/broll/`), the set's folder and `inputs/vlog/` (the brand guide may narrow this). Get best moments:
   ```
   .venv/bin/python -m engine vlog analyse brands/<brand>/broll
   .venv/bin/python -m engine vlog analyse inputs/vlog          # slow for raw iPhone clips: run in background
   ```
   Read `work/vlog-broll/clips.json` + `brands/<brand>/broll/library.json` descriptions, and `work/vlog-vlog/clips.json` + sheets. **Check files still exist**: clips get removed sometimes.
4. **fill each reel** in plan.json: `shots` = one `{"file", "start"}` per text beat (3 different clips; the first matches the `b-roll` column; the others related shots), `music` = `assets/music/<file>`, `music_start` = null (auto) or a beat time. Vary clips and tracks across the set so reels don't look alike. Use the brand guide's music-by-type and b-roll-type maps if it has them. When there's no real footage for a b-roll type, use a stand-in and tell them which reels use stand-ins.
5. **samples first** for a new set or a changed look: render 3 different types, show them, wait for approval:
   ```
   .venv/bin/python -m engine textreel render <name> --only 1,3,6
   ```
6. **render all** (background, a few minutes for 30):
   ```
   .venv/bin/python -m engine textreel render <name>            # in the brand saved by import
   ```
   Outputs `output/<brand>/trial/<date>_<time>_<name>/<name>_01.mp4` ... plus `captions.md` in the same folder (each reel's post caption + the carousel it points to, ready to paste; only written on a full render).
7. **check** (checks.md): a hook-frame contact sheet of every reel (is the text readable, centred, on a sensible shot?), flash scan, audio present.

## feedback history

In the brand's brand.md. Don't undo anything listed there.
