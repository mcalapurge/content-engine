"""the files people and claude edit by hand: brand folders, style packs, the b-roll library, and
the docs / skills (every command and flag they mention must exist)."""
import functools
import json
import re
import subprocess
import sys
import unittest

from engine.__main__ import COMMANDS
from engine.core import contrast, grade
from engine.core.brand import Brand, brand_names
from tests.support import ROOT

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# what the renderer reads from every style without a default
STYLE_KEYS = ("font", "font_size", "text_colour", "highlight_colour", "outline_colour", "outline", "shadow",
              "caption_position", "caption_mode", "hook_font", "hook_size", "hook_text_colour", "hook_box_colour",
              "stat_colour")
CAPTION_MODES = ("word", "line", "karaoke", "build")
# a brand guide must cover these (matched against its "## " headings)
GUIDE_TOPICS = ("tone", "film", "take", "caption", "pacing", "font", "grade")

USER_DOCS = ([ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / "SETUP.md", ROOT / "brands" / "README.md",
              ROOT / "assets" / "styles" / "README.md"]
             + sorted((ROOT / ".claude" / "skills").rglob("*.md"))
             + sorted((ROOT / "brands").glob("*/*.md"))
             + sorted((ROOT / "inputs").glob("*/README.txt")))


def style_files():
    files = sorted((ROOT / "assets" / "styles").glob("*.json"))
    files += sorted((ROOT / "brands").glob("*/style.json")) + sorted((ROOT / "brands").glob("*/styles/*.json"))
    return files


class Styles(unittest.TestCase):
    def test_every_style_has_what_the_renderer_needs(self):
        for path in style_files():
            with self.subTest(style=str(path.relative_to(ROOT))):
                style = json.loads(path.read_text(encoding="utf-8"))
                missing = [k for k in STYLE_KEYS if k not in style]
                self.assertEqual(missing, [])
                self.assertIn(style["caption_mode"], CAPTION_MODES)
                if style["caption_mode"] != "word":
                    self.assertIn("words_per_caption", style)
                self.assertTrue(0 <= style["caption_position"] <= 1)
                for key, value in style.items():
                    if key.endswith(("_colour", "_bg")) and isinstance(value, str):
                        self.assertRegex(value, HEX, key)

    def test_every_style_is_readable(self):
        for path in style_files():
            with self.subTest(style=str(path.relative_to(ROOT))):
                style = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(contrast.problems(style), [])


class BrandFolders(unittest.TestCase):
    def test_brands_are_complete(self):
        for name in brand_names():
            brand = Brand(name)
            with self.subTest(brand=name):
                for path in (brand.guide, brand.effects, brand.grade_file, brand.style_file):
                    self.assertTrue(path.exists(), path.name)
                headings = " ".join(re.findall(r"^## (.+)$", brand.guide.read_text(encoding="utf-8"), re.M)).lower()
                self.assertEqual([t for t in GUIDE_TOPICS if t not in headings], [], "brand.md is missing topics")

    def test_grades_are_well_formed(self):
        for path in sorted((ROOT / "brands").glob("*/grade.json")):
            with self.subTest(grade=str(path.relative_to(ROOT))):
                g = json.loads(path.read_text(encoding="utf-8"))
                for key in ("temp", "tint", "saturation", "whites", "blacks", "clarity"):
                    self.assertIsInstance(g.get(key, 0), (int, float), key)
                self.assertIsInstance(g.get("enabled", True), bool)
                for colour, adj in (g.get("hsl") or {}).items():
                    self.assertIn(colour, grade.HSL_NAMES)
                    self.assertTrue(set(adj) <= {"hue", "saturation", "brightness"}, adj)

    def test_broll_libraries(self):
        for name in brand_names():
            brand = Brand(name)
            if not brand.library.exists():
                continue
            clips = json.loads(brand.library.read_text(encoding="utf-8"))["clips"]
            files = [c["file"] for c in clips]
            with self.subTest(brand=name):
                self.assertEqual(len(files), len(set(files)), "a clip is listed twice")
            for clip in clips:
                with self.subTest(brand=name, clip=clip["file"]):
                    self.assertTrue(clip["file"].startswith(f"brands/{name}/broll/"))
                    self.assertTrue(clip.get("description"), "needs a description (claude fills these in)")
                    self.assertIsInstance(clip.get("tags", []), list)
                    if clip.get("preview"):
                        self.assertTrue(clip["preview"].startswith(f"brands/{name}/broll/_previews/"))

    def test_template_matches_a_real_brand(self):
        template = ROOT / "brands" / "_template"
        for path in ("brand.md", "effects.md", "grade.json", "broll/library.json", "broll/_previews/.gitkeep"):
            self.assertTrue((template / path).exists(), path)
        self.assertFalse(json.loads((template / "grade.json").read_text(encoding="utf-8"))["enabled"])


@functools.lru_cache(maxsize=None)
def help_text(*command):
    res = subprocess.run([sys.executable, "-m", "engine", *command, "--help"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8")
    return res.stdout if res.returncode == 0 else ""


def mentions():
    """(doc, command words, flags) for every `python -m engine ...` in the docs."""
    for doc in USER_DOCS:
        for match in re.finditer(r"python -m engine ([^`\n#|;&]*)", doc.read_text(encoding="utf-8")):
            parts = match.group(1).split()
            if not parts or parts[0].startswith("<"):
                continue
            flags = sorted({p.split("=")[0] for p in parts if p.startswith("--")})
            yield doc, parts, flags


class Docs(unittest.TestCase):
    def test_every_engine_command_in_the_docs_exists_with_its_flags(self):
        for doc, parts, flags in mentions():
            name = parts[0]
            with self.subTest(doc=str(doc.relative_to(ROOT)), command=" ".join(parts)):
                self.assertIn(name, COMMANDS)
                text = help_text(name)
                sub = parts[1] if len(parts) > 1 and re.search(rf"\{{[^}}]*\b{re.escape(parts[1])}\b[^}}]*\}}", text) else None
                if sub and name not in ("vlog", "textreel"):          # these take the action as a plain argument
                    text = help_text(name, sub)
                for flag in flags:
                    self.assertIn(flag, text, f"{flag} isn't an option of `{name}{' ' + sub if sub else ''}`")

    def test_every_command_is_documented_somewhere(self):
        documented = {parts[0] for _, parts, _ in mentions()}
        self.assertEqual(sorted(set(COMMANDS) - documented), [])

    def test_skills_have_valid_headers(self):
        for skill in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=skill.parent.name):
                text = skill.read_text(encoding="utf-8")
                header = re.match(r"^---\n(.*?)\n---\n", text, re.S)
                self.assertIsNotNone(header, "no front matter")
                fields = dict(re.findall(r"^([\w-]+): (.*)$", header.group(1), re.M))
                self.assertEqual(fields.get("name"), skill.parent.name)
                self.assertGreater(len(fields.get("description", "")), 40)

    def test_skills_carry_no_brand_styling(self):
        """styling belongs in brands/<brand>/, skills only say how to work."""
        for skill in sorted((ROOT / ".claude" / "skills").rglob("*.md")):
            text = skill.read_text(encoding="utf-8")
            with self.subTest(skill=str(skill.relative_to(ROOT))):
                if skill.name != "checks.md":        # checks.md uses a colour pair to explain contrast
                    self.assertNotRegex(text, r"#[0-9A-Fa-f]{6}\b")
                self.assertNotIn("beth.json", text)
                self.assertNotIn("Helvetica", text)

    def test_no_em_dashes_in_user_facing_text(self):
        for doc in USER_DOCS:
            with self.subTest(doc=str(doc.relative_to(ROOT))):
                self.assertNotIn("—", doc.read_text(encoding="utf-8"))

    def test_relative_links_in_readmes_point_at_real_files(self):
        for doc in (ROOT / "README.md", ROOT / "brands" / "README.md"):
            for target in re.findall(r"\]\(([^)#:]+)\)", doc.read_text(encoding="utf-8")):
                with self.subTest(doc=doc.name, link=target):
                    self.assertTrue((doc.parent / target).exists())

    def test_folders_in_the_claude_md_tree_exist(self):
        tree = re.search(r"```\ncontent-engine/\n(.*?)```", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(tree)
        stack = []
        for row in tree.group(1).splitlines():
            m = re.match(r"^([│ ]*)[├└]── ([\w.\-]+)/", row)
            if not m or "<" in row.split("──")[1].split()[0]:
                continue
            depth = len(m.group(1)) // 4
            stack = stack[:depth] + [m.group(2)]
            with self.subTest(folder="/".join(stack)):
                self.assertTrue((ROOT.joinpath(*stack)).is_dir())


if __name__ == "__main__":
    unittest.main()
