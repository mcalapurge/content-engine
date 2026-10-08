"""builds the review page: every line of the rough cut with keep/delete, zoom, notes.

usage: python -m engine review [video] [--no-open]
opens work/<clip>/review.html in your browser. hit 'copy instructions',
paste them back into claude code.
"""
import argparse
import base64
import html
import json
import webbrowser

from engine.core.brand import add_brand_arg, get_brand, style_names
from engine.core.common import (vin, SFX_DIR, find_bin, load_json, resolve_video, run,
                    sdr_filter, work_dir_for)

SLOW_LINE_SECS = 6.0


def thumb(video, t, path):
    run([find_bin("ffmpeg"), "-y", *vin(video, "-ss", f"{t:.2f}"), "-frames:v", "1",
         "-vf", f"{sdr_filter(video)}scale=-2:150", "-q:v", "5", str(path)])
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--no-open", action="store_true")
    add_brand_arg(ap)
    args = ap.parse_args()
    video = resolve_video(args.video)
    wd = work_dir_for(video)
    plan = load_json(wd / "plan.json")
    brand = get_brand(args.brand, plan)
    tdir = wd / "thumbs"
    tdir.mkdir(exist_ok=True)

    rows = []
    for l in plan["lines"]:
        img = thumb(video, (l["start"] + l["end"]) / 2, tdir / f"{l['id']:02d}.jpg")
        rows.append({"id": l["id"], "secs": l["seconds"], "text": l["text"], "keep": l["keep"],
                     "reason": l["reason"], "motion": l["motion"], "treatment": l["treatment"],
                     "takes": l["takes"], "notes": l.get("notes", ""), "img": img,
                     "broll": (l.get("broll") or {}).get("file", ""),
                     "pip": (l.get("broll") or {}).get("mode") == "pip",
                     "sfx": l.get("sfx") or ""})
    styles = style_names(brand)
    lib = brand.library
    clips = [c["file"] for c in load_json(lib)["clips"]] if lib.exists() else []
    sfx = sorted({p.stem for p in SFX_DIR.glob("*") if p.suffix.lower() in (".wav", ".mp3", ".m4a")})
    data = {"broll": clips, "sfx": sfx, "clip": video.name, "hook": plan.get("hook_text", ""), "style": plan.get("style") or brand.name,
            "styles": styles, "rows": rows, "slow": SLOW_LINE_SECS}

    page = PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/")) \
               .replace("__TITLE__", html.escape(video.name))
    out = wd / "review.html"
    out.write_text(page, encoding="utf-8")
    print(f"[engine] review page: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>review - __TITLE__</title>
<style>
:root{--bg:#faf8f4;--card:#fff;--ink:#1e1e1e;--muted:#8a857c;--line:#e8e3da;--accent:#d9a441;--cut:#f3efe8}
@media (prefers-color-scheme:dark){:root{--bg:#161514;--card:#201f1d;--ink:#f1ede6;--muted:#9a948a;--line:#33302c;--cut:#1b1a18}}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:16px 20px;z-index:2}
h1{font-size:18px;margin:0 0 10px}.top{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
label{font-size:12px;color:var(--muted);text-transform:lowercase}
input[type=text],select,textarea{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:7px 9px}
#hook{min-width:320px}main{padding:16px 20px 140px;max-width:1100px;margin:0 auto}
.row{display:grid;grid-template-columns:30px 90px 1fr 340px;gap:14px;align-items:start;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:10px}
.row.cut{background:var(--cut);opacity:.6}.row.cut .say{text-decoration:line-through}
.num{font-weight:700;color:var(--muted)}img{width:84px;border-radius:6px;display:block}
.meta{font-size:12px;color:var(--muted);margin-top:4px}.slow{color:#c0563b;font-weight:600}
.ctl{display:flex;flex-direction:column;gap:6px}.ctl .pair{display:flex;gap:6px}.ctl select{flex:1}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:inherit;border-radius:8px;padding:7px 12px;cursor:pointer}
button.del{min-width:84px}.row.cut button.del{background:var(--accent);color:#1e1e1e;border-color:var(--accent)}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--bg);border-top:1px solid var(--line);padding:12px 20px;display:flex;gap:12px;align-items:center}
#send{background:var(--accent);border-color:var(--accent);color:#1e1e1e;font-weight:700;padding:10px 18px}
#out{flex:1;height:44px;font-size:12px}#msg{font-size:13px;color:var(--muted)}
@media(max-width:760px){.row{grid-template-columns:24px 1fr}.row img{grid-column:2}.row .ctl{grid-column:1/-1}}
</style></head><body>
<header><h1>rough cut review - __TITLE__</h1>
<div class="top"><div><label>hook on screen</label><br><input id="hook" type="text"></div>
<div><label>style</label><br><select id="style"></select></div>
<div id="total" class="meta"></div></div></header>
<main id="rows"></main>
<footer><button id="send">copy instructions</button><textarea id="out" readonly placeholder="your instructions appear here"></textarea><span id="msg"></span></footer>
<script>
const D = __DATA__;
const MOTIONS = [["none","static"],["slow","slow zoom in"],["jump","jump cut zoom"],["punch","punch-in"]];
const TREAT = [["none","captions only"],["hook","hook card"],["stat pop","stat pop"],["step","step badge"],["takeover","full screen takeover"]];
const BR = [["","no b-roll"], ...D.broll.map(f => [f, f.replace(/^broll\//,"")])];
const SFX = [["","auto sound"],["none","no sound"], ...D.sfx.map(n => [n, "sound: " + n])];
const state = D.rows.map(r => ({...r}));
const $ = s => document.querySelector(s);
$("#hook").value = D.hook;
D.styles.forEach(s => $("#style").add(new Option(s, s, false, s === D.style)));
function opts(list, cur){return list.map(([v,l]) => `<option value="${v}" ${v===cur?"selected":""}>${l}</option>`).join("")}
function esc(t){return t.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function render(){
  $("#rows").innerHTML = state.map((r,i) => `
  <div class="row ${r.keep?"":"cut"}">
    <div class="num">${r.id}</div><img src="${r.img}" alt="">
    <div><div class="say">${esc(r.text)}</div>
      <div class="meta"><span class="${r.secs>D.slow&&r.keep?"slow":""}">${r.secs}s${r.secs>D.slow&&r.keep?" - slow, viewers may drop":""}</span>
      ${r.takes.length?` &middot; take ${r.takes.indexOf(r.id)+1} of ${r.takes.length}`:""}
      ${!r.keep&&r.reason?` &middot; ${esc(r.reason)}`:""}</div></div>
    <div class="ctl"><div class="pair"><select data-i="${i}" data-k="motion">${opts(MOTIONS,r.motion)}</select>
      <select data-i="${i}" data-k="treatment">${opts(TREAT,r.treatment)}</select></div>
      <div class="pair"><select data-i="${i}" data-k="broll">${opts(BR,r.broll)}</select>
      <label style="display:flex;align-items:center;gap:4px"><input type="checkbox" data-i="${i}" data-k="pip" ${r.pip?"checked":""}>pip</label></div>
      <div class="pair"><select data-i="${i}" data-k="sfx">${opts(SFX,r.sfx)}</select></div>
      <div class="pair"><input type="text" data-i="${i}" data-k="notes" placeholder="note for this line" value="${esc(r.notes||"")}" style="flex:1">
      <button class="del" data-i="${i}">${r.keep?"delete":"restore"}</button></div></div>
  </div>`).join("");
  const secs = state.filter(r=>r.keep).reduce((a,r)=>a+r.secs,0);
  $("#total").textContent = `about ${secs.toFixed(1)}s kept from ${state.length} lines`;
}
document.addEventListener("click", e => { if(e.target.matches("button.del")){const r=state[e.target.dataset.i]; r.keep=!r.keep; render();}});
document.addEventListener("change", e => { const t=e.target; if(t.dataset.k){state[t.dataset.i][t.dataset.k]= t.type==="checkbox" ? t.checked : t.value;}});
document.addEventListener("input", e => { const t=e.target; if(t.dataset.k==="notes"){state[t.dataset.i].notes=t.value;}});
$("#send").onclick = async () => {
  const lines = [`review for ${D.clip} - apply these to plan.json, show me the updated beat table:`];
  if ($("#hook").value !== D.hook) lines.push(`- hook text: "${$("#hook").value}"`);
  if ($("#style").value !== D.style) lines.push(`- style: ${$("#style").value}`);
  state.forEach((r,i) => { const o=D.rows[i], c=[];
    if (r.keep!==o.keep) c.push(r.keep?"keep it":"cut it");
    if (r.motion!==o.motion) c.push(`motion: ${r.motion}`);
    if (r.treatment!==o.treatment) c.push(`treatment: ${r.treatment}`);
    if (r.broll!==o.broll) c.push(r.broll ? `b-roll: ${r.broll}` : "no b-roll");
    if (r.broll && r.pip!==o.pip) c.push(r.pip ? "b-roll as picture in picture" : "b-roll full screen");
    if (r.sfx!==o.sfx) c.push(r.sfx ? `sound: ${r.sfx}` : "sound: automatic");
    if ((r.notes||"")!==(o.notes||"")) c.push(`note: ${r.notes}`);
    if (c.length) lines.push(`- line ${r.id}: ${c.join("; ")}`); });
  if (lines.length===1) lines.push("- no changes, looks good. go ahead and build it");
  const text = lines.join("\n"); $("#out").value = text;
  try { await navigator.clipboard.writeText(text); $("#msg").textContent = "copied - paste into claude code"; }
  catch { $("#out").select(); document.execCommand("copy"); $("#msg").textContent = "copied (if not, copy from the box)"; }
};
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
