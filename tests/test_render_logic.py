"""render's decisions, without rendering: the timeline, zooms, captions, graphics, b-roll timing,
sound cues and the mix. everything here is plain python, no ffmpeg needed."""
import copy
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.commands import render
from engine.core.brand import Brand, load_style
from tests.support import ROOT, words


def line(id, word_ids, **extra):
    base = {"id": id, "keep": True, "words": list(word_ids), "cut_words": [], "treatment": "none",
            "motion": "none", "text": "x"}
    return {**base, **extra}


def beth_style(**changes):
    return {**load_style(None, Brand("beth")), **changes}


class Timeline(unittest.TestCase):
    def test_kept_words_become_padded_whole_frame_segments(self):
        w = words("one two three | four five six")
        plan = {"lines": [line(1, range(3)), line(2, range(3, 6))]}
        segments, timed = render.build_segments(plan, w)
        self.assertEqual(len(segments), 2)                       # the pause is cut out
        for seg in segments:
            self.assertAlmostEqual((seg["end"] - seg["start"]) * render.FPS, seg["frames"])
        self.assertAlmostEqual(segments[0]["start"], 0.0)        # padding never goes below zero
        self.assertAlmostEqual(segments[1]["new_start"], segments[0]["new_end"])
        starts = [timed[i][0] for i in sorted(timed)]
        self.assertEqual(starts, sorted(starts))                 # words stay in order on the new timeline
        self.assertLess(segments[-1]["new_end"], w[-1]["end"])   # the reel is shorter than the raw clip

    def test_cut_words_split_a_line_and_dropped_lines_disappear(self):
        w = words("one two um three")
        plan = {"lines": [line(1, range(4), cut_words=[2]), line(2, [], keep=False)]}
        segments, timed = render.build_segments(plan, w)
        self.assertNotIn(2, timed)
        self.assertEqual(sorted(timed), [0, 1, 3])

    def test_a_punch_in_gets_its_own_shot_even_without_a_pause(self):
        w = words("one two three four")
        plan = {"lines": [line(1, range(2), motion="slow"), line(2, range(2, 4), motion="punch")]}
        segments, _ = render.build_segments(plan, w)
        self.assertEqual([s["line"] for s in segments], [1, 2])
        plan["lines"][1]["motion"] = "jump"
        segments, _ = render.build_segments(plan, w)
        self.assertEqual(len(segments), 1)                       # no cut = no framing change

    def test_cuts_snap_to_the_real_silence(self):
        w = words("one two | three")
        plan = {"lines": [line(1, range(2)), line(2, [2])]}
        silences = [(0.0, 0.05), (0.62, 1.7)]                    # voice really stops at 0.62
        segments, _ = render.build_segments(plan, copy.deepcopy(w), silences)
        self.assertGreaterEqual(segments[0]["end"], 0.62)        # ran on until the voice stopped

    def test_never_straddles_a_scene_cut_in_the_footage(self):
        w = words("one two three four")
        plan = {"lines": [line(1, range(4))]}
        segments, _ = render.build_segments(plan, w, scenes=[1.4])
        for seg in segments:
            self.assertFalse(seg["start"] < 1.4 < seg["end"])


class Zoom(unittest.TestCase):
    def setUp(self):
        self.style = {"slow_zoom": 1.1, "jump_zoom": 1.2, "punch_zoom": 1.3}

    def test_slow_zoom_spans_the_whole_line_and_jump_cuts_alternate(self):
        segs = [{"line": 1, "motion": "slow", "new_start": 0, "new_end": 1},
                {"line": 1, "motion": "slow", "new_start": 1, "new_end": 2},
                {"line": 2, "motion": "jump", "new_start": 2, "new_end": 3},
                {"line": 3, "motion": "jump", "new_start": 3, "new_end": 4},
                {"line": 4, "motion": "punch", "new_start": 4, "new_end": 5}]
        render.assign_zoom(segs, self.style)
        self.assertEqual([(s["z0"], s["z1"]) for s in segs[:2]], [(1.0, 1.05), (1.05, 1.1)])
        self.assertEqual([s["z0"] for s in segs[2:4]], [1.2, 1.0])
        self.assertEqual(segs[4]["z0"], 1.3)

    def test_framing_filters(self):
        still = {"start": 0, "end": 1, "z0": 1.0, "z1": 1.0}
        push = {"start": 0, "end": 1, "z0": 1.0, "z1": 1.07}
        self.assertTrue(render.frame_filter(still, 1080, 1920).startswith("crop=1080.00:1920.00:0.00:0.00"))
        self.assertIn("crop=607.50:1080.00:656.25:0.00", render.frame_filter(still, 1920, 1080))   # landscape: centre strip
        self.assertIn("zoompan=z='1.00000+0.07000*on/30'", render.frame_filter(push, 1080, 1920))
        with render.half_size_frames():
            self.assertIn("scale=540:960", render.frame_filter(still, 1080, 1920))
        self.assertIn("scale=1080:1920", render.frame_filter(still, 1080, 1920))


class Captions(unittest.TestCase):
    def make(self, text, style, **line_extra):
        w = words(text)
        plan = {"lines": [line(1, range(len(w)), **line_extra)]}
        _, timed = render.build_segments(plan, w)
        total = max(end for _, end in timed.values()) + 1
        return render.caption_events(plan, w, timed, style, total)

    @staticmethod
    def plain(event_text):
        return re.sub(r"\{[^}]*\}", "", event_text)

    def test_lowercase_keeps_brand_capitals_and_a_capital_i(self):
        style = beth_style(caption_mode="line", words_per_caption=10, keep_caps=["TikTok Shop", "UK"], caption_chars=0)
        events = self.make("i'm SELLING on tiktok shop in the uk", style)
        self.assertEqual(self.plain(events[0][3]), "I'm selling on TikTok Shop in the UK")

    def test_captions_never_wrap_and_never_split_a_brand_name(self):
        style = beth_style(caption_mode="line", words_per_caption=6, caption_chars=14, keep_caps=["TikTok Shop"])
        events = self.make("lots of people sell on tiktok shop every single day now", style)
        texts = [self.plain(e[3]) for e in events]
        self.assertTrue(all(len(t) <= 14 or " " not in t for t in texts if "TikTok Shop" not in t), texts)
        self.assertTrue(any("TikTok Shop" in t for t in texts), texts)

    def test_no_word_left_on_its_own(self):
        style = beth_style(caption_mode="line", words_per_caption=3, caption_chars=0)
        events = self.make("one two three four five six seven", style)
        self.assertGreater(len(self.plain(events[-1][3]).split()), 1)

    def test_numbers_are_keywords_and_get_the_keyword_look(self):
        style = beth_style(caption_mode="line", words_per_caption=10, caption_chars=0, keyword_colour="#123456")
        events = self.make("charge 700 pounds", style)
        tagged = re.findall(r"\{([^}]*)\}([^{ ]+)", events[0][3])
        looks = {word: tags for tags, word in tagged}
        self.assertIn(render.ass_colour("#123456"), looks["700"])
        self.assertNotIn(render.ass_colour("#123456"), looks["charge"])

    def test_build_mode_lays_out_the_whole_line_from_the_start(self):
        style = beth_style(caption_mode="build", words_per_caption=4, build_step=1, caption_chars=0)
        events = self.make("one two three four", style)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0][3].count("\\alpha&HFF&"), 3)    # unsaid words invisible
        self.assertEqual(events[-1][3].count("\\alpha&HFF&"), 0)
        self.assertTrue(all(e[1] > e[0] for e in events))

    def test_karaoke_and_word_modes(self):
        karaoke = self.make("one two three", beth_style(caption_mode="karaoke", words_per_caption=3, caption_chars=0))
        self.assertEqual(len(karaoke), 3)
        word = self.make("one two three", beth_style(caption_mode="word", caption_chars=0))
        self.assertEqual([self.plain(e[3]) for e in word], ["one", "two", "three"])

    def test_takeover_lines_have_no_captions(self):
        self.assertEqual(self.make("one two", beth_style(), treatment="takeover"), [])


class Graphics(unittest.TestCase):
    def events(self, plan, w, style=None):
        _, timed = render.build_segments(plan, w)
        total = max(end for _, end in timed.values()) + 0.5
        return render.overlay_events(plan, w, timed, total, style or beth_style()), total

    def test_hook_is_on_screen_from_zero_split_into_short_lines(self):
        w = words("you need to charge more")
        plan = {"hook_text": "the price nobody tells you about", "lines": [line(1, range(5))]}
        events, total = self.events(plan, w, beth_style(hook_line_height=0.85, hook_chars=18, hook_uppercase=True))
        hook = [e for e in events if e[2] == "Hook"]
        self.assertGreater(len(hook), 1)
        self.assertTrue(all(e[0] == 0.0 and e[1] <= total for e in hook))
        self.assertIn("THE PRICE", hook[0][3])
        self.assertEqual(render.hook_lines("one two three four five", {"hook_chars": 9}), ["one two", "three", "four five"])

    def test_big_stats_count_up_then_pop_small_ones_just_pop(self):
        w = words("we made 1,500 pounds")
        plan = {"lines": [line(1, range(4), treatment="stat pop", stat="£1,500")]}
        events, _ = self.events(plan, w)
        stats = [e for e in events if e[2] == "Stat"]
        self.assertEqual(len(stats), render.STAT_COUNT_STEPS + 1)
        self.assertTrue(stats[0][3].endswith("£187"))
        self.assertTrue(stats[-1][3].endswith("£1,500"))
        plan["lines"][0]["stat"] = "3x"
        events, _ = self.events(plan, w)
        self.assertEqual(len([e for e in events if e[2] == "Stat"]), 1)

    def test_takeover_splits_its_time_between_cards_and_badges_show_the_step(self):
        w = words("one two three four | five six")
        plan = {"lines": [line(1, range(4), treatment="takeover", takeover_text=["card\none", "card\\ntwo"]),
                          line(2, range(4, 6), treatment="step", step=2)]}
        events, _ = self.events(plan, w)
        cards = [e for e in events if e[2] == "TakeText"]
        self.assertEqual(len(cards), 2)
        self.assertAlmostEqual(cards[0][1], cards[1][0])
        self.assertTrue(cards[0][3].endswith("card\\None"))      # a real newline
        self.assertTrue(cards[1][3].endswith("card\\Ntwo"))      # a typed \n
        self.assertTrue(any(e[2] == "Badge" and e[3].endswith("step 2") for e in events))

    def test_no_hook_card_when_the_reel_opens_on_a_takeover(self):
        w = words("one two")
        plan = {"hook_text": "hook", "lines": [line(1, range(2), treatment="takeover")]}
        events, _ = self.events(plan, w)
        self.assertFalse(any(e[2] == "Hook" for e in events))


class AssFiles(unittest.TestCase):
    def test_header_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.ass"
            render.write_ass(path, beth_style(), [(1.5, 2.0, "Caption", "hi"), (0, 3725.5, "TakeText", "big")])
            text = path.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1080", text)
        self.assertIn("Dialogue: 3,0:00:00.00,1:02:05.50,TakeText,,0,0,0,,big", text)
        self.assertLess(text.index("TakeText,,0,0,0,,big"), text.index("Caption,,0,0,0,,hi"))   # sorted by start
        self.assertEqual(render.ass_colour("#FAEAF0"), "&H00F0EAFA")
        self.assertEqual(render.ass_escape("a{b}\\c"), "a(b)c")
        self.assertEqual(render.srt_time(3725.5), "01:02:05,500")


class Broll(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.still = Path(self.tmp.name) / "still.jpg"     # an image: no scene detection needed
        self.still.write_bytes(b"")

    def tearDown(self):
        self.tmp.cleanup()

    def windows(self, plan, w, cuts=()):
        _, timed = render.build_segments(plan, w)
        total = max(end for _, end in timed.values()) + 0.5
        return render.broll_windows(plan, timed, total, cuts)

    def test_windows_cover_their_line_snap_to_cuts_and_join_up(self):
        w = words("one two three four five six")
        spec = {"file": str(self.still), "start": 0, "mode": "full"}
        plan = {"lines": [line(1, range(2), broll=spec), line(2, range(2, 4)), line(3, range(4, 6), broll=spec)]}
        windows = self.windows(plan, w, cuts=[0.61])
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][0], 0.0)
        self.assertEqual(windows[0][1], windows[1][0])     # less than BROLL_JOIN_GAP apart: runs straight through

    def test_continue_merges_into_the_previous_shot(self):
        w = words("one two three four")
        spec = {"file": str(self.still)}
        plan = {"lines": [line(1, range(2), broll=spec), line(2, range(2, 4), broll={**spec, "continue": True})]}
        self.assertEqual(len(self.windows(plan, w)), 1)

    def test_missing_file_stops_the_render(self):
        plan = {"lines": [line(1, range(2), broll={"file": "brands/beth/broll/not-there.mp4"})]}
        with self.assertRaises(SystemExit):
            self.windows(plan, words("one two"))

    @mock.patch.object(render, "sdr_filter", lambda path: "")     # the test image is empty: skip probing it
    def test_pip_is_smaller_and_framed(self):
        spec = {"path": self.still, "mode": "pip"}
        chain = render.broll_filter(3, 1.0, 2.0, spec)
        self.assertIn(f"s={render.PIP_W}x{render.PIP_H}", chain)
        self.assertTrue(chain.endswith("pad=iw+16:ih+16:8:8:white"))
        self.assertIn(",lut", render.broll_filter(3, 1.0, 2.0, {**spec, "grade": True}, "lut"))
        self.assertNotIn("lut", render.broll_filter(3, 1.0, 2.0, spec, "lut"))   # b-roll ungraded by default


class Sound(unittest.TestCase):
    def cues(self, plan, w, windows=()):
        _, timed = render.build_segments(plan, w)
        return render.sfx_cues(plan, w, timed, list(windows))

    def test_automatic_cues_and_overrides(self):
        w = words("one two | three 70% | four five | six seven")
        plan = {"lines": [line(1, range(2), sfx="click", sfx_volume=0.6),
                          line(2, range(2, 4), treatment="stat pop", stat="70%"),
                          line(3, range(4, 6), treatment="takeover"),
                          line(4, range(6, 8), treatment="step", step=1, sfx="none")]}
        cues = self.cues(plan, w)
        self.assertEqual([name for _, name, _ in cues], ["click", "pop", "whoosh"])
        self.assertEqual(cues[0][2], 0.6)
        self.assertEqual(cues, sorted(cues))

    def test_swoosh_into_b_roll_unless_another_sound_is_close_and_all_off_switch(self):
        w = words("one two three four")
        plan = {"lines": [line(1, range(4))]}
        self.assertEqual([c[1] for c in self.cues(plan, w, [(1.0, 2.0, {})])], ["swoosh"])
        plan["sound"] = {"sfx": False}
        self.assertEqual(self.cues(plan, w, [(1.0, 2.0, {})]), [])

    def test_mix(self):
        self.assertEqual(render.mix(["music"], "aout", 10, with_speech=False, loud=False),
                         "[music]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:10.000[aout]")
        self.assertIn("amix=inputs=3", render.mix(["music", "fx0"], "aout", 10))
        self.assertIn("loudnorm=I=-14", render.mix(["music", "fx0"], "aout", 10))
        self.assertTrue(render.mix([], "aout", 5, with_speech=False).startswith("anullsrc"))
        self.assertTrue((render.SFX_DIR / "click.wav").exists() and render.find_sfx("click"))
        self.assertIsNone(render.find_sfx("not-a-sound"))


class Speed(unittest.TestCase):
    """the render audit's changes: same pictures, less work."""

    @mock.patch.object(render, "sdr_filter", lambda path: "zscale=hdr,")
    def test_frames_are_picked_and_counted_before_any_picture_work(self):
        still = {"start": 0, "end": 1, "z0": 1.1, "z1": 1.1}
        push = {"start": 0, "end": 1, "z0": 1.0, "z1": 1.07}
        for seg, order in ((still, ["fps=30", "trim=end_frame=30", "crop=", "zscale=hdr", "scale=1080:1920"]),
                           (push, ["fps=30", "trim=end_frame=30", "zscale=hdr", "scale=2160", "zoompan"])):
            chain = render.segment_chain(4, seg, 30, "clip.mov", 1080, 1920)
            self.assertTrue(chain.startswith("[4:v]setpts=PTS-STARTPTS,fps=30,"))
            positions = [chain.index(part) for part in order]
            self.assertEqual(positions, sorted(positions), chain)     # still shots crop before the hdr conversion
            self.assertEqual(chain.count("fps=30,"), 1)
        broll = render.broll_filter(2, 1.0, 2.0, {"path": Path("b.mov")})
        positions = [broll.index(part) for part in ("fps=30", "trim=end_frame=34", "zscale=hdr", "zoompan")]
        self.assertEqual(positions, sorted(positions), broll)

    def test_captions_draw_above_every_graphic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reel.ass"
            render.write_ass(path, beth_style(), [(0, 1, name, "x") for name in
                                                  ("Caption", "Hook", "Stat", "Badge", "TakeBox", "TakeText")])
            layers = {line.split(",")[3]: int(line.split(",")[0].split()[-1])
                      for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue")}
        self.assertGreater(layers["Caption"], max(v for k, v in layers.items() if k != "Caption"))

    def test_b_roll_edges_land_on_the_nearest_frame(self):
        # a window snapped onto cuts (whole frames) covers exactly the frames from the first cut to the second,
        # whatever tiny drift the frame times have
        expr = render.on_frames(233 / 30, 286 / 30)
        low, high = (float(x) for x in re.search(r"between\(t,([\d.]+),([\d.]+)\)", expr).groups())
        shown = [k for k in range(220, 300) for drift in (-0.0004, 0, 0.0004) if low <= k / 30 + drift <= high]
        self.assertEqual(sorted(set(shown)), list(range(233, 286)))
        self.assertEqual(len(shown), 3 * (286 - 233))

    def edit(self, cuts, windows=(), total=None, slow=()):
        starts = [0.0] + list(cuts)
        ends = list(cuts) + [total or cuts[-1] + 10]
        segments = [{"new_start": a, "new_end": b, "frames": round((b - a) * 30), "z0": 1.0,
                     "z1": 1.07 if n in slow else 1.0} for n, (a, b) in enumerate(zip(starts, ends))]
        return render.Edit(inputs=[], filters=[], segments=segments, timed={}, total=ends[-1], captions=[],
                           graphics=[], windows=[(a, b, {}) for a, b in windows], cues=[], missing_sfx=[],
                           sound_labels=[], music=None, video="clip.mov", size=(1080, 1920))

    def test_long_reels_split_into_chunks_at_cuts_never_inside_b_roll(self):
        edit = self.edit([5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55], windows=[(18, 22), (38, 41)], total=60)
        chunks = render.chunk_plan(edit)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0][0], 0)
        self.assertEqual(chunks[-1][1], len(edit.segments))
        for (_, after), (first, _) in zip(chunks, chunks[1:]):
            self.assertEqual(after, first)                           # every segment in exactly one chunk
            join = edit.segments[first]["new_start"]
            self.assertFalse(any(a < join < b for a, b, _ in edit.windows), join)
            self.assertNotIn(join, (20, 40))
        self.assertEqual(render.chunk_plan(self.edit([4, 8], total=12)), [(0, 3)])     # short: one go
        # no cut far enough from the ends: one go
        self.assertEqual(render.chunk_plan(self.edit([2, 58], total=60)), [(0, 3)])

    @mock.patch.object(render, "sdr_filter", lambda path: "")
    def test_chunks_grade_in_the_format_a_one_pass_render_picks(self):
        def fmt(pix_fmt, slow=()):
            with mock.patch.object(render, "probe", lambda path: {"streams": [{"codec_type": "video",
                                                                                 "pix_fmt": pix_fmt}]}):
                return render.grade_format(self.edit([5, 10], slow=slow))
        self.assertEqual(fmt("yuv420p10le", slow=(1,)), "gbrp")     # a slow zoom anywhere: 8-bit planar
        self.assertEqual(fmt("yuv420p"), "rgb24")
        self.assertEqual(fmt("yuv420p10le"), "gbrp10le")
        with mock.patch.object(render, "sdr_filter", lambda path: "zscale,"):
            self.assertEqual(fmt("yuv420p10le"), "rgb24")           # phone hdr is 8-bit after conversion


class Paths(unittest.TestCase):
    def test_fonts_dir_is_relative_to_where_ffmpeg_runs(self):
        self.assertEqual(render.fonts_dir_from(ROOT / "work" / "clip"), "../../assets/fonts")
        self.assertEqual(render.fonts_dir_from(ROOT / "work" / "clip" / "cut_previews"), "../../../assets/fonts")


if __name__ == "__main__":
    unittest.main()
