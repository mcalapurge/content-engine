"""the shared library: brands and style lookup, contrast, grade settings, work folder naming,
plus the `inputs` command's rules for picking clips."""
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import engine.core.brand as brand_mod
import engine.core.common as common
from engine.core import contrast, grade
from tests.support import Sandbox


class Brands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("_template", "beth", "mia"):
            (self.tmp / name / "styles").mkdir(parents=True)
            (self.tmp / name / "style.json").write_text(json.dumps({"look": name}), encoding="utf-8")
        (self.tmp / "mia" / "styles" / "shop.json").write_text('{"look": "mia shop"}', encoding="utf-8")
        (self.tmp / ".hidden").mkdir()
        self.patch = mock.patch.object(brand_mod, "BRANDS_DIR", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_template_and_hidden_folders_are_not_brands(self):
        self.assertEqual(brand_mod.brand_names(), ["beth", "mia"])

    def test_which_brand(self):
        get = brand_mod.get_brand
        self.assertEqual(get("mia").name, "mia")
        self.assertEqual(get(None, {"brand": "beth"}).name, "beth")
        self.assertEqual(get(None, {"style": "mia"}).name, "mia")        # older plans
        self.assertEqual(get("beth", {"brand": "mia"}).name, "beth")      # --brand wins
        with self.assertRaises(SystemExit):
            get(None)                                                     # two brands: must ask
        with self.assertRaises(SystemExit):
            get("nope")
        shutil.rmtree(self.tmp / "mia")
        self.assertEqual(get(None).name, "beth")                          # only one: no need to say

    def test_style_lookup_order(self):
        mia = brand_mod.Brand("mia")
        self.assertEqual(brand_mod.load_style(None, mia), {"look": "mia"})
        self.assertEqual(brand_mod.load_style("mia", mia), {"look": "mia"})
        self.assertEqual(brand_mod.load_style("shop", mia), {"look": "mia shop"})
        self.assertIn("font", brand_mod.load_style("editorial", mia))    # generic template
        self.assertEqual(brand_mod.style_names(mia)[:2], ["mia", "shop"])
        with self.assertRaises(SystemExit):
            brand_mod.load_style("shop", brand_mod.Brand("beth"))         # another brand's variation


class Contrast(unittest.TestCase):
    def test_ratio(self):
        self.assertAlmostEqual(contrast.ratio("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(contrast.ratio("#777777", "#777777"), 1.0)
        self.assertAlmostEqual(contrast.ratio("#1E1E1E", "#FAEAF0"), 14.4, places=1)

    def test_only_boxed_text_the_plan_uses_is_checked(self):
        style = {"hook_text_colour": "#FFFFFF", "hook_box_colour": "#FFFFFF", "hook_box": True,
                 "takeover_bg": "#000000", "takeover_text_colour": "#FFFFFF"}
        plan = {"hook_text": "", "lines": [{"keep": True, "treatment": "takeover"}]}
        self.assertEqual([p[0] for p in contrast.boxed_pairs(style, plan)], ["takeover card"])
        self.assertEqual(contrast.problems(style, plan), [])
        plan["hook_text"] = "hook"
        self.assertEqual([p[0] for p in contrast.problems(style, plan)], ["hook box"])


class Grade(unittest.TestCase):
    def test_no_grade_is_no_filter(self):
        self.assertEqual(grade.grade_filter(None), "")
        self.assertEqual(grade.colour_chain({}), "")

    def test_neutral_blacks_keep_temperature_out_of_the_shadows(self):
        g = {"temp": -10, "tint": 5}
        self.assertIn("rs=-0.03", grade.colour_chain(g))
        self.assertRegex(grade.colour_chain({**g, "neutral_blacks": True}), r"rs=-?0\.0:")

    def test_strength_scales_and_unknown_hsl_colours_are_ignored(self):
        g = {"temp": 10, "strength": {"temp_tint": 0.5},
             "hsl": {"blue": {"saturation": -100}, "beige": {"hue": 50}}}
        chain = grade.colour_chain(g)
        self.assertIn("rh=0.015", chain)                       # 10 * 0.5 * 0.006 / 2
        self.assertIn("huesaturation=colors=b:hue=0.0:saturation=-1.000", chain)
        self.assertNotIn("beige", chain)
        self.assertNotIn("huesaturation", grade.colour_chain(g, hsl_supported=False))

    def test_disabled_or_missing_grade(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(brand_mod, "BRANDS_DIR", Path(tmp)):
            (Path(tmp) / "x").mkdir()
            b = brand_mod.Brand("x")
            self.assertIsNone(grade.load_grade(b))
            b.grade_file.write_text('{"enabled": false, "temp": 5}', encoding="utf-8")
            self.assertIsNone(grade.load_grade(b))
            b.grade_file.write_text('{"temp": 5}', encoding="utf-8")
            self.assertEqual(grade.load_grade(b)["temp"], 5)


class WorkFolders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(common, "WORK_DIR", self.tmp / "work"),
                        mock.patch.object(common, "INPUTS_DIR", self.tmp / "inputs")]
        for p in self.patches:
            p.start()
        for d in ("talking-head/mia", "talking-head/beth"):
            (self.tmp / "inputs" / d).mkdir(parents=True)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_subfolders_are_part_of_the_name(self):
        th = self.tmp / "inputs" / "talking-head"
        names = [common.work_dir_for(p).name for p in
                 (th / "intro.mov", th / "mia" / "intro.mov", th / "beth" / "intro.mov", self.tmp / "intro.mov",
                  th / "my clip (1).MOV")]
        self.assertEqual(names, ["intro", "mia-intro", "beth-intro", "intro", "my-clip-1"])

    def test_jobs_from_before_the_change_are_still_found(self):
        clip = self.tmp / "inputs" / "talking-head" / "mia" / "intro.mov"
        legacy = self.tmp / "work" / "intro"
        legacy.mkdir(parents=True)
        (legacy / "transcript.json").write_text(json.dumps({"source": str(clip.resolve())}), encoding="utf-8")
        self.assertEqual(common.work_dir_for(clip).name, "intro")
        other = self.tmp / "inputs" / "talking-head" / "beth" / "intro.mov"
        self.assertEqual(common.work_dir_for(other).name, "beth-intro")

    def test_norm_and_safe_name(self):
        self.assertEqual(common.norm("Hello,"), "hello")
        self.assertEqual(common.norm("£700!"), "£700")
        self.assertEqual(common.safe_name("a b/c"), "a-b-c")


class SetupCheck(unittest.TestCase):
    def test_ffmpeg_version_parsing(self):
        from engine.commands.check_setup import ffmpeg_major
        self.assertEqual(ffmpeg_major("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023"), 6)
        self.assertEqual(ffmpeg_major("ffmpeg version 7.0.2-static https://johnvansickle.com/ffmpeg/"), 7)
        self.assertEqual(ffmpeg_major("ffmpeg version n7.1-latest-linux64-gpl"), 7)
        self.assertEqual(ffmpeg_major("ffmpeg version 8.0 Copyright (c) 2000-2025"), 8)
        self.assertIsNone(ffmpeg_major("ffmpeg version N-127233-g452820cba6-20261007"))   # built from latest code


class InputsCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = Sandbox("inputs", copy_brands=False)

    @classmethod
    def tearDownClass(cls):
        cls.box.remove()

    def test_rules(self):
        vlog = self.box.inputs / "vlog"
        for name in ("a.mov", "b.mp4", "notes.txt"):
            (vlog / name).write_bytes(b"")
        out = self.box.engine("inputs", vlog).stdout.splitlines()
        self.assertTrue(out[0].startswith("FOLDER "))
        self.assertEqual(sorted(Path(x).name for x in out[1:]), ["a.mov", "b.mp4"])     # videos only
        (vlog / "trip").mkdir()
        (vlog / "_skip").mkdir()
        self.assertEqual(self.box.engine("inputs", vlog).stdout.splitlines(), ["ASK", "folders in vlog/: trip"])
        res = self.box.engine("inputs", vlog, "trip", check=False)
        self.assertNotEqual(res.returncode, 0)                                         # empty folder
        (vlog / "trip" / "c.mov").write_bytes(b"")
        self.assertEqual(Path(self.box.engine("inputs", vlog, "trip").stdout.splitlines()[-1]).name, "c.mov")
        self.assertNotEqual(self.box.engine("inputs", vlog, "nope", check=False).returncode, 0)

    def test_newest_and_sheets(self):
        trial = self.box.inputs / "trial"
        for name in ("old.mov", "new.mov"):
            (trial / name).write_bytes(b"")
            time.sleep(0.05)                             # different "date added"
        (trial / "set.xlsx").write_bytes(b"")
        out = self.box.engine("inputs", trial, "--newest", "--sheets").stdout.splitlines()
        self.assertTrue(out[1].startswith("SHEET") and out[1].endswith("set.xlsx"))
        self.assertEqual(len(out), 3)                    # folder, sheet, one clip
        if sys.platform != "darwin":                     # finder's "date added" is per second: ties on a mac
            self.assertEqual(Path(out[2]).name, "new.mov")


if __name__ == "__main__":
    unittest.main()
