"""quick checks that the engine is wired up: every command loads, brands resolve, paths saved in
json point at real folders. no video work, runs in a second or two.

run from the project root:  python -m unittest
"""
import json
import subprocess
import sys
import unittest

from engine.__main__ import COMMANDS
from engine.core import brand as brands
from engine.core.paths import BRAND_TEMPLATE_DIR, BRANDS_DIR, INPUTS_DIR, ROOT, STYLES_DIR


def engine(*args):
    return subprocess.run([sys.executable, "-m", "engine", *args], cwd=ROOT, capture_output=True, text=True)


class Commands(unittest.TestCase):
    def test_command_list(self):
        res = engine()
        self.assertEqual(res.returncode, 0)
        for name in COMMANDS:
            self.assertIn(name, res.stdout)

    def test_every_command_has_help(self):
        # imports each command module and runs its argument parser
        for name in COMMANDS:
            if name in ("check_setup",):      # no options, runs the check straight away
                continue
            with self.subTest(command=name):
                res = engine(name, "--help")
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn("usage:", res.stdout)

    def test_unknown_command(self):
        self.assertEqual(engine("nope").returncode, 2)


class Brands(unittest.TestCase):
    def test_brand_folders_are_complete(self):
        names = brands.brand_names()
        self.assertTrue(names, "no brands in brands/")
        for name in names:
            b = brands.Brand(name)
            for f in (b.guide, b.effects, b.grade_file, b.style_file):
                with self.subTest(brand=name, file=f.name):
                    self.assertTrue(f.exists())
            json.loads(b.grade_file.read_text(encoding="utf-8"))
            brands.load_style(None, b)

    def test_template_is_complete(self):
        for f in ("brand.md", "effects.md", "grade.json", "broll/library.json"):
            self.assertTrue((BRAND_TEMPLATE_DIR / f).exists(), f)
        self.assertNotIn("_template", brands.brand_names())

    def test_plan_brand_wins_over_guessing(self):
        name = brands.brand_names()[0]
        self.assertEqual(brands.get_brand(None, {"brand": name}).name, name)
        # older plans only saved a style named after the brand
        self.assertEqual(brands.get_brand(None, {"style": name}).name, name)

    def test_generic_styles_load(self):
        b = brands.Brand(brands.brand_names()[0])
        for p in STYLES_DIR.glob("*.json"):
            with self.subTest(style=p.stem):
                brands.load_style(p.stem, b)

    def test_broll_library_paths_belong_to_the_brand(self):
        for name in brands.brand_names():
            b = brands.Brand(name)
            if not b.library.exists():
                continue
            for c in json.loads(b.library.read_text(encoding="utf-8"))["clips"]:
                with self.subTest(brand=name, clip=c["file"]):
                    self.assertTrue(c["file"].startswith(f"brands/{name}/broll/"))


class Layout(unittest.TestCase):
    def test_folders_exist(self):
        for d in ("talking-head", "shop", "vlog", "trial", "brand-guides"):
            self.assertTrue((INPUTS_DIR / d).is_dir(), d)
        for d in ("assets/fonts", "assets/music", "assets/sfx", "assets/styles", "work", "output", "references"):
            self.assertTrue((ROOT / d).is_dir(), d)
        self.assertTrue(BRANDS_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
