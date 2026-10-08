# batch split: several videos from one file

Two situations:
- **A. batch take**: they filmed several short videos in one long take, separated by pauses. each video starts with its own hook.
- **B. compilation**: one file made of several different clips stitched together (some talking, some silent footage like close-ups or outfits). they want several videos built from it.

Source files live in `inputs/shop/` (read only). Read the brand's brand.md first (its shop defaults: product name spelling, captions only or not, grade). On a mac, prefix with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ` if ffmpeg isn't found.

## A. batch take

1. **split**
   ```
   .venv/bin/python -m engine batch split inputs/shop/<video>              # splits at pauses >= 1.5s
   .venv/bin/python -m engine batch split inputs/shop/<video> --gap 2.5    # tune the pause
   .venv/bin/python -m engine batch split inputs/shop/<video> --count 6    # force N videos (uses the biggest pauses)
   ```
   Then print the full transcript of every section and READ it:
   - a short section followed by a section with the same hook = **false start**. drop the short one: remove it from `work/<video>/batch.json` `sections` before cutting
   - two sections with only ~2s between them: check whether the second opens with its own hook (separate video) or continues the first
   - a section ending with the next video's hook line = they started the next one; cut that line in the plan later
2. **cut**
   ```
   .venv/bin/python -m engine batch cut inputs/shop/<video>
   ```
   Saves `work/<video>/parts/<video>_01.mp4` ..., three at a time. The picture is copied, not re-encoded (instant, and the edit works from the camera's own frames), so a part starts on the keyframe in the pause before its hook, a moment early; the planner cuts that pause anyway. A part whose keyframe would reach back into the previous video's speech is re-encoded exactly instead (the printout says which). Original untouched.
3. **each part**: follow talking-head.md with the part path. Use `--model medium` to transcribe (the small model mishears product names badly). Loop:
   ```
   for n in 01 02 03; do P=work/<video>/parts/<video>_$n.mp4; .venv/bin/python -m engine transcribe $P --model medium; .venv/bin/python -m engine plan $P --brand <brand> --no-text; done
   ```
   If they chose the small upload file (the tiktok shop size question, asked every job), add `--max-mb <cap>` to each `plan` (eg `--max-mb 10`): every render of that part is then h.265 under the cap, and qc checks it.
   Each part gets its own work folder `work/<video>_<n>/`. Each render lands in its own folder in `output/<brand>/shop/`.
4. one combined summary table (length, hook, punch-in line), one approval, render all in the background, qc all, report in one table.

## B. compilation (several videos built from one file)

1. transcribe the whole file with `--model medium`, print the transcript with gaps, and find the clip boundaries:
   ```
   ffmpeg -hide_banner -i inputs/shop/<file> -vf "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time" -an -f null - 2>&1 | grep -o "lavfi.scd.time=[0-9.]*"
   ```
   Make frame strips of every clip (6-8 frames each) and look at them: which clips are talking, which are silent (close-ups, outfits, product shots), and where the silent "money shots" are (eg zipping a boot up, a reaction face). Note: the transcriber invents words in silence ("you", "Thank you") - ignore those.
2. **plan the videos** and show them a table before building: each talking section = one video; silent footage becomes full-screen b-roll under voiceover lines; you can also make voiceover-only videos (their voice from one section over outfit or close-up footage from another). Lines must stay in source order within a video.
3. **one work folder per video without copying**: hard-link the source and copy the transcript:
   ```
   mkdir -p work/<file>/videos
   for n in 01 02 03; do ln -f inputs/shop/<file>.mp4 work/<file>/videos/<file>_$n.mp4; mkdir -p work/<file>_$n; cp work/<file>/transcript.json work/<file>_$n/; .venv/bin/python -m engine plan work/<file>/videos/<file>_$n.mp4 --brand <brand> --no-text; done
   ```
   (hard links don't touch the original; `resolve()` would follow a symlink back to the same name, so use `ln` without `-s`)
4. in each plan.json: set `keep` for the lines in that video, `cut_words` for stumbles/asides, and b-roll from the same file:
   ```
   "broll": {"file": "inputs/shop/<file>.mp4", "start": 105.6, "mode": "full", "grade": true}
   "broll": {"file": "inputs/shop/<file>.mp4", "start": 0, "mode": "full", "grade": true, "continue": true}   # next line: keep the same shot running
   ```
   - `"grade": true` because it's their raw footage (matches the graded talking shots). drop it if they say the compilation is already graded (then also render with `--no-grade`)
   - silent action moments get cut by the edit (no speech), so bring them back as b-roll over the following line (eg the zip-up under "okay... shut up")
   - make sure a b-roll shot's `start + length` stays inside its clip; render shifts a start past a built-in cut if it's within 1.5s, otherwise it warns
5. summary table, approval, `render.py <video> --cuts` for each video (fix anything flagged), then render all in background, qc, flash scan (checks.md).

## lessons from past batches

- the planner groups different lines that start the same way as retakes; check `takes` groups
- product/brand names: ask for the product name once; add it (and things like "UK", "XL") to `keep_caps` in `brands/<brand>/style.json`
- numbers like 5'2": merge with a blank second word (talking-head.md)
- captions low in the frame can cover the product in full-body try-on shots. offer to move them higher for these videos only: copy `brands/<brand>/style.json` to `brands/<brand>/styles/shop.json`, lower `caption_position` (0 = top, 1 = bottom), and render with `--style shop`. don't change the brand's style.json for this
- garbled endings or asides you can't caption reliably: cut them and say so
