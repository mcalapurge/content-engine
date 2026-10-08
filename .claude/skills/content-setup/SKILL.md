---
name: content-setup
description: Set up (or repair) the editing engine on this computer so everything is installed and ready to use - homebrew, python, ffmpeg with captions, the python packages, the parakeet speech model and the starter sound effects - then check it and move on to the first brand. Use for "set up my editing engine", "install everything", "something's missing", "the setup check failed", or /content-setup.
argument-hint: "[nothing]"
---

# /content-setup - everything installed and ready

Talk casually and briefly, no jargon. Say what you're installing in plain words ("the video tool", "the speech model"), never paste install logs at them.

## 1. which computer

`uname` (or `ver` on windows). a mac → step 2. windows → step 4.

## 2. mac: run the setup script

```
bash scripts/setup_mac.sh
```

Run it in the background (the first run takes 10-20 minutes: ffmpeg and the speech model are big downloads) and tell them roughly how long. It installs only what's missing, so it's also the fix for anything broken; rerunning is always safe. It:

1. finds homebrew, or installs it
2. installs `python@3.13` and `ffmpeg-full` (homebrew's plain `ffmpeg` has no captions; the engine finds `ffmpeg-full` by itself, no PATH changes)
3. makes `.venv` (remakes it if it was built with a python older than 3.10) and installs `requirements.txt`
4. downloads the parakeet speech model (about 700MB) so the first edit doesn't wait
5. makes the starter sound effects (`python -m engine sfx`)
6. runs `python -m engine check_setup`

When it stops, read the end of its output:

| what you see | what to do |
|---|---|
| exits with "homebrew isn't installed, and its installer needs your password" | homebrew needs their mac password, which you can't type. ask them to open the Terminal app and paste `cd "<this folder>" && bash scripts/setup_mac.sh`, wait for it to finish, then tell you. (it asks for the password once, and may ask them to press return.) then rerun it yourself to check |
| "couldn't load the parakeet speech model" | no internet, or huggingface.co is blocked (a work network or vpn). once it's sorted, rerun the script |
| a `brew install` failing | read the error. most often it's xcode's command line tools: ask them to run `xcode-select --install` in the Terminal, then rerun |
| check_setup with a MISSING line | do what that line says, then rerun the script |
| "all good" | step 3 |

## 3. ready

Tell them in one line that it's all installed. Then:
- no brands yet (`.venv/bin/python -m engine brand list`): move straight on to the `content-new-brand` skill ("let's set up your first brand: have you got a brand guide file?")
- brands already there: tell them they can drop a clip in `inputs/talking-head/` and say "i have a new reel"

## 4. windows

There's no script yet; do it step by step, checking each:

1. python 3.10+: `py --version`. missing or older: `winget install Python.Python.3.12`, then they close and reopen claude code
2. ffmpeg 7+: `ffmpeg -version`. missing: `winget install Gyan.FFmpeg` (the full build, with captions), then they close and reopen claude code
3. `py -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`. a `.venv` from an older python: delete it and make it again
4. speech model: `.venv\Scripts\python -c "from engine.commands.transcribe import load_parakeet; load_parakeet()"`
5. `.venv\Scripts\python -m engine sfx`
6. `.venv\Scripts\python -m engine check_setup` until it says all good, then step 3
