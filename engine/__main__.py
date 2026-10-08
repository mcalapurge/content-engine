"""python -m engine <command> [args]

run from the project root. `python -m engine` on its own lists the commands,
`python -m engine <command> --help` shows a command's options.
"""
import importlib
import sys

# name -> (module, one line on what it does). listed in the order a reel goes through them
COMMANDS = {
    "check_setup": ("engine.commands.check_setup", "check python, ffmpeg and packages are installed"),
    "brand":       ("engine.commands.brand", "list brands, start a new one"),
    "inputs":      ("engine.commands.inputs", "decide which clips a job uses"),
    "transcribe":  ("engine.commands.transcribe", "transcribe a clip with word timings"),
    "plan":        ("engine.commands.plan", "rough cut: edit plan + beat table"),
    "takes":       ("engine.commands.takes", "frames from every take of a repeated line"),
    "broll":       ("engine.commands.broll", "index the b-roll library, match it to lines"),
    "review":      ("engine.commands.review", "open the review page in the browser"),
    "render":      ("engine.commands.render", "render the approved plan into a reel"),
    "qc":          ("engine.commands.qc", "check the finished reel"),
    "batch":       ("engine.commands.batch", "split a batch-filmed shop video into parts"),
    "vlog":        ("engine.commands.vlog", "b-roll / vlog edits from a folder of clips"),
    "textreel":    ("engine.commands.textreel", "text-over-b-roll trial reels"),
    "music":       ("engine.commands.music", "list, generate or add background music"),
    "sfx":         ("engine.commands.sfx", "make the starter sound effects"),
    "analyse":     ("engine.commands.analyse", "break down someone else's reel"),
    "grade":       ("engine.core.grade", "colour grade before/after preview"),
    "contrast":    ("engine.core.contrast", "contrast of boxed text in a style"),
}


def usage():
    print("usage: python -m engine <command> [args]\n\ncommands:")
    for name, (_, about) in COMMANDS.items():
        print(f"  {name:12} {about}")
    print("\n`python -m engine <command> --help` for a command's options")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        usage()
        return
    name = sys.argv[1].removesuffix(".py")
    if name not in COMMANDS:
        print(f"unknown command '{sys.argv[1]}'\n", file=sys.stderr)
        usage()
        sys.exit(2)
    module = importlib.import_module(COMMANDS[name][0])
    sys.argv = [f"python -m engine {name}", *sys.argv[2:]]
    module.main()


if __name__ == "__main__":
    main()
