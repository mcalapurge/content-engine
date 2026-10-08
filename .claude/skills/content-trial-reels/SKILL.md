---
name: content-trial-reels
description: Make Instagram trial reels for @beth.ejm (3 lines of on-screen text over b-roll with music) from a spreadsheet of hooks. Slash command only.
disable-model-invocation: true
argument-hint: "[folder in input_trial/]"
---

# /content-trial-reels - Instagram @beth.ejm

Arguments: `$ARGUMENTS` (a folder inside `input_trial/`, or a path to a spreadsheet elsewhere).

**Which files**: run `engine/inputs.py input_trial [folder] --sheets`. Folder given → its spreadsheet + clips. `ASK` → ask her which folder. No folders → everything in `input_trial/`. No spreadsheet found → ask for it. Name the set after the folder (eg `october`); with no folder use `trial`, `trial-2`... (don't overwrite an existing set).

**B-roll pool**: clips from that folder + the whole `broll/` library + `input_vlog/` (top level).

**First load the `video-pipeline` skill** and read `brand/brand.md`, `styles/beth.json`. Follow `video-pipeline/references/text-reels.md`, then `references/checks.md`.

## what they are

- Instagram trial reels to test hooks: ~8-11s, hook → middle line → call to action pointing to a carousel on her grid/profile
- spreadsheet columns: `#`, `type`, `beat 1 (hook)`, `beat 2`, `beat 3`, `b-roll`, `caption`, `carousel it points to`
- types: number reveal, hot take, I thought / actually, mistake, pov, brand-facing, list tease (music map by type in text-reels.md)
- keep her text exactly as written: lowercase with CAPS for emphasis
- text centred, tight line spacing, soft dark band behind it, numbers / money / CAPS in the accent colour
- b-roll from `broll/` + `input_vlog/` (check files exist), matched to the `b-roll` column first, varied across the set. no grade, no transitions, no speed changes

## steps

1. `textreel.py import <sheet> <set name>` → `textreel.py music` → `vlog.py analyse` the set's folder (if it has clips), plus `broll` and `input_vlog` if not already done (check `work/vlog-*/clips.json`)
2. fill shots + music for every reel; list the reels using stand-in footage
3. render 3 samples of different types (`--only`) → wait for her ok on the look
4. render all in the background → hook-frame contact sheet + flash scan + audio check
5. hand over `output/<name>/` and `captions.md` (post captions + carousels)

## footage she still needs

Banking app / invoice screens, editing in CapCut, sitting on the sofa with her phone. Use stand-ins until she films them and tell her which reels use stand-ins.

## status (7 Oct 2026)

- set `trial`: 30 reels in `output/trial/` from `work/trial/plan.json`. no final feedback yet
- `input_vlog/` has 64 new raw clips (travel, airport, plane, Italy lakeside, cafes, food, selfies, shops) measured but not yet described or used
- the DJI kitchen-table clip was removed from `broll/`; don't use it
