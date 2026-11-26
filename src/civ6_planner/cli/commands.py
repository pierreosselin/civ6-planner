"""The commands: one cmd_<name>(args) per subcommand."""
import argparse
import csv
import json
import os
import random
import shutil
import sys
import time

from .. import dataset, dump, metrics, paths, planner, results, tacks, viewer
from ..gamemap import GameMap
from ..rules import Rules
from . import maps


def cmd_plan(args):
    d, label, _ = maps.load(args)
    gmap = GameMap(d)
    print(f"Map from {label}: turn {gmap.turn}, {len(gmap)} revealed tiles")
    rules = Rules.from_game()
    p = planner.solve(gmap, rules, random.Random(args.seed), args.planner, maps.settings(args))
    planned, notes = planner.to_tacks(gmap, rules, p), planner.explain(gmap, rules, p, args.planner)
    for line in metrics.format_metrics(metrics.plan_metrics(gmap, rules, p)):
        print("  " + line)
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
    d, label = maps.dump_from_save(args.save, "full" if args.full else "revealed")
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
    d, label, original = maps.load(args)
    gmap = GameMap(d)
    planned: list[planner.Tack] = []
    notes: list[str] = []
    if args.plan:
        planned, notes = planner.plan(gmap, Rules.from_game(), random.Random(args.seed), args.planner,
                                   maps.settings(args))
    path = viewer.write(d, args.output, title=label, tacks=planned, hidden_from=original)
    for note in notes:
        print(f"  {note}")
    print(f"{label}: {len(gmap)} tiles{', ' + str(len(planned)) + ' tacks' if args.plan else ''} -> {path}")
    if args.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(path))


def cmd_make_map(args):
    """Save a masked scenario as a test case data/<name>/, so every run uses the same one."""
    if not args.map or not args.mask:
        sys.exit("make-map needs --map (a full test map) and --mask.")
    d, label, _ = maps.load(args)
    d["id"] = args.name
    d["scenario"]["source"] = args.map
    folder = dataset.save_case(args.name, d)
    print(f"{label}: {len(d['tiles'])} tiles -> {folder}/{{map.json, config.toml}}")


def cmd_results(args):
    out = args.output or os.path.join("results", time.strftime("%Y%m%d-%H%M%S"))
    scenarios = dataset.cases()
    if args.only:
        unknown = [k for k in args.only if k not in scenarios]
        if unknown:
            sys.exit(f"unknown test case {', '.join(unknown)}; cases: {', '.join(scenarios)}")
        scenarios = list(args.only)
    summary = results.run(out, scenarios, seed=args.seed, method=args.planner, config_file=args.config,
                          echo=None if args.quiet else print)
    for line in results.summary_lines(summary, out):
        print(line)
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
