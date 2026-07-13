"""
Geospatial helpers. `haversine_km` is what the SQLite/dev backends use for
"nearest resource" queries. In production, once DATABASE_URL points at
PostGIS, replace the Python-side sort in resources.py with a native query:

    SELECT *, ST_Distance(geom, ST_MakePoint(:lon, :lat)::geography) AS distance_m
    FROM resources
    ORDER BY geom <-> ST_MakePoint(:lon, :lat)::geography
    LIMIT :limit;

which uses the GiST index for O(log n) nearest-neighbor lookups instead of
this O(n) full-table haversine scan — the same KD-Tree-style speedup the
blueprint's "Technical Differentiators" section calls out.
"""
import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
