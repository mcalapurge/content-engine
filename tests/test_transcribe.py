"""real speech-to-text with whisper's tiny model on a synthetic voice. slow (downloads the model) so
it only runs when RUN_TRANSCRIBE=1, and needs faster-whisper plus a speech synthesiser
(espeak-ng on linux, `say` on a mac)."""
import json
import os
import shutil
import subprocess
import unittest

from tests.support import Sandbox, ffmpeg, needs_ffmpeg

SENTENCE = "You need to charge seven hundred pounds for usage rights. Send the invoice and follow up every time."


def synthesiser():
    if shutil.which("espeak-ng"):
        return lambda wav: subprocess.run(["espeak-ng", "-s", "150", "-w", str(wav), SENTENCE], check=True)
    if shutil.which("say"):
        return lambda wav: subprocess.run(["say", "-o", str(wav), "--data-format=LEI16@22050", SENTENCE], check=True)
    return None


@unittest.skipUnless(os.environ.get("RUN_TRANSCRIBE") == "1", "set RUN_TRANSCRIBE=1 to run (downloads a whisper model)")
@needs_ffmpeg
class Transcribe(unittest.TestCase):
    def test_tiny_model_hears_the_words_in_order(self):
        speak = synthesiser()
        if speak is None:
            self.skipTest("no espeak-ng or say to make a test voice")
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            self.skipTest("faster-whisper isn't installed")
        box = Sandbox("transcribe", copy_brands=False)
        try:
            wav = box.dir / "voice.wav"
            speak(wav)
            video = box.inputs / "talking-head" / "voice.mp4"
            ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x568:r=30", "-i", wav, "-shortest",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video)
            box.engine("transcribe", video, "--model", "tiny")
            data = json.loads((box.work / "voice" / "transcript.json").read_text(encoding="utf-8"))
            heard = " ".join(w["text"] for w in data["words"]).lower()
            for word in ("charge", "usage", "rights", "invoice", "follow"):
                self.assertIn(word, heard)
            starts = [w["start"] for w in data["words"]]
            self.assertEqual(starts, sorted(starts))
            self.assertTrue(all(w["end"] >= w["start"] for w in data["words"]))
            self.assertEqual((data["width"], data["height"]), (320, 568))
        finally:
            box.remove()


if __name__ == "__main__":
    unittest.main()
