"""The index page of a results folder: one card per test case with its score, tacks
and notes, linking to its map and log."""
from __future__ import annotations

import html
from typing import Any


def index(summary: dict[str, Any], run_name: str) -> str:
    e = html.escape
    cards = []
    for r in summary["scenarios"]:
        rows = "".join(
            f"<tr><td>{e(t['name'])}{''.join(f' +{v} {_short(k).lower()}' for k, v in t.get('yields', {}).items())}</td><td>({t['x']}, {t['y']})</td>"
            f"<td>{e(_short(t['tile'].get('terrain')))}{' · ' + e(_short(t['tile']['feature'])) if t['tile'].get('feature') not in (None, 'NONE') else ''}"
            f"{' · ' + e(_short(t['tile']['resource'])) if t['tile'].get('resource') not in (None, 'NONE') else ''}</td></tr>"
            for t in r["tacks"]) or '<tr><td colspan="3" class="muted">no tacks placed</td></tr>'
        notes = "".join(f"<li>{e(n)}</li>" for n in r["notes"])
        cards.append(f"""<section class="card">
  <div class="head"><h2>{e(r['name'])}</h2><span><a class="btn" href="{e(r['log'])}">Log</a> · <a class="btn" href="{e(r['map'])}">Open map →</a></span></div>
  <p class="muted">{e(r['description'])} · {r['tiles']} tiles · <b>score {r['score']}</b></p>
  <table><thead><tr><th>Tack</th><th>Tile</th><th>Terrain</th></tr></thead><tbody>{rows}</tbody></table>
  <ul>{notes}</ul>
</section>""")
    return _INDEX.replace("__RUN__", e(run_name)).replace("__SEED__", e(f'{summary["method"]} planner, seed {summary["seed"]}')) \
        .replace("__CARDS__", "\n".join(cards))


def _short(type_name: str | None) -> str:
    """TERRAIN_GRASS_HILLS -> Grass hills."""
    if not type_name:
        return ""
    return type_name.split("_", 1)[-1].replace("_", " ").capitalize()


_INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Planner results</title>
<style>
  :root { --bg:#f7f6f2; --panel:#ffffff; --ink:#1f1e1b; --muted:#6b6963; --line:#dddbd3; --accent:#2f5fb3; }
  @media (prefers-color-scheme: dark) { :root { --bg:#1a1a19; --panel:#242422; --ink:#f0efec; --muted:#a3a29b; --line:#3a3a37; --accent:#8fb0ec; } }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; font:14px/1.5 system-ui, sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:1100px; margin:0 auto; }
  h1 { font-size:20px; margin:0 0 4px; }
  h2 { font-size:15px; margin:0; }
  .muted { color:var(--muted); font-size:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:14px; margin-top:18px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
  .head { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .btn { color:var(--accent); text-decoration:none; font-size:13px; white-space:nowrap; }
  .btn:hover { text-decoration:underline; }
  table { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0; }
  th, td { text-align:left; padding:4px 6px; border-bottom:1px solid var(--line); }
  th { font-weight:600; color:var(--muted); font-size:12px; }
  ul { padding-left:18px; margin:6px 0 0; font-size:12px; color:var(--muted); }
</style></head>
<body><main>
<h1>Planner results</h1>
<p class="muted">Run <b>__RUN__</b> · __SEED__ · each map opens with the tacks drawn (red C city, blue S campus)</p>
<div class="grid">
__CARDS__
</div>
</main></body></html>
"""
