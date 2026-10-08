# effects library

named effects claude can reuse. to add one: show claude a screenshot of something you like,
give it a name, and say "add this to my effects library". check this file before every build.

## slow zoom in
plan.json: `"motion": "slow"`. gentle push-in across the whole line, ends at the style's `slow_zoom`.
use for: hooks, emotional or reflective lines, endings.

## jump cut zoom
plan.json: `"motion": "jump"`. framing alternates between normal and `jump_zoom` at every cut.
use for: fast talking-head sections, lists, keeping energy up.

## punch-in
plan.json: `"motion": "punch"`. hard cut to a tight `punch_zoom` frame for the whole line.
use for: stats, punchlines, the one line you want to land.

## full screen takeover
plan.json: `"treatment": "takeover"`, optional `"takeover_text": ["card one", "card two"]`.
solid brand-colour screen with huge text. a list splits the line into several cards in sequence
("split it into two" = two cards). captions are hidden during it.

## stat pop
plan.json: `"treatment": "stat pop"`, `"stat": "70%"`. big number lands on the word you say it.
numbers 10+ count up first.

## step badge
plan.json: `"treatment": "step"`, `"step": 1`. small "step 1" label up top.

## hook card
plan.json: `"hook_text"`. boxed text at the top for the first ~3 seconds.
