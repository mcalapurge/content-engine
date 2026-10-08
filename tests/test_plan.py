"""the rough cut: splitting speech into lines, spotting retakes, cutting fillers, stats, hooks."""
import json
import unittest

from engine.commands import plan
from tests.support import Sandbox, fake_transcript, words


class SplitLines(unittest.TestCase):
    def test_pause_starts_a_new_line(self):
        w = words("one two three | four five")
        self.assertEqual(plan.split_lines(w), [[0, 1, 2], [3, 4]])

    def test_sentence_end_starts_a_new_line_once_it_has_three_words(self):
        self.assertEqual(plan.split_lines(words("this is it. and more")), [[0, 1, 2], [3, 4]])
        self.assertEqual(plan.split_lines(words("ok. and more")), [[0, 1, 2]])

    def test_long_runs_are_capped(self):
        lines = plan.split_lines(words(" ".join(["word"] * 40)))
        self.assertTrue(all(len(line) <= plan.MAX_LINE_WORDS for line in lines))
        self.assertEqual(sum(len(line) for line in lines), 40)


class Retakes(unittest.TestCase):
    def test_same_opening_words_is_a_retake(self):
        self.assertTrue(plan.is_retake(["you", "need", "to", "charge"], ["you", "need", "to", "charge", "more"]))

    def test_close_wording_is_a_retake(self):
        self.assertTrue(plan.is_retake(["the", "real", "rate", "is"], ["so", "the", "real", "rate", "is", "700"]))

    def test_different_lines_are_not(self):
        self.assertFalse(plan.is_retake(["contracts", "matter"], ["usage", "rights", "explained"]))
        self.assertFalse(plan.is_retake([], ["anything"]))


class Stats(unittest.TestCase):
    def test_finds_money_percentages_and_multipliers(self):
        cases = {"I charge £700 now": "£700", "70 percent of creators": "70%", "it went up 3x": "3x",
                 "made $5,000.": "$5,000", "a 10k month": "10k", "no numbers here": None}
        for text, stat in cases.items():
            with self.subTest(text=text):
                self.assertEqual(plan.find_stat(text), stat)


class Hooks(unittest.TestCase):
    def test_strips_fillers_caps_the_first_letter_and_trims(self):
        self.assertEqual(plan.short_hook("um so you need to charge more"), "You need to charge more")
        long = plan.short_hook("one two three four five six seven eight nine ten")
        self.assertEqual(long, "One two three four five six seven eight...")

    def test_first_sentence_spans_lines_until_a_full_stop(self):
        kept = [{"text": "you need"}, {"text": "to charge more."}, {"text": "next"}]
        self.assertEqual(plan.first_sentence(kept), "you need to charge more.")


class PlanCommand(unittest.TestCase):
    """the real command on a fake transcript (no video work, so no ffmpeg needed)."""

    @classmethod
    def setUpClass(cls):
        cls.box = Sandbox("plan")
        cls.video = cls.box.inputs / "talking-head" / "clip.mp4"
        cls.video.write_bytes(b"")      # plan never opens the video
        fake_transcript(cls.box.work / "clip", cls.video,
                        "you need to charge um 700 pounds | you need to charge 700 pounds for usage rights | "
                        "step one know your rates | 70% of creators forget this | so write it down")

    @classmethod
    def tearDownClass(cls):
        cls.box.remove()

    def load(self):
        return json.loads((self.box.work / "clip" / "plan.json").read_text(encoding="utf-8"))

    def test_rough_cut(self):
        out = self.box.engine("plan", self.video, "--brand", "beth").stdout
        p = self.load()
        self.assertEqual((p["brand"], p["style"]), ("beth", "beth"))
        first, retake, step, stat, last = p["lines"]
        self.assertFalse(first["keep"])                      # earlier take, the later one is kept
        self.assertIn("earlier take", first["reason"])
        self.assertTrue(retake["keep"])
        self.assertEqual(retake["takes"], [1, 2])
        self.assertEqual((retake["treatment"], retake["motion"]), ("hook", "slow"))
        self.assertEqual((step["treatment"], step["step"]), ("step", 1))
        self.assertEqual((stat["treatment"], stat["stat"], stat["motion"]), ("stat pop", "70%", "punch"))
        self.assertNotEqual(last["motion"], "none")           # the ending never sits still
        um = next(i for i in first["words"] if "um" == fake_words(self.box)[i]["text"])
        self.assertIn(um, first["cut_words"])
        self.assertTrue(p["hook_text"].startswith("You need to charge 700 pounds"))
        self.assertIn("| 4 | yes |", out)
        self.assertTrue((self.box.work / "clip" / "plan.md").exists())

    def test_captions_only(self):
        self.box.engine("plan", self.video, "--brand", "beth", "--no-text")
        p = self.load()
        self.assertEqual(p["hook_text"], "")
        self.assertEqual({l["treatment"] for l in p["lines"]}, {"none"})

    def test_table_only_reprints_hand_edits(self):
        self.box.engine("plan", self.video, "--brand", "beth")
        p = self.load()
        p["lines"][4]["keep"] = False
        (self.box.work / "clip" / "plan.json").write_text(json.dumps(p), encoding="utf-8")
        out = self.box.engine("plan", self.video, "--table-only").stdout
        self.assertIn("| 5 | no |", out)

    def test_generic_style_and_unknown_style(self):
        self.box.engine("plan", self.video, "--brand", "beth", "--style", "editorial")
        self.assertEqual(self.load()["style"], "editorial")
        res = self.box.engine("plan", self.video, "--brand", "beth", "--style", "nope", check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("no style called 'nope'", res.stderr)


def fake_words(box):
    return json.loads((box.work / "clip" / "transcript.json").read_text(encoding="utf-8"))["words"]


if __name__ == "__main__":
    unittest.main()
