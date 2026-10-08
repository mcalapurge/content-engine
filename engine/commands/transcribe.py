"""step 1: transcribe a clip with word-level timings.

usage: python -m engine transcribe [video] [--model parakeet]

parakeet (nvidia's parakeet-tdt-0.6b-v2, english only) runs on this computer through onnx-asr; the first
run downloads it (about 700MB). a whisper size (tiny / base / small / medium / large-v3) uses faster-whisper
instead, the engine's older speech-to-text, if it's installed (pip install faster-whisper).
"""
import argparse
import bisect
import math
import time
import wave
from pathlib import Path

import numpy as np

from engine.core.common import die, find_bin, resolve_video, run, save_json, video_info, work_dir_for

PARAKEET = "nemo-parakeet-tdt-0.6b-v2"
WHISPER_SIZES = ("tiny", "base", "small", "medium", "large-v3")
SAMPLE_RATE = 16000

CHUNK_SECS = 45          # parakeet hears at most this much audio at once...
CHUNK_SEARCH = 15        # ...cut at the quietest moment in the last this-many seconds of each piece
FRAME = 0.01             # loudness is measured in 10ms frames
QUIET_SMOOTH = 10        # frames averaged when looking for the quietest moment to cut a piece
QUIET_LEVEL = 0.3        # quiet = below this fraction of the way from the noise floor to speech level
QUIET_MIN = 0.06         # a word ends where at least this much quiet starts
WORD_MIN = 0.08          # parakeet's time step: every word lasts at least this long
WORD_TAIL_MAX = 0.8      # a word's last sound lasts at most this long when no quiet follows it

# a disfluent prompt nudges whisper into keeping ums and false starts,
# which we need so the planner can cut them
FILLER_PROMPT = "Umm, so, uh, I was like, erm... okay. Hmm, let me start again. So the thing is,"


def read_wav(path):
    """16-bit mono wav -> float samples in -1..1"""
    with wave.open(str(path), "rb") as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32) / 32768


def loudness(samples):
    """dB per FRAME of audio"""
    size = int(FRAME * SAMPLE_RATE)
    frames = samples[:len(samples) // size * size].reshape(-1, size)
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-5)


def chunk_bounds(db):
    """[(start, end)] seconds: pieces of at most CHUNK_SECS, each cut at the quietest moment near its end,
    so a word is never split between two pieces."""
    total = len(db) * FRAME
    smooth = np.convolve(db, np.ones(QUIET_SMOOTH) / QUIET_SMOOTH, mode="same")
    bounds, start = [], 0.0
    while total - start > CHUNK_SECS:
        lo, hi = int((start + CHUNK_SECS - CHUNK_SEARCH) / FRAME), int((start + CHUNK_SECS) / FRAME)
        cut = (lo + int(np.argmin(smooth[lo:hi]))) * FRAME
        bounds.append((start, cut))
        start = cut
    return bounds + [(start, total)]


def quiet_starts(db):
    """start times of every quiet stretch of at least QUIET_MIN. quiet is measured against this clip's own
    noise floor and speech level, so a noisy room still has pauses."""
    floor, speech = np.percentile(db, 10), np.percentile(db, 90)
    quiet = np.concatenate([[False], db < floor + QUIET_LEVEL * (speech - floor), [False]])
    edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
    need = round(QUIET_MIN / FRAME)
    return [start * FRAME for start, end in zip(edges[::2], edges[1::2]) if end - start >= need]


def words_from_tokens(tokens, times, logprobs, offset):
    """parakeet's word pieces -> words with a start, the start of their last piece and a confidence.
    a piece starting with a space begins a new word; punctuation and endings join the word before."""
    words = []
    for token, at, logprob in zip(tokens, times, logprobs):
        if token.startswith(" ") or not words:
            words.append({"text": "", "start": offset + at, "last": offset + at, "logprobs": []})
        word = words[-1]
        word["text"] += token
        word["last"] = offset + at
        word["logprobs"].append(logprob)
    return [w for w in words if w["text"].strip()]


def add_word_ends(words, quiet, duration):
    """parakeet only times where each piece starts. a word ends where the next quiet stretch starts, if
    one comes before the next word (a pause), else where the next word starts (no pause between them)."""
    out = []
    for i, w in enumerate(words):
        limit = words[i + 1]["start"] if i + 1 < len(words) else duration
        earliest, latest = w["last"] + WORD_MIN, min(limit, w["last"] + WORD_TAIL_MAX)
        n = bisect.bisect_left(quiet, earliest)
        end = quiet[n] if n < len(quiet) and quiet[n] < latest else latest
        end = min(max(end, w["start"] + WORD_MIN), limit)
        prob = math.exp(sum(w["logprobs"]) / len(w["logprobs"]))
        out.append({"text": w["text"].strip(), "start": round(w["start"], 3), "end": round(max(end, w["start"]), 3),
                    "prob": round(prob, 3)})
    return out


def transcribe_parakeet(audio, duration):
    try:
        import onnx_asr
    except ImportError:
        die("parakeet isn't installed. run: pip install -r requirements.txt")
    samples = read_wav(audio)
    db = loudness(samples)
    if not len(db):
        return []
    model = onnx_asr.load_model(PARAKEET, quantization="int8").with_timestamps()
    words = []
    for start, end in chunk_bounds(db):
        piece = model.recognize(samples[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)], sample_rate=SAMPLE_RATE)
        tokens = piece.tokens or []
        words += words_from_tokens(tokens, piece.timestamps or [], piece.logprobs or [0.0] * len(tokens), start)
    return add_word_ends(words, quiet_starts(db), duration)


def transcribe_whisper(audio, size):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die("whisper models need faster-whisper. run: pip install faster-whisper (or leave out --model for parakeet)")
    model = WhisperModel(size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language="en", word_timestamps=True, initial_prompt=FILLER_PROMPT,
                                   vad_filter=False, condition_on_previous_text=False)
    return [{"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
             "prob": round(w.probability, 3)}
            for seg in segments for w in seg.words or [] if w.word.strip()]


def transcribe_file(video, out_dir, model_name="parakeet"):
    if model_name != "parakeet" and model_name not in WHISPER_SIZES:
        die(f"unknown model '{model_name}': use parakeet or a whisper size ({', '.join(WHISPER_SIZES)})")
    info = video_info(video)
    if not info["has_audio"]:
        die(f"{Path(video).name} has no audio track, so there's nothing to transcribe")
    audio = Path(out_dir) / "audio.wav"
    run([find_bin("ffmpeg"), "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-c:a", "pcm_s16le", str(audio)])
    words = (transcribe_parakeet(audio, info["duration"]) if model_name == "parakeet"
             else transcribe_whisper(audio, model_name))
    data = {"source": str(video), "duration": info["duration"], "width": info["width"],
            "height": info["height"], "language": "en", "model": model_name, "words": words}
    save_json(Path(out_dir) / "transcript.json", data)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--model", default="parakeet",
                    help="parakeet (default, english) or a whisper size: " + " / ".join(WHISPER_SIZES)
                         + " (needs faster-whisper)")
    args = ap.parse_args()
    video = resolve_video(args.video)
    wd = work_dir_for(video)
    print(f"[engine] transcribing {video.name} with {args.model} (the first run downloads the model)...")
    t0 = time.time()
    data = transcribe_file(video, wd, args.model)
    print(f"[engine] done in {time.time() - t0:.0f}s - {len(data['words'])} words")
    print(f"[engine] saved {wd / 'transcript.json'}")


if __name__ == "__main__":
    main()
