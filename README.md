# reels engine

An agentic video editing tool. Clients film reels on their phone and talk to Claude Code in plain
words; Claude runs this engine to cut, caption, grade, add b-roll and sound, check the result and
hand back finished videos. It supports several brands (clients), each with its own brand guide,
look, colour grade and b-roll.

- **using it**: see [SETUP.md](SETUP.md)
- **how Claude works in here**: [CLAUDE.md](CLAUDE.md) and the skills in [.claude/skills/](.claude/skills/)
- **brands**: [brands/README.md](brands/README.md)

This is a tool folder rather than a code project that changes often: Claude is told not to commit,
push or open pull requests unless asked.

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
