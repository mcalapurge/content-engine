"""the other commands' logic: b-roll matching, text reels, vlog scoring, batch splitting, the brand
command and the layout migration. none of these need ffmpeg."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


from engine.commands import batch, broll, textreel, vlog
from tests.support import ROOT, Sandbox, fake_transcript, words


class BrollMatching(unittest.TestCase):
    def test_tokens_drop_filler_and_stem_plurals(self):
        self.assertEqual(broll.tokens("I'm typing the invoices and emails"), {"typ", "invoic", "email"})

    def test_match_places_clips_by_meaning_within_budget(self):
        box = Sandbox("broll")
        try:
            video = box.inputs / "talking-head" / "clip.mp4"
            video.write_bytes(b"")
            fake_transcript(box.work / "clip", video, "the real price of ugc | send the invoice by email | "
                            "then follow up on the invoice | pack the camera bag | and go film")
            box.engine("plan", video, "--brand", "beth")
            library = {"clips": [
                {"file": "brands/beth/broll/laptop.mp4", "tags": ["laptop"], "description": "typing an email invoice",
                 "good_for": "invoices, admin"},
                {"file": "brands/beth/broll/camera.mp4", "tags": ["camera"], "description": "packing a camera bag",
                 "good_for": "filming days"}]}
            (box.brands / "beth" / "broll" / "library.json").write_text(json.dumps(library), encoding="utf-8")
            box.engine("broll", "match", video, "--max-share", "0.5")
            lines = json.loads((box.work / "clip" / "plan.json").read_text(encoding="utf-8"))["lines"]
            placed = {l["id"]: l["broll"]["file"] for l in lines if l.get("broll")}
            self.assertNotIn(1, placed)                                   # the hook stays on camera
            self.assertEqual(sorted(placed.values()), sorted(c["file"] for c in library["clips"]))   # no reuse
            self.assertEqual(placed.get(4), "brands/beth/broll/camera.mp4")
            self.assertLessEqual(len(placed), 2)                          # 50% of 5 kept lines
        finally:
            box.remove()


class TextReels(unittest.TestCase):
    def test_wrap_balances_lines_and_keeps_pairs_together(self):
        lines = textreel.wrap("I charged £150 + £700 for the exact same video last month")
        self.assertTrue(all(len(l) <= textreel.LINE_CHARS for l in lines), lines)
        self.assertTrue(any("£150 + £700" in l for l in lines), lines)
        self.assertEqual(textreel.wrap("short"), ["short"])

    def test_reading_time(self):
        hook, middle = textreel.beat_lengths(["a b", "a b c d e f g h i j k l m n"])
        self.assertEqual(hook, 2.4)                                       # minimum for a hook
        self.assertEqual(middle, 3.8)                                     # capped
        snapped = textreel.beat_lengths(["a b c d"], bpm=120)[0]
        self.assertAlmostEqual(snapped / 0.5, round(snapped / 0.5))      # whole beats

    def test_numbers_and_shouty_words_get_the_accent(self):
        text = textreel.ass_text("I made £700 in ONE week", {"highlight_colour": "#FF0000"})
        self.assertIn("{\\c&H000000FF&}£700", text)
        self.assertIn("{\\c&H000000FF&}ONE", text)
        self.assertNotIn("{\\c&H000000FF&}I ", text)

    def test_reads_xlsx_with_shared_and_inline_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.xlsx"
            write_xlsx(path, [["#", "type", "beat 1 (hook)", "beat 2"], ["1", "hot take", "rates & fees", "inline"]])
            rows = textreel.read_xlsx(path)
        self.assertEqual(rows, [{"#": "1", "type": "hot take", "beat 1 (hook)": "rates & fees", "beat 2": "inline"}])


class Vlog(unittest.TestCase):
    def test_frame_score_rewards_sharp_bright_moving_frames(self):
        good = vlog.frame_score({"blur": 2, "yavg": 120, "ydif": 4})
        dark = vlog.frame_score({"blur": 2, "yavg": 5, "ydif": 4})
        shaky = vlog.frame_score({"blur": 2, "yavg": 120, "ydif": 40})
        self.assertGreater(good, dark)
        self.assertGreater(good, shaky)
        self.assertTrue(0 <= shaky <= good <= 1)

    def test_best_windows_find_the_strong_stretch_without_overlap(self):
        frames = [{"t": t / 5, "blur": 7.5, "yavg": 120, "ydif": 0} for t in range(50)]
        for f in frames[25:40]:
            f.update(blur=2, ydif=4)
        picks = vlog.best_windows(frames, 10.0, length=2.5, count=2)
        self.assertTrue(4.6 <= picks[0]["start"] <= 5.4 and picks[0]["score"] > 0.95, picks)
        a, b = picks
        self.assertFalse(a["start"] < b["start"] + b["length"] and b["start"] < a["start"] + a["length"])

    def test_source_span_accounts_for_speed_ramps_and_freezes(self):
        self.assertAlmostEqual(vlog.source_span({"dur": 2, "speed": 1.5, "ramp": False, "freeze": 0.5}), 2.25)
        self.assertAlmostEqual(vlog.source_span({"dur": 2, "speed": 1, "ramp": True}), 2 * 0.4 * 2.5 + 2 * 0.6 * 0.5)


class BatchSplit(unittest.TestCase):
    def test_splits_at_big_pauses_or_into_a_set_count(self):
        w = words("hook one more words | hook two more | hook three")
        for word in w[4:]:                     # make the first pause the biggest
            word["start"] += 1.0
            word["end"] += 1.0
        self.assertEqual(batch.find_sections(w, gap=1.0, count=None), [(0, 3), (4, 6), (7, 8)])
        self.assertEqual(batch.find_sections(w, gap=5.0, count=None), [(0, 8)])
        self.assertEqual(batch.find_sections(w, gap=5.0, count=2), [(0, 3), (4, 8)])
        self.assertEqual(batch.mmss(75.25), "1:15.2")


class BrandCommand(unittest.TestCase):
    def test_new_list_and_show(self):
        box = Sandbox("brand-cmd")
        try:
            box.engine("brand", "new", "mia", "--style", "playful")
            mia = box.brands / "mia"
            self.assertEqual(json.loads((mia / "style.json").read_text(encoding="utf-8")),
                             json.loads((ROOT / "assets" / "styles" / "playful.json").read_text(encoding="utf-8")))
            for f in ("brand.md", "effects.md", "grade.json", "broll/library.json"):
                self.assertTrue((mia / f).exists(), f)
            listing = box.engine("brand", "list").stdout
            self.assertIn("mia", listing)
            self.assertIn("beth", listing)
            self.assertIn("brands/mia/brand.md", box.engine("brand", "show", "mia").stdout.replace("\\", "/"))
            for bad in (("new", "mia"), ("new", "Mia Smith"), ("new", "zed", "--style", "nope")):
                self.assertNotEqual(box.engine("brand", *bad, check=False).returncode, 0, bad)
            # with two brands, a command that needs one asks instead of guessing
            res = box.engine("contrast", check=False)
            self.assertIn("which brand is this for?", res.stderr)
            self.assertIn("ok", box.engine("contrast", "--brand", "beth").stdout)
        finally:
            box.remove()


class Migration(unittest.TestCase):
    """scripts/migrate_layout.py on a copy of the old flat layout."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "migrate_layout.py", self.root / "scripts")
        files = {"input/README.txt": "old readme", "input/clip.MOV": "", "input_vlog/trip/a.mov": "",
                 "broll/products/x.mp4": "", "music/song.mp3": "", "brand/brand.md": "guide",
                 "inputs/talking-head/README.txt": "new readme",
                 "work/clip/plan.json": json.dumps({"style": "editorial", "lines": [{"broll": {"file": "broll/products/x.mp4"}}],
                                                   "sound": {"music": "music/song.mp3"}}),
                 "work/vlog-trip/plan.json": json.dumps({"folder": "input_vlog/trip", "pieces": []})}
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root)

    def migrate(self, *args):
        return subprocess.run([sys.executable, "scripts/migrate_layout.py", "--brand", "beth", *args], cwd=self.root,
                              capture_output=True, text=True)

    def test_dry_run_changes_nothing(self):
        res = self.migrate()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("run again with --apply", res.stdout)
        self.assertTrue((self.root / "input" / "clip.MOV").exists())

    def test_apply_moves_files_rewrites_paths_and_stamps_the_brand(self):
        res = self.migrate("--apply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for rel in ("inputs/talking-head/clip.MOV", "inputs/vlog/trip/a.mov", "brands/beth/broll/products/x.mp4",
                    "assets/music/song.mp3", "brands/beth/brand.md"):
            self.assertTrue((self.root / rel).exists(), rel)
        plan = json.loads((self.root / "work/clip/plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["brand"], "beth")
        self.assertEqual(plan["lines"][0]["broll"]["file"], "brands/beth/broll/products/x.mp4")
        self.assertEqual(plan["sound"]["music"], "assets/music/song.mp3")
        vlog_plan = json.loads((self.root / "work/vlog-trip/plan.json").read_text(encoding="utf-8"))
        self.assertEqual((vlog_plan["brand"], vlog_plan["folder"]), ("beth", "inputs/vlog/trip"))
        self.assertEqual((self.root / "inputs/talking-head/README.txt").read_text(encoding="utf-8"), "new readme")
        self.assertIn("nothing to move", self.migrate("--apply").stdout)       # running it twice is harmless

    def test_a_real_clash_stops_everything(self):
        (self.root / "brands/beth/broll/products").mkdir(parents=True)
        (self.root / "brands/beth/broll/products/x.mp4").write_text("different", encoding="utf-8")
        res = self.migrate("--apply")
        self.assertEqual(res.returncode, 1)
        self.assertIn("CLASH broll/products/x.mp4", res.stdout)
        self.assertTrue((self.root / "input/clip.MOV").exists())              # nothing moved
        self.assertNotIn("brand", json.loads((self.root / "work/clip/plan.json").read_text(encoding="utf-8")))


def write_xlsx(path, rows):
    """a minimal xlsx: first row as shared strings, the rest as inline strings."""
    shared = rows[0]
    sst = "".join(f"<si><t>{v.replace('&', '&amp;')}</t></si>" for v in shared)
    cells = []
    for r, row in enumerate(rows, 1):
        if r == 1:
            cs = "".join(f'<c r="{chr(65 + i)}{r}" t="s"><v>{i}</v></c>' for i in range(len(row)))
        else:
            cs = "".join(f'<c r="{chr(65 + i)}{r}" t="inlineStr"><is><t>{v.replace("&", "&amp;")}</t></is></c>'
                         for i, v in enumerate(row))
        cells.append(f'<row r="{r}">{cs}</row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="x">{sst}</sst>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="x"><sheetData>{"".join(cells)}</sheetData></worksheet>')


if __name__ == "__main__":
    unittest.main()
