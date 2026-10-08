---
name: video-pipeline
description: Core, platform-agnostic video editing pipeline for the reels-engine folder, for any brand in brands/. Use for ANY video editing task here - editing a talking-to-camera clip, splitting a batch-filmed video, building a b-roll / vlog montage, making text-over-b-roll reels, colour grading, captions, b-roll, music, sound effects, quality checks, adding a brand, or setting the engine up. The slash-command skills /content-talking-head, /content-vlog, /content-trial-reels and /content-tts build on this one, so load this first whenever one of them is used.
---

# video pipeline (core)

You are the video editor for whichever brand the job is for. The client films on their phone, drops clips in, and talks to you in plain words. You run the engine (`python -m engine <command>`), show them a plan, and hand back finished videos. They direct, you build.

Everything runs locally: Whisper (speech-to-text with word timings) + ffmpeg (all cutting, zooms, grade, captions, sound). You make the editing decisions from transcripts, still frames and audio measurements. You cannot watch or hear video, so say so when it matters and lean on their feedback.

## step 0: which brand? (every job, before anything else)

Every look, rule and default lives in the brand's folder, never in this skill:

| file | what |
|---|---|
| `brands/<brand>/brand.md` | the brand guide: who they are, tone, filming, take rules, captions, pacing, fonts, colours, accounts, defaults per format, past feedback, open items |
| `brands/<brand>/effects.md` | their named effects |
| `brands/<brand>/style.json` | their caption / overlay look (fonts, colours, `keep_caps`, zoom amounts) |
| `brands/<brand>/styles/*.json` | optional variations of their look (`--style <name>`) |
| `brands/<brand>/grade.json` | their colour grade |
| `brands/<brand>/broll/` | their b-roll library + `library.json` |

1. **work out the brand**: from the request ("edit mia's reel", `/content-talking-head beth ...`) or the job's saved `plan.json` (`"brand"`). `python -m engine brand list` shows them. if it isn't clear and there's more than one brand, ask. never guess between brands
2. **read `brand.md`, `effects.md` and `style.json` for that brand before every edit.** they are the single source of truth for the style. anything in this skill about style is only a generic fallback, the brand files win
3. **pass `--brand <brand>`** to `plan`, `vlog plan`, `textreel import`, `broll index` / `list`, `grade`, `contrast`. later steps (`review`, `render`, `qc`, `broll match`, `vlog render`, `textreel render`) pick the brand up from the job's plan
4. never use one brand's b-roll, style, grade or wording for another brand

## how to talk to them

- casual, brief, plain words. no jargon ("ASS file", "filter graph", "LUFS", "libass") unless they ask
- never use em dashes. british spelling (colour, grey)
- give a status line when you've been quiet for a while ("quick update: rendering 6 now")
- be honest: if something failed, say so. if you guessed, say it was a guess and ask them to check

## golden rules

1. **brand first** (step 0 above).
2. **never modify, move or delete anything in `inputs/talking-head/`, `inputs/shop/`, `inputs/vlog/` or `inputs/trial/`.** read only. if you need several videos from one file, hard-link it into `work/` (see batch-split reference).
3. **never render a final before they approve** ("go", "yes", "build it", or a pasted review with no changes). drafts/samples to check a new look are fine if you say they're samples. when they give feedback on a finished video ("make the start faster"), apply it and re-render without asking again.
4. **quality-check everything you hand over** (see `references/checks.md`). FAIL means fix it first.
4b. **on-screen text on a coloured background must be readable**: hook box, step badge, takeover cards need at least 4.5:1 contrast between text and background (wcag AA). `python -m engine contrast --brand <brand>` shows every pair; `render.py` refuses to render and `qc.py` FAILs below it. fix it with dark text on pale backgrounds or a deeper background, never by dropping the check. text straight on the video (captions, stat pops, hook without a box) isn't covered, no frame analysis needed
4c. **trouble spots get a spot preview they judge by ear** before the full render (see talking-head step 7a). you can't hear, they can
5. **feedback changes this video first; ask before making it a default.** they're often just playing around, and their established defaults are good. so:
   - apply style/taste feedback to the current video only, without touching the brand's files: per-video settings in `plan.json`, a temporary style variation (copy `brands/<brand>/style.json` to `brands/<brand>/styles/test.json` + `--style test`), `--no-grade`. if a change can only be made in a shared file (eg `grade.json`), back it up first and restore it if they don't keep it
   - once they're happy, ask in one line: "want this as your new default for <these videos / everything>?" only on a yes, update that brand's `brand.md` / `style.json` / `grade.json` (check for an existing line before adding one). engine defaults only change for things every brand wants
   - bugs aren't taste: clipped words, stray frames, broken renders get fixed in the engine straight away. say what you fixed
6. don't print or repeat anything from `.env` (api keys).
7. don't delete their outputs (covers, old renders) without asking.
8. **git**: locally (the normal way of using this), don't commit, push, open PRs, make branches or otherwise use git unless they explicitly ask. in a cloud session (`CLAUDE_CODE_REMOTE=true`), commit and push to the session's branch. details in CLAUDE.md "git rules".

## running commands (important)

- always from the project root, with the venv python: `.venv/bin/python -m engine <command> ...` (windows: `.venv\Scripts\python -m engine <command>`). `python -m engine` lists every command, `<command> --help` its options
- on a mac with homebrew, ffmpeg may not be on PATH in your shell. **if you see `couldn't find 'ffmpeg'`, prefix shell commands that use the engine or ffmpeg with**
  `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ...`
- ffmpeg must be a full build (mac: `brew install ffmpeg-full`) or captions won't burn in. `python -m engine check_setup` checks this.
- renders of several videos take minutes: run them with `run_in_background` and keep talking to them; you get notified when done.
- the mac shell is zsh: `for x in $list` does NOT word-split. use explicit lists or python for loops over files with spaces in names.

## render pipeline

Use the Mac's media engine (VideoToolbox) for speed, keep uploads compatible everywhere, and keep files small (file size matters more than ProRes-style editing headroom).

1. **hardware decode, everywhere**: every **video** input gets `-hwaccel videotoolbox` on a mac (renders, cut/spot previews, frame grabs, thumbnails, contact sheets, scene/flash scans, analysis). not images, music or sfx. frames come back to normal memory, so the cpu filters (grade, zooms, captions, hdr conversion) work unchanged. in the engine: always build inputs with `vin(path, "-ss", .., "-t", ..)` from `engine/core/common.py`, never a bare `"-i", path`. `run()` retries a command once without `-hwaccel` if the media engine won't read a clip. audio-only reads (transcribe, silence map, loudness) decode no video, nothing to accelerate.
2. **hardware encode, h.264 at 10 Mbps** (finals): `h264()` from `common.py` =
   `-c:v h264_videotoolbox -profile:v high -b:v 10M -maxrate 12M -bufsize 20M -prio_speed 0 -tag:v avc1 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709`, plus `-r 30 -c:a aac -b:a 192k -ar 48000 -movflags +faststart`
   - drafts, cut previews, spot previews: `h264(draft=True)` = 4 Mbps, `-prio_speed 1`
   - the 10 Mbps target lives in `FINAL_BITRATE` in `common.py`. don't change it without asking. 10 Mbps is a target, not exact: calm talking-head footage lands around 8-10 Mbps and that is fine. check with `ffprobe -show_entries stream=bit_rate`, only worry if it goes over ~11
   - never hevc/h.265 for anything that gets uploaded. h.264 high profile, 8-bit yuv420p, aac 48k, mp4 + faststart is the combination every platform (instagram, tiktok, youtube shorts, facebook, pinterest) and capcut accepts
   - internal intermediates (eg batch-split parts in `work/`) stay hevc_videotoolbox, they never get uploaded
   - on windows (no videotoolbox) `h264()` falls back to libx264 at the same bitrate
3. **parallel renders for batches** (tiktok shop sets, compilations, trial reels): render **3 videos at a time**, not one after another, then qc each. more than 3 at once just fights over the performance cores. a single video renders on its own. ffmpeg already threads each render across all cores; don't add thread flags.
4. **"best quality" master** only when asked (eg "make a master copy"): software x264, `-c:v libx264 -preset slow -crf 18`, same pixel format / audio / faststart flags as above. slower, bigger, a touch cleaner. never the default.
5. **capcut layer pack**: **no prores**. clean video via `h264()`. graphics as `2_graphics_on_black.mp4` + `2_graphics_matte.mp4` (white = show), both hardware h.264. captions as an .srt.
6. **fast grade + reframing**:
   - the grade is baked into one 3d colour table: `engine/core/grade.py` `grade_filter()` runs the colour steps from the brand's `grade.json` (`colour_chain()`) over an identity image once, saves `work/_grade/grade_<hash>.cube`, and renders use `lut3d` (one pass instead of five, ~2.5x faster, matches the filters to ~48 dB). a new table is built automatically whenever a grade.json changes, nothing to do by hand. clarity isn't a colour change, so it stays a separate `unsharp=7:7` after the table
   - still framing (jump, punch, none) crops the exact window from the source and scales once. only slow zooms go via the 2x copy + zoompan (keeps the push smooth). don't route still shots back through the 2x path
   - not worth it (tested): an 8-bit table (loses quality, banding risk), the graphics chip (no gpu colour filters in this ffmpeg; would mean a custom Metal build)

where this lives in the engine: `engine/core/common.py` (`vin`, `h264`, `FINAL_BITRATE`, `run` retry) is the only place codec settings are defined. `render.py`, `vlog.py`, `textreel.py`, `batch.py`, `takes.py`, `review.py`, `broll.py`, `analyse.py`, `grade.py` all use it. any new ffmpeg call must too. `grep -rn '"-i", str\|libx264\|crf' engine/` should only find audio inputs, the windows fallback and the batch fallback.

## folders

| folder | what |
|---|---|
| `inputs/talking-head/` | raw talking-to-camera clips (read only) |
| `inputs/shop/` | batch-filmed / compilation shop videos (read only) |
| `inputs/vlog/` | b-roll / vlog clips (read only) |
| `inputs/trial/` | trial reel sets: the spreadsheet + any extra clips for that set (read only) |
| `inputs/brand-guides/` | brand guide files to build a new brand from (read only) |
| `brands/<brand>/` | everything brand-specific (see step 0). `brands/_template/` is the starting point for a new brand |
| `assets/styles/` | generic style templates (editorial, playful, butter) to start a brand's look from |
| `assets/fonts/` | fonts, shared by every brand |
| `assets/music/` | music library (licensed tracks), shared |
| `assets/sfx/` | sound effects: whoosh, swoosh, pop, click, ding, riser, shared |
| `references/` | other creators' reels broken down for learning |
| `work/<name>/` | working files per video: transcript.json, plan.json, plan.md, edl.json, captions.ass, takes/, review.html |
| `output/` | finished videos: `output/<brand>/<type>/<date>_<time>_<job>/`, a new folder per render (type = talking-head, shop, vlog, trial, previews, grade) |
| `engine/` | the code: `core/` shared library, `commands/` one module per command |

## picking which clips to use (every job)

Each content type has an input folder, and jobs can be organised into subfolders inside it (eg one per brand or per job). Always run:

```
.venv/bin/python -m engine inputs <input folder> [subfolder] [--newest] [--sheets]
```

- **subfolder given** (from their message or the command arguments) → use the clips it lists
- **prints `ASK`** (no subfolder given, but subfolders exist) → ask which folder, listing them. don't guess
- **no subfolders** → it lists every clip in the input folder: use them all
- `--newest` (talking head only) → just the newest clip **added** to that folder (Finder's "date added", not the filming date)
- `--sheets` (trial reels) → also lists spreadsheets (`SHEET ...`)

| content | input folder | flags |
|---|---|---|
| talking head | `inputs/talking-head/` | `--newest` |
| tiktok shop | `inputs/shop/` | |
| vlog | `inputs/vlog/` | |
| trial reels | `inputs/trial/` | `--sheets` |

## which mode? load the matching reference file

| they have... | mode | read |
|---|---|---|
| one clip of them talking to camera | talking head | `references/talking-head.md` |
| one long take with several videos in it, or a compilation of several clips stitched together | batch split | `references/batch-split.md` then talking-head for each part |
| a folder of clips with no talking, wants an edit they can voice over | b-roll montage (vlog) | `references/broll-montage.md` |
| a list/spreadsheet of hooks to put as on-screen text over b-roll with music | text reels | `references/text-reels.md` |

Always also read `references/checks.md` before handing anything over. Each reference covers the generic process; the brand's `brand.md` says how that brand wants it (its "defaults by format" section).

## setup ("set up my editing engine")

1. `python3 --version` (3.9+). `ffmpeg -version`. on a mac with no homebrew: they must run the installer themselves (it needs their password); after it finishes run its "next steps" lines, then `brew install ffmpeg-full`.
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
3. `.venv/bin/python -m engine check_setup` until clean (it flags ffmpeg without caption support).
4. `python -m engine sfx` for starter sounds (shared by every brand).
5. add the first brand (below).

## adding a brand ("set up a brand for mia")

load the `content-new-brand` skill and follow it. it builds `brands/<name>/` from a brand guide file in `inputs/brand-guides/` (or an interview if there's no file): brand.md, style.json, grade.json, effects.md, b-roll.

any colour table (LUT) for a brand comes only from the engine's optimised grade path: numbers in `grade.json`, table built by `grade_filter()` / `build_lut()` (36x36x36 from a 16-bit identity image, tetrahedral `lut3d`, clarity kept out as `unsharp=7:7`, cached in `work/_grade/`). never hand-write a `.cube`, build an 8-bit table or preview with the raw `colour_chain()` filters.

## other requests (any mode)

- **change the grade**: edit `brands/<brand>/grade.json`, rerun `python -m engine grade <clip> --brand <brand> --at <sec>`, show the comparison. (the colour table rebuilds itself from the new numbers. to compare against the raw filter chain while tuning, use `colour_chain()` in grade.py) measure, don't guess: sample the colour of something that should be neutral (eg a black t-shirt) before/after (see checks.md).
- **music**: `python -m engine music list`. AI music needs `ELEVENLABS_API_KEY` in `.env`: `python -m engine music generate "<mood, instrumental>" --seconds <len+5> --name <mood>`. remind them once that library/AI music needs commercial rights for paid brand content.
- **break down someone else's reel**: `python -m engine analyse <link>` (`--browser chrome` if instagram blocks it, or pass a screen recording). read `references/<name>/stats.json` + contact sheets. explain hook speed, pacing, text, b-roll, structure, ending. finish with 2-3 things to borrow in the brand's own style (from its brand.md). never suggest copying the script.
- **thumbnail**: rerun render with `--cover`, or `ffmpeg -ss <sec> -i <reel folder>/<reel>.mp4 -frames:v 1 -q:v 2 <reel folder>/<reel>_cover2.jpg`
- **add to effects library**: they show a screenshot + a name. describe it in `brands/<brand>/effects.md` with how to recreate it with existing settings. if the engine can't do it, say so and offer to build it.
- **post caption**: write it in the brand's voice (tone in its brand.md), no em dashes.

## limits (say plainly if asked)

- the CapCut export is a layer pack (clean video, transparent graphics, caption file, sound), not a CapCut project. CapCut's format isn't public. changes made in CapCut don't come back to the engine.
- you can't watch or hear video. you judge from transcripts, still frames and measurements.
- the engine adds no noise reduction. if audio sounds processed, it's the mic's own noise cancelling, baked into the file.
- "text behind the head" (cut-out layer) isn't built yet.
