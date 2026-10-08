"""contrast check for on-screen text that sits on a solid background (hook box, step badge,
takeover cards). uses the wcag contrast formula. text straight on the video (captions, stat pops,
hook without a box) has no fixed background, so it isn't checked here.

usage: python -m engine contrast --brand <name> [--style <style>]   # every boxed text colour pair in a style
"""

MIN_RATIO = 4.5     # wcag AA for normal text. we hold all boxed text to it, whatever the size


def _lum(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def badge_colours(st):
    return (st.get("badge_text_colour", st["hook_text_colour"]),
            st.get("badge_bg", st["hook_box_colour"]))


def takeover_colours(st):
    return (st.get("takeover_text_colour", st["hook_text_colour"]),
            st.get("takeover_bg", st["hook_box_colour"]))


def boxed_pairs(st, plan=None):
    """(name, text colour, background colour) for every boxed element this style/plan shows.
    no plan = every boxed element the style could show."""
    lines = [l for l in (plan or {}).get("lines", []) if l.get("keep")]
    used = lambda t: plan is None or any(l.get("treatment") == t for l in lines)
    pairs = []
    if st.get("hook_box", True) and (plan is None or plan.get("hook_text")):
        pairs.append(("hook box", st["hook_text_colour"], st["hook_box_colour"]))
    if used("step"):
        pairs.append(("step badge", *badge_colours(st)))
    if used("takeover"):
        pairs.append(("takeover card", *takeover_colours(st)))
    return pairs


def problems(st, plan=None):
    """[(name, text, bg, ratio)] for every boxed element below MIN_RATIO."""
    out = []
    for name, fg, bg in boxed_pairs(st, plan):
        r = ratio(fg, bg)
        if r < MIN_RATIO:
            out.append((name, fg, bg, r))
    return out


def main():
    import argparse
    from engine.core.brand import add_brand_arg, get_brand, load_style
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default=None, help="default: the brand's own style")
    add_brand_arg(ap)
    args = ap.parse_args()
    st = load_style(args.style, get_brand(args.brand))
    for name, fg, bg in boxed_pairs(st):
        r = ratio(fg, bg)
        print(f"{name:14} {fg} on {bg}: {r:4.1f}:1  {'ok' if r >= MIN_RATIO else 'TOO LOW (need ' + str(MIN_RATIO) + ':1)'}")


if __name__ == "__main__":
    main()
