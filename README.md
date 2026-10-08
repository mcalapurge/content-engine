# reels engine

An agentic video editing tool. Clients film reels on their phone and talk to Claude Code in plain
words; Claude runs this engine to cut, caption, grade, add b-roll and sound, check the result and
hand back finished videos. It supports several brands (clients), each with its own brand guide,
look, colour grade and b-roll.

- **using it**: see [SETUP.md](SETUP.md)
- **how Claude works in here**: [CLAUDE.md](CLAUDE.md) and the skills in [.claude/skills/](.claude/skills/)
- **brands**: [brands/README.md](brands/README.md)

This is a tool folder: it's used as is, locally, with the skills. Locally, Claude is told not to
commit, push or open pull requests unless asked. Changes to the tool's own code happen in cloud
sessions (Claude Code on the web), where Claude commits and pushes its work to the session's branch.
See "git rules" in [CLAUDE.md](CLAUDE.md).

## using the skills with brands

Every job is for one brand. Claude works out which one from what you say, the slash command's first
argument, or the brand saved with an earlier job. With only one brand set up you never need to name
it; with several, name it, or Claude will ask. Claude then reads that brand's guide
(`brands/<brand>/brand.md`), effects and look before it edits anything, and only uses that brand's
b-roll, style and colour grade.

### slash commands

The brand always comes first, then the optional bits.

| command | what it makes | example |
|---|---|---|
| `/content-talking-head <brand> [folder] [notes]` | a talking-to-camera reel from the newest clip in `inputs/talking-head/` (or that subfolder) | `/content-talking-head mia` <br> `/content-talking-head beth october punch in on the price` |
| `/content-tts <brand> [folder] [product] [how many]` | tiktok shop videos split from a batch take or compilation in `inputs/shop/` | `/content-tts beth halara-batch "Halara Wide Leg Trousers" 5` |
| `/content-vlog <brand> [folder] [track] [no grade]` | a short b-roll / vlog edit from a folder in `inputs/vlog/` | `/content-vlog mia lisbon-trip assets/music/sunny.mp3` |
| `/content-trial-reels <brand> [folder]` | instagram trial reels (text over b-roll) from a spreadsheet in `inputs/trial/` | `/content-trial-reels beth october` |

The `video-pipeline` skill is the shared core behind all four. It loads by itself for any editing
request, so you don't call it directly.

### or just ask in plain words

```
i have a new reel for mia
edit beth's shop batch, it's the halara trousers, 4 videos
edit mia's vlog lisbon-trip with the sunny track
make beth's trial reels from the october folder
index mia's b-roll
change beth's grade, it's looking too warm
add this to mia's effects library: (screenshot) call it "pink flash"
what's working in this reel: (link)   ← then: "what could mia borrow from it?"
```

### adding a brand

```
set up a new brand for mia
```

Claude runs `python -m engine brand new mia --style <editorial|playful|butter>`, which copies
`brands/_template/` to `brands/mia/`. Then it interviews you one question at a time and fills in
`brands/mia/brand.md`, sets her fonts and colours in `style.json`, takes her capcut grade numbers into
`grade.json`, and indexes her b-roll once you've copied it into `brands/mia/broll/`. Check what's
set up with `python -m engine brand list` (or ask "which brands do we have?").

### organising footage

Input folders are shared by every brand. To keep clients apart, give each brand (or each job) its
own subfolder and name it in the command, eg `inputs/talking-head/mia/` with
`/content-talking-head mia mia`. Claude never changes, moves or deletes anything in `inputs/`.

### brand-specific variations

A brand can have extra looks in `brands/<brand>/styles/`, eg `shop.json` with captions placed
higher for try-on videos. Ask for it by name ("use beth's shop style") or Claude picks it when the
brand guide says to. Changes you try on a single video stay on that video until you say "make that
the default", and then Claude updates that brand's files only.

## layout

```
.claude/skills/        workflows: video-pipeline (core) + /content-* slash commands. process only, no styling
engine/                the code, run as: python -m engine <command>
  __main__.py          command list
  core/                shared library: paths, brands, ffmpeg helpers, colour grade, contrast
  commands/            one module per command
brands/<brand>/        brand.md, effects.md, style.json, styles/, grade.json, broll/
brands/_template/      copied for a new brand
inputs/                raw footage, read only: talking-head/, shop/, vlog/, trial/
assets/                shared by every brand: styles/ (generic looks), fonts/, music/, sfx/
references/            other people's reels broken down
work/                  per-job working files (git-ignored)
output/                finished videos (git-ignored)
docs/                  engine notes (render audit)
scripts/               one-off maintenance (migrate_layout.py)
tests/                 smoke tests
```

## running

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m engine                    # list commands
.venv/bin/python -m engine check_setup        # python, ffmpeg, packages
.venv/bin/python -m engine brand list
.venv/bin/python -m unittest                  # smoke tests
```

Always run from the project root. Needs Python 3.9+ and a full ffmpeg build (7+, with libass).

## brands in the code

`engine/core/brand.py` resolves the brand for a job: `--brand <name>`, else the brand saved in the
job's `plan.json`, else the only brand there is; with several brands and nothing to go on it stops
and asks. `load_style(name, brand)` reads the brand's `style.json` (or a variation in
`brands/<brand>/styles/`, or a generic look in `assets/styles/`), `load_grade(brand)` its
`grade.json`. Paths saved in json files are relative to the project root.

## moving from the old flat layout

Older copies kept `input/`, `input_shop/`, `input_vlog/`, `input_trial/`, `brand/`, `broll/`,
`styles/`, `fonts/`, `music/` and `sfx/` at the top level. Footage and b-roll aren't tracked by git,
so after pulling, move them with:

```
python scripts/migrate_layout.py --brand beth            # shows what it will do
python scripts/migrate_layout.py --brand beth --apply    # moves files, updates paths in work/ plans
```
