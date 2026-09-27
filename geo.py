"""
Area outlines: keep only places inside the real boundary of a city / region /
country (a bounding box of Lyon also covers half its suburbs).
Plain ray casting on the simplified GeoJSON outline Nominatim returns.
"""

from __future__ import annotations


class Area:
    def __init__(self, geojson: dict | None):
        self.rings: list[list[tuple[float, float]]] = []  # (lon, lat); outer + holes, even-odd rule
        self.boxes: list[tuple[float, float, float, float]] = []
        if not geojson:
            return
        t, c = geojson.get("type"), geojson.get("coordinates") or []
        polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
        for poly in polys:
            for ring in poly:
                pts = [(float(x), float(y)) for x, y, *_ in ring]
                if len(pts) >= 4:
                    self.rings.append(pts)
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    self.boxes.append((min(xs), min(ys), max(xs), max(ys)))

    def __bool__(self):
        return bool(self.rings)

    def contains(self, lat, lon) -> bool:
        if not self.rings:
            return True
        if lat is None or lon is None:
            return True  # no position: can't judge, keep it
        inside = False
        for ring, (x0, y0, x1, y1) in zip(self.rings, self.boxes):
            if lon < x0 or lon > x1 or lat < y0 or lat > y1:
                continue
            j = len(ring) - 1
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
                    inside = not inside
                j = i
        return inside

    def touches(self, s, w, n, e) -> bool:
        """Could this tile hold places inside the area? (cheap, errs on yes)"""
        if not self.rings:
            return True
        if any(not (x1 < w or x0 > e or y1 < s or y0 > n) for x0, y0, x1, y1 in self.boxes):
            cy, cx = (s + n) / 2, (w + e) / 2
            if self.contains(cy, cx) or any(self.contains(a, b) for a in (s, n) for b in (w, e)):
                return True
            return any(w <= x <= e and s <= y <= n for ring in self.rings for x, y in ring)
        return False
