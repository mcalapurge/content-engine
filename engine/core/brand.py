"""brands: one folder per client in brands/<name>/ holding everything that makes their videos theirs.

  brands/<name>/brand.md       the brand guide: who they are, tone, filming, take rules, captions, defaults
  brands/<name>/effects.md     their named effects library
  brands/<name>/grade.json     their colour grade (capcut-style numbers)
  brands/<name>/style.json     their caption / overlay look
  brands/<name>/styles/        optional variations of their look (eg shop.json with captions higher)
  brands/<name>/broll/         their b-roll library + library.json + _previews/

every command that reads brand settings takes --brand <name>. plan.py saves the brand into the job's
plan.json, so later steps (review, render, qc) pick it up without being told again.
"""
from engine.core.common import die, load_json
from engine.core.paths import BRANDS_DIR, STYLES_DIR


class Brand:
    def __init__(self, name):
        self.name = name
        self.dir = BRANDS_DIR / name
        self.guide = self.dir / "brand.md"
        self.effects = self.dir / "effects.md"
        self.grade_file = self.dir / "grade.json"
        self.style_file = self.dir / "style.json"
        self.styles_dir = self.dir / "styles"
        self.broll_dir = self.dir / "broll"
        self.library = self.broll_dir / "library.json"
        self.previews = self.broll_dir / "_previews"

    def __repr__(self):
        return f"Brand({self.name!r})"


def brand_names():
    """every brand folder (folders starting with _ or . are not brands, eg _template)."""
    if not BRANDS_DIR.is_dir():
        return []
    return sorted(d.name for d in BRANDS_DIR.iterdir() if d.is_dir() and not d.name.startswith(("_", ".")))


def get_brand(name=None, plan=None):
    """the brand for this job: --brand if given, else the one saved in the job's plan, else the only
    brand there is. with several brands and nothing to go on, stops and asks which one."""
    names = brand_names()
    if not name and plan:
        # older plans only saved a style named after the brand
        name = plan.get("brand") or (plan.get("style") if plan.get("style") in names else None)
    if not name:
        if len(names) == 1:
            name = names[0]
        else:
            die("which brand is this for? add --brand <name>. brands: "
                + (", ".join(names) or "none yet (python -m engine brand new <name>)"))
    if name not in names:
        die(f"no brand called '{name}' in brands/. brands: {', '.join(names) or 'none yet'}")
    return Brand(name)


def add_brand_arg(ap):
    ap.add_argument("--brand", default=None,
                    help="which brand in brands/ (default: the job's brand, or the only brand)")


def style_names(brand):
    """styles this brand can use: its own look, its variations, then the generic templates."""
    own = sorted(p.stem for p in brand.styles_dir.glob("*.json")) if brand.styles_dir.is_dir() else []
    generic = sorted(p.stem for p in STYLES_DIR.glob("*.json"))
    return [brand.name] + [s for s in own if s != brand.name] + [s for s in generic if s not in own]


def style_path(name, brand):
    if not name or name == brand.name:
        return brand.style_file
    for p in (brand.styles_dir / f"{name}.json", STYLES_DIR / f"{name}.json"):
        if p.exists():
            return p
    return None


def load_style(name, brand):
    """a style pack. no name (or the brand's name) = the brand's own style.json. otherwise one of the
    brand's variations in brands/<name>/styles/, or a generic template from assets/styles/."""
    p = style_path(name, brand)
    if p is None or not p.exists():
        die(f"no style called '{name or brand.name}' for brand '{brand.name}'. "
            f"options: {', '.join(style_names(brand))}")
    return load_json(p)
