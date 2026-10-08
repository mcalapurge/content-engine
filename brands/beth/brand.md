# brand guide: beth

claude reads this before every edit for beth (with `effects.md`, `style.json` and `grade.json` in this folder).
it fills this in during the brand interview. edit it any time, or say "update beth's brand file: ...".

## who i am and who i'm talking to
- beth, @beth.ejm. uk ugc creator based in manchester, founder of captura digital
- 3+ years full-time ugc, 6 years in social media. brands: l'oréal, revlon, spotify, hugo boss, tampax, hairburst. also edits videos for tiktok shop
- main topic: the real business side of full-time ugc
  - rates and pricing (£150 vs £700 jobs, £5k months)
  - contracts and usage rights
  - pitching and building a portfolio
  - process from brief to delivery
  - honest "what i thought vs what actually worked" lessons
- also: creator life in manchester with boyfriend alex, and beauty/product content that doubles as ugc portfolio
- main viewer: uk woman, ~22-35, starting out in ugc or on a 9-5 and wants ugc as her full-time income by 2027. past "what is ugc", stuck on getting paid clients, charging properly and making income consistent. wants someone a few steps ahead with real numbers, not hype
- second viewer: brands and marketing managers looking to hire a ugc creator. they come for process and pricing content

## tone
- warm and direct, like a trusted friend who's a few steps ahead
- realistic and honest, never salesy or hype
- knowledgeable: she knows her stuff and backs it with real numbers and experience

## how i film
- mic: DJI. its noise cancelling is baked into the recording (the engine adds no noise reduction). she's switching NC off on the mic
- i repeat lines when i want another go. pick the best take using the rules below
- never restarts the whole video. repeats just the line, sometimes a few goes at it before moving on
- good lighting: in front of a window or with a clip-on light
- location varies: usually the couch, sometimes the bedroom or standing by the window
- looks straight into the lens, usually sitting
- social reels: raw clip ~2-3 mins, finished reel ~1:30 once mistakes are cut
- tiktok shop: ~30 sec clip, or several short clips stitched into a 15-20 sec video

## picking the best take
- first priority: no mistakes (no stumbles, no fluffed or missing words)
- then: the take where she sounds most confident and sincere
- the first or third take is usually the best one. if takes are equally clean, lean toward those
- if takes still look the same, keep the last one

## captions
- all lowercase, except brand names (see below) and "I" on its own (I, I'm, I'd, I've, I'll)
- no outline on caption text (soft shadow only). letters tight
- build-up style: a short line (~4-5 words) builds on screen a word or two at a time until the full line shows, then clears for the next line. not one lonely word at a time, not a full static line
- highlight a keyword in most lines (pick them per reel, ~1 per line): keywords (numbers like £700, key terms like "usage rights", "rates", "contracts") pop in the pink accent. same font as the rest, colour only (no serif)
- brand names always capitalised and spelt correctly, even though the rest is lowercase: L'Oréal, Revlon, Spotify, Hugo Boss, Tampax, Hairburst, TikTok, TikTok Shop, Instagram, Captura Digital, Halara
- always: ugc (lowercase, matches caption style), @beth.ejm, alex, manchester (lowercase like everything else)

## pacing
- cut tight: remove pretty much all pauses so it flows fast and holds attention
- but cuts must sound natural. never clip the end or start of a word, no harsh joins
- hook is instant: no pause or dead air at the start, straight into the first word. on-screen hook appears at 0s too
- a quiet mouse click on the first frame
- movement: a mix of slow zoom-ins and jump cut zooms, with punch-ins on keywords and key points
- a nice amount of movement, never all over the place or unnatural. slow zoom is the default, punch-ins saved for moments that matter

## b-roll
- always full screen. no small picture-in-picture overlays
- never colour grade b-roll, it's already edited. grade only the talking-head footage

## fonts and colours
- main captions: helvetica neue, bold, white, tight letters (matched to her example screenshot), always one line
- keywords: same font, pink accent. decided against playfair display
- accent colour: soft pink #FAEAF0 (keywords, stats, takeover cards). text is otherwise white
- text on a coloured background (step badges, takeover cards, a boxed hook) must be easy to read: at least 4.5:1 contrast (wcag AA). on the pink that means dark #1E1E1E text, never white
- hook: bold text on the video, IN CAPITALS, letters almost touching, max 2 lines with tight line spacing, on screen from the very first frame. open to experimenting. she sometimes puts the hook text behind her head (duplicate layer with background removed so text sits between her and the background)

## colour grade
- lives in brands/beth/grade.json (my usual capcut settings, confirmed during setup)
- blacks must stay black, never blue. blue saturation is -100 and the temperature skips the shadows (`neutral_blacks`)

## b-roll / vlog edits
- ~30 seconds. opens with a very fast teaser: 4-frame snaps (0.13s) from ~16 different clips, done in ~2s. then the best bits of each clip, short shots early on
- never speed footage up or down (no speed ramps). freeze frames are ok
- NO transitions (no flashes, whips or fades), just cuts. lots of jump cuts (same shot, skip ahead, tighter frame) mixed with slow zooms. fast start
- keep the natural sound. order = whatever is most engaging, not chronological
- she sends the music track when she wants it cut to the beat, otherwise no music (she adds her own + voiceover later)

## accounts
- **@beth.ejm** (tiktok + instagram): talking head reels, vlog edits, instagram trial reels. one 9:16 edit works for both platforms
- **wornbybeth** (tiktok shop): try-on and product videos she earns commission on. separate account, never mix it with @beth.ejm

## talking head defaults (@beth.ejm)
- raw ~2-3 min, finished ~1-1:30
- `hook_text`: punchy, max ~8 words, ideally the question her viewer is asking. shows IN CAPITALS on 2 lines from 0s; she speaks straight away, no dead air
- first kept line: `"sfx": "click", "sfx_volume": 0.6` (the quiet mouse click on frame 1)
- motion: slow zoom on the hook, then alternate `jump` / `slow`. `punch` on the 2-3 lines that land the point (the answer, the money line, the opinion). avoid `none`
- keywords: about one per line, numbers first, then the key term
- b-roll from her library: always full screen, max ~40% of lines, never on the hook, a key opinion line or the ending
- grade on for her talking footage. b-roll stays ungraded unless it's her raw footage (`"grade": true`)
- output lands as `output/<clip>_beth.mp4`

## tiktok shop defaults (wornbybeth)
- past products: Halara Wide Leg Trousers, wide-calf boots
- viewer: midsize uk women looking for clothes / shoes that fit. she shares her sizes: UK 16, 5'2", 17-inch calves, 34" waist / 46" hip, wears XL
- each video ~15-45s: one product, strong hook, honest try-on, recommendation at the end
- **captions only** (`--no-text`): she adds her own on-screen text in the tiktok app
- same look as her other videos: her captions, pink keywords, her grade, quiet click on frame 1
- ask for the product name once (spelling) and add it to `keep_caps`, plus words like UK / XL
- compilations: ask if it was already colour graded (yes = `--no-grade`, no `"grade": true` on b-roll)
- transcribe with `--model medium`: product names get misheard (eg "these two love trousers" = "these Halara trousers", "white calf" = "wide-calf", "buried amount" = "varied amount")
- merge sizes like 5'2" into one caption word
- keywords from the selling points (comfortable, stretch, padded, zip, XL, UK 16, 17-inch...)
- punch-in on the sizing / proof / verdict line
- no covers
- captions sit at ~70% height, which in full-body try-on shots can cover the product. offer a variation with captions higher for those videos only: `brands/beth/styles/shop.json` (copy of style.json with a lower `caption_position`), render with `--style shop`. don't change style.json for this

## vlog defaults (@beth.ejm)
- grade: ask if she didn't say. last time she said "they don't need colour grading" (`--no-grade`)
- a little story, eg morning, work, shoot, out, evening. end on a satisfying shot (eg a laugh that echoes the teaser)
- music only if she names a track, then she also gets a `_no_music` version

## trial reel defaults (instagram @beth.ejm)
- instagram trial reels to test hooks: ~8-11s, hook, middle line, call to action pointing to a carousel on her grid / profile
- spreadsheet columns: `#`, `type`, `beat 1 (hook)`, `beat 2`, `beat 3`, `b-roll`, `caption`, `carousel it points to`
- types: number reveal, hot take, I thought / actually, mistake, pov, brand-facing, list tease
- keep her text exactly as written: lowercase with CAPS for emphasis
- text: helvetica neue bold, white, tight letters, centred, tight line spacing, soft dark band behind it (no outline, no box). numbers, money and CAPS words in the accent colour
- b-roll pool: the set's folder + her b-roll library (`brands/beth/broll/`) + `inputs/vlog/` (top level). match the `b-roll` column first, vary clips across the set. no grade
- music by reel type (tracks in `assets/music/`):

  | type | tracks |
  |---|---|
  | number reveal | my-chapters, move, feels-so-right, think-straight, girl-in-the-southeast, do-my-thing |
  | hot take | look-at-me, splurge, washing-up, sex-and-money, melons |
  | I thought / actually | coffee-drips, last-call, the-waves |
  | mistake | stokerville, undercover, teal, fountains, do-my-thing, sex-and-money |
  | pov | melons, washing-up, still-waters, look-at-me |
  | brand-facing | leaders-greenhouse, nota-bene, wabisabi, fall-night-drift |
  | list tease | move, odyssey, my-chapters |

- b-roll types to the closest footage she has (check files exist and look at the preview):

  | b-roll type | use |
  |---|---|
  | typing an email | cafe laptop typing clips (BR004-1, BR004-8, b-roll 23rd, b-roll 2, trail reels-3, b-roll 3) |
  | laptop + matcha at café | BR004-8, b-roll 2, b-roll 23rd, BR004-9, BR004-1, trail reels-2 |
  | walking in manchester with coffee | BR004-11, BR004-12, b-roll-1, vlog street coffee clips |
  | filming setup with ring light | BR004-2 (home studio), BR004-3 (Alex photographing her), vlog studio clips |
  | desk flat lay with notebook | trail reels-4 (flat lay), vlog jewellery flat lay, BR004-7 |
  | filming product close up / getting ready / skincare | copy_6C2F... (skincare), trail reels-1 (lip product), vlog makeup close-up |
  | pr packages / unboxing | vlog ring box flat lay, b-roll event, vlog pr event |
  | packing camera bag | trail reels-4, vlog Alex with camera |
  | **invoice / banking app screen** | **no real footage yet.** stand-in: cafe laptop / phone shots. tell her |
  | **editing in capcut** | **no real footage yet.** stand-in: BR004-5 (laptop screen with her on a call), b-roll 3. tell her |
  | **sat on sofa with phone** | **no real footage yet.** stand-in: BR004-4, vlog in-bed-with-mug. tell her |

- footage she still needs: banking app / invoice screens (numbers blurred), editing in capcut, sitting on the sofa with her phone. use stand-ins until she films them and say which reels use stand-ins

## feedback she's given before (already the defaults, don't undo)
- talking head:
  - "gap at the start" → first word on frame 1, hook text at 0s
  - "text outlined" → no outline, soft shadow
  - "letters closer" → tight spacing (applied inline by the engine)
  - "hook in capitals, lines closer" → `hook_uppercase`, `hook_line_height`, `hook_chars: 20` (2 lines)
  - "I should be capital" → done in captions
  - "no small overlay" → b-roll always full screen
  - "don't grade the b-roll" → grade before b-roll is laid on
  - "Playfair Display" → dropped, keywords are colour only
  - "last word cuts off" / "no words cut off" → audio snapping + tail
  - "glitchy" → framing changes only at real cuts
  - "noise reduction" → engine has none; it's the DJI mic's NC setting
- vlog:
  - "I really don't like the flashy transitions" → no transitions
  - "speed up the start, more jump cuts, slow zooms" → 4-frame teaser, jump pairs + pushes
  - "don't speed things up" → no ramps
- trial reels:
  - text was hard to read on bright shots → soft dark band, bigger text
  - "line spacing much smaller, make sure it's in the centre" → lines placed individually at 0.84 spacing, block centred

## open items
- accent pink #FAEAF0 is so pale it barely shows against white. no deeper pink chosen yet; ask if it matters for the job
- "text behind my head" hook (cut-out layer) isn't built yet
- the DJI kitchen-table clip was removed from her b-roll; don't use it

## status (7 Oct 2026)
- trial set `trial`: 30 reels in `output/trial/` from `work/trial/plan.json`. no final feedback yet
- `inputs/vlog/` has 64 raw clips (travel, airport, plane, italy lakeside, cafes, food, selfies, shops) measured but not yet described or used
