---
name: content-tts
description: Edit TikTok Shop product videos for Beth's shop account wornbybeth - split a batch-filmed take or a compilation into separate videos, captions only. Slash command only.
disable-model-invocation: true
argument-hint: "[folder in input_shop/] [product name] [how many videos]"
---

# /content-tts - TikTok Shop wornbybeth

Arguments: `$ARGUMENTS` (a folder inside `input_shop/`, the product name, maybe how many videos are in it).

**Which files**: run `engine/inputs.py input_shop [folder]`. Folder given → every file in it. `ASK` → ask her which folder. No folders → every file in `input_shop/`. Each file is its own batch take or compilation: work through them one at a time, then give one combined approval table.

**First load the `video-pipeline` skill** and read `brand/brand.md`, `styles/beth.json`. Follow `video-pipeline/references/batch-split.md` (each part then goes through `talking-head.md`), then `references/checks.md`. This account only: not @beth.ejm.

## the account

- wornbybeth: try-on and product videos she earns commission on (past: Halara Wide Leg Trousers, wide-calf boots)
- viewer: midsize UK women looking for clothes / shoes that fit. she shares her sizes (UK 16, 5'2", 17-inch calves, 34" waist / 46" hip, wears XL)
- each video ~15-45s: one product, strong hook, honest try-on, recommendation at the end
- **captions only** (`plan.py --no-text`): she adds her own on-screen text in the TikTok app
- same look as her other videos: beth captions, pink keywords, her grade, quiet click on frame 1

## ask first (if not in the arguments)

1. the product name (spelling; add it to `keep_caps`, plus UK / XL style words)
2. compilation: was it already colour graded? (yes = `--no-grade`, no `"grade": true` on b-roll)

## what she sends

- **batch take**: several videos in one long take, all the same product, no cue between them, each starts with its own hook after a pause. drop false starts (short section then the same hook again)
- **compilation**: clips stitched together (talking sections + silent close-ups / outfits). talking sections become videos; silent footage goes full screen under her voice; voiceover-only videos are possible; silent action moments (zip going up, her reaction) come back as b-roll

## the edit

- transcribe parts with `--model medium` (product names get misheard)
- check retake groups; cut a last line that's really the next video's hook; cut garbled asides
- 5'2" etc: merge into one caption word
- keywords from the selling points (comfortable, stretch, padded, zip, XL, UK 16, 17-inch...)
- punch-in on the sizing / proof / verdict line
- one table of all videos → one "go" → `render.py <video> --cuts` on each (fix any FLASH) → render all in background → `qc.py` each + flash scan → one results table. no covers

## known issues

- captions at ~70% height can cover the product in full-body shots: offer a shop copy of the style with captions higher (batch-split.md)
- pale pink accent barely shows (no deeper pink chosen yet)
