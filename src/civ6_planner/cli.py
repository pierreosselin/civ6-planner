"""Command line: python -m civ6_planner <command>."""
import argparse
import csv
import json
import os
import random
import shutil
import sys
import time

from . import config, dataset, dump, paths, planner, results, tacks, viewer
from .gamemap import GameMap
from .rules import Rules


def _dump_from_save(save, wanted="revealed"):
    path = save or paths.newest_save()
    if not path:
        sys.exit(f"No save found in {paths.SAVES_DIR}.")
    lines = dump.save_lines(path)
    data = [d for d in dump.read_dumps(lines) if dump.scope(d) == wanted]
    if not data:
        for line in dump.status_lines(lines):
            print("  in save:", line, file=sys.stderr)
        hint = "press Ctrl+Shift+F in game, then save" if wanted == "full" else \
            "is the Map Dump mod enabled, and has a turn passed?"
        sys.exit(f"No {wanted} map dump in {path}: {hint}")
    return data[-1], os.path.basename(path)


def _load(args):
    """The map to work on (a dump dict), a label saying where it came from, and the
    unmasked map when --mask hid part of it (else None).

    --map NAME (a test case in data/, or any map JSON) or else the newest save; then
    --mask hides all but part of it, to make a test scenario.
    """
    if args.map:
        d, label = dataset.load_map(args.map), args.map
    else:
        d, label = _dump_from_save(args.save)
    original = dataset.source_of(d)
    if args.mask:
        original = d
        centre = dataset.player_centre(d) if args.at_player else args.centre
        d = dataset.mask(d, mode=args.mask, size=args.size, centre=centre, seed=args.mask_seed,
                         resources=args.resources)
        label += f" masked ({args.mask} {args.size}, seed {args.mask_seed}, centre {tuple(d['scenario']['centre'] or ())})"
    return d, label, original


def _config(args):
    """Settings: config/default.toml, then the test case's config.toml (with --map),
    then --config."""
    case = dataset.config_path(args.map) if getattr(args, "map", None) else None
    return config.load(case, args.config)


def _add_map_args(p):
    p.add_argument("--save", help="use this .Civ6Save instead of the newest")
    p.add_argument("--map", help="use a test case instead of a save: a name in data/ (its map.json and "
                                  "config.toml), or a map JSON path")
    p.add_argument("--mask", choices=["blob", "radius", "revealed"],
                   help="show only part of the map: a random explored-looking blob, a radius, "
                        "or what the player had revealed at capture")
    p.add_argument("--size", type=int, default=60, help="blob: tiles shown; radius: hex radius (default 60)")
    p.add_argument("--centre", type=int, nargs=2, metavar=("X", "Y"), help="mask centre (default: random land)")
    p.add_argument("--at-player", action="store_true",
                   help="centre the mask on the middle of what the player had revealed at capture")
    p.add_argument("--mask-seed", type=int, help="seed for the mask")
    p.add_argument("--resources", choices=["all", "visible"], default="all",
                   help="mask: keep all resources, or only those visible at capture")


def cmd_plan(args):
    d, label, _ = _load(args)
    gmap = GameMap(d)
    print(f"Map from {label}: turn {gmap.turn}, {len(gmap)} revealed tiles")
    planned, notes = planner.plan(gmap, Rules.from_game(), random.Random(args.seed), args.planner,
                                   _config(args))
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
    d, label = _dump_from_save(args.save, "full" if args.full else "revealed")
    tiles = d["tiles"]
    if os.path.dirname(args.output):
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    print(f"{label}: turn {d['turn']}, {len(tiles)} tiles ({dump.scope(d)}) -> {args.output}")
    case_config = os.path.join(os.path.dirname(args.output) or ".", dataset.CONFIG_FILE)
    if os.path.basename(args.output) == dataset.MAP_FILE and not os.path.exists(case_config):
        with open(case_config, "w") as f:   # a new test case: give it its (empty) settings
            f.write(dataset.CONFIG_TEMPLATE)
        print(f"  and {case_config}")
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
                cmd_plan(argparse.Namespace(save=save, map=None, mask=None, seed=args.seed, dry_run=False,
                                            planner=args.planner, config=args.config))
            except SystemExit as e:
                print(e, file=sys.stderr)
        time.sleep(args.interval)


def cmd_view(args):
    d, label, original = _load(args)
    gmap = GameMap(d)
    planned, notes = [], []
    if args.plan:
        planned, notes = planner.plan(gmap, Rules.from_game(), random.Random(args.seed), args.planner,
                                   _config(args))
    path = viewer.write(d, args.output, title=label, tacks=planned, notes=notes, hidden_from=original)
    print(f"{label}: {len(gmap)} tiles{', ' + str(len(planned)) + ' tacks' if args.plan else ''} -> {path}")
    if args.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(path))


def cmd_make_map(args):
    """Save a masked scenario as a test case data/<name>/, so every run uses the same one."""
    if not args.map or not args.mask:
        sys.exit("make-map needs --map (a full test map) and --mask.")
    d, label, _ = _load(args)
    d["id"] = args.name
    d["scenario"]["source"] = args.map
    folder = dataset.save_case(args.name, d)
    print(f"{label}: {len(d['tiles'])} tiles -> {folder}/{{map.json, config.toml}}")


def cmd_results(args):
    out = args.output or os.path.join("results", time.strftime("%Y%m%d-%H%M%S"))
    scenarios = dataset.cases()
    if args.only:
        scenarios = [s for s in scenarios if any(k in s for k in args.only)]
    summary = results.run(out, scenarios, seed=args.seed, method=args.planner, config_file=args.config,
                          echo=None if args.quiet else print)
    for r in summary["scenarios"]:
        counts: dict[str, int] = {}
        for t in r["tacks"]:
            kind = "City" if t["icon"] == planner.CITY_ICON else planner.district_name(t["icon"].removeprefix("ICON_"))
            counts[kind] = counts.get(kind, 0) + 1
        placed = ", ".join(f"{n} {name}" for name, n in counts.items()) or "nothing"
        solver = r["solver"]
        print(f"  {r['name']:<22} score {r['score']:>8}  {solver.get('status', '')} {solver.get('seconds', '')}s  {placed}")
    print(f"-> {os.path.join(out, 'index.html')}")
    if args.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(os.path.join(out, "index.html")))


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

    p = sub.add_parser("plan", help="plan tacks from the newest save's map dump (or --map)")
    _add_map_args(p)
    p.add_argument("--seed", type=int, help="random seed, for repeatable choices")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--dry-run", action="store_true", help="print the plan instead of writing it")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("watch", help="re-plan each time the game saves")
    p.add_argument("--seed", type=int)
    p.add_argument("--planner", choices=planner.METHODS, default="mip")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between checks")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("clear", help="write an empty plan")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("dump", help="export the newest save's map dump to JSON/CSV")
    p.add_argument("--save")
    p.add_argument("--full", action="store_true",
                   help="the whole-map capture made with Ctrl+Shift+F, e.g. -o data/NAME/map.json")
    p.add_argument("-o", "--output", default="map.json")
    p.add_argument("--csv")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("view", help="draw a map (and optionally the plan) as an HTML page")
    _add_map_args(p)
    p.add_argument("--plan", action="store_true", help="run the planner and draw its tacks")
    p.add_argument("--seed", type=int, help="planner seed")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("-o", "--output", default="view.html")
    p.add_argument("--open", action="store_true", help="open the page in your browser")
    p.set_defaults(func=cmd_view)

    p = sub.add_parser("make-map", help="save a masked scenario as a test case data/NAME/")
    _add_map_args(p)
    p.add_argument("name", help="map name, e.g. continents-start")
    p.set_defaults(func=cmd_make_map)

    p = sub.add_parser("results", help="run the planner on every test case in data/ and write a results folder")
    p.add_argument("-o", "--output", help="folder (default results/<date-time>)")
    p.add_argument("--seed", type=int, default=1, help="planner seed (default 1)")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--only", nargs="+", metavar="TEXT", help="only maps whose name contains TEXT")
    p.add_argument("--open", action="store_true", help="open index.html in your browser")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="don't print each map's optimisation log, only the summary")
    p.set_defaults(func=cmd_results)

    p = sub.add_parser("install-mod", help="copy the mod into the game's Mods folder")
    p.set_defaults(func=cmd_install_mod)

    args = ap.parse_args(argv)
    args.func(args)
