---
name: mod-dev
description: Change, install or debug the Map Dump Civ VI mod (mod/mapdump, Lua). Use before editing any file under mod/, adding a hotkey or tack type, or when the mod seems not to run in game.
---

# Changing the Map Dump mod

Read the "Lessons learnt" section of CLAUDE.md first: it lists what does and doesn't
work on this Linux port, established by trial.

## Files

| File | Role |
|---|---|
| `mapdump.modinfo` | components; the `ReplaceUIScript` on `StatusMessagePanel` is the live entry point |
| `ui/mapdump_statusmessagepanel.lua` | the hook: includes the base panel, then the core; hotkeys; load/turn events |
| `ui/mapdump_core.lua` | `DumpMap(full)`, `MapDump_SafeDump`, `MapDump_CaptureFull`, `MapDump_PlaceTacks` |
| `ui/mapdump_plan.lua` | the plan (`MapDump_Plan = { {x, y, icon, name}, … }`), rewritten by `civ6_planner plan` |
| `ui/mapdump.lua`, `ui/mapdump.xml` | own UI context: never runs on this install (leftover) |
| `mapdump_probe.sql` | harmless probe table proving local mod files load (leftover) |

## Rules

- Edit `mod/mapdump`, then `civ6-planner install-mod` (it keeps
  the installed plan). Never edit only the installed copy.
- `.modinfo` changed → the user must fully restart Civ VI. Lua only → loading a save is
  enough (restart if in doubt). Files read through `include()` are re-read on each call.
- Lowercase file names. Every new file goes in both `<ImportFiles>` and `<Files>`.
- No Lua interpreter here: keep edits small, mirror existing patterns, wrap game API
  calls in `pcall` (see `Call()` in core), and check the game's own Lua under
  `~/.local/share/Steam/steamapps/common/Sid Meier's Civilization VI/steamassets/` for
  exact API names before using one.
- Output only through `MapDump_SetConfig(key, text)` (ends up in the next save); end
  values with `\n` so `dump.save_lines` can cut them out. Use a new key per kind of
  data, and a `MAPDUMP|KIND|key=value|…` record format.
- On-screen feedback: `Notify(text)` in the hook (calls the panel's `OnStatusMessage`).
- New hotkey: add a branch in the hook's `OnInput` (Ctrl+Shift+letter, `KeyEvents.KeyUp`,
  return `true` when handled). Taken: T (tacks), F (full capture), C (clear planner
  tacks), X (clear all tacks).

## Debugging when "nothing happens"

1. `grep -n mapdump ~/.local/share/aspyr-media/"Sid Meier's Civilization VI"/Logs/Modding.log | tail`:
   the mod and its components should be listed as applied for the current game.
2. Read the status lines from the newest save (snippet in **plan-in-game**):
   `statusmessagepanel hook started` proves the hook ran; `ERROR` lines carry Lua errors
   caught by `pcall`.
3. Prove files load at all: the probe table `MapDumpProbe` should exist in
   `Cache/DebugGameplay.sqlite` (query with Python `sqlite3`, read-only).
4. Don't retry Lua.log, the clipboard, or `AddUserInterfaces`; they're known not to work
   here.
