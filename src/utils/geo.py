"""Geospatial helpers: great-circle distance and nearest-grid-cell lookup.

Used to match gridded ERA5/CAMS cells to point OpenAQ stations
(COPILOT_CONTEXT.md section 6).
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0


def haversine_distance(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> float | np.ndarray:
    """Great-circle distance in km between two points (or broadcast arrays)."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlambda = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def find_nearest_grid_cell(
    station_lat: float,
    station_lon: float,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
) -> tuple[int, int, float]:
    """Return (lat_idx, lon_idx, distance_km) of the grid cell nearest a station.

    ``grid_lats`` and ``grid_lons`` are the 1-D coordinate axes of a regular
    grid. Uses true great-circle distance over the candidate cell (nearest on
    each axis independently), which is exact for regular lat/lon grids.
    """
    lat_idx = int(np.argmin(np.abs(np.asarray(grid_lats) - station_lat)))
    lon_idx = int(np.argmin(np.abs(np.asarray(grid_lons) - station_lon)))
    dist = float(
        haversine_distance(
            station_lat, station_lon, grid_lats[lat_idx], grid_lons[lon_idx]
        )
    )
    return lat_idx, lon_idx, dist
