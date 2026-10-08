---
name: content-vlog
description: Cut a folder of b-roll / vlog clips into a short edit (Instagram + TikTok) for a brand in brands/. Slash command only.
disable-model-invocation: true
argument-hint: "<brand> [folder in inputs/vlog/] [music track] [no grade]"
---

# /content-vlog - b-roll / vlog edit (Instagram + TikTok)

Arguments: `$ARGUMENTS` (the brand, a folder inside `inputs/vlog/`, optionally a track in `assets/music/` and "no grade").

**Which brand**: the brand named in the arguments or request (a folder in `brands/`). Not given and more than one brand → ask. Never guess.

**Which clips**: run `python -m engine inputs inputs/vlog [folder]`. Folder given → every clip in it. `ASK` → ask which folder. No folders → every clip in `inputs/vlog/` (then analyse / plan / render `inputs/vlog` itself).

**First load the `video-pipeline` skill**, then read `brands/<brand>/brand.md` (especially its vlog / b-roll edit defaults, feedback history), `brands/<brand>/effects.md`. Follow `video-pipeline/references/broll-montage.md`, then `references/checks.md`.

All styling (length, teaser, transitions, speed, jump cuts, sound, music, grade) comes from the brand's files. This skill only sets the order of work.

## steps

1. `vlog analyse` → look at every frame sheet → write a description per clip
2. build `work/vlog-<folder>/plan.json` by eye (or `vlog plan --brand <brand>` as a start) following the brand's vlog defaults → `vlog table`
3. send the storyboard + a section-by-section summary → wait for "go"
4. `vlog render` (graded with the brand's grade; `--no-grade` if asked or the brand says so) → checks → send it
5. grade not mentioned and the brand guide doesn't settle it → ask
