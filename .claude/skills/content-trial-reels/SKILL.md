---
name: content-trial-reels
description: Make Instagram trial reels (3 lines of on-screen text over b-roll with music) from a spreadsheet of hooks, for a brand in brands/. Slash command only.
disable-model-invocation: true
argument-hint: "<brand> [folder in inputs/trial/]"
---

# /content-trial-reels - Instagram trial reels

Arguments: `$ARGUMENTS` (the brand, and a folder inside `inputs/trial/` or a path to a spreadsheet elsewhere).

**Which brand**: the brand named in the arguments or request (a folder in `brands/`). Not given and more than one brand → ask. Never guess.

**Which files**: run `python -m engine inputs inputs/trial [folder] --sheets`. Folder given → its spreadsheet + clips. `ASK` → ask which folder. No folders → everything in `inputs/trial/`. No spreadsheet found → ask for it. Name the set after the folder (eg `october`); with no folder use `trial`, `trial-2`... (don't overwrite an existing set).

**B-roll pool**: clips from that folder + `brands/<brand>/broll/` + `inputs/vlog/` (top level), unless the brand guide narrows it. Never another brand's b-roll.

**First load the `video-pipeline` skill**, then read `brands/<brand>/brand.md` (especially "trial reel defaults": spreadsheet columns, reel types, music by type, b-roll types, footage still needed, status) and `brands/<brand>/style.json`. Follow `video-pipeline/references/text-reels.md`, then `references/checks.md`.

All styling and wording rules come from the brand's files. This skill only sets the order of work.

## steps

1. `textreel import <sheet> <set name> --brand <brand>` → `textreel music` → `vlog analyse` the set's folder (if it has clips), plus `brands/<brand>/broll` and `inputs/vlog` if not already done (check `work/vlog-*/clips.json`)
2. fill shots + music for every reel (the brand's maps if it has them); list the reels using stand-in footage
3. render 3 samples of different types (`--only`) → wait for their ok on the look
4. render all in the background → hook-frame contact sheet + flash scan + audio check
5. hand over the set's folder in `output/<brand>/trial/` with its `captions.md` (post captions + carousels)
6. update the brand guide's status line for this set
