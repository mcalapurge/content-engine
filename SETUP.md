# your reels editing engine

## what you need

- a mac (macOS 13+) or a windows 10/11 pc
- a paid claude plan with claude code
- 10 GB+ free space (more if your b-roll library is big)
- optional: an elevenlabs account if you want ai-generated music
- optional: capcut desktop if you like finishing things by hand

## first time setup (about an hour, once)

1. unzip this folder somewhere permanent, eg `Documents/reels-engine`. don't leave it in downloads
2. open claude code and point it at this folder
3. type: **set up my editing engine**
4. say yes when it asks to install things. on a mac it may ask for your password. on windows you might need to close and reopen claude code once
5. it sets up your first brand and interviews you about it: how you film and how you like captions. this is what makes every edit come out on-brand
6. copy your b-roll into your brand's folder, `brands/<your name>/broll` (subfolders like `brands/<your name>/broll/hairburst` help), then say **index my b-roll**. claude looks at every clip and writes a description so it knows when to use it
7. it shows you a before/after of your colour grade on a test clip so you can check it matches your capcut look

## every reel after that

1. film on your phone (say lines as many times as you like), copy it into `inputs/talking-head`
2. say: **i have a new reel** (with more than one brand, say whose it is: **i have a new reel for mia**)
3. it cuts your ums and dead air, picks your best takes, and drops in b-roll where it fits
4. a review page opens in your browser: every line with a thumbnail, how long it took to say, and dropdowns for zoom, b-roll and sound. make changes, hit **copy instructions**, paste into claude
5. say **go**. it builds the reel with your grade, captions, hook, zooms, b-roll, sound effects and music, checks its own work, and saves it in `output/<brand>/<type>/`, a new dated folder each time

## more than one brand (clients)

every brand gets its own folder in `brands/` with its own brand guide, look, colour grade and b-roll.

- say **set up a new brand for mia**. claude makes `brands/mia/` and interviews you about that brand
- then say whose video it is: **edit mia's reel**, or `/content-talking-head mia`
- each brand only ever uses its own b-roll, captions style and grade

## sound

- sound effects go in automatically (whoosh into takeovers, pop on stats, click on step badges)
- say **be my sound designer** for music. it suggests moods, makes a few ai tracks if you've added an elevenlabs key, and lets you pick
- to add the key: make a file called `.env` in this folder with one line: `ELEVENLABS_API_KEY=your-key`
- for paid brand content, make sure your music has commercial rights

## finishing in capcut

say **export it for capcut too** (or ask claude to do it every time). you get a folder in `output` with:

- the clean video (cut, zoomed, graded, b-roll, your voice, no text)
- a see-through graphics layer (hook, stats, takeovers) for the track above
- a caption file you can import as editable text, or skip and use capcut's auto captions
- the music and sound effects as their own track

line them all up at the very start of the timeline and everything stays in sync. full steps are in `HOW_TO_OPEN_IN_CAPCUT.txt` inside each export.

## learning from other reels

paste a reel link and say **what's working in this reel**. it downloads it, maps the pacing and cuts, reads the script, and tells you what you could borrow in your own style.

## things you can say

- i have a new reel
- set up a new brand for mia
- i have a new reel for mia
- make line 3 a full screen takeover, split into two
- put the gummies clip on line 6, picture in picture
- punch in on the stat
- no b-roll on this one
- make this one feel calm
- be my sound designer
- export it for capcut too
- a week of reels from this folder
- what's working in this reel: (link)
- write me the caption for this one

## if something breaks

tell claude what happened ("it won't render", "the captions spelt hairburst wrong") and it'll fix it.
