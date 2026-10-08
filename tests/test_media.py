"""real renders with ffmpeg, on synthetic clips: the colour table, hdr conversion, beat detection,
a full talking-head reel (checked against golden copies of its recipe files), cut / spot previews,
the capcut pack, qc, batch splitting, a vlog edit, text reels, b-roll indexing and take frames.

needs ffmpeg 7+ with libass, zimg, freetype etc (see support.NEEDED_FILTERS), otherwise skipped.
the encoded videos themselves differ a little from run to run, so they're checked by size, length
and streams; the recipes that produced them are what's compared exactly.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import (ROOT, Sandbox, assert_golden, fake_transcript, ffmpeg, make_clip, needs_ffmpeg, normalise,
                           probe)


def duration(path):
    return float(probe(path)["format"]["duration"])


def video_stream(path):
    return next(s for s in probe(path)["streams"] if s["codec_type"] == "video")


def has_audio(path):
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def outputs(box, kind, name):
    """files called `name` in the sandbox's output/beth/<kind>/<date>_<time>_<job>/ folders, oldest first."""
    return sorted((box.output / "beth" / kind).glob(f"*/{name}"))


def click_track(path, bpm, secs):
    """a click on every beat, to test beat detection and cutting to music."""
    period = 60 / bpm
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='if(lt(mod(t,{period}),0.03),sin(2*PI*1200*t),0)':s=44100:d={secs}",
           "-c:a", "libmp3lame", "-q:a", "4", path)
    return path


@needs_ffmpeg
class Colour(unittest.TestCase):
    def test_baked_colour_table_matches_the_filter_chain(self):
        from engine.core import grade
        from engine.core.brand import Brand
        g = json.loads(Brand("beth").grade_file.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(grade, "WORK_DIR", Path(tmp)):
            chain = grade.colour_chain(g)
            table = grade.grade_filter(g)
            self.assertTrue(table.startswith("lut3d="))
            self.assertEqual(table, grade.grade_filter(g))                    # cached, same file
            self.assertEqual(len(list(Path(tmp, "_grade").glob("*.cube"))), 1)
            source = Path(tmp) / "frame.png"
            ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1", source)
            lut = table.split(",unsharp")[0]
            res = subprocess.run(["ffmpeg", "-hide_banner", "-i", source, "-i", source, "-filter_complex",
                                  f"[0:v]format=rgb48le,{chain},format=rgb24[a];[1:v]format=rgb48le,{lut},format=rgb24[b];"
                                  "[a][b]psnr", "-f", "null", "-"], capture_output=True, text=True)
            psnr = float(re.search(r"average:([\d.]+|inf)", res.stderr).group(1).replace("inf", "99"))
        self.assertGreater(psnr, 40, "the fast colour table drifted away from the real grade")

    def test_phone_hdr_is_converted_and_normal_clips_are_left_alone(self):
        from engine.core import common
        with tempfile.TemporaryDirectory() as tmp:
            sdr = make_clip(Path(tmp) / "sdr.mp4", 1, audio=False)
            hlg = Path(tmp) / "hlg.mp4"
            ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:d=1", "-vf",       # tagged like an iphone hdr clip
                   "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,format=yuv420p10le",
                   "-c:v", "libx264", hlg)
            self.assertEqual(common.sdr_filter(sdr), "")
            chain = common.sdr_filter(hlg)
            self.assertIn("zscale", chain)
            out = Path(tmp) / "out.png"
            ffmpeg("-i", hlg, "-vf", chain.rstrip(","), "-frames:v", "1", out)     # ffmpeg accepts the chain
            self.assertTrue(out.exists())


@needs_ffmpeg
class Beats(unittest.TestCase):
    def test_tempo_of_a_click_track(self):
        from engine.commands.vlog import detect_beats
        with tempfile.TemporaryDirectory() as tmp:
            bpm, beats = detect_beats(click_track(Path(tmp) / "click.mp3", 120, 20))
        self.assertAlmostEqual(bpm, 120, delta=3)
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        self.assertAlmostEqual(sum(gaps) / len(gaps), 0.5, delta=0.02)


@needs_ffmpeg
class TalkingHeadReel(unittest.TestCase):
    """one feature-heavy reel, rendered once, then checked from every angle."""

    @classmethod
    def setUpClass(cls):
        box = cls.box = Sandbox("reel")
        cls.video = box.inputs / "talking-head" / "reel.mp4"
        cls.wd = box.work / "reel"
        said = fake_transcript(cls.wd, cls.video, "you need to charge um 700 pounds | you need to charge 700 pounds | "
                               "step one know your rates | 70% of creators forget this | so write it down | "
                               "then send the invoice | and follow up every time", unsure=("invoice",))
        make_clip(cls.video, said["duration"])
        cls.broll = make_clip(box.dir / "broll.mp4", 6, pattern="smptebars", audio=False)
        cls.music = click_track(box.dir / "music.mp3", 100, 30)
        box.engine("plan", cls.video, "--brand", "beth")
        plan = json.loads((cls.wd / "plan.json").read_text(encoding="utf-8"))
        kept = [l for l in plan["lines"] if l["keep"]]
        kept[0].update(sfx="click", sfx_volume=0.6)
        kept[3].update(treatment="takeover", takeover_text=["so write", "it DOWN"])
        kept[4]["broll"] = {"file": str(cls.broll), "start": 1.0, "mode": "full"}
        kept[5]["broll"] = {"file": str(cls.broll), "start": 2.0, "mode": "pip"}
        plan["sound"]["music"] = str(cls.music)
        (cls.wd / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        cls.render = box.engine("render", cls.video, "--draft", "--capcut", "--cover")
        cls.qc = box.engine("qc", cls.video, check=False)       # now, before other tests re-render this job
        cls.edl = json.loads((cls.wd / "edl.json").read_text(encoding="utf-8"))
        cls.files = {name: normalise((cls.wd / name).read_text(encoding="utf-8"), box)
                     for name in ("captions.ass", "graphics.ass", "filter.txt")}

    @classmethod
    def tearDownClass(cls):
        cls.box.remove()

    def test_recipes_match_the_golden_copies(self):
        edl = {k: v for k, v in self.edl.items() if k not in ("output", "cover", "capcut_pack")}
        assert_golden(self, "reel/edl.json", normalise(json.dumps(edl, indent=2), self.box) + "\n")
        for name, text in self.files.items():
            with self.subTest(file=name):
                assert_golden(self, f"reel/{name}", text)

    def test_the_reel(self):
        out = Path(self.edl["output"])
        # output/<brand>/<type>/<date>_<time>_<job>/<job>_<style>_draft.mp4, with the cover and pack beside it
        folder = out.parent
        self.assertEqual(folder.parent, self.box.output / "beth" / "talking-head")
        self.assertRegex(folder.name, r"^\d{4}-\d\d-\d\d_\d{4}_reel(-\d+)?$")
        self.assertEqual(out.name, "reel_beth_draft.mp4")
        self.assertEqual(Path(self.edl["cover"]).parent, folder)
        self.assertEqual(Path(self.edl["capcut_pack"]).parent, folder)
        stream = video_stream(out)
        self.assertEqual((stream["width"], stream["height"], stream["codec_name"]), (1080, 1920, "h264"))
        self.assertEqual(stream["r_frame_rate"], "30/1")
        self.assertAlmostEqual(duration(out), self.edl["duration"], delta=0.2)
        self.assertTrue(has_audio(out))
        said = json.loads((self.wd / "transcript.json").read_text(encoding="utf-8"))["duration"]
        self.assertLess(self.edl["duration"], said - 5)                       # pauses and the retake are gone
        self.assertEqual(len(self.edl["broll"]), 2)
        # click on frame 1, click on the step badge, pop on the stat, whoosh into the takeover, swoosh into each b-roll
        self.assertEqual([c["name"] for c in self.edl["sfx"]], ["click", "click", "pop", "whoosh", "swoosh", "swoosh"])
        self.assertTrue(self.edl["graded"] and self.edl["music"] and self.edl["has_hook"])
        self.assertTrue(Path(self.edl["cover"]).exists())

    def test_capcut_pack(self):
        pack = Path(self.edl["capcut_pack"])
        for name in ("1_video_clean.mp4", "2_graphics_on_black.mp4", "2_graphics_matte.mp4", "3_captions.srt",
                     "4_music_and_sfx.wav", "HOW_TO_OPEN_IN_CAPCUT.txt"):
            self.assertTrue((pack / name).exists(), name)
        for name in ("1_video_clean.mp4", "2_graphics_on_black.mp4", "2_graphics_matte.mp4", "4_music_and_sfx.wav"):
            # every layer exactly as long as the reel, or they drift apart on the capcut timeline
            self.assertAlmostEqual(duration(pack / name), self.edl["duration"], delta=0.05, msg=name)
        srt = (pack / "3_captions.srt").read_text(encoding="utf-8")
        self.assertRegex(srt, r"^1\n00:00:00,\d{3} --> 00:00:\d\d,\d{3}\n")
        self.assertNotIn("so write", srt.lower())                             # takeover lines have no captions

    def test_qc_passes_and_flags_the_unsure_word(self):
        res = self.qc
        self.assertEqual(res.returncode, 0, res.stdout)
        for check in ("format | PASS", "loudness | PASS", "captions | PASS", "capcut pack | PASS", "text contrast | PASS"):
            self.assertIn(check, res.stdout)
        self.assertIn("caption accuracy | WARN", res.stdout)
        self.assertIn("invoice", res.stdout)

    def test_cut_preview_finds_no_stray_frames(self):
        out = self.box.engine("render", self.video, "--cuts").stdout
        self.assertIn("cut preview:", out)
        self.assertNotIn("FLASH", out)
        preview = outputs(self.box, "previews", "reel_cuts_preview.mp4")[-1]
        self.assertEqual(video_stream(preview)["width"], 540)                 # half size

    def test_spot_preview(self):
        out = self.box.engine("render", self.video, "--spot", "2,6", "--pad", "1").stdout
        self.assertIn("spot  2 at", out)
        self.assertEqual(video_stream(outputs(self.box, "previews", "reel_spot.mp4")[-1])["width"], 1080)

    def test_another_style_ungraded(self):
        self.box.engine("render", self.video, "--draft", "--style", "editorial", "--no-grade")
        renders = outputs(self.box, "talking-head", "reel_*_draft.mp4")
        self.assertEqual(renders[-1].name, "reel_editorial_draft.mp4")
        self.assertNotEqual(renders[-1].parent, Path(self.edl["output"]).parent)     # a new folder, nothing overwritten
        self.assertTrue(Path(self.edl["output"]).exists())
        edl = json.loads((self.wd / "edl.json").read_text(encoding="utf-8"))
        self.assertEqual((edl["style"], edl["graded"]), ("editorial", False))
        self.assertNotIn("lut3d", (self.wd / "filter.txt").read_text(encoding="utf-8"))

    def test_review_page(self):
        self.box.engine("review", self.video, "--no-open")
        page = (self.wd / "review.html").read_text(encoding="utf-8")
        data = json.loads(re.search(r"const D = (\{.*?\});\n", page, re.S).group(1))
        self.assertEqual(len(data["rows"]), 7)
        self.assertEqual(data["style"], "beth")
        self.assertTrue(all(row["img"].startswith("data:image/jpeg;base64,") for row in data["rows"]))
        self.assertEqual(len(list((self.wd / "thumbs").glob("*.jpg"))), 7)

    def test_take_frames(self):
        self.box.engine("takes", self.video)
        self.assertTrue(list((self.wd / "takes").glob("*.jpg")))


@needs_ffmpeg
class BatchTake(unittest.TestCase):
    def test_split_and_cut(self):
        box = Sandbox("batch")
        try:
            video = make_clip(box.inputs / "shop" / "batch.mp4", 14)
            fake_transcript(box.work / "batch", video, "hook one these trousers fit | | hook two the boots stretch | | "
                            "hook three honest review", pause=2.0, duration=14)
            out = box.engine("batch", "split", video, "--gap", "1.5").stdout
            self.assertIn("found 3 video(s)", out)
            sections = json.loads((box.work / "batch" / "batch.json").read_text(encoding="utf-8"))["sections"]
            self.assertEqual([s["hook"].split()[:2] for s in sections], [["hook", "one"], ["hook", "two"], ["hook", "three"]])
            self.assertIn("found 2 video(s)", box.engine("batch", "split", video, "--count", "2").stdout)
            box.engine("batch", "split", video, "--gap", "1.5")
            box.engine("batch", "cut", video)
            parts = sorted((box.work / "batch" / "parts").glob("*.mp4"))
            self.assertEqual([p.name for p in parts], ["batch_01.mp4", "batch_02.mp4", "batch_03.mp4"])
            for part, section in zip(parts, sections):
                self.assertAlmostEqual(duration(part), section["end"] - section["start"], delta=0.15)
            self.assertTrue(video.exists())                                  # the original is untouched
        finally:
            box.remove()


@needs_ffmpeg
class VlogAndTextReels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        box = cls.box = Sandbox("vlog")
        cls.folder = box.inputs / "vlog" / "trip"
        make_clip(cls.folder / "a.mp4", 6, pattern="testsrc2")
        make_clip(cls.folder / "b.mp4", 6, pattern="mandelbrot", tone=440)
        make_clip(cls.folder / "c.mp4", 5, pattern="life", tone=520)
        cls.music = click_track(box.dir / "beat.mp3", 120, 40)

    @classmethod
    def tearDownClass(cls):
        cls.box.remove()

    def test_vlog_edit(self):
        box, wd = self.box, self.box.work / "vlog-trip"
        box.engine("vlog", "analyse", self.folder)
        clips = json.loads((wd / "clips.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(len(clips), 3)
        self.assertTrue(all(c["windows"] and c["has_audio"] for c in clips))
        self.assertEqual(len(list((wd / "sheets").glob("*.jpg"))), 3)

        out = box.engine("vlog", "plan", self.folder, "--brand", "beth", "--music", self.music, "--length", "12").stdout
        self.assertAlmostEqual(float(re.search(r"music: ([\d.]+) bpm", out).group(1)), 120, delta=3)
        plan = json.loads((wd / "plan.json").read_text(encoding="utf-8"))
        pieces = plan["pieces"]
        self.assertEqual(plan["brand"], "beth")
        self.assertTrue(any(p["kind"] == "teaser" for p in pieces))
        self.assertTrue(all(p["transition"] == "cut" and p["speed"] == 1.0 for p in pieces if p["kind"] == "shot"))
        shots = [p for p in pieces if p["kind"] == "shot"]
        for first, second in zip(shots, shots[1:]):     # the same clip twice in a row only as a jump cut pair
            if first["clip"] == second["clip"]:
                self.assertIn("zoom", first)
                self.assertNotEqual(first["zoom"], second["zoom"])
        self.assertTrue((wd / "storyboard.jpg").exists())
        box.engine("vlog", "table", self.folder)

        box.engine("vlog", "render", self.folder, "--draft")
        total = sum(p["dur"] for p in pieces)
        for name in ("vlog-trip_draft.mp4", "vlog-trip_draft_no_music.mp4"):
            out = outputs(box, "vlog", name)[-1]
            self.assertTrue(out.parent.name.endswith("_trip"))
            self.assertAlmostEqual(duration(out), total, delta=0.2, msg=name)
            self.assertEqual(video_stream(out)["height"], 1920)

    def test_text_reels(self):
        from tests.test_tools import write_xlsx
        box = self.box
        sheet = box.inputs / "trial" / "set.xlsx"
        write_xlsx(sheet, [["#", "type", "beat 1 (hook)", "beat 2", "beat 3", "b-roll", "caption", "carousel it points to"],
                           ["1", "number reveal", "I charged £150 + £700", "same video", "see my carousel", "laptop",
                            "the caption", "rates"],
                           ["2", "hot take", "stop doing FREE work", "it costs you", "read this", "camera", "c2", "pricing"]])
        box.engine("textreel", "import", sheet, "set", "--brand", "beth")
        plan_path = box.work / "set" / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual([r["beats"][0] for r in plan["reels"]], ["I charged £150 + £700", "stop doing FREE work"])
        rel = lambda p: p.relative_to(ROOT).as_posix()
        for reel in plan["reels"]:
            reel["shots"] = [{"file": rel(self.folder / f"{x}.mp4"), "start": 0.5} for x in "abc"]
            reel["music"] = str(self.music)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        box.engine("textreel", "render", "set", "--only", "1", "--draft")
        reels = outputs(box, "trial", "*.mp4")
        self.assertEqual(len(reels), 1)
        self.assertTrue(reels[0].parent.name.endswith("_set"))
        from engine.commands.textreel import beat_lengths
        expected = sum(beat_lengths(["I charged £150 + £700", "same video", "see my carousel"], bpm=120))
        self.assertAlmostEqual(duration(reels[0]), expected, delta=0.3)       # reading time, snapped to the beat
        self.assertEqual(outputs(box, "trial", "captions.md"), [])            # only written on a full render
        box.engine("textreel", "render", "set", "--draft")
        captions = outputs(box, "trial", "captions.md")
        self.assertEqual(len(captions), 1)
        self.assertEqual(len(list(captions[0].parent.glob("*.mp4"))), 2)      # the full set in its own folder
        self.assertIn("(carousel: pricing)", captions[0].read_text(encoding="utf-8"))


@needs_ffmpeg
class BrollLibrary(unittest.TestCase):
    def test_index_previews_and_tags(self):
        box = Sandbox("broll-index")
        try:
            broll = box.brands / "beth" / "broll"
            for old in broll.glob("*.mp4"):
                old.unlink()
            make_clip(broll / "products" / "pouring-gummies.mp4", 3, audio=False)
            ffmpeg("-f", "lavfi", "-i", "testsrc2=size=400x600", "-frames:v", "1", broll / "flat-lay.jpg")
            out = box.engine("broll", "index", "--brand", "beth").stdout
            self.assertIn("2 clip(s) in the library, 2 need a description", out)
            clips = {c["file"]: c for c in json.loads((broll / "library.json").read_text(encoding="utf-8"))["clips"]}
            video = clips["work/_tests/broll-index/brands/beth/broll/products/pouring-gummies.mp4"]
            self.assertEqual((video["kind"], video["orientation"]), ("video", "portrait"))
            self.assertTrue({"product", "pour", "gummi"} <= set(video["tags"]), video["tags"])
            self.assertEqual(clips["work/_tests/broll-index/brands/beth/broll/flat-lay.jpg"]["kind"], "image")
            for clip in clips.values():
                self.assertTrue((ROOT / clip["preview"]).exists())
            # descriptions claude writes survive a re-index, and unchanged clips aren't redone
            library = json.loads((broll / "library.json").read_text(encoding="utf-8"))
            for clip in library["clips"]:
                clip["description"] = "a described clip"
            (broll / "library.json").write_text(json.dumps(library), encoding="utf-8")
            self.assertIn("1 need a description", self.add_and_reindex(box, broll))
        finally:
            box.remove()

    @staticmethod
    def add_and_reindex(box, broll):
        make_clip(broll / "new.mp4", 2, audio=False)
        out = box.engine("broll", "index", "--brand", "beth").stdout
        library = json.loads((broll / "library.json").read_text(encoding="utf-8"))["clips"]
        assert sum(c["description"] == "a described clip" for c in library) == 2, library
        return out


if __name__ == "__main__":
    unittest.main()
