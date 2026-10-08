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

    def test_content_type_from_where_the_source_sits(self):
        inputs, work = self.tmp / "inputs", self.tmp / "work"
        cases = {inputs / "talking-head" / "mia" / "a.mov": "talking-head", inputs / "shop" / "b.mp4": "shop",
                 inputs / "vlog" / "trip": "vlog", inputs / "trial" / "october": "trial",
                 work / "batch" / "parts" / "batch_01.mp4": "shop", self.tmp / "elsewhere.mov": "talking-head"}
        for source, kind in cases.items():
            with self.subTest(source=str(source)):
                self.assertEqual(common.content_type(source), kind)

    def test_every_render_gets_its_own_folder(self):
        with mock.patch.object(common, "OUTPUT_DIR", self.tmp / "output"):
            first = common.output_folder("mia", "vlog", "lisbon trip")
            second = common.output_folder("mia", "vlog", "lisbon trip")
        self.assertEqual(first.parent, self.tmp / "output" / "mia" / "vlog")
        self.assertRegex(first.name, r"^\d{4}-\d\d-\d\d_\d{4}_lisbon-trip$")
        self.assertTrue(first.is_dir() and second.is_dir())
        self.assertNotEqual(first, second)                  # same minute: -2, never the same folder

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


class SizeCap(unittest.TestCase):
    """the tiktok shop upload (--max-mb): h.265, never over the cap. the encoder is faked here: each try
    writes a file of the size the test says it came out at."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.master, self.out = self.tmp / "master.mp4", self.tmp / "reel_10mb.mp4"
        self.master.write_bytes(b"")
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def encode(self, sizes, hardware):
        sizes = list(sizes)

        def fake_run(cmd, cwd=None, quiet=True):
            self.calls.append(cmd)
            if cmd[-1] == str(self.out):
                with open(self.out, "wb") as f:      # sparse: the size without writing megabytes
                    f.truncate(sizes.pop(0))
            elif "pass=1" in " ".join(cmd):
                (self.tmp / "x265_stats.log").write_text("stats")
        with mock.patch.object(common, "run", fake_run), mock.patch.object(common, "HW", hardware), \
                mock.patch.object(common, "probe", lambda path: {"format": {"duration": "40.0"}}), \
                mock.patch.object(common, "find_bin", lambda name: name):
            return common.encode_under(self.master, self.out, 10, 30, self.tmp)

    def rates(self):
        return [int(cmd[cmd.index("-b:v") + 1]) for cmd in self.calls if cmd[-1] == str(self.out)]

    def encoders(self):
        return [cmd[cmd.index("-c:v") + 1] for cmd in self.calls if cmd[-1] == str(self.out)]

    def test_rate_fills_the_cap_after_the_sound(self):
        rate = common.small_rate(10_000_000, 60)
        self.assertAlmostEqual(rate, 10_000_000 * 8 * common.SIZE_AIM / 60 - common.SMALL_AUDIO_BPS, delta=1)
        self.assertEqual(common.small_rate(10_000_000, 2), 10_000_000)       # short: never above the normal rate

    def test_hardware_first_and_every_try_over_the_cap_goes_again_lower(self):
        size, tries = self.encode([12_000_000, 10_000_001, 9_800_000], hardware=True)
        self.assertEqual((size, tries), (9_800_000, 3))
        self.assertEqual(self.encoders(), ["hevc_videotoolbox"] * 3)
        rates = self.rates()
        self.assertEqual(rates, sorted(rates, reverse=True))
        self.assertLess(rates[1], rates[0] * 10 / 12)                       # scaled down by how far over it was
        cmd = self.calls[-1]
        for flag, value in (("-tag:v", "hvc1"), ("-pix_fmt", "yuv420p"), ("-c:a", "aac"), ("-r", "30")):
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        self.assertIn("+faststart", cmd)

    def test_two_pass_x265_takes_over_from_the_full_budget(self):
        size, tries = self.encode([11_000_000] * 3 + [9_000_000], hardware=True)
        self.assertEqual(tries, 4)
        self.assertEqual(self.encoders(), ["hevc_videotoolbox"] * 3 + ["libx265"])
        self.assertEqual(self.rates()[3], self.rates()[0])                   # x265 lands close: back to the full rate
        self.assertTrue(any("pass=1" in " ".join(c) for c in self.calls))
        self.assertFalse(list(self.tmp.glob("x265_stats.log*")))             # no leftovers

    def test_off_a_mac_it_is_x265_from_the_start(self):
        self.encode([9_000_000], hardware=False)
        self.assertEqual(self.encoders(), ["libx265"])

    def test_a_file_over_the_cap_is_never_left_behind(self):
        with self.assertRaises(SystemExit):
            self.encode([20_000_000] * 6, hardware=True)
        self.assertFalse(self.out.exists())

    def test_too_long_for_the_cap_says_so_without_encoding(self):
        with mock.patch.object(common, "probe", lambda path: {"format": {"duration": "4000"}}), \
                self.assertRaises(SystemExit):
            common.encode_under(self.master, self.out, 1, 30, self.tmp)
        self.assertFalse(self.out.exists())


class Jobs(unittest.TestCase):
    def test_results_come_back_in_order(self):
        def slow_square(n):
            time.sleep(0.02 * (5 - n))
            return n * n
        self.assertEqual(common.in_parallel(slow_square, range(5)), [0, 1, 4, 9, 16])
        self.assertEqual(common.in_parallel(slow_square, [3], jobs=3), [9])

    def test_a_failure_stops_the_lot(self):
        def job(n):
            if n == 2:
                common.die("job 2 broke")
            return n
        with self.assertRaises(SystemExit):
            common.in_parallel(job, range(5))


class Scans(unittest.TestCase):
    def test_measured_once_per_file_until_it_changes(self):
        from engine.core import scan
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "WORK_DIR", Path(tmp)):
            clip = Path(tmp) / "clip.mov"
            clip.write_bytes(b"one")
            measured = []
            fake = mock.patch.object(scan, "detect_silences", lambda v: measured.append(v) or [[0.0, 1.0], [5.0, None]])
            with fake:
                self.assertEqual(scan.silence_map(clip), [(0.0, 1.0), (5.0, float("inf"))])
                scan.silence_map(clip)
                self.assertEqual(len(measured), 1)
                clip.write_bytes(b"changed")
                scan.silence_map(clip)
                self.assertEqual(len(measured), 2)
            # caches written before this change ({"stamp", "cuts"}) still count
            stat = clip.stat()
            old = Path(tmp) / "_scenes" / f"{stat.st_ino}.json"
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text(json.dumps({"stamp": f"{stat.st_size}-{int(stat.st_mtime)}", "cuts": [2.5]}))
            self.assertEqual(scan.scene_cuts(clip), [2.5])

    def test_ffmpeg_filter_check_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(grade, "WORK_DIR", Path(tmp)):
            ffmpeg = Path(tmp) / "ffmpeg"                    # a stand-in: the logic runners have no ffmpeg
            ffmpeg.write_bytes(b"")
            grade.has_huesaturation.cache_clear()
            fake = mock.MagicMock(return_value=mock.Mock(stdout=" ... huesaturation  V->V ..."))
            with mock.patch("subprocess.run", fake), mock.patch.object(grade, "find_bin", lambda name: str(ffmpeg)):
                self.assertTrue(grade.has_huesaturation())
                grade.has_huesaturation.cache_clear()
                self.assertTrue(grade.has_huesaturation())            # from work/_grade/filters.json
            self.assertEqual(fake.call_count, 1)
            grade.has_huesaturation.cache_clear()


if __name__ == "__main__":
    unittest.main()
