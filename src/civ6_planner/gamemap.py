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

    # Directions of `neighbours`: 0 NE, 1 E, 2 SE, 3 SW, 4 W, 5 NW. The game's flags say
    # which side of a river the plot is on: IsWOfRiver (river_w) = the plot is west of a
    # river, i.e. the river runs along its EAST edge; river_nw -> its SE edge; river_ne ->
    # its SW edge (as the game's map scripts use them). Its W, NW and NE edges are the
    # E, SE and SW edges of the neighbour on that side. Checked: the edges found agree
    # with IsRiver on every tile of both test maps, and every floodplain touches a river.
    _RIVER_FLAG = {1: (None, "river_w"), 2: (None, "river_nw"), 3: (None, "river_ne"),
                   4: (4, "river_w"), 5: (5, "river_nw"), 0: (0, "river_ne")}

    def neighbour_at(self, tile: Tile, direction: int) -> Tile | None:
        """The revealed neighbour in a direction (0 NE … 5 NW), or None."""
        i = tile["neighbours"][direction]
        return self._by_index.get(i)

    def river_edge(self, tile: Tile, direction: int) -> bool:
        """Does a river run along the tile's edge in this direction? False if the flag is
        on an unrevealed neighbour."""
        side, flag = self._RIVER_FLAG[direction]
        owner = tile if side is None else self.neighbour_at(tile, side)
        return bool(owner and owner.get(flag))

    def river_edges(self, tile: Tile) -> list[int]:
        """Directions of the tile's edges that have a river."""
        return [d for d in range(6) if self.river_edge(tile, d)]

    def rivers(self) -> dict[XY, int]:
        """River id of every tile touching a river: tiles facing each other across a river
        edge are on the same river, and consecutive edges of one river always share a
        tile, so this joins whole rivers (and rivers that meet)."""
        parent: dict[XY, XY] = {}

        def find(a: XY) -> XY:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for t in self:
            for d in self.river_edges(t):
                a = (t["x"], t["y"])
                parent.setdefault(a, a)
                n = self.neighbour_at(t, d)
                if n is not None:
                    b = (n["x"], n["y"])
                    parent.setdefault(b, b)
                    parent[find(a)] = find(b)
        roots: dict[XY, int] = {}
        return {xy: roots.setdefault(find(xy), len(roots)) for xy in parent}

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
