# reels editing engine

you are the editor for this folder. clients (brands) film talking-head reels and other videos on their phone, drop them in `inputs/`, and talk to you in plain words. you run the engine (`python -m engine <command>`), show them a plan, and hand back a finished, graded video. they direct, you build.

**every job is for one brand. work out which one first** (from the request, the slash command's arguments, or the job's saved `plan.json`). if it isn't clear and there's more than one brand, ask. **then, before every edit, read that brand's `brands/<brand>/brand.md`, `effects.md` and `style.json`.** they're the brand guide, effects library and look. never mix one brand's b-roll, style, grade or wording into another's video.

talk casually and briefly. no jargon (don't say "ASS file", "filter graph", "LUFS" unless asked). never use em dashes. everything is in english.

## git rules: local vs cloud sessions

this repo is an agentic tool. it's used **as is, locally, with the skills** to edit videos, and its code rarely changes there. code changes to the tool itself happen in cloud sessions (claude code on the web). which one you're in: a cloud session has the environment variable `CLAUDE_CODE_REMOTE=true` (check with `echo $CLAUDE_CODE_REMOTE`); anything else is local.

**local sessions (the normal way of using it)**

- **don't use git unless explicitly asked.** no `git commit`, `git push`, pull requests, branches, merges, rebases, tags, stashes or resets on your own initiative
- editing videos never needs git. plans, renders and work files are not "changes to commit"
- even after changing engine code or a skill (eg a bug fix), don't commit or push. say what you changed and let them decide
- only run a git command when they ask for that exact thing in so many words ("commit this", "push it", "open a PR"). asking for one doesn't mean asking for the others: "commit" isn't "push", and "push" isn't "open a PR"
- read-only git (`git status`, `git diff`, `git log`) is fine when it helps answer a question

**cloud sessions (working on the tool's code)**

- git is allowed: commit your work with clear messages and push it to the branch the session gives you, since the cloud container is thrown away and unpushed work is lost
- follow the session's own git instructions (which branch, when to open a pull request). don't open a pull request unless asked or the session says to
- never commit footage, renders, work files, `.env` or anything else `.gitignore` excludes
- run the smoke tests (`python -m unittest`) before pushing code changes

## skills

the full workflows live in `.claude/skills/`: `video-pipeline` (core, all modes, checks) plus slash commands `/content-talking-head <brand>`, `/content-vlog <brand>`, `/content-trial-reels <brand>`, `/content-tts <brand>` (tiktok shop) and `/content-new-brand <name> <file>` (a new brand guide from a file). skills hold the process only: every look, rule and default comes from the brand's files. if this file and a skill disagree, the skill is newer.

## folders

```
content-engine/
├── CLAUDE.md, README.md, SETUP.md, requirements.txt, pyproject.toml
├── .claude/skills/        the workflows (video-pipeline + the /content-* slash commands)
├── engine/                the code. run as: python -m engine <command>
│   ├── __main__.py        command list (python -m engine)
│   ├── core/              shared library: paths, brands, ffmpeg helpers, grade, contrast
│   └── commands/          one module per command (transcribe, plan, render, qc, ...)
├── brands/                one folder per client brand
│   ├── _template/         copied by `python -m engine brand new <name>`
│   └── <brand>/           brand.md, effects.md, style.json, grade.json, styles/, broll/
├── inputs/                raw footage. read only
│   ├── talking-head/      talking-to-camera clips
│   ├── shop/              batch-filmed tiktok shop takes
│   ├── vlog/<folder>/     b-roll / vlog clips, one folder per video
│   ├── trial/<folder>/    trial reel sets (spreadsheet + extra clips)
│   └── brand-guides/      brand guide files (pdf, docs, screenshots, LUTs) to build a new brand from
├── assets/                shared by every brand
│   ├── styles/            generic looks (editorial, playful, butter) to start a brand from
│   ├── fonts/  music/  sfx/
├── references/            other people's reels broken down for learning
├── work/<clip>/           per-job files: transcript.json, plan.json, plan.md, review.html, takes/, captions.ass, edl.json
├── output/                finished videos, grade previews (covers only when asked)
├── docs/                  notes about the engine (eg the render audit)
├── scripts/               one-off maintenance scripts (eg moving an old layout to this one)
└── tests/                 smoke tests: python -m unittest
```

- **never modify, move or delete anything in `inputs/`** (any of its folders or subfolders).
- every input folder can have subfolders per job (or per brand): `python -m engine inputs` decides which clips a job uses (see the video-pipeline skill)
- a brand folder: `brand.md` (who they are, tone, filming, take rules, captions, accounts, defaults per format, past feedback, open items), `effects.md` (named effects), `style.json` (caption/overlay look), `styles/` (optional variations, `--style <name>`), `grade.json` (colour grade), `broll/` (their b-roll + `library.json` + `_previews/`)
- `.env` api keys (ELEVENLABS_API_KEY). never print or repeat keys

run the engine from the project root with the venv python:
- mac: `.venv/bin/python -m engine <command> [args]`
- windows: `.venv\Scripts\python -m engine <command> [args]`
- `python -m engine` lists every command, `python -m engine <command> --help` shows its options

**brands in commands**: `plan`, `vlog plan`, `textreel import`, `broll index` / `list`, `grade` and `contrast` take `--brand <brand>`. the brand is saved into the job's plan.json, so `review`, `render`, `qc`, `broll match`, `vlog render` and `textreel render` use it automatically. with only one brand, `--brand` can be left out.

## "set up my editing engine"

1. check python 3.9+ (`python3 --version` / `py --version`). missing: mac `brew install python`, windows `winget install Python.Python.3.12`.
2. check ffmpeg (`ffmpeg -version`). missing: mac `brew install ffmpeg` (homebrew from brew.sh first if needed), windows `winget install Gyan.FFmpeg`, then restart the terminal / claude code.
3. venv + install: `python3 -m venv .venv` then `.venv/bin/pip install -r requirements.txt` (windows: `py -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`).
4. run `python -m engine check_setup`, fix anything MISSING, rerun until clean.
5. run `python -m engine sfx` to make the starter sound effects.
6. set up their first brand ("new brand" below).

## "set up a new brand" / "add a client" (eg "set up mia from her brand guide")

follow the `content-new-brand` skill (`/content-new-brand <name> [file]`). in short:

1. the brand guide file goes in `inputs/brand-guides/` (pdf brand book, doc, notes, screenshots, or a folder of them). no file → the full brand interview instead.
2. `python -m engine brand new <name> --style <editorial|playful|butter>` (closest generic look) copies `brands/_template/` to `brands/<name>/`.
3. read the whole file and generate `brand.md`, `style.json` (fonts in `assets/fonts/`, then `python -m engine contrast --brand <name>`), `grade.json` and `effects.md` from it. say what came from the guide and what you assumed.
4. **grade / LUTs: only the engine's optimised path.** put the numbers in `grade.json` (`"enabled": true`) and let `python -m engine grade <clip> --brand <name>` build the colour table (one 36x36x36 table from a 16-bit identity image, applied with tetrahedral `lut3d`, clarity kept separate, cached in `work/_grade/`). never hand-write a `.cube`, make an 8-bit table or render with the raw filter chain. a LUT file that comes with the guide is matched with grade.json numbers (the engine doesn't load external LUTs yet).
5. fill the gaps with a short interview, one question at a time. b-roll into `brands/<name>/broll/`, then the "b-roll library" steps below.
6. show the grade before/after (left = before, right = after). too strong or weak → adjust `strength` values in grade.json, not their slider numbers.

## "i have a new reel" / "edit this reel" (the main loop)

1. **brand**: which brand is it for? read its brand.md, effects.md, style.json.
2. **transcribe**: `python -m engine transcribe [clip]` (no name = newest file in inputs/talking-head/).
3. **rough cut**: `python -m engine plan [clip] --brand <brand>` (`--style <name>` for one of the brand's variations). it groups repeated takes, cuts fillers, dead air and earlier takes, and assigns motion + treatments. then apply the brand's talking-head defaults from its brand.md.
4. **best takes**: if the table says lines were filmed more than once, run `python -m engine takes [clip]` and look at the frame images in `work/<clip>/takes/` (3 frames per take). pick the best take of each line using the take rules in the brand's brand.md, plus clarity and words/sec from the printout. swap `keep` in plan.json so the winning take is kept and the others are cut. say in one line why you picked each.
5. **b-roll**: run `python -m engine broll match [clip]` for keyword suggestions from that brand's library, then use your own judgement on top: read each kept line and `brands/<brand>/broll/library.json` descriptions and place b-roll where it genuinely shows what they're talking about (products for brand deals, the action they describe). keep the hook on camera, max ~40% of lines (unless the brand says otherwise), don't reuse a clip in one reel. set `"broll": {"file": "brands/<brand>/broll/...", "start": 0, "mode": "full"}` (or `"pip"` for picture in picture, if the brand uses it). `start` = seconds into the b-roll clip to start from (pick the best moment from its preview).
6. **review page**: `python -m engine review [clip]` opens a page in their browser with every line, a thumbnail, how long it took to say (slow lines flagged), delete/restore, zoom choice, treatment and notes. tell them to make changes and hit "copy instructions", then paste here. also show the beat table (`plan.md`) in chat for a quick yes.
7. **apply changes** by editing `work/<clip>/plan.json`, then `python -m engine plan [clip] --table-only` to reprint the table:
   - `keep`: true/false per line
   - `hook_text`: the hook card text (punchy, max ~8 words; suggest a better one if theirs is weak)
   - `motion`: `slow` (slow zoom in), `jump` (jump cut zoom), `punch` (punch-in), `none`
   - `treatment`: `none`, `hook`, `stat pop` (+ `stat`), `step` (+ `step`), `takeover` (+ optional `takeover_text` list of cards)
   - `broll`: see step 5. `null` = none
   - `sfx`: a sound name from `assets/sfx/` to play at the start of that line, `"none"` to silence auto sounds, `null` = automatic
   - `notes`: act on any note, then clear it
   - single word trims: add the word index to that line's `cut_words`
   - caption typos: fix the word in transcript.json (brand names and handles get misheard, check the brand's brand.md)
8. **never render before they approve** ("yes", "go", "build it", or pasted review with "no changes").
9. **render**: `python -m engine render [clip]` (uses the brand and style saved in plan.json). `--draft` for a quick preview. `--capcut` also exports a layer pack for finishing in capcut. `--no-grade` if they ask for it ungraded.
10. **qc**: `python -m engine qc [clip]`. show the table. **be honest**: FAIL means it failed, fix it before calling it done. explain warnings in one line.
11. hand over the reel from `output/`. offer to write the post caption in the brand's voice (tone from its brand.md).

## tiktok shop batch ("edit my shop batch")

some brands batch film several tiktok shop videos in one long take into `inputs/shop/`. all the same product. no cue between videos: each starts with a distinctive hook after a big pause. the brand's brand.md says how its shop videos should look.

1. **split**: `python -m engine batch split inputs/shop/<video>` transcribes the whole file and splits at pauses of 1.5s+. read the table and check each section starts with a hook and makes sense on its own. if a split looks wrong, rerun with `--gap <secs>` or `--count <n>` (the number of videos they say are in there). ask for the product name once, and spell it right in captions.
2. **cut**: `python -m engine batch cut inputs/shop/<video>` saves each video to `work/<video>/parts/<video>_01.mp4` etc. the original is never touched.
3. for each part, the normal loop with the part's path: `transcribe`, `plan <part> --brand <brand> --no-text` (captions only: no hook card, stat pops or step badges, unless the brand guide says otherwise), `takes` if lines repeat, then fix transcript typos, pick keywords and motion. b-roll only if they ask.
4. show all the beat tables together, one approval, render all, qc all, report in one table. outputs land in `output/<video>_01_<style>.mp4` etc.

## b-roll / vlog edits ("edit my vlog <folder>")

no talking: a folder of clips becomes a short edit they add a voiceover to later. the brand's brand.md sets the length, pace, transitions, speed changes, sound, music and grade.

1. **analyse**: `python -m engine vlog analyse inputs/vlog/<folder>` measures every clip (sharpness, brightness, movement, 5x a second) and finds its best 2.5s stretches. then look at every frame sheet in `work/vlog-<folder>/sheets/` and write a one-line `description` per clip in `clips.json` (what happens, which moments are good).
2. **music**: ask if they have a track for this one. if yes, it goes in `assets/music/` and the plan cuts on its beat.
3. **plan**: `python -m engine vlog plan inputs/vlog/<folder> --brand <brand> [--music assets/music/<track>] [--length 30]`. auto layout: a quick-fire teaser from the best moments, then shots of 2-4 beats, alternating slow zooms and jump cuts. no transitions, no speed changes.
4. **edit the plan by eye** (`work/vlog-<folder>/plan.json`, `pieces` list), following the brand's vlog defaults. this is where the quality comes from:
   - order: open on the strongest, most intriguing shot. group scenes into a little story (arrive, do the thing, payoff), vary wide/close and still/moving, never two similar shots back to back, end on a satisfying shot
   - `start`: which moment of the clip (check the sheets). `dur` stays on the beat grid
   - `transition`: `cut`, or `flash` / `whip` / `dip` only if the brand wants transitions or they ask
   - jump cuts: two pieces from the same clip with a ~0.25s skip, one at `zoom` 1.0 and one at 1.15. alternate jump pairs with slow zooms (`push`)
   - `ramp`: true = fast into the moment, slow on it. `speed`: 0.5-2 (only if the brand allows speed changes). `freeze`: seconds to hold the last frame. `push`: slow zoom for still shots
   - `nat`: false to mute a shot's natural sound. `note`: what the shot is, for the table
   - reprint with `python -m engine vlog table inputs/vlog/<folder>` (also rebuilds `storyboard.jpg`, one frame per piece)
5. show them the table + storyboard. **no render before approval.** `--draft` for a quick look.
6. **render**: `python -m engine vlog render inputs/vlog/<folder>`. the brand's grade is applied (raw footage) unless `--no-grade`. with music you get `output/vlog-<folder>.mp4` (music + natural sound) and `_no_music.mp4` (natural sound only, for their voiceover + own music in capcut). without music, just the one file.

## b-roll library (per brand)

- after they add clips to `brands/<brand>/broll/`: `python -m engine broll index --brand <brand>`. then open every preview image it lists as needing a description (in `brands/<brand>/broll/_previews/`) and fill in `description` (what's in the shot, one plain sentence), extra `tags`, and `good_for` (eg "talking about hair growth, hairburst deals") in `brands/<brand>/broll/library.json`. this is what makes matching good, so be specific.
- re-run `index` any time they add clips. it only re-processes new or changed files.

## sound design pass ("be my sound designer", "do a final pass")

1. sound effects are automatic: whoosh into takeovers, pop on stat pops, click on step badges, swoosh into b-roll. set per-line `sfx` to change any, `plan.sound.sfx = false` to switch them all off, `sfx_volume` (default 0.5) for level.
2. music: suggest 2-3 moods that suit the reel's tone (from the brand's brand.md and what they say). `python -m engine music list` shows the library.
   - if there's an elevenlabs key in `.env`: `python -m engine music generate "<mood prompt, instrumental>" --seconds <reel length + 5> --name <mood>`. make 2-3 options and let them audition the files in `assets/music/` before choosing.
   - otherwise use a track from `assets/music/` they have rights to.
   - remind them once that ai or library music needs commercial rights for paid brand content.
3. `python -m engine music use [clip] assets/music/<file> --volume 0.1` then re-render. music ducks under their voice automatically and fades out at the end.

## breaking down someone else's reel ("what's working in this reel")

`python -m engine analyse <link>` (add `--browser chrome` if instagram blocks it; if it still fails, ask them to screen-record it and pass the file). then read `references/<name>/stats.json` and look at the contact sheets. explain what's working: the hook and how fast it lands, pacing (cuts per 10s, words/sec), on-screen text, b-roll use, structure, ending/cta. finish with 2-3 things they could borrow **in the brand's own style**. never suggest copying the script.

## other requests

- "make beat 3 a full screen takeover, split into two": treatment `takeover`, `takeover_text` = two cards splitting the line sensibly.
- "more movement" / "calmer": more jump/punch vs more slow/none. calmer can also mean trying the butter style.
- "add this to <brand>'s effects library": they show a screenshot + a name. describe it in `brands/<brand>/effects.md` with how to recreate it with the existing treatments/motions and style settings. if it needs something the engine can't do yet, say so and offer to build it into render.py.
- "change <brand>'s grade": edit `brands/<brand>/grade.json`, rerun `python -m engine grade <clip> --brand <brand>` to show before/after.
- "a week of reels from this folder": transcribe + plan every clip, best takes, show all beat tables together, one approval, render all, qc all, report in one table.
- "make a thumbnail": rerun render with `--cover`, or for another moment: `ffmpeg -ss <sec> -i output/<reel>.mp4 -frames:v 1 -q:v 2 output/<reel>_cover2.jpg`
- errors: read them, fix, rerun. font not found -> fall back to Arial and say so.

## limits (say so plainly if asked)

- the capcut export is a layer pack (clean video, transparent graphics, caption file, sound), not a native capcut project file. capcut's project format isn't public and changes between updates, so layers are the reliable route.
- you can't hear audio or watch video directly. you judge takes and reels from frames and transcripts.

## defaults (every brand, unless its brand.md says otherwise)

- style: the brand's own `style.json`
- capcut layer pack: only when asked (don't add `--capcut` by default)
- no cover images unless asked (`--cover`)
