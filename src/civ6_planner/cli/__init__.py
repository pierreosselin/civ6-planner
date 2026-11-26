"""Command line: python -m civ6_planner <command>."""
# The parser is here; maps.py picks the map and settings a command works on,
# commands.py has one function per command.
import argparse

from .. import planner
from . import commands, maps


def main(argv=None):
    ap = argparse.ArgumentParser(prog="civ6_planner", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="plan tacks from the newest save's map dump (or --map)")
    maps.add_map_args(p)
    p.add_argument("--seed", type=int, help="random seed, for repeatable choices")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--dry-run", action="store_true", help="print the plan instead of writing it")
    p.set_defaults(func=commands.cmd_plan)

    p = sub.add_parser("watch", help="re-plan each time the game saves")
    p.add_argument("--seed", type=int)
    p.add_argument("--planner", choices=planner.METHODS, default="mip")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between checks")
    p.set_defaults(func=commands.cmd_watch)

    p = sub.add_parser("clear", help="write an empty plan")
    p.set_defaults(func=commands.cmd_clear)

    p = sub.add_parser("dump", help="export the newest save's map dump to JSON/CSV")
    p.add_argument("--save")
    p.add_argument("--full", action="store_true",
                   help="the whole-map capture made with Ctrl+Shift+F, e.g. -o data/NAME/map.json")
    p.add_argument("-o", "--output", default="map.json")
    p.add_argument("--csv")
    p.set_defaults(func=commands.cmd_dump)

    p = sub.add_parser("view", help="draw a map (and optionally the plan) as an HTML page")
    maps.add_map_args(p)
    p.add_argument("--plan", action="store_true", help="run the planner and draw its tacks")
    p.add_argument("--seed", type=int, help="planner seed")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("-o", "--output", default="view.html")
    p.add_argument("--open", action="store_true", help="open the page in your browser")
    p.set_defaults(func=commands.cmd_view)

    p = sub.add_parser("make-map", help="save a masked scenario as a test case data/NAME/")
    maps.add_map_args(p)
    p.add_argument("name", help="map name, e.g. continents-start")
    p.set_defaults(func=commands.cmd_make_map)

    p = sub.add_parser("results", help="run the planner on every test case in data/ and write a results folder")
    p.add_argument("-o", "--output", help="folder (default results/<date-time>)")
    p.add_argument("--seed", type=int, default=1, help="planner seed (default 1)")
    p.add_argument("--planner", choices=planner.METHODS, default="mip", help="mip (default) or the greedy stub")
    p.add_argument("--config", metavar="FILE", help="settings TOML overlaid last (after config/default.toml "
                                                     "and the test case's config.toml)")
    p.add_argument("--only", nargs="+", metavar="CASE", help="only these test cases, by exact name (e.g. continents shuffle-radius6)")
    p.add_argument("--open", action="store_true", help="open index.html in your browser")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="don't print each map's optimisation log, only the summary")
    p.set_defaults(func=commands.cmd_results)

    p = sub.add_parser("install-mod", help="copy the mod into the game's Mods folder")
    p.set_defaults(func=commands.cmd_install_mod)

    args = ap.parse_args(argv)
    args.func(args)
