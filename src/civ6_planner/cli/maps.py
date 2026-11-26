"""Which map and settings a command works on: the newest save's dump, or a test case
(--map), optionally masked (--mask), and the settings files that go with it."""
import os
import sys

from .. import config, dataset, dump, paths


def dump_from_save(save, wanted="revealed"):
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


def load(args):
    """The map to work on (a dump dict), a label saying where it came from, and the
    unmasked map when --mask hid part of it (else None).

    --map NAME (a test case in data/, or any map JSON) or else the newest save; then
    --mask hides all but part of it, to make a test scenario.
    """
    if args.map:
        d, label = dataset.load_map(args.map), args.map
    else:
        d, label = dump_from_save(args.save)
    original = dataset.source_of(d)
    if args.mask:
        original = d
        centre = dataset.player_centre(d) if args.at_player else args.centre
        d = dataset.mask(d, mode=args.mask, size=args.size, centre=centre, seed=args.mask_seed,
                         resources=args.resources)
        label += f" masked ({args.mask} {args.size}, seed {args.mask_seed}, centre {tuple(d['scenario']['centre'] or ())})"
    return d, label, original


def settings(args):
    """Settings: config/default.toml, then the test case's config.toml (with --map),
    then --config."""
    case = dataset.config_path(args.map) if getattr(args, "map", None) else None
    return config.load(case, args.config)


def add_map_args(p):
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
