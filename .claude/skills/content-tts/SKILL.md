---
name: content-tts
description: Edit TikTok Shop product videos for a brand in brands/ - split a batch-filmed take or a compilation into separate videos, captions only by default. Slash command only.
disable-model-invocation: true
argument-hint: "<brand> [folder in inputs/shop/] [product name] [how many videos] [max size, eg 10mb]"
---

# /content-tts - TikTok Shop videos

Arguments: `$ARGUMENTS` (the brand, a folder inside `inputs/shop/`, the product name, maybe how many videos are in it, maybe a size cap like `10mb`: that answers the file size question for this job).

**Which brand**: the brand named in the arguments or request (a folder in `brands/`; a shop account can be its own brand or a section of one, see its brand.md "accounts"). Not given and more than one brand → ask. Never guess.

**Which files**: run `python -m engine inputs inputs/shop [folder]`. Folder given → every file in it. `ASK` → ask which folder. No folders → every file in `inputs/shop/`. Each file is its own batch take or compilation: work through them one at a time, then give one combined approval table.

**First load the `video-pipeline` skill**, then read `brands/<brand>/brand.md` (especially "tiktok shop defaults", captions, feedback history, open items), `brands/<brand>/effects.md`, `brands/<brand>/style.json`. Follow `video-pipeline/references/batch-split.md` (each part then goes through `talking-head.md`), then `references/checks.md`.

All styling, wording and defaults come from the brand's files. This skill only sets the order of work.

## ask first (if not in the arguments or the brand guide)

1. the product name (spelling; add it to `keep_caps` in the brand's style.json, plus size words like UK / XL)
2. compilation: was it already colour graded? (yes = `--no-grade`, no `"grade": true` on b-roll)

## always ask (every job, even if the brand guide or an earlier job answered it)

3. **file size**: "normal file, or a small h.265 one under 10MB for uploading?" they can name another cap ("under 8MB"). one answer covers every video in the job
   - small → `--max-mb <cap>` on every part's `plan` (saved in its plan.json, so re-renders after feedback keep it without asking again). the small file is the only one made, named `<part>_<style>_<cap>mb.mp4`; there's no normal-size copy, so if they later want one, re-render with `--max-mb 0`
   - normal → nothing to add (h.264, as usual)
   - a video too long to fit the cap at a watchable quality is refused before rendering: say so and offer a higher cap or a tighter cut

## what they send

- **batch take**: several videos in one long take, all the same product, no cue between them, each starts with its own hook after a pause. drop false starts (short section then the same hook again)
- **compilation**: clips stitched together (talking sections + silent close-ups / outfits). talking sections become videos; silent footage goes full screen under their voice; voiceover-only videos are possible; silent action moments come back as b-roll

## the edit

- transcribe parts with `--model medium` (product names get misheard)
- `plan --brand <brand> --no-text` unless the brand guide says shop videos get on-screen text, plus `--max-mb <cap>` if they chose the small file
- check retake groups; cut a last line that's really the next video's hook; cut garbled asides
- keywords and punch-ins per the brand's shop defaults
- one table of all videos (with the file choice: "normal" or "h.265, max 10MB") → one "go" → `render <video> --cuts` on each (fix any FLASH) → render all in background → `qc` each + flash scan → one results table (add each file's size when capped: qc FAILs anything over the cap or not h.265). covers only if asked
