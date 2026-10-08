# checks before handing anything over + known pitfalls

You can't watch or hear video, so measure. `<output folder>` below = the folder the render printed (also `output` in the job's `edl.json`). Run these after every render and fix anything they find before saying it's done. On a mac, prefix with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ` if ffmpeg isn't found.

## 1. engine qc (talking head / shop)

```
.venv/bin/python -m engine qc <clip-or-part-path>
```
Checks format, length, dead air, loudness, caption coverage, hook, grade, b-roll, sfx, leftover fillers, uncertain words, text contrast (against the style the video was rendered with). FAIL = fix. Expected warnings: "no hook text" on `--no-text` videos; "caption accuracy" lists low-confidence words (check them, say they read fine or fix them).

## 1b. text contrast (anything with on-screen graphics)

Text on a solid background (hook box, step badge, takeover cards) needs 4.5:1 contrast or more (wcag AA). `qc.py` checks it ("text contrast"), `render.py` won't render below it, and `.venv/bin/python -m engine contrast --brand <brand> [--style <style>]` lists every pair in a style. Style keys: `badge_text_colour` / `badge_bg`, `takeover_text_colour` / `takeover_bg`, `hook_text_colour` / `hook_box_colour`. Pale accent colours only work with dark text (eg #1E1E1E on a pale pink = 14.4:1; white on it can be 1.2:1). Text straight on the video isn't checked.

## 2. cut preview (talking head / shop): check cuts BEFORE the full render

`.venv/bin/python -m engine render <clip> --cuts` renders just the cuts (half size), flash-scans each, and prints clean / FLASH per cut. `--only 3,7` re-checks specific cuts. Much faster than rendering the whole video to find one bad cut. Still run the full flash scan below on the final file.

## 2b. flash scan on a finished file (catches "glitchy" cuts) - every video type

A picture change less than 0.4s after another one is almost always a stray frame of the wrong scene. Real 4-frame teaser snaps in vlog edits are the only intended exception.

```
.venv/bin/python - <<'EOF'
import subprocess, re, sys
for out in sys.argv[1:] or ["<output folder>/<file>.mp4"]:
    r = subprocess.run(["ffmpeg","-hide_banner","-i",out,"-vf","scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time","-an","-f","null","-"],capture_output=True,text=True)
    det = [float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", r.stdout + r.stderr)]
    print(out, "flashes:", [(round(a,2), round(b-a,2)) for a,b in zip(det,det[1:]) if b-a < 0.4] or "none")
EOF
```

## 3. look at frames

Contact sheet of moments that matter (hook at ~0.5s, each b-roll window from `work/<clip>/edl.json` → `broll`, jump cuts, the ending):
```
ffmpeg -v error -y -ss <sec> -i <output folder>/<file>.mp4 -frames:v 1 -vf scale=240:-2 <scratch>/f1.png
ffmpeg -v error -y -i f1.png -i f2.png -i f3.png -filter_complex "[0:v][1:v][2:v]hstack=inputs=3[o]" -map "[o]" sheet.png
```
(hstack/vstack need `inputs=N` and an explicit `-map "[o]"`.) Then Read the image. Look for: text readable and placed right, captions not covering the product, b-roll shown the way the brand wants (full screen / pip), nothing covering their face, right clip at the right moment.

## 4. sound

```
ffmpeg -hide_banner -i <output folder>/<file>.mp4 -af ebur128 -f null - 2>&1 | grep "I:" | tail -1     # want about -14 (talking/music)
ffmpeg -hide_banner -i "<source clip>" -af volumedetect -vn -f null - 2>&1 | grep mean_volume  # -91 dB = silent track
ffmpeg -hide_banner -t 1 -i <output folder>/<file>.mp4 -af "silencedetect=noise=-35dB:d=0.05" -f null - 2>&1 | grep silence_   # no silence at the start = instant hook
```

## 5. freezes / length

```
ffmpeg -hide_banner -i <output folder>/<file>.mp4 -vf "freezedetect=n=0.002:d=0.6" -an -f null - 2>&1 | grep freeze_start
ffprobe -v error -show_entries format=duration -of csv=p=0 <output folder>/<file>.mp4
```

## 6. colour (when they say the grade looks off)

Sample the average colour of something that should be neutral, before vs after:
```
ffmpeg -v error -i <grade folder>/<clip>_grade_compare.jpg -vf "crop=120:80:<x>:<y>,scale=1:1:flags=area,format=rgb24" -f rawvideo - | xxd -p
```
Neutral black ≈ equal R, G, B. Blue higher than red = blue cast (that's what `neutral_blacks` fixes).

## 7. built-in cuts in source footage (compilations)

```
ffmpeg -hide_banner -i <source> -vf "scale=270:-2,scdet=threshold=8,metadata=mode=print:key=lavfi.scd.time" -an -f null - 2>&1 | grep -o "lavfi.scd.time=[0-9.]*"
```
render.py does this itself (cached in `work/_scenes/`) and keeps shots off these cuts, but use it when planning b-roll starts.

## known pitfalls

- `couldn't find 'ffmpeg'` → missing the `eval "$(/opt/homebrew/bin/brew shellenv zsh)"` prefix
- ffmpeg 8+/9 removed `-filter_complex_script`; the engine uses `-/filter_complex <file>`
- captions not burning in → ffmpeg without libass; needs `ffmpeg-full`
- the caption renderer ignores letter spacing set in a style line; spacing must go inline (`\fsp`). the engine does this
- iPhone HDR (HLG) clips look flat/grey without conversion; `sdr_filter` in common.py handles it everywhere (zscale primaries in float). don't tone-map HLG, it blows out skin
- clips exported from editing apps often have silent audio tracks
- Whisper's first-word start is often early and its last-word end often short; render.py snaps to the real audio
- `broll.py match` writes suggestions straight into plan.json; review and remove what doesn't fit
- `vlog.py analyse` overwrites clips.json descriptions
- zsh doesn't word-split `$var` in for loops; file names have spaces; use python or quoted explicit lists
- spreadsheets from some tools use namespaced xml (`<x:row>`); `textreel.py import` handles it
- big renders: run in background, don't block the chat
