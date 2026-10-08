#!/bin/bash
# one-command setup for a mac: everything the engine needs, ready to edit.
#
#   bash scripts/setup_mac.sh
#
# installs (only what's missing): homebrew, python 3.13, ffmpeg with captions (ffmpeg-full), the
# engine's python packages in .venv, the parakeet speech model and the starter sound effects, then runs
# the setup check. safe to run again any time: it skips what's already there and repairs what isn't.
#
# homebrew's installer needs your mac password, so the very first run has to be in the Terminal app
# (claude code can't type a password). after that claude can run this itself.

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_FORMULA="python@3.13"
step() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
done_() { printf "    %s\n" "$1"; }

if [[ "$(uname)" != "Darwin" ]]; then
  echo "this script is for macs. on windows, follow 'set up my editing engine' in CLAUDE.md"
  exit 1
fi

step "homebrew"
BREW=""
for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew "$(command -v brew || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then BREW="$candidate"; break; fi
done
if [[ -z "$BREW" ]]; then
  if [[ ! -t 0 ]]; then
    echo "homebrew isn't installed, and its installer needs your password."
    echo "open the Terminal app, go to this folder and run:  bash scripts/setup_mac.sh"
    exit 2
  fi
  echo "installing homebrew (it will ask for your mac password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$candidate" ]]; then BREW="$candidate"; break; fi
  done
fi
eval "$("$BREW" shellenv)"
done_ "homebrew ready ($(brew --prefix))"

step "python and ffmpeg"
for formula in "$PYTHON_FORMULA" ffmpeg-full; do
  if brew list --versions "$formula" >/dev/null 2>&1; then
    done_ "$formula already installed"
  else
    brew install "$formula"
  fi
done
PYTHON="$(brew --prefix "$PYTHON_FORMULA")/bin/python3.13"
done_ "ffmpeg: $("$(brew --prefix ffmpeg-full)/bin/ffmpeg" -version | head -1)"

step "the engine's python packages (.venv)"
if [[ -x .venv/bin/python ]] && ! .venv/bin/python -c "import sys; sys.exit(sys.version_info < (3, 10))"; then
  echo "    .venv was made with an older python, making it again"
  rm -rf .venv
fi
[[ -x .venv/bin/python ]] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
done_ "installed: $(.venv/bin/python --version)"

step "speech model (parakeet, about 700MB the first time)"
.venv/bin/python -c "from engine.commands.transcribe import load_parakeet; load_parakeet()"
done_ "ready"

step "starter sound effects"
.venv/bin/python -m engine sfx

step "setup check"
.venv/bin/python -m engine check_setup

echo "next: open claude code in this folder and say 'set up a new brand for <name>'"
echo "      (or 'i have a new reel' once a brand is set up)"
