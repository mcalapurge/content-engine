# brands

one folder per client brand. everything that makes a brand's videos look and sound like theirs lives
here, so the engine and the skills stay generic.

| file | what |
|---|---|
| `brand.md` | the brand guide: who they are, tone, filming, take rules, captions, fonts, colours, accounts, defaults per format, past feedback, open items. claude reads it before every edit for that brand |
| `effects.md` | their named effects library |
| `style.json` | their caption / overlay look (fonts, colours, `keep_caps`, zoom amounts). see `assets/styles/README.md` |
| `styles/` | optional variations of their look, used with `--style <name>` (eg `shop.json` with captions higher) |
| `grade.json` | their colour grade, capcut-style numbers |
| `broll/` | their b-roll library: clips (subfolders ok), `library.json` (descriptions, tags), `_previews/` |

- new brand: `python -m engine brand new <name> --style editorial` (copies `_template/`), then the brand interview
- see them all: `python -m engine brand list`
- every command that reads brand settings takes `--brand <name>`; a job's plan.json remembers it
- folders starting with `_` (like `_template`) are not brands
