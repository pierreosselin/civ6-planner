"""Command line: python -m civ6_planner <command>."""
import argparse
import csv
import json
import os
import random
import shutil
import sys
import time

from . import dump, paths, planner, tacks
from .gamemap import GameMap
from .rules import Rules


def _load_map(save):
    path = save or paths.newest_save()
    if not path:
        sys.exit(f"No save found in {paths.SAVES_DIR}.")
    lines = dump.save_lines(path)
    data = list(dump.read_dumps(lines))
    if not data:
        for line in dump.status_lines(lines):
            print("  in save:", line, file=sys.stderr)
        sys.exit(f"No map dump in {path}. Is the Map Dump mod enabled, and has a turn passed?")
    return GameMap(data[-1]), path


def cmd_plan(args):
    gmap, path = _load_map(args.save)
    print(f"Map from {os.path.basename(path)}: turn {gmap.turn}, {len(gmap)} revealed tiles")
    planned, notes = planner.plan(gmap, Rules.from_game(), random.Random(args.seed))
    for note in notes:
        print("  " + note)
    if args.dry_run:
        print(tacks.render(planned), end="")
    else:
        print(f"Wrote {tacks.write(planned)}\nPress Ctrl+Shift+T in game to place the tacks.")


def cmd_clear(args):
    tacks.write([])
    print("Plan cleared. Press Ctrl+Shift+T in game to remove the planner's tacks.")


def cmd_dump(args):
    gmap, path = _load_map(args.save)
    tiles = list(gmap)
    with open(args.output, "w") as f:
        json.dump({"turn": gmap.turn, "player": gmap.player, "w": gmap.width, "h": gmap.height,
                   "tiles": tiles, "cities": gmap.own_cities}, f, indent=1)
    print(f"Turn {gmap.turn}: {len(tiles)} tiles -> {args.output}")
    if args.csv:
        columns = list(dict.fromkeys(k for t in tiles for k in t))
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for t in tiles:
                writer.writerow({**t, "neighbours": ",".join(map(str, t["neighbours"]))})
        print(f"  and {args.csv}")


def cmd_watch(args):
    """Re-plan whenever the game writes a new save (each turn's autosave)."""
    print(f"Watching {paths.SAVES_DIR}; Ctrl+C to stop.")
    last = None
    while True:
        save = paths.newest_save()
        if save and (save, os.path.getmtime(save)) != last:
            time.sleep(1)  # let the game finish writing
            last = (save, os.path.getmtime(save))
            try:
                cmd_plan(argparse.Namespace(save=save, seed=args.seed, dry_run=False))
            except SystemExit as e:
                print(e, file=sys.stderr)
        time.sleep(args.interval)


def cmd_install_mod(args):
    """Copy mod/mapdump into the game's Mods folder, keeping the current plan."""
    plan = None
    if os.path.exists(paths.INSTALLED_PLAN):
        with open(paths.INSTALLED_PLAN, encoding="utf-8") as f:
            plan = f.read()
    shutil.copytree(paths.MOD_SOURCE, paths.INSTALLED_MOD, dirs_exist_ok=True)
    if plan is not None:
        with open(paths.INSTALLED_PLAN, "w", encoding="utf-8") as f:
            f.write(plan)
    print(f"Installed {paths.MOD_SOURCE} -> {paths.INSTALLED_MOD}")
    print("Restart Civ VI if the .modinfo changed; Lua-only changes apply on loading a save.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="civ6_planner", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="plan tacks from the newest save's map dump")
    p.add_argument("--save", help="use this .Civ6Save instead of the newest")
    p.add_argument("--seed", type=int, help="random seed, for repeatable choices")
    p.add_argument("--dry-run", action="store_true", help="print the plan instead of writing it")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("watch", help="re-plan each time the game saves")
    p.add_argument("--seed", type=int)
    p.add_argument("--interval", type=float, default=2.0, help="seconds between checks")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("clear", help="write an empty plan")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("dump", help="export the newest save's map dump to JSON/CSV")
    p.add_argument("--save")
    p.add_argument("-o", "--output", default="map.json")
    p.add_argument("--csv")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("install-mod", help="copy the mod into the game's Mods folder")
    p.set_defaults(func=cmd_install_mod)

    args = ap.parse_args(argv)
    args.func(args)
