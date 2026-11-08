"""Reading the Map Dump mod's output.

The mod writes records as lines `MAPDUMP|KIND|key=value|...`. On the Linux port they
only get out of the game inside saves: the mod stores the dump in the game
configuration, which every save (autosaves included) contains, partly
zlib-compressed. Lua.log works too on builds that write one.
"""
import re
import sys
import zlib

MARKER = "MAPDUMP|"
_SAVE_LINE = re.compile(rb"MAPDUMP\|[^\x00-\x1f]*\n")


def _parse_value(key, value):
    if key == "neighbours":
        return [int(n) for n in value.split(",")]
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def parse_record(line):
    """'MAPDUMP|TILE|i=3|x=1' -> ('TILE', {'i': 3, 'x': 1}), or None if not a record."""
    pos = line.find(MARKER)
    if pos < 0:
        return None
    parts = line[pos + len(MARKER):].rstrip("\r\n").split("|")
    fields = {}
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        if sep:
            fields[key] = _parse_value(key, value)
    return parts[0], fields


def read_dumps(lines):
    """Yield every complete dump (BEGIN..END) in the lines, oldest first.

    A dump is {'id', 'turn', 'player', 'w', 'h', 'tiles': [...], 'cities': [...]}.
    """
    current = None
    for line in lines:
        record = parse_record(line)
        if record is None:
            continue
        kind, fields = record
        if kind == "BEGIN":
            current = {**fields, "tiles": [], "cities": []}
        elif current is None:
            continue
        elif kind == "TILE":
            current["tiles"].append(fields)
        elif kind == "CITY":
            current["cities"].append(fields)
        elif kind == "ERROR":
            print(f"warning: dump {current.get('id')} failed: {fields.get('msg')}", file=sys.stderr)
            current = None
        elif kind == "END":
            if fields.get("id") == current.get("id"):
                yield current
            current = None


def save_lines(path):
    """All MAPDUMP lines in a save: its raw bytes plus every zlib stream in it."""
    with open(path, "rb") as f:
        data = f.read()
    blobs = [data]
    pos = data.find(b"\x78\x9c")
    while pos >= 0:
        d = zlib.decompressobj()
        out = []
        # Feed in pieces so output decoded before a corrupt or chunk boundary is kept.
        for i in range(pos, len(data), 4096):
            try:
                out.append(d.decompress(data[i:i + 4096]))
            except zlib.error:
                break
            if d.eof:
                break
        blobs.append(b"".join(out))
        pos = data.find(b"\x78\x9c", pos + 2)

    lines = []
    for blob in blobs:
        lines += [m.group().decode("utf-8", "replace") for m in _SAVE_LINE.finditer(blob)]
    return lines


def status_lines(lines):
    """The mod's STATUS/TACKS/ERROR records, deduplicated, for diagnostics."""
    wanted = ("|STATUS|", "|TACKS|", "|ERROR|")
    return list(dict.fromkeys(l.strip() for l in lines if any(w in l for w in wanted)))


def scope(d):
    """'revealed' (what the player has seen; the default) or 'full' (fog ignored)."""
    return d.get("scope", "revealed")


def latest_dump_from_save(path, wanted="revealed"):
    dumps = [d for d in read_dumps(save_lines(path)) if scope(d) == wanted]
    return dumps[-1] if dumps else None
