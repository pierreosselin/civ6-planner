"""Writing the tack plan the mod reads when you press Ctrl+Shift+T (or load a save)."""
import os

from . import paths

HEADER = "-- Map tack plan, rewritten by civ6-planner. Empty: no tacks.\n"


def _lua_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def render(tacks):
    body = "".join(
        f"\t{{ x={t.x}, y={t.y}, icon={_lua_string(t.icon)}, name={_lua_string(t.name)} }},\n"
        for t in tacks
    )
    return HEADER + "MapDump_Plan = {\n" + body + "}\n"


def write(tacks, path=paths.INSTALLED_PLAN):
    if not os.path.isdir(os.path.dirname(path)):
        raise FileNotFoundError(f"{os.path.dirname(path)} not found; run `install-mod` first.")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(tacks))
    return path
