"""The revealed map as a hex grid.

Civ VI stores plots in offset coordinates: index = y * width + x, y grows northwards,
and odd rows sit half a hex to the east ("odd-r"). Maps wrap east-west by default.
This was checked against the neighbour lists the game itself reports.
"""
from __future__ import annotations

from typing import Any, Iterator

Tile = dict[str, Any]      # one plot from the dump: x, y, terrain, YIELD_*, … (see CLAUDE.md)
XY = tuple[int, int]       # a tile's (x, y)


class GameMap:
    def __init__(self, dump: dict[str, Any], wrap_x: bool = True):
        self.width = dump["w"]
        self.height = dump["h"]
        self.turn = dump["turn"]
        self.player = dump["player"]
        self.wrap_x = wrap_x
        self.tiles: dict[XY, Tile] = {(t["x"], t["y"]): t for t in dump["tiles"]}
        self._by_index = {t["i"]: t for t in dump["tiles"]}
        self.own_cities = dump["cities"]
        # The player's own map tacks (from the mod's PIN records): {x, y, name, icon}.
        self.pins: list[dict[str, Any]] = dump.get("pins", [])

    def __iter__(self) -> Iterator[Tile]:
        return iter(self.tiles.values())

    def __len__(self) -> int:
        return len(self.tiles)

    def neighbours(self, tile: Tile) -> list[Tile]:
        """Revealed neighbours of a tile, using the adjacency the game reported."""
        return [self._by_index[i] for i in tile["neighbours"] if i in self._by_index]

    @staticmethod
    def _axial(x: int, y: int) -> XY:
        return x - (y - (y & 1)) // 2, y

    def distance(self, a: Tile | XY, b: Tile | XY) -> int:
        """Hex distance between two tiles (or (x, y) pairs), accounting for wrap."""
        ax, ay = (a["x"], a["y"]) if isinstance(a, dict) else a
        bx, by = (b["x"], b["y"]) if isinstance(b, dict) else b
        shifts = (-self.width, 0, self.width) if self.wrap_x else (0,)
        q2, r2 = self._axial(bx, by)
        return min((abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2
                   for q1, r1 in (self._axial(ax + dx, ay) for dx in shifts))

    def within(self, centre: Tile | XY, radius: int) -> list[Tile]:
        """Revealed tiles at distance 1..radius from centre (centre excluded)."""
        cx, cy = (centre["x"], centre["y"]) if isinstance(centre, dict) else centre
        out, seen = [], set()
        for y in range(max(0, cy - radius), min(self.height, cy + radius + 1)):
            for x in range(cx - radius - 1, cx + radius + 2):
                if self.wrap_x:
                    x %= self.width
                t = self.tiles.get((x, y))
                if t is not None and 0 < self.distance((cx, cy), t) <= radius and t["i"] not in seen:
                    seen.add(t["i"])
                    out.append(t)
        return out

    def city_positions(self) -> set[XY]:
        """Every known city centre: the player's own plus any other revealed city tiles."""
        positions = {(c["x"], c["y"]) for c in self.own_cities}
        positions |= {(t["x"], t["y"]) for t in self if t.get("is_city")}
        return positions
