"""The revealed map as a hex grid.

Civ VI stores plots in offset coordinates: index = y * width + x, y grows northwards,
and odd rows sit half a hex to the east ("odd-r"). Maps wrap east-west by default.
This was checked against the neighbour lists the game itself reports.
"""


class GameMap:
    def __init__(self, dump, wrap_x=True):
        self.width = dump["w"]
        self.height = dump["h"]
        self.turn = dump["turn"]
        self.player = dump["player"]
        self.wrap_x = wrap_x
        self.tiles = {(t["x"], t["y"]): t for t in dump["tiles"]}
        self._by_index = {t["i"]: t for t in dump["tiles"]}
        self.own_cities = dump["cities"]

    def __iter__(self):
        return iter(self.tiles.values())

    def __len__(self):
        return len(self.tiles)

    def neighbours(self, tile):
        """Revealed neighbours of a tile, using the adjacency the game reported."""
        return [self._by_index[i] for i in tile["neighbours"] if i in self._by_index]

    @staticmethod
    def _axial(x, y):
        return x - (y - (y & 1)) // 2, y

    def distance(self, a, b):
        """Hex distance between two tiles (or (x, y) pairs), accounting for wrap."""
        ax, ay = (a["x"], a["y"]) if isinstance(a, dict) else a
        bx, by = (b["x"], b["y"]) if isinstance(b, dict) else b
        shifts = (-self.width, 0, self.width) if self.wrap_x else (0,)
        best = None
        for dx in shifts:
            q1, r1 = self._axial(ax + dx, ay)
            q2, r2 = self._axial(bx, by)
            d = (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2
            best = d if best is None else min(best, d)
        return best

    def within(self, centre, radius):
        """Revealed tiles at distance 1..radius from centre (centre excluded)."""
        return [t for t in self if 0 < self.distance(centre, t) <= radius]

    def city_positions(self):
        """Every known city centre: the player's own plus any other revealed city tiles."""
        positions = {(c["x"], c["y"]) for c in self.own_cities}
        positions |= {(t["x"], t["y"]) for t in self if t.get("is_city")}
        return positions
