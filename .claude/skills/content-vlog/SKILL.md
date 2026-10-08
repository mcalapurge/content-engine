---
name: content-vlog
description: Cut a folder of b-roll / vlog clips into a ~30s edit for Beth's @beth.ejm accounts (Instagram and TikTok). Slash command only.
disable-model-invocation: true
argument-hint: "[folder in input_vlog/] [music track] [no grade]"
---

# /content-vlog - @beth.ejm (Instagram + TikTok)

Arguments: `$ARGUMENTS` (a folder inside `input_vlog/`, optionally a track in `music/` and "no grade").

**Which clips**: run `engine/inputs.py input_vlog [folder]`. Folder given → every clip in it. `ASK` → ask her which folder. No folders → every clip in `input_vlog/` (then analyse / plan / render `input_vlog` itself).

**First load the `video-pipeline` skill** and read `brand/brand.md`, `styles/beth.json`. Follow `video-pipeline/references/broll-montage.md`, then `references/checks.md`. Not for the TikTok Shop account.

## what she wants

- a ~30s edit with no talking; she adds a voiceover (and maybe her own music) later
- very fast start: teaser of 4-frame snaps from ~16 different clips (~2s), then short opening shots
- the most engaging order (a little story, never the same scene twice in a row, satisfying ending), not chronological
- NO transitions (no flash, whip, fade), NO speed changes; lots of jump cuts (same clip, skip ahead, tighter frame) mixed with slow zooms; freeze frames are ok
- keep the natural sound (check it isn't a silent track)
- music only if she names a track: then cut on the beat, and she also gets a `_no_music` version
- grade: ask if she didn't say (last time: "they don't need colour grading")

## steps

1. `vlog.py analyse` → look at every frame sheet → write a description per clip
2. build `work/vlog-<folder>/plan.json` by eye (or `vlog.py plan` as a start) → `vlog.py table`
3. send the storyboard + a section-by-section summary → wait for "go"
4. `vlog.py render` (`--no-grade` if asked) → checks → send it
