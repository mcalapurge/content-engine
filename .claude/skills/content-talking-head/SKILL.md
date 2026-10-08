---
name: content-talking-head
description: Edit a talking-to-camera video (TikTok / Instagram reel) for a brand in brands/. Slash command only.
disable-model-invocation: true
argument-hint: "<brand> [folder in inputs/talking-head/] [notes]"
---

# /content-talking-head - talking-to-camera reel (TikTok + Instagram)

Arguments: `$ARGUMENTS` (the brand, a folder inside `inputs/talking-head/` and/or notes).

**Which brand**: the brand named in the arguments or request (a folder in `brands/`). Not given and more than one brand (`python -m engine brand list`) → ask. Never guess.

**Which clip**: run `python -m engine inputs inputs/talking-head [folder] --newest`. Folder given → the newest clip added to it. `ASK` → ask which folder. No folders → the newest clip added to `inputs/talking-head/`. Always just one clip.

**First load the `video-pipeline` skill**, then read the brand's files: `brands/<brand>/brand.md` (especially "talking head defaults", take rules, captions, feedback history, open items), `brands/<brand>/effects.md`, `brands/<brand>/style.json`. Follow `video-pipeline/references/talking-head.md`, then `references/checks.md`. One 9:16 edit works for both TikTok and Instagram.

All styling, wording and defaults come from the brand's files. This skill only sets the order of work.

## the edit

1. `transcribe` → `plan --brand <brand>` → fix misheard words using the brand guide's spellings (say your guesses) → `takes` if lines repeat, picked by the brand's take rules
2. `hook_text`: punchy, max ~8 words, per the brand's hook rules
3. apply the brand's talking-head defaults: first-line sound, motion mix, punch-ins, keywords
4. b-roll only from `brands/<brand>/broll/`, shown the way the brand wants, within the brand's share of lines
5. grade per the brand (b-roll ungraded unless it's their raw footage)
6. short summary + `review` → wait for "go" → trouble spots (retake joins, stumbles cut, anything they flag): `render --spot <secs>` for them to judge by ear, A/B with `--plan` when there's a choice → `render --cuts` (fix any FLASH, re-check with `--only`) → `render` → `qc` + flash scan + frame checks → send it, offer a post caption in the brand's voice
7. mention any of the brand's open items that affect this video
