# b-roll montage (vlog edit): a folder of clips → a short edit

No talking. A folder of clips becomes a short edit they add a voiceover (and maybe their own music) to later. On a mac, prefix with `eval "$(/opt/homebrew/bin/brew shellenv zsh)" && ` if ffmpeg isn't found.

## the brand's style for these

Read the brand's brand.md ("vlog" / b-roll edit defaults) first: length, how fast the start is, transitions or none, speed changes or none, jump cuts vs slow zooms, natural sound, music, grade. Generic fallback when the brand doesn't say:

- ~30 seconds, a fast start (a quick-fire teaser of very short snaps from many clips, then short opening shots)
- order = most engaging, not chronological: open strong, group scenes into a little story, never the same scene twice in a row, end on a satisfying shot
- jump cuts (same clip, skip ~0.25s ahead, switch between wide and tighter framing) alternating with slow zooms
- keep the natural sound. music only if they give a track (then cuts land on the beat)
- grade: ask if they didn't say

## steps

1. **analyse** (slow for raw 4K iPhone clips, run in background for big folders):
   ```
   .venv/bin/python -m engine vlog analyse inputs/vlog/<folder>     # or inputs/vlog if clips are loose in the folder
   ```
   Measures sharpness, brightness, movement 5x a second, finds the best stretches, writes `work/vlog-<folder>/clips.json` and frame sheets in `sheets/`. NOTE: re-running analyse overwrites descriptions in clips.json.
2. **look at every sheet** (combine them into a few overview images to save time) and write a one-line `description` per clip in clips.json: what happens and which moment is best.
3. **check the audio**: clips exported from apps often have silent audio tracks. if every clip measures about -91 dB, tell them there's no natural sound to keep.
   ```
   ffmpeg -hide_banner -i "<clip>" -af volumedetect -vn -f null - 2>&1 | grep mean_volume
   ```
4. **plan**: either the auto plan as a starting point
   ```
   .venv/bin/python -m engine vlog plan inputs/vlog/<folder> --brand <brand> [--music assets/music/<track>] [--length 30]
   ```
   or (usually better) write `work/vlog-<folder>/plan.json` by hand from the sheets. pieces:

   | field | meaning |
   |---|---|
   | `kind` | `teaser` or `shot` |
   | `clip` | path from project root |
   | `start` / `dur` | seconds into the clip / seconds on screen (must fit inside the clip) |
   | `speed`, `ramp` | speed 0.5-2, `ramp` true = fast into the moment, slow on it. only if the brand allows speed changes |
   | `transition` | `cut`, or `flash` / `whip` / `dip` only if the brand wants transitions |
   | `push` | slow zoom in |
   | `zoom` | static framing: 1.0 wide, 1.15 tighter. a jump cut = two pieces from the same clip, ~0.25s apart, one at 1.0 and one at 1.15 |
   | `freeze` | seconds to hold the last frame (counts inside `dur`) |
   | `nat` | false to mute that piece |
   | `note` | what it is (shows in the table) |

   Top level: `brand`, `music`, `music_start`, `bpm`, `music_volume` (0.8), `nat_volume` (1.0 without music, 0.5 with), `teaser_nat`.
   Teaser pieces: `dur` = 4/30, start ~0.07s before the moment you want.
5. **show them** the table + storyboard (one frame per piece):
   ```
   .venv/bin/python -m engine vlog table inputs/vlog/<folder>     # rebuilds plan.md + work/vlog-<folder>/storyboard.jpg
   ```
   Send the storyboard image and a section-by-section summary. Wait for "go".
6. **render**:
   ```
   .venv/bin/python -m engine vlog render inputs/vlog/<folder> [--no-grade] [--draft]     # graded with the plan's brand
   ```
   Output `output/vlog-<folder>.mp4`; with music also `_no_music.mp4` (natural sound only, for their own voiceover + music in CapCut).
7. **check** (checks.md): length, freezes, frames at jump cuts, cut timing vs beats if music.

## feedback history

In the brand's brand.md. Don't undo anything listed there.
