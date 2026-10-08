# batch split: several videos from one file

Two situations:
- **A. batch take**: she filmed several short videos in one long take, separated by pauses. each video starts with its own hook.
- **B. compilation**: one file made of several different clips stitched together (some talking, some silent footage like close-ups or outfits). she wants several videos built from it.

Source files live in `input_shop/` (read only). Prefix engine commands with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && `.

## A. batch take

1. **split**
   ```
   .venv/bin/python engine/batch.py split input_shop/<video>              # splits at pauses >= 1.5s
   .venv/bin/python engine/batch.py split input_shop/<video> --gap 2.5    # tune the pause
   .venv/bin/python engine/batch.py split input_shop/<video> --count 6    # force N videos (uses the biggest pauses)
   ```
   Then print the full transcript of every section and READ it:
   - a short section followed by a section with the same hook = **false start**. drop the short one: remove it from `work/<video>/batch.json` `sections` before cutting
   - two sections with only ~2s between them: check whether the second opens with its own hook (separate video) or continues the first
   - a section ending with the next video's hook line = she started the next one; cut that line in the plan later
2. **cut**
   ```
   .venv/bin/python engine/batch.py cut input_shop/<video>
   ```
   Saves `work/<video>/parts/<video>_01.mp4` ... (re-encoded, colour info kept). Original untouched.
3. **each part**: follow talking-head.md with the part path. Use `--model medium` to transcribe (the small model mishears product names badly). Loop:
   ```
   for n in 01 02 03; do P=work/<video>/parts/<video>_$n.mp4; .venv/bin/python engine/transcribe.py $P --model medium; .venv/bin/python engine/plan.py $P --no-text; done
   ```
   Each part gets its own work folder `work/<video>_<n>/`. Outputs: `output/<video>_<n>_beth.mp4`.
4. one combined summary table (length, hook, punch-in line), one approval, render all in the background, qc all, report in one table.

## B. compilation (several videos built from one file)

1. transcribe the whole file with `--model medium`, print the transcript with gaps, and find the clip boundaries:
   ```
   ffmpeg -hide_banner -i input_shop/<file> -vf "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time" -an -f null - 2>&1 | grep -o "lavfi.scd.time=[0-9.]*"
   ```
   Make frame strips of every clip (6-8 frames each) and look at them: which clips are talking, which are silent (close-ups, outfits, product shots), and where the silent "money shots" are (eg zipping a boot up, a reaction face). Note: the transcriber invents words in silence ("you", "Thank you") - ignore those.
2. **plan the videos** and show her a table before building: each talking section = one video; silent footage becomes full-screen b-roll under voiceover lines; you can also make voiceover-only videos (her voice from one section over outfit or close-up footage from another). Lines must stay in source order within a video.
3. **one work folder per video without copying**: hard-link the source and copy the transcript:
   ```
   mkdir -p work/<file>/videos
   for n in 01 02 03; do ln -f input_shop/<file>.mp4 work/<file>/videos/<file>_$n.mp4; mkdir -p work/<file>_$n; cp work/<file>/transcript.json work/<file>_$n/; .venv/bin/python engine/plan.py work/<file>/videos/<file>_$n.mp4 --no-text; done
   ```
   (hard links don't touch the original; `resolve()` would follow a symlink back to the same name, so use `ln` without `-s`)
4. in each plan.json: set `keep` for the lines in that video, `cut_words` for stumbles/asides, and b-roll from the same file:
   ```
   "broll": {"file": "input_shop/<file>.mp4", "start": 105.6, "mode": "full", "grade": true}
   "broll": {"file": "input_shop/<file>.mp4", "start": 0, "mode": "full", "grade": true, "continue": true}   # next line: keep the same shot running
   ```
   - `"grade": true` because it's her raw footage (matches the graded talking shots). drop it if she says the compilation is already graded (then also render with `--no-grade`)
   - silent action moments get cut by the edit (no speech), so bring them back as b-roll over the following line (eg the zip-up under "okay... shut up")
   - make sure a b-roll shot's `start + length` stays inside its clip; render shifts a start past a built-in cut if it's within 1.5s, otherwise it warns
5. summary table, approval, `render.py <video> --cuts` for each video (fix anything flagged), then render all in background, qc, flash scan (checks.md).

## lessons from past batches

- the planner groups different lines that start the same way as retakes; check `takes` groups
- product/brand names: ask her the product name once; add it (and things like "UK", "XL") to `keep_caps` in `styles/beth.json`
- numbers like 5'2": merge with a blank second word (talking-head.md)
- captions sit at ~70% height, which in full-body try-on shots covers the product (trousers, boots). offer to move them higher for these videos only: copy `styles/beth.json` to e.g. `styles/beth-shop.json`, lower `caption_position` (0 = top, 1 = bottom), and render with `--style beth-shop`. don't change beth.json for this
- garbled endings or asides you can't caption reliably: cut them and tell her
