"""
patch_nuts.py — Add NUTS region codes (levels 0–3) to existing WAHIS outbreak
Excel files.

Downloads the official Eurostat NUTS GeoJSON boundaries for each level (cached
locally), performs a spatial point-in-polygon lookup on each outbreak's
coordinates, and writes nuts columns back into the same Excel files.

Uses NUTS 2024 boundaries for current EU/EEA countries and falls back to
NUTS 2016 for countries no longer covered (e.g. the UK after Brexit).

Columns added:
    nuts0_id, nuts0_name   — country level        (e.g. "FR", "France")
    nuts1_id, nuts1_name   — major region level    (e.g. "FR1", "Île-de-France")
    nuts2_id, nuts2_name   — region level          (e.g. "FR10", "Île-de-France")
    nuts3_id, nuts3_name   — small region level    (e.g. "FR101", "Paris")

Usage:
    python patch_nuts2.py
"""

import glob
import os
import urllib.request

import geopandas as gpd
import pandas as pd

# ── Config ───────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.getcwd(), "OUTPUTS")

NUTS_BASE_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
)
# Primary (2024) + fallback (2016 for UK etc.)
NUTS_YEARS = [2024, 2016]
NUTS_LEVELS = [0, 1, 2, 3]
NUTS_COLUMNS = [
    ("nuts0_id", "nuts0_name"),
    ("nuts1_id", "nuts1_name"),
    ("nuts2_id", "nuts2_name"),
    ("nuts3_id", "nuts3_name"),
]

ALL_NUTS_COLS = [col for pair in NUTS_COLUMNS for col in pair]


def _geojson_filename(year: int, level: int) -> str:
    return f"NUTS_RG_01M_{year}_4326_LEVL_{level}.geojson"


def download_nuts(year: int, level: int) -> str:
    """Download a single NUTS level GeoJSON if not already cached. Returns path."""
    filename = _geojson_filename(year, level)
    dest = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(dest):
        print(f"  Using cached: {filename}")
        return dest
    url = NUTS_BASE_URL + filename
    print(f"  Downloading NUTS {year} level {level} from Eurostat …")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved to {dest}")
    return dest


def load_nuts(path: str) -> gpd.GeoDataFrame:
    """Load a NUTS GeoJSON and keep only the columns we need."""
    gdf = gpd.read_file(path)
    return gdf[["NUTS_ID", "NUTS_NAME", "geometry"]]


def build_combined_nuts(level: int) -> gpd.GeoDataFrame:
    """Download and merge NUTS boundaries for a given level across all years.

    The 2024 boundaries are used as the primary source. The 2016 boundaries
    are added as a fallback for regions not present in 2024 (e.g. UK).
    """
    combined = None
    for year in NUTS_YEARS:
        path = download_nuts(year, level)
        gdf = load_nuts(path)
        if combined is None:
            combined = gdf
        else:
            # Only add regions whose NUTS_ID isn't already covered
            new_ids = ~gdf["NUTS_ID"].isin(combined["NUTS_ID"])
            if new_ids.any():
                extra = gdf.loc[new_ids]
                combined = pd.concat([combined, extra], ignore_index=True)
                print(f"    +{len(extra)} regions from {year} fallback (level {level})")
    return combined


def spatial_join(points: gpd.GeoDataFrame, nuts: gpd.GeoDataFrame) -> pd.Series:
    """Join points to nearest NUTS polygon, returning (NUTS_ID, NUTS_NAME) aligned to points index.

    Uses sjoin_nearest instead of sjoin(predicate="within") so that coastal
    and boundary points that fall just outside simplified polygons still get
    matched to their nearest region.

    Both GeoDataFrames are projected to EPSG:3035 (ETRS89-extended / LAEA
    Europe) before the nearest join so that distances are computed in metres.
    max_distance is 50 km — generous enough for simplified coastlines.
    """
    # Project to metre-based European CRS for accurate distance calculation
    points_proj = points.to_crs(epsg=3035)
    nuts_proj = nuts.to_crs(epsg=3035)

    joined = gpd.sjoin_nearest(
        points_proj, nuts_proj, how="left", max_distance=50_000  # 50 km
    )
    # Deduplicate: keep only the first (nearest) match per original index
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined["NUTS_ID"], joined["NUTS_NAME"]


def patch_file(filepath: str, nuts_gdfs: dict[int, gpd.GeoDataFrame]) -> None:
    """Read an Excel file, spatial-join all NUTS levels, and overwrite it."""
    print(f"\n  Processing {os.path.basename(filepath)} …")
    df = pd.read_excel(filepath)

    # Drop any previous NUTS columns so we get a clean join
    df = df.drop(columns=ALL_NUTS_COLS, errors="ignore")

    has_coords = df["latitude"].notna() & df["longitude"].notna()
    if not has_coords.any():
        for col in ALL_NUTS_COLS:
            df[col] = ""
        df.to_excel(filepath, index=False)
        print(f"    No rows with coordinates — skipped spatial join")
        return

    # Build a GeoDataFrame from valid-coordinate rows
    valid = df.loc[has_coords].copy()
    points = gpd.GeoDataFrame(
        valid,
        geometry=gpd.points_from_xy(valid["longitude"], valid["latitude"]),
        crs="EPSG:4326",
    )

    # Spatial join for each NUTS level
    for level in NUTS_LEVELS:
        id_col, name_col = NUTS_COLUMNS[level]
        nuts_id, nuts_name = spatial_join(points, nuts_gdfs[level])
        df[id_col] = nuts_id
        df[name_col] = nuts_name
        df[id_col] = df[id_col].fillna("")
        df[name_col] = df[name_col].fillna("")

    df.to_excel(filepath, index=False)

    # Report match rate using the finest level (NUTS 3)
    matched = (df["nuts3_id"] != "").sum()
    total = has_coords.sum()
    print(f"    {matched}/{total} coordinate rows matched a NUTS 3 region")
    print(f"    Saved {filepath}")


def main() -> None:
    print("patch_nuts: Adding NUTS region codes (levels 0–3) to outbreak data\n")

    # 1. Download / cache and combine NUTS boundaries (2024 + 2016 fallback)
    nuts_gdfs: dict[int, gpd.GeoDataFrame] = {}
    for level in NUTS_LEVELS:
        gdf = build_combined_nuts(level)
        nuts_gdfs[level] = gdf
        print(f"  Combined NUTS level {level}: {len(gdf)} regions")

    # 2. Find Excel files
    pattern = os.path.join(OUTPUT_DIR, "WAHIS_ReportOutbreaks_*.xlsx")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"\n  No files matching {pattern}")
        return
    print(f"\n  Found {len(files)} Excel file(s)")

    # 3. Patch each file
    for f in files:
        patch_file(f, nuts_gdfs)

    print("\nDone.")


if __name__ == "__main__":
    main()
