"""A standalone HTML view of a map, so plans can be checked without opening Civ VI.

The page embeds the map as JSON and draws it as SVG hexes in the game's layout
(odd rows shifted east, north up). Drag to pan, scroll to zoom, hover for a tile's
fields. Hidden tiles of a masked map can be shown faded.
"""
import html
import json
import os

from .rules import Rules


def _resource_classes():
    try:
        return Rules.from_game().resource_class
    except FileNotFoundError:
        return {}


TEMPLATE = os.path.join(os.path.dirname(__file__), "viewer.html")   # the page, with __TITLE__ and __DATA__
_KEEP = {"i", "x", "y", "terrain", "owner"}


def _slim(t: dict) -> dict:
    """A tile with only what the page uses: no neighbour list, no empty fields (zero,
    false, NONE, -1; the page treats a missing field the same). Halves the page."""
    return {k: v for k, v in t.items() if k in _KEEP or (k != "neighbours" and v not in (0, False, "NONE", -1, None))}


def write(d, path, title="", tacks=(), hidden_from=None):
    """Write the page for dump `d`. hidden_from: the unmasked map, if d is masked."""
    shown = {t["i"] for t in d["tiles"]}
    hidden = [t for t in hidden_from["tiles"] if t["i"] not in shown] if hidden_from else []
    data = {
        "w": d["w"], "h": d["h"], "turn": d["turn"],
        "tiles": [_slim(t) for t in d["tiles"]], "hidden": [_slim(t) for t in hidden],
        "tacks": [{"x": t.x, "y": t.y, "icon": t.icon, "name": t.name, "yields": getattr(t, "yields", {})} for t in tacks],
        "resourceClass": _resource_classes(),
    }
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    page = (template
            .replace("__TITLE__", html.escape(title or "map"))
            .replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path
