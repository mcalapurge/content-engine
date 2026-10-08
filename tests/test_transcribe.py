"""speech-to-text. the logic tests (pieces, word ends, confidence) run everywhere with a stand-in for the
model. the real one, parakeet on a synthetic voice, is slow (downloads the model) so it only runs when
RUN_TRANSCRIBE=1, and needs onnx-asr plus a speech synthesiser (espeak-ng on linux, `say` on a mac)."""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from engine.commands import transcribe as tr
from tests.support import Sandbox, ffmpeg, needs_ffmpeg

SENTENCE = "You need to charge seven hundred pounds for usage rights. Send the invoice and follow up every time."


def tone_and_gaps(*parts):
    """samples at 16kHz: ("tone", secs) is speech-loud, ("gap", secs) is near silent."""
    out = []
    for kind, secs in parts:
        n = int(secs * tr.SAMPLE_RATE)
        t = np.arange(n) / tr.SAMPLE_RATE
        out.append(0.3 * np.sin(2 * np.pi * 220 * t) if kind == "tone" else 0.001 * np.ones(n))
    return np.concatenate(out).astype(np.float32)


class Pieces(unittest.TestCase):
    def test_short_clips_go_in_whole(self):
        db = tr.loudness(tone_and_gaps(("tone", 10)))
        self.assertEqual(tr.chunk_bounds(db), [(0.0, 10.0)])

    def test_long_clips_are_cut_in_the_quiet(self):
        # 40s talking, a pause at 40-40.5s, 30s more: the cut lands in the pause, not mid word
        db = tr.loudness(tone_and_gaps(("tone", 40), ("gap", 0.5), ("tone", 30)))
        bounds = tr.chunk_bounds(db)
        self.assertEqual(len(bounds), 2)
        self.assertTrue(40.0 <= bounds[0][1] <= 40.5, bounds)
        self.assertEqual(bounds[0][1], bounds[1][0])
        self.assertAlmostEqual(bounds[-1][1], 70.5)

    def test_quiet_is_relative_to_the_room(self):
        noisy = tone_and_gaps(("tone", 1), ("gap", 0.3), ("tone", 1)) + 0.02     # a loud noise floor
        runs = tr.quiet_runs(tr.loudness(noisy))
        self.assertEqual(len(runs), 1)
        self.assertAlmostEqual(runs[0][0], 1.0, delta=0.02)
        self.assertAlmostEqual(runs[0][1], 1.3, delta=0.02)


class Words(unittest.TestCase):
    def test_pieces_join_into_words_with_punctuation(self):
        tokens = [" Char", "ge", " seven", " hundred", ",", " pounds", "."]
        times = [0.0, 0.08, 0.4, 0.8, 1.04, 1.2, 1.44]
        words = tr.words_from_tokens(tokens, times, [math.log(0.9)] * 7, offset=10.0)
        self.assertEqual([w["text"].strip() for w in words], ["Charge", "seven", "hundred,", "pounds."])
        self.assertEqual((words[0]["start"], words[0]["last"]), (10.0, 10.08))
        self.assertEqual(words[2]["last"], 10.8)                        # the comma isn't a sound

    def test_a_word_ends_at_the_pause_or_where_the_next_begins(self):
        words = tr.words_from_tokens([" one", " two", " three"], [0.0, 0.3, 2.0], [0.0, math.log(0.5), 0.0], 0.0)
        out = tr.add_word_ends(words, quiet=[(0.5, 1.9), (2.6, 3.0)], duration=3.0)
        self.assertEqual([w["end"] for w in out], [0.3, 0.5, 2.6])     # no pause / pause / last word
        self.assertEqual([w["prob"] for w in out], [1.0, 0.5, 1.0])

    def test_a_word_never_runs_on_forever_or_past_the_next(self):
        words = tr.words_from_tokens([" so", " then"], [0.0, 5.0], [0.0, 0.0], 0.0)
        out = tr.add_word_ends(words, quiet=[], duration=5.05)
        self.assertEqual(out[0]["end"], tr.WORD_TAIL_MAX)               # no quiet found: capped
        self.assertEqual(out[1]["end"], 5.05)                           # never past the end of the clip
        same = tr.words_from_tokens([" a", " b"], [1.0, 1.0], [0.0, 0.0], 0.0)
        self.assertEqual(tr.add_word_ends(same, [], 2.0)[0]["end"], 1.0)

    def test_a_late_full_stop_or_a_short_last_sound_still_finds_the_pause(self):
        # "rights." then "Send": the full stop is timed inside the pause, which starts 0.05s after "rights"
        words = tr.words_from_tokens([" rights", ".", " Send"], [1.0, 1.4, 1.8], [0.0, 0.0, 0.0], 0.0)
        out = tr.add_word_ends(words, quiet=[(1.05, 1.75)], duration=2.5)
        self.assertEqual(out[0]["text"], "rights.")
        self.assertEqual(out[0]["end"], 1.08)                           # at least WORD_MIN long
        self.assertGreater(out[1]["start"] - out[0]["end"], 0.6)


class WithStandInModel(unittest.TestCase):
    """the glue: audio in, pieces to the model, words out with times on the clip's own clock."""

    def test_pieces_are_heard_separately_and_put_back_in_place(self):
        heard = []

        class Model:
            def with_timestamps(self):
                return self

            def recognize(self, samples, sample_rate):
                heard.append(len(samples) / sample_rate)
                return types.SimpleNamespace(tokens=[" hi", " there"], timestamps=[0.5, 1.0],
                                             logprobs=[0.0, 0.0])

        fake = types.SimpleNamespace(load_model=mock.Mock(return_value=Model()))
        samples = tone_and_gaps(("tone", 40), ("gap", 0.5), ("tone", 20))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"onnx_asr": fake}):
            audio = Path(tmp) / "audio.wav"
            with wave.open(str(audio), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(tr.SAMPLE_RATE)
                f.writeframes((samples * 32767).astype("<i2").tobytes())
            words = tr.transcribe_parakeet(audio, 60.5)
        fake.load_model.assert_called_once_with(tr.PARAKEET, quantization="int8")
        self.assertEqual(len(heard), 2)
        self.assertEqual([w["text"] for w in words], ["hi", "there", "hi", "there"])
        second = words[2]["start"] - 0.5
        self.assertTrue(40.0 <= second <= 40.5, words)                  # offset by where the piece starts
        self.assertEqual([w["start"] for w in words], sorted(w["start"] for w in words))

    def test_unknown_model_names_are_refused(self):
        with self.assertRaises(SystemExit):
            tr.transcribe_file("clip.mov", ".", "large")


def synthesiser():
    if shutil.which("espeak-ng"):
        return lambda wav: subprocess.run(["espeak-ng", "-s", "150", "-w", str(wav), SENTENCE], check=True)
    if shutil.which("say"):
        return lambda wav: subprocess.run(["say", "-o", str(wav), "--data-format=LEI16@22050", SENTENCE], check=True)
    return None


@unittest.skipUnless(os.environ.get("RUN_TRANSCRIBE") == "1", "set RUN_TRANSCRIBE=1 to run (downloads parakeet)")
@needs_ffmpeg
class Transcribe(unittest.TestCase):
    def test_parakeet_hears_the_words_in_order(self):
        speak = synthesiser()
        if speak is None:
            self.skipTest("no espeak-ng or say to make a test voice")
        try:
            import onnx_asr  # noqa: F401
        except ImportError:
            self.skipTest("onnx-asr isn't installed")
        box = Sandbox("transcribe", copy_brands=False)
        try:
            wav = box.dir / "voice.wav"
            speak(wav)
            video = box.inputs / "talking-head" / "voice.mp4"
            ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x568:r=30", "-i", wav, "-shortest",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video)
            box.engine("transcribe", video)
            data = json.loads((box.work / "voice" / "transcript.json").read_text(encoding="utf-8"))
            print("\n  heard:", " ".join(f'{w["text"]}[{w["start"]}-{w["end"]}]' for w in data["words"]))
            heard = " ".join(w["text"] for w in data["words"]).lower()
            for word in ("charge", "usage", "rights", "invoice", "follow"):
                self.assertIn(word, heard)
            starts = [w["start"] for w in data["words"]]
            self.assertEqual(starts, sorted(starts))
            self.assertTrue(all(w["end"] >= w["start"] for w in data["words"]))
            self.assertTrue(all(0 < w["prob"] <= 1 for w in data["words"]))
            self.assertEqual((data["width"], data["height"], data["model"]), (320, 568, "parakeet"))
            # the full stop after "rights" is a real pause, so the words either side of it don't touch
            i = next(n for n, w in enumerate(data["words"]) if w["text"].lower().startswith("rights"))
            self.assertGreater(data["words"][i + 1]["start"] - data["words"][i]["end"], 0.1)
        finally:
            box.remove()


if __name__ == "__main__":
    unittest.main()
