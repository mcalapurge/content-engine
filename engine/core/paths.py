"""every folder the engine reads or writes, in one place. paths in json files (plan.json,
library.json) are stored relative to ROOT, eg "brands/beth/broll/x.mp4".

the tests point inputs/, brands/, work/ and output/ somewhere else (inside the project, so saved
paths still work) with REELS_INPUTS_DIR, REELS_BRANDS_DIR, REELS_WORK_DIR and REELS_OUTPUT_DIR."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _dir(env_name, default):
    value = os.environ.get(env_name)
    return Path(value).resolve() if value else default


# raw footage. never modified, moved or deleted by the engine
INPUTS_DIR = _dir("REELS_INPUTS_DIR", ROOT / "inputs")
INPUT_DIR = INPUTS_DIR / "talking-head"     # talking head reels
SHOP_DIR = INPUTS_DIR / "shop"              # batch-filmed tiktok shop takes
VLOG_DIR = INPUTS_DIR / "vlog"              # b-roll / vlog clips, one folder per video
TRIAL_DIR = INPUTS_DIR / "trial"            # trial reel sets (spreadsheet + clips)

# one folder per client brand: guide, effects, grade, style, b-roll (see engine/core/brand.py)
BRANDS_DIR = _dir("REELS_BRANDS_DIR", ROOT / "brands")
BRAND_TEMPLATE_DIR = BRANDS_DIR / "_template"

# assets shared by every brand
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"
SFX_DIR = ASSETS_DIR / "sfx"
STYLES_DIR = ASSETS_DIR / "styles"          # generic style templates to start a brand's look from

# generated
WORK_DIR = _dir("REELS_WORK_DIR", ROOT / "work")
OUTPUT_DIR = _dir("REELS_OUTPUT_DIR", ROOT / "output")
REF_DIR = ROOT / "references"

ENV_FILE = ROOT / ".env"
