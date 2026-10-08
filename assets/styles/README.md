# style packs

the files here are generic starting looks (editorial, playful, butter). each brand's own look lives in
`brands/<brand>/style.json` (made from one of these by `python -m engine brand new <brand> --style <look>`),
with optional variations in `brands/<brand>/styles/`. to change a brand's look, edit its style.json:

- `font` / `hook_font` - must be installed on your computer, or drop the .ttf/.otf file into the `assets/fonts/` folder and use the font's name
- colours - hex codes like `#FFD43B`
- `caption_mode` - `word` (one word at a time), `line` (a few words at once), `karaoke` (a line with the spoken word highlighted) or `build` (a line builds up as each word is said, `build_step` words at a time)
- `words_per_caption` - how many words show at once in line/karaoke mode
- `lowercase` - all captions lowercase. names in `keep_caps` keep their capitals (eg "TikTok Shop")
- `spacing` - letter spacing (negative = tighter)
- `keywords` - words/phrases that pop in `keyword_font` / `keyword_colour` / `keyword_size` (numbers and money pop automatically). a line in plan.json can list its own `keywords` (word indexes) instead
- `hook_box` - false = bold hook text straight on the video, no box
- `caption_position` - 0 is the top of the screen, 1 is the bottom
- `slow_zoom` - where the slow push-in ends (1.07 = 7% closer by the end of the line)
- `jump_zoom` - how much tighter the alternate framing is on jump cuts
- `punch_zoom` - how hard the punch-in hits
- `takeover_bg`, `takeover_text_colour`, `takeover_size` - the full screen takeover card

or just tell claude "build <brand> a style pack in their brand colours" and it'll do it for you.
