"""Where the game keeps its user data on the native Linux (Aspyr) port."""
import os

USER_DIR = os.path.expanduser(
    os.environ.get("CIV6_USER_DIR", "~/.local/share/aspyr-media/Sid Meier's Civilization VI")
)
SAVES_DIR = os.path.join(USER_DIR, "Saves")
MODS_DIR = os.path.join(USER_DIR, "Mods")
GAMEPLAY_DB = os.path.join(USER_DIR, "Cache", "DebugGameplay.sqlite")
LUA_LOG = os.path.join(USER_DIR, "Logs", "Lua.log")

INSTALLED_MOD = os.path.join(MODS_DIR, "mapdump")
INSTALLED_PLAN = os.path.join(INSTALLED_MOD, "ui", "mapdump_plan.lua")

# The mod's source, shipped in this repository.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOD_SOURCE = os.path.join(REPO_ROOT, "mod", "mapdump")


def newest_save():
    """Path of the most recently written .Civ6Save (autosaves included), or None."""
    saves = []
    for root, _, files in os.walk(SAVES_DIR):
        saves += [os.path.join(root, f) for f in files if f.endswith(".Civ6Save")]
    return max(saves, key=os.path.getmtime) if saves else None
