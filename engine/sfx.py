"""makes a starter set of sound effects in sfx/ (generated, so no licensing worries).

usage: python engine/sfx.py [--force]
replace any of them with your own file of the same name (whoosh.wav, pop.mp3 ...),
or add new ones and use them by name in plan.json ("sfx": "ding").
"""
import argparse

from common import SFX_DIR, find_bin, run

SOUNDS = {
    # name: (lavfi source, extra filters)
    "whoosh": ("anoisesrc=d=0.55:c=pink:a=0.6",
               "highpass=f=300,lowpass=f=5000,afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.25"),
    "swoosh": ("anoisesrc=d=0.35:c=white:a=0.35",
               "bandpass=f=2500:w=1800,afade=t=in:d=0.15,afade=t=out:st=0.15:d=0.2"),
    "pop": ("aevalsrc='0.7*sin(2*PI*(500+1800*exp(-t*45))*t)*exp(-t*28)':d=0.18:s=48000", ""),
    "click": ("aevalsrc='0.6*(random(0)*2-1)*exp(-t*220)':d=0.05:s=48000", "highpass=f=1500"),
    "ding": ("aevalsrc='0.35*sin(2*PI*1320*t)*exp(-t*5)+0.15*sin(2*PI*2640*t)*exp(-t*7)':d=1.4:s=48000", ""),
    "riser": ("aevalsrc='0.3*sin(2*PI*(200+900*t*t)*t)*(t/1.2)':d=1.2:s=48000",
              "afade=t=out:st=1.1:d=0.1"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    args = ap.parse_args()
    SFX_DIR.mkdir(exist_ok=True)
    for name, (src, fx) in SOUNDS.items():
        out = SFX_DIR / f"{name}.wav"
        if out.exists() and not args.force:
            print(f"  kept   {out.name} (already there)")
            continue
        cmd = [find_bin("ffmpeg"), "-y", "-f", "lavfi", "-i", src]
        filt = "aformat=sample_rates=48000:channel_layouts=stereo" + ("," + fx if fx else "")
        run(cmd + ["-af", filt, str(out)])
        print(f"  made   {out.name}")
    print(f"\n[engine] sound effects ready in {SFX_DIR}")


if __name__ == "__main__":
    main()
