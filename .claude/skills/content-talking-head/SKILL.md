---
name: content-talking-head
description: Edit a talking-to-camera video for Beth's @beth.ejm accounts (TikTok and Instagram). Slash command only.
disable-model-invocation: true
argument-hint: "[folder in input/] [notes]"
---

# /content-talking-head - @beth.ejm (TikTok + Instagram)

Arguments: `$ARGUMENTS` (a folder inside `input/` and/or notes).

**Which clip**: run `engine/inputs.py input [folder] --newest`. Folder given → the newest clip added to it. `ASK` → ask her which folder. No folders → the newest clip added to `input/`. Always just one clip.

**First load the `video-pipeline` skill** and read `brand/brand.md`, `brand/effects.md`, `styles/beth.json`. Follow `video-pipeline/references/talking-head.md`, then `references/checks.md`. One edit works for both TikTok and Instagram (same 9:16 file).

## the account

- @beth.ejm: Beth, UK UGC creator in Manchester, founder of Captura Digital, 3+ years full-time UGC. brands: L'Oréal, Revlon, Spotify, Hugo Boss, Tampax, Hairburst
- topics: rates and pricing (£150 vs £700 jobs, £5k months), contracts and usage rights, pitching, portfolio, brief to delivery, "what I thought vs what actually worked", creator life with her boyfriend Alex
- viewer: UK woman ~22-35, starting out or on a 9-5, wants UGC full-time by 2027, wants real numbers not hype. second viewer: brands hiring UGC creators
- tone: warm, direct, trusted friend a few steps ahead, never salesy

## how she films

- straight to the lens, usually on the couch, window light or clip-on light, DJI mic (its noise cancelling is baked in; the engine adds none)
- repeats a fluffed line (never restarts), sometimes 2-3 goes. take rules: no mistakes first, then most confident and sincere, 1st or 3rd take usually best, if equal keep the last
- raw ~2-3 min → finished ~1-1:30

## the edit

1. `transcribe.py` → `plan.py --style beth` → fix misheard words (tell her your guesses) → `takes.py` if lines repeat
2. `hook_text`: punchy, max ~8 words, ideally the question her viewer is asking. shows IN CAPITALS on 2 lines from 0s; she speaks straight away, no dead air
3. first kept line: `"sfx": "click", "sfx_volume": 0.6`
4. motion: slow zoom on the hook, alternate jump / slow, punch-in on the 2-3 lines that land the point
5. keywords: ~1 per line, numbers first
6. b-roll from `broll/`: full screen, max ~40% of lines, never on the hook, key opinion or ending
7. grade on (b-roll stays ungraded)
8. short summary + `review.py` → wait for "go" → trouble spots (retake joins, stumbles cut, anything she flags, or whenever she says she struggled): `render.py --spot <secs>` for her to judge by ear, A/B with `--plan` when there's a choice → `render.py --cuts` (fix any FLASH, re-check with `--only`) → `render.py` → `qc.py` + flash scan + frame checks → send it, offer a post caption in her voice

## open items

- accent pink #FAEAF0 barely shows on white text; no deeper pink chosen yet
- "text behind my head" hook isn't built yet
