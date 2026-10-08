"""turns a brand's grade.json (capcut-style numbers) into an ffmpeg colour grade.

usage (preview): python -m engine grade [video] --brand <name> [--at 3.0]
saves output/<brand>/grade/<date>_<time>_<clip>/<clip>_grade_compare.jpg - before on the left, after on the right.
"""
import argparse
import hashlib
import struct
from pathlib import Path

from engine.core.brand import add_brand_arg, get_brand
from engine.core.common import vin, WORK_DIR, output_folder, find_bin, load_json, resolve_video, run, sdr_filter, video_info

HSL_NAMES = {"red": "r", "yellow": "y", "green": "g", "cyan": "c", "blue": "b",
             "magenta": "m", "purple": "m"}


def load_grade(brand):
    """the brand's grade settings, or None if it has no grade.json or grading is switched off."""
    if not brand.grade_file.exists():
        return None
    g = load_json(brand.grade_file)
    return g if g.get("enabled", True) else None


LUT_LEVEL = 6     # identity hald image level 6 = a 36x36x36 colour table (matches the filters to ~48 dB)


def grade_filter(g, hsl_supported=True):
    """the grade as used in renders: every colour step baked into one 3d colour table (one fast
    pass instead of five slow ones), then clarity, which isn't a colour change so can't go in the table.
    the table is rebuilt automatically whenever grade.json changes (cached in work/_grade/)."""
    if not g:
        return ""
    colour = colour_chain(g, hsl_supported)
    out = []
    if colour:
        out.append(f"lut3d=file='{build_lut(colour)}':interp=tetrahedral")
    clarity = g.get("clarity", 0)
    if clarity:
        out.append(clarity_filter(clarity))
    return ",".join(out)


def clarity_filter(clarity):
    # 7x7 at 0.05 per step matches the old 13x13 at 0.04 to ~60 dB, for about 30% less work
    return f"unsharp=7:7:{clarity * 0.05:.3f}:5:5:0"


def build_lut(colour):
    """run the colour filters over an identity image once and save the result as a .cube table."""
    key = hashlib.sha1(f"{LUT_LEVEL}|{colour}".encode()).hexdigest()[:12]
    cube = WORK_DIR / "_grade" / f"grade_{key}.cube"
    if cube.exists():
        return cube.as_posix()
    cube.parent.mkdir(parents=True, exist_ok=True)
    raw = cube.with_suffix(".raw")
    run([find_bin("ffmpeg"), "-y", "-f", "lavfi", "-i", f"haldclutsrc=level={LUT_LEVEL}", "-frames:v", "1",
         "-vf", f"format=rgb48le,{colour},format=rgb48le", "-f", "rawvideo", "-pix_fmt", "rgb48le", str(raw)])
    d = raw.read_bytes()
    raw.unlink()
    vals = struct.unpack(f"<{len(d) // 2}H", d)
    n = LUT_LEVEL * LUT_LEVEL
    # hald order (red fastest, then green, then blue) is the same order a .cube file uses
    lines = [f"LUT_3D_SIZE {n}"] + [f"{vals[i] / 65535:.6f} {vals[i + 1] / 65535:.6f} {vals[i + 2] / 65535:.6f}"
                                     for i in range(0, len(vals), 3)]
    tmp = cube.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(cube)
    return cube.as_posix()


def colour_chain(g, hsl_supported=True):
    """the colour steps as plain ffmpeg filters. capcut sliders run -100..100 (some -50..50).
    these factors are tuned by eye. renders use the baked table from grade_filter instead."""
    if not g:
        return ""
    st = g.get("strength", {})
    tt = st.get("temp_tint", 1.0)
    f = []
    temp, tint = g.get("temp", 0) * tt, g.get("tint", 0) * tt
    if temp or tint:
        r = round(temp * 0.006, 4)
        b = round(-temp * 0.006, 4)
        gr = round(-tint * 0.005, 4)
        # neutral_blacks: temp/tint skip the shadows and go easy on the mids, so black clothes stay black
        sh, md = (0.0, 0.5) if g.get("neutral_blacks") else (0.5, 1.0)
        f.append(f"colorbalance=rs={r*sh}:rm={r*md}:rh={r/2}:bs={b*sh}:bm={b*md}:bh={b/2}"
                 f":gs={gr*sh}:gm={gr*md}:gh={gr/2}")
    sat = g.get("saturation", 0)
    if sat:
        f.append(f"eq=saturation={1 + sat / 100:.3f}")
    whites, blacks = g.get("whites", 0), g.get("blacks", 0)
    if whites or blacks:
        lo = min(max(0.1 + blacks * 0.004, 0.0), 0.3)
        hi = min(max(0.9 + whites * 0.004, 0.7), 1.0)
        f.append(f"curves=all='0/0 0.1/{lo:.3f} 0.9/{hi:.3f} 1/1'")
    if hsl_supported:
        hh, hs = st.get("hsl_hue", 1.0), st.get("hsl_sat_bright", 1.0)
        for name, adj in (g.get("hsl") or {}).items():
            c = HSL_NAMES.get(name.lower())
            if not c:
                continue
            hue = adj.get("hue", 0) * 0.3 * hh          # capcut +-100 -> about +-30 degrees
            s = adj.get("saturation", 0) / 100 * hs
            i = adj.get("brightness", 0) / 100 * 0.5 * hs
            if hue or s or i:
                f.append(f"huesaturation=colors={c}:hue={hue:.1f}:saturation={s:.3f}:intensity={i:.3f}")
    return ",".join(f)


def has_huesaturation():
    import subprocess
    out = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-filters"],
                         capture_output=True, text=True).stdout
    return " huesaturation " in out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--at", type=float, default=None, help="seconds into the clip to sample")
    add_brand_arg(ap)
    args = ap.parse_args()
    brand = get_brand(args.brand)
    video = resolve_video(args.video)
    info = video_info(video)
    at = args.at if args.at is not None else info["duration"] / 2
    g = load_grade(brand)
    if not g:
        print(f"[engine] grading is switched off (or missing) in brands/{brand.name}/grade.json")
        return
    gf = grade_filter(g, has_huesaturation())
    out = output_folder(brand.name, "grade", Path(video).stem) / f"{Path(video).stem}_grade_compare.jpg"
    scale = "scale=-2:960"
    # left = before, right = after (no text labels, so it works without font setup)
    fc = f"[0:v]{sdr_filter(video)}{scale},split[a][b];[b]{gf}[g];[a]pad=iw+12:ih:0:0:white[a2];[a2][g]hstack"
    run([find_bin("ffmpeg"), "-y", *vin(video, "-ss", f"{at:.2f}"), "-frames:v", "1",
         "-filter_complex", fc, "-q:v", "2", str(out)])
    print(f"[engine] grade preview saved: {out}")


if __name__ == "__main__":
    main()
