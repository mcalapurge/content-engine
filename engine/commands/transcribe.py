"""step 1: transcribe a clip with word-level timings.

usage: python -m engine transcribe [video] [--model small]
"""
import argparse
import time
from pathlib import Path

from engine.core.common import die, find_bin, resolve_video, run, save_json, video_info, work_dir_for

# a disfluent prompt nudges whisper into keeping ums and false starts,
# which we need so the planner can cut them
FILLER_PROMPT = "Umm, so, uh, I was like, erm... okay. Hmm, let me start again. So the thing is,"


def transcribe_file(video, out_dir, model_name="small", language="en"):
    info = video_info(video)
    if not info["has_audio"]:
        die(f"{Path(video).name} has no audio track, so there's nothing to transcribe")
    audio = Path(out_dir) / "audio.wav"
    run([find_bin("ffmpeg"), "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="auto", compute_type="int8")
    segments, meta = model.transcribe(str(audio), language=language, word_timestamps=True,
                                      initial_prompt=FILLER_PROMPT, vad_filter=False,
                                      condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"text": text, "start": round(w.start, 3), "end": round(w.end, 3),
                              "prob": round(w.probability, 3)})
    data = {"source": str(video), "duration": info["duration"], "width": info["width"],
            "height": info["height"], "language": meta.language, "words": words}
    save_json(Path(out_dir) / "transcript.json", data)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--model", default="small",
                    help="tiny / base / small / medium / large-v3 (bigger = slower, more accurate)")
    args = ap.parse_args()
    video = resolve_video(args.video)
    wd = work_dir_for(video)
    print(f"[engine] transcribing {video.name} with the '{args.model}' model (first run downloads it)...")
    t0 = time.time()
    data = transcribe_file(video, wd, args.model)
    print(f"[engine] done in {time.time() - t0:.0f}s - {len(data['words'])} words")
    print(f"[engine] saved {wd / 'transcript.json'}")


if __name__ == "__main__":
    main()
