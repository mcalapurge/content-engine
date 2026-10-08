# b-roll montage (vlog edit): a folder of clips → ~30s edit

No talking. A folder of clips becomes a ~30s edit she adds a voiceover (and maybe her own music) to later. Prefix engine commands with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && `.

## her style for these (in brand.md, files win)

- ~30 seconds
- **very fast start**: a teaser of 4-frame snaps (0.13s each) from ~16 different clips, done in ~2s, then short opening shots (~0.7-0.9s)
- **no transitions at all**: no flash, whip, dip. just cuts
- **no speed changes**: no speed ramps, no slow-mo, no fast-forward. freeze frames are fine
- **lots of jump cuts** (same clip, skip ~0.25s ahead, switch between wide and tighter framing) alternating with **slow zooms**
- order = most engaging, not chronological: open strong, group scenes into a little story (morning → work → shoot → out → evening), never the same scene twice in a row, end on a satisfying shot (eg a laugh that echoes the teaser)
- keep the natural sound
- music: only if she gives a track (then cuts land on the beat). otherwise no music
- grade: ask. last time she said "they don't need colour grading" (`--no-grade`)

## steps

1. **analyse** (slow for raw 4K iPhone clips, run in background for big folders):
   ```
   .venv/bin/python engine/vlog.py analyse input_vlog/<folder>     # or input_vlog if clips are loose in the folder
   ```
   Measures sharpness, brightness, movement 5x a second, finds the best stretches, writes `work/vlog-<folder>/clips.json` and frame sheets in `sheets/`. NOTE: re-running analyse overwrites descriptions in clips.json.
2. **look at every sheet** (combine them into a few overview images to save time) and write a one-line `description` per clip in clips.json: what happens and which moment is best.
3. **check the audio**: clips exported from apps often have silent audio tracks. if every clip measures about -91 dB, tell her there's no natural sound to keep.
   ```
   ffmpeg -hide_banner -i "<clip>" -af volumedetect -vn -f null - 2>&1 | grep mean_volume
   ```
4. **plan**: either the auto plan as a starting point
   ```
   .venv/bin/python engine/vlog.py plan input_vlog/<folder> [--music music/<track>] [--length 30]
   ```
   or (usually better) write `work/vlog-<folder>/plan.json` by hand from the sheets. pieces:

   | field | meaning |
   |---|---|
   | `kind` | `teaser` or `shot` |
   | `clip` | path from project root |
   | `start` / `dur` | seconds into the clip / seconds on screen (must fit inside the clip) |
   | `speed`, `ramp` | keep 1.0 / false (she doesn't want speed changes) |
   | `transition` | keep `cut` |
   | `push` | slow zoom in |
   | `zoom` | static framing: 1.0 wide, 1.15 tighter. a jump cut = two pieces from the same clip, ~0.25s apart, one at 1.0 and one at 1.15 |
   | `freeze` | seconds to hold the last frame (counts inside `dur`) |
   | `nat` | false to mute that piece |
   | `note` | what it is (shows in the table) |

   Top level: `music`, `music_start`, `bpm`, `music_volume` (0.8), `nat_volume` (1.0 without music, 0.5 with), `teaser_nat`.
   Teaser pieces: `dur` = 4/30, start ~0.07s before the moment you want.
5. **show her** the table + storyboard (one frame per piece):
   ```
   .venv/bin/python engine/vlog.py table input_vlog/<folder>     # rebuilds plan.md + work/vlog-<folder>/storyboard.jpg
   ```
   Send the storyboard image and a section-by-section summary. Wait for "go".
6. **render**:
   ```
   .venv/bin/python engine/vlog.py render input_vlog/<folder> [--no-grade] [--draft]
   ```
   Output `output/vlog-<folder>.mp4`; with music also `_no_music.mp4` (natural sound only, for her own voiceover + music in CapCut).
7. **check** (checks.md): length, freezes, frames at jump cuts, cut timing vs beats if music.

## feedback history (already the defaults)

- "I really don't like the flashy transitions" → no transitions
- "speed up the start, more jump cuts, slow zooms" → 4-frame teaser, jump pairs + pushes
- "don't speed things up" → no ramps
