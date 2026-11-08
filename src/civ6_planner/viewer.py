"""A standalone HTML view of a map, so plans can be checked without opening Civ VI.

The page embeds the map as JSON and draws it as SVG hexes in the game's layout
(odd rows shifted east, north up). Drag to pan, scroll to zoom, hover for a tile's
fields. Hidden tiles of a masked map can be shown faded.
"""
import html
import json

from .rules import Rules


def _resource_classes():
    try:
        return Rules.from_game().resource_class
    except FileNotFoundError:
        return {}


def write(d, path, title="", tacks=(), notes=(), hidden_from=None):
    """Write the page for dump `d`. hidden_from: the unmasked map, if d is masked."""
    shown = {t["i"] for t in d["tiles"]}
    hidden = [t for t in hidden_from["tiles"] if t["i"] not in shown] if hidden_from else []
    data = {
        "w": d["w"], "h": d["h"], "turn": d["turn"],
        "tiles": d["tiles"], "hidden": hidden,
        "tacks": [{"x": t.x, "y": t.y, "icon": t.icon, "name": t.name} for t in tacks],
        "resourceClass": _resource_classes(),
    }
    page = (_TEMPLATE
            .replace("__TITLE__", html.escape(title or "map"))
            .replace("__NOTES__", "".join(f"<li>{html.escape(n)}</li>" for n in notes))
            .replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Civ map view</title>
<style>
  :root { --bg:#f7f6f2; --panel:#ffffff; --ink:#1f1e1b; --muted:#6b6963; --line:#dddbd3; }
  @media (prefers-color-scheme: dark) { :root { --bg:#1a1a19; --panel:#242422; --ink:#f0efec; --muted:#a3a29b; --line:#3a3a37; } }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 system-ui, sans-serif; background:var(--bg); color:var(--ink);
         display:grid; grid-template-columns:minmax(0,1fr) 300px; height:100vh; }
  #map { width:100%; height:100vh; cursor:grab; display:block; }
  #map.dragging { cursor:grabbing; }
  aside { background:var(--panel); border-left:1px solid var(--line); padding:14px 16px; overflow:auto; }
  h1 { font-size:15px; font-weight:600; margin:0 0 4px; word-break:break-word; }
  .muted { color:var(--muted); font-size:12px; }
  ul { padding-left:18px; margin:6px 0 12px; }
  .legend { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:3px 8px; font-size:12px; margin:8px 0 12px; }
  .sw { display:inline-block; width:11px; height:11px; border-radius:2px; vertical-align:-1px; margin-right:5px; border:1px solid rgba(0,0,0,.15); }
  #info { font:12px/1.45 ui-monospace, monospace; white-space:pre-wrap; background:var(--bg); border-radius:6px; padding:8px; min-height:60px; }
  label { font-size:13px; display:block; margin:4px 0; }
  @media (max-width: 700px) { body { grid-template-columns:1fr; height:auto; } #map { height:70vh; } aside { border-left:0; } }
</style></head>
<body>
<svg id="map" xmlns="http://www.w3.org/2000/svg"></svg>
<aside>
  <h1>__TITLE__</h1>
  <div class="muted" id="summary"></div>
  <ul>__NOTES__</ul>
  <label><input type="checkbox" id="showHidden"> Show hidden tiles (faded)</label>
  <label><input type="checkbox" id="showRes" checked> Resource labels</label>
  <label><input type="checkbox" id="showCoords"> Coordinates</label>
  <div class="legend" id="legend"></div>
  <div class="muted">Drag to pan, scroll to zoom, hover a tile.</div>
  <div id="info">—</div>
</aside>
<script>
const D = __DATA__;
const R = 20, SQ3 = Math.sqrt(3);
const TERRAIN = { GRASS:"#8fbf5a", PLAINS:"#d9c36a", DESERT:"#ead9a6", TUNDRA:"#a59f8a", SNOW:"#eef2f4",
                  COAST:"#8cc3e6", OCEAN:"#3d78b8" };
const FEATURE = { FOREST:"#2f6b2f", JUNGLE:"#1f8a6a", MARSH:"#5f8f8a", OASIS:"#38b0c9", REEF:"#e88fb0",
                  ICE:"#ffffff", FLOODPLAINS:"#6d9e3a", FLOODPLAINS_GRASSLAND:"#6d9e3a", FLOODPLAINS_PLAINS:"#b59a3a",
                  VOLCANIC_SOIL:"#7a4a3a", VOLCANO:"#c0392b", GEOTHERMAL_FISSURE:"#d27a2c" };
const RES_COLOR = { RESOURCECLASS_BONUS:"#4c7a2a", RESOURCECLASS_LUXURY:"#7b4bc4", RESOURCECLASS_STRATEGIC:"#c0392b", RESOURCECLASS_ARTIFACT:"#8a6d3b" };
const TACK = { ICON_DISTRICT_CITY_CENTER:["C","#c0392b"], ICON_DISTRICT_CAMPUS:["S","#2a6fd6"] };
const OWNER = ["#e6194b","#3cb44b","#4363d8","#f58231","#911eb4","#46f0f0","#f032e6","#bcf60c","#008080","#9a6324"];

const base = t => t.terrain.replace("TERRAIN_","").replace("_HILLS","").replace("_MOUNTAIN","");
const nice = s => s && s !== "NONE" ? s.replace(/^(TERRAIN|FEATURE|RESOURCE|IMPROVEMENT|DISTRICT|BUILDING)_/,"").toLowerCase().replace(/_/g," ") : "";
// The map wraps east-west. Start drawing at the column after the widest run of empty
// columns, so a shown area that crosses the wrap is drawn in one piece.
const START = (() => {
  const used = new Set(D.tiles.map(t => t.x));
  if (!used.size || used.size === D.w) return 0;
  let best = 0, bestLen = -1;
  for (let c = 0; c < D.w; c++) {
    if (used.has(c) || !used.has((c + D.w - 1) % D.w)) continue;  // c starts an empty run
    let len = 0; while (!used.has((c + len) % D.w)) len++;
    if (len > bestLen) { bestLen = len; best = (c + len) % D.w; }
  }
  return best;
})();
const col = x => ((x - START) % D.w + D.w) % D.w;
const centre = (x, y) => [(col(x) + 0.5 * (y & 1)) * SQ3 * R + SQ3 * R / 2, (D.h - 1 - y) * 1.5 * R + R];
const corner = (cx, cy, k, r = R) => { const a = Math.PI / 180 * (60 * k - 30); return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
const hexPts = (cx, cy, r) => [0,1,2,3,4,5].map(k => corner(cx, cy, k, r).map(v => v.toFixed(1)).join(",")).join(" ");
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

const svg = document.getElementById("map");
const world = el("g", {}, svg);
const hiddenLayer = el("g", { opacity: 0.28, display: "none" }, world);
const tileLayer = el("g", {}, world), riverLayer = el("g", {}, world), labelLayer = el("g", {}, world),
      coordLayer = el("g", { display: "none" }, world), tackLayer = el("g", {}, world);

function drawTile(t, layer, interactive) {
  const [cx, cy] = centre(t.x, t.y);
  const g = el("g", {}, layer);
  const fill = t.mountain ? "#6e675d" : (TERRAIN[base(t)] || "#cccccc");
  el("polygon", { points: hexPts(cx, cy, R - 0.6), fill, stroke: t.owner >= 0 ? OWNER[t.owner % OWNER.length] : "rgba(0,0,0,.18)",
                  "stroke-width": t.owner >= 0 ? 2.2 : 0.8 }, g);
  if (t.hills) el("path", { d: `M${cx-8},${cy+7} L${cx-3},${cy} L${cx+2},${cy+7} M${cx},${cy+7} L${cx+5},${cy+1} L${cx+10},${cy+7}`,
                            fill: "none", stroke: "rgba(60,40,20,.55)", "stroke-width": 1.4 }, g);
  if (t.mountain) el("path", { d: `M${cx-10},${cy+8} L${cx},${cy-9} L${cx+10},${cy+8} Z`, fill: "#4a443c", stroke: "#efece6", "stroke-width": 1 }, g);
  const f = (t.feature || "NONE").replace("FEATURE_", "");
  if (f !== "NONE") el("circle", { cx: cx - 9, cy: cy - 7, r: 4.5, fill: FEATURE[f] || "#555", stroke: "rgba(0,0,0,.3)", "stroke-width": .6 }, g);
  if (t.natural_wonder) el("circle", { cx, cy, r: 7, fill: "none", stroke: "#f1c40f", "stroke-width": 2.5 }, g);
  if (t.is_city) el("rect", { x: cx - 6, y: cy - 6, width: 12, height: 12, fill: "#fff", stroke: "#222", "stroke-width": 1.5 }, g);
  else if (t.district && t.district !== "NONE") el("rect", { x: cx - 5, y: cy - 5, width: 10, height: 10, fill: "#ddd", stroke: "#444" }, g);
  if (interactive) g.addEventListener("mouseenter", () => showInfo(t));
  return [cx, cy];
}

function drawRivers(t, layer) {
  const [cx, cy] = centre(t.x, t.y);
  // Edges by corner pair; corner k sits at 60k-30 degrees, clockwise on screen from east,
  // so 0 is upper-right, 3 lower-left, 5 top: W = 3-4, NW = 4-5, NE = 5-0.
  [["river_w", 3, 4], ["river_nw", 4, 5], ["river_ne", 5, 0]].forEach(([key, a, b]) => {
    if (!t[key]) return;
    const [x1, y1] = corner(cx, cy, a), [x2, y2] = corner(cx, cy, b);
    el("line", { x1, y1, x2, y2, stroke: "#1f6fd1", "stroke-width": 3.2, "stroke-linecap": "round" }, layer);
  });
}

function drawLabels(t) {
  const [cx, cy] = centre(t.x, t.y);
  if (t.resource && t.resource !== "NONE") {
    const cls = D.resourceClass[t.resource];
    el("circle", { cx: cx + 9, cy: cy - 7, r: 4, fill: RES_COLOR[cls] || "#333", stroke: "#fff", "stroke-width": 1 }, tileLayer);
    const txt = el("text", { x: cx, y: cy + 14, "text-anchor": "middle", "font-size": 6.5, fill: "#111", "paint-order": "stroke",
                             stroke: "rgba(255,255,255,.75)", "stroke-width": 2 }, labelLayer);
    txt.textContent = nice(t.resource);
  }
  const c = el("text", { x: cx, y: cy + 3, "text-anchor": "middle", "font-size": 6, fill: "#222" }, coordLayer);
  c.textContent = t.x + "," + t.y;
}

D.hidden.forEach(t => drawTile(t, hiddenLayer, true));
D.tiles.forEach(t => drawTile(t, tileLayer, true));
D.tiles.forEach(t => drawRivers(t, riverLayer));
D.tiles.forEach(drawLabels);
D.tacks.forEach(k => {
  const [cx, cy] = centre(k.x, k.y);
  const [letter, color] = TACK[k.icon] || ["?", "#333"];
  const g = el("g", {}, tackLayer);
  el("circle", { cx, cy: cy - 2, r: 8.5, fill: color, stroke: "#fff", "stroke-width": 2 }, g);
  const t = el("text", { x: cx, y: cy + 1.6, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#fff" }, g);
  t.textContent = letter;
  el("title", {}, g).textContent = `${k.name} (${k.x}, ${k.y})`;
});

function showInfo(t) {
  const skip = new Set(["neighbours"]);
  const lines = [`(${t.x}, ${t.y})  index ${t.i}`];
  for (const k in t) if (!skip.has(k) && !["x","y","i"].includes(k)) {
    const v = t[k]; if (v === 0 || v === "NONE" || v === -1) continue;
    lines.push(`${k}: ${typeof v === "string" ? nice(v) || v : v}`);
  }
  document.getElementById("info").textContent = lines.join("\n");
}

document.getElementById("summary").textContent =
  `turn ${D.turn} · ${D.w}×${D.h} map · ${D.tiles.length} tiles shown` + (D.hidden.length ? ` · ${D.hidden.length} hidden` : "") +
  (D.tacks.length ? ` · ${D.tacks.length} tacks` : "");
const legend = [["grass", TERRAIN.GRASS], ["plains", TERRAIN.PLAINS], ["desert", TERRAIN.DESERT], ["tundra", TERRAIN.TUNDRA],
  ["snow", TERRAIN.SNOW], ["coast", TERRAIN.COAST], ["ocean", TERRAIN.OCEAN], ["mountain", "#6e675d"],
  ["bonus res.", RES_COLOR.RESOURCECLASS_BONUS], ["luxury res.", RES_COLOR.RESOURCECLASS_LUXURY],
  ["strategic res.", RES_COLOR.RESOURCECLASS_STRATEGIC], ["river", "#1f6fd1"], ["city tack", TACK.ICON_DISTRICT_CITY_CENTER[1]],
  ["campus tack", TACK.ICON_DISTRICT_CAMPUS[1]]];
document.getElementById("legend").innerHTML = legend.map(([n, c]) => `<span><span class="sw" style="background:${c}"></span>${n}</span>`).join("")
  + `<span class="muted" style="grid-column:1/-1">dot top-left: feature · ^^: hills · coloured edge: owner</span>`;
if (!D.hidden.length) document.getElementById("showHidden").parentElement.style.display = "none";
document.getElementById("showHidden").onchange = e => hiddenLayer.setAttribute("display", e.target.checked ? "inline" : "none");
document.getElementById("showRes").onchange = e => labelLayer.setAttribute("display", e.target.checked ? "inline" : "none");
document.getElementById("showCoords").onchange = e => coordLayer.setAttribute("display", e.target.checked ? "inline" : "none");

// Pan and zoom by editing the viewBox; start fitted to the shown tiles.
const pts = D.tiles.map(t => centre(t.x, t.y));
let vb = pts.length ? (() => {
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  return [Math.min(...xs) - 2 * R, Math.min(...ys) - 2 * R, Math.max(...xs) - Math.min(...xs) + 4 * R, Math.max(...ys) - Math.min(...ys) + 4 * R];
})() : [0, 0, D.w * SQ3 * R, D.h * 1.5 * R];
const apply = () => svg.setAttribute("viewBox", vb.map(v => v.toFixed(1)).join(" "));
apply();
svg.addEventListener("wheel", e => {
  e.preventDefault();
  const s = e.deltaY > 0 ? 1.15 : 1 / 1.15;
  const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
  const m = p.matrixTransform(svg.getScreenCTM().inverse());  // mouse in map units
  vb = [m.x - (m.x - vb[0]) * s, m.y - (m.y - vb[1]) * s, vb[2] * s, vb[3] * s];
  apply();
}, { passive: false });
let drag = null;
svg.addEventListener("pointerdown", e => { drag = [e.clientX, e.clientY]; svg.classList.add("dragging"); svg.setPointerCapture(e.pointerId); });
svg.addEventListener("pointermove", e => {
  if (!drag) return;
  const rect = svg.getBoundingClientRect(), scale = Math.max(vb[2] / rect.width, vb[3] / rect.height);
  vb[0] -= (e.clientX - drag[0]) * scale; vb[1] -= (e.clientY - drag[1]) * scale; drag = [e.clientX, e.clientY]; apply();
});
svg.addEventListener("pointerup", () => { drag = null; svg.classList.remove("dragging"); });
</script>
</body></html>
"""
