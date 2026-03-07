"""
DengueWatch SG — Weekly Feature Builder
-----------------------------------------
Reads raw data from PostgreSQL (populated by data-ingestion Lambda) and
produces a features CSV with one row per planning area, ready for inference.py.

Run this script once per week before running inference.py.

Prerequisites
-------------
  1. run prepare_data.py at least once to generate:
       ml/data/planning_areas.json
       ml/data/station_planning_area.json
  2. PostgreSQL raw tables must be populated:
       raw_dengue_clusters (case_size, geometry JSONB, ingested_at)
       raw_weather (station_id, metric, value, reading_timestamp, ingested_at)

Usage
-----
    # Output to local file:
    python ml/scripts/build_features.py \\
        --output ml/data/features_current.csv \\
        --week 2024-W10

    # Output to S3:
    python ml/scripts/build_features.py \\
        --output s3://my-bucket/features/2024-W10.csv \\
        --week 2024-W10

Environment Variables
---------------------
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
  (same as inference.py)
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pandas as pd
import psycopg2
from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATA_DIR = Path(__file__).parent.parent / "data"

FEATURE_COLS = [
    "lag_cases_1w", "lag_cases_2w", "lag_cases_3w", "lag_cases_4w",
    "lag_rainfall_2w", "lag_rainfall_3w",
    "lag_temp_2w", "lag_temp_3w",
    "week_of_year",
]


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build weekly feature CSV for DengueWatch inference")
    p.add_argument("--output", required=True, help="Output path (local file or s3://bucket/key)")
    p.add_argument("--week", required=True, help="Target ISO week, e.g. 2024-W10")
    p.add_argument("--db-host", default=os.environ.get("DB_HOST", "localhost"))
    p.add_argument("--db-port", type=int, default=int(os.environ.get("DB_PORT", 5432)))
    p.add_argument("--db-name", default=os.environ.get("DB_NAME", "denguewatch"))
    p.add_argument("--db-user", default=os.environ.get("DB_USER", "postgres"))
    p.add_argument("--db-password", default=os.environ.get("DB_PASSWORD", "postgres"))
    p.add_argument(
        "--data-dir", default=str(DATA_DIR),
        help="Directory containing planning_areas.json and station_planning_area.json"
    )
    return p.parse_args()


# ── Week helpers ──────────────────────────────────────────────────────────────

def parse_iso_week(week_str: str) -> tuple[int, int]:
    """Parse '2024-W10' → (2024, 10)."""
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError(f"Expected ISO week like '2024-W10', got: {week_str!r}")
    return int(parts[0]), int(parts[1])


def iso_week_to_monday(year: int, week: int) -> datetime:
    """Return the Monday of the given ISO week as a UTC datetime."""
    # ISO week: year/week/day=1 (Monday)
    return datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)


def week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def prior_weeks(current_monday: datetime, n: int) -> list[str]:
    """Return week labels for the n weeks ending the week before current_monday."""
    return [week_label(current_monday - timedelta(weeks=i)) for i in range(1, n + 1)]


# ── Database ──────────────────────────────────────────────────────────────────

def get_db_conn(args: argparse.Namespace):
    return psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )


# ── Static reference data ─────────────────────────────────────────────────────

def load_planning_areas(data_dir: Path) -> list[str]:
    path = data_dir / "planning_areas.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run prepare_data.py first to generate static reference files."
        )
    with open(path) as f:
        return json.load(f)


def load_station_map(data_dir: Path) -> dict[str, str]:
    """Return {station_id: planning_area}."""
    path = data_dir / "station_planning_area.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run prepare_data.py first to generate static reference files."
        )
    with open(path) as f:
        return json.load(f)


# ── Dengue cluster feature extraction ────────────────────────────────────────

def _geojson_centroid(geometry_json: str | dict) -> tuple[float, float] | None:
    """
    Extract (lat, lng) centroid from a GeoJSON geometry stored as JSONB string or dict.
    Returns None if parsing fails.
    """
    try:
        if isinstance(geometry_json, str):
            geom_dict = json.loads(geometry_json)
        else:
            geom_dict = geometry_json
        geom = shape(geom_dict)
        centroid = geom.centroid
        return centroid.y, centroid.x  # (lat, lng)
    except Exception as exc:
        logger.debug("Failed to parse geometry: %s", exc)
        return None


def _point_in_planning_area(
    lat: float, lng: float, area_polygons: dict[str, object]
) -> str | None:
    """Return planning area name for (lat, lng) using pre-built polygon index."""
    pt = Point(lng, lat)
    for area_name, polygon in area_polygons.items():
        if polygon.contains(pt):
            return area_name
    return None


def fetch_dengue_weekly(
    conn, weeks: list[str], area_polygons: dict[str, object]
) -> dict[str, dict[str, float]]:
    """
    Query raw_dengue_clusters for the given week labels.
    Returns {week_label: {planning_area: total_cases}}.
    """
    # Determine the date range: from start of earliest week to end of latest week
    # We use ingested_at as a proxy for the observation week
    result: dict[str, dict[str, float]] = {w: {} for w in weeks}

    # Build week → date range mapping
    week_ranges: dict[str, tuple[datetime, datetime]] = {}
    for w in weeks:
        year, iso_wk = parse_iso_week(w)
        monday = iso_week_to_monday(year, iso_wk)
        sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
        week_ranges[w] = (monday, sunday)

    min_ts = min(r[0] for r in week_ranges.values())
    max_ts = max(r[1] for r in week_ranges.values())

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT case_size, geometry::text, ingested_at
            FROM raw_dengue_clusters
            WHERE ingested_at BETWEEN %s AND %s
            """,
            (min_ts, max_ts),
        )
        rows = cur.fetchall()

    logger.info("Fetched %d dengue cluster rows for weeks %s", len(rows), weeks)

    for case_size, geometry_text, ingested_at in rows:
        # Assign to week based on ingested_at
        row_week = None
        for w, (start, end) in week_ranges.items():
            ts = ingested_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if start <= ts <= end:
                row_week = w
                break
        if row_week is None:
            continue

        # Assign to planning area via centroid
        centroid = _geojson_centroid(geometry_text)
        if centroid is None:
            continue
        lat, lng = centroid
        area = _point_in_planning_area(lat, lng, area_polygons)
        if area is None:
            continue

        result[row_week][area] = result[row_week].get(area, 0.0) + float(case_size or 0)

    return result


# ── Weather feature extraction ────────────────────────────────────────────────

def fetch_weather_weekly(
    conn, weeks: list[str], station_map: dict[str, str]
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """
    Query raw_weather for the given week labels.
    Returns (rainfall_by_week_area, temp_by_week_area) where each is
    {week_label: {planning_area: mean_value}}.
    """
    week_ranges: dict[str, tuple[datetime, datetime]] = {}
    for w in weeks:
        year, iso_wk = parse_iso_week(w)
        monday = iso_week_to_monday(year, iso_wk)
        sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
        week_ranges[w] = (monday, sunday)

    min_ts = min(r[0] for r in week_ranges.values())
    max_ts = max(r[1] for r in week_ranges.values())

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT station_id, metric, value, reading_timestamp
            FROM raw_weather
            WHERE reading_timestamp BETWEEN %s AND %s
              AND metric IN ('rainfall', 'temperature')
            """,
            (min_ts, max_ts),
        )
        rows = cur.fetchall()

    logger.info("Fetched %d weather rows for weeks %s", len(rows), weeks)

    # Accumulate sum + count per (week, planning_area, metric)
    accum: dict[tuple[str, str, str], list[float]] = {}
    for station_id, metric, value, reading_ts in rows:
        planning_area = station_map.get(station_id)
        if planning_area is None or value is None:
            continue

        row_week = None
        for w, (start, end) in week_ranges.items():
            ts = reading_ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if start <= ts <= end:
                row_week = w
                break
        if row_week is None:
            continue

        key = (row_week, planning_area, metric)
        accum.setdefault(key, []).append(float(value))

    rainfall: dict[str, dict[str, float]] = {w: {} for w in weeks}
    temp: dict[str, dict[str, float]] = {w: {} for w in weeks}

    for (week, area, metric), values in accum.items():
        mean_val = sum(values) / len(values)
        if metric == "rainfall":
            rainfall[week][area] = mean_val
        else:
            temp[week][area] = mean_val

    return rainfall, temp


# ── Assemble feature rows ─────────────────────────────────────────────────────

def build_feature_rows(
    current_week: str,
    all_areas: list[str],
    dengue_by_week: dict[str, dict[str, float]],
    rainfall_by_week: dict[str, dict[str, float]],
    temp_by_week: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """
    Build one feature row per planning area for the current week.
    Lag features use the previous weeks' aggregated data.
    Missing values are filled with 0.
    """
    _, iso_wk = parse_iso_week(current_week)
    rows = []
    for area in all_areas:
        row: dict[str, object] = {"planning_area": area, "week_of_year": iso_wk}

        # Dengue lags: lag_cases_1w = week-1, lag_cases_2w = week-2, ...
        for lag in range(1, 5):
            year_c, wk_c = parse_iso_week(current_week)
            monday_c = iso_week_to_monday(year_c, wk_c)
            lag_monday = monday_c - timedelta(weeks=lag)
            lag_week = week_label(lag_monday)
            row[f"lag_cases_{lag}w"] = dengue_by_week.get(lag_week, {}).get(area, 0.0)

        # Weather lags: lag_rainfall_2w = week-2, lag_rainfall_3w = week-3
        for lag in (2, 3):
            year_c, wk_c = parse_iso_week(current_week)
            monday_c = iso_week_to_monday(year_c, wk_c)
            lag_monday = monday_c - timedelta(weeks=lag)
            lag_week = week_label(lag_monday)
            row[f"lag_rainfall_{lag}w"] = rainfall_by_week.get(lag_week, {}).get(area, 0.0)
            row[f"lag_temp_{lag}w"] = temp_by_week.get(lag_week, {}).get(area, 0.0)

        rows.append(row)

    df = pd.DataFrame(rows)
    # Ensure all feature columns are present (fill any still-missing with 0)
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0
    return df[["planning_area"] + FEATURE_COLS]


# ── Output ────────────────────────────────────────────────────────────────────

def write_output(df: pd.DataFrame, output_path: str) -> None:
    if output_path.startswith("s3://"):
        bucket, key = output_path[5:].split("/", 1)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode())
        logger.info("Wrote features to s3://%s/%s", bucket, key)
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Wrote features to %s", output_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)

    # Load static reference data
    all_areas = load_planning_areas(data_dir)
    station_map = load_station_map(data_dir)
    logger.info("Loaded %d planning areas, %d station mappings", len(all_areas), len(station_map))

    # Parse target week and compute which prior weeks we need
    year, iso_wk = parse_iso_week(args.week)
    current_monday = iso_week_to_monday(year, iso_wk)
    needed_weeks = prior_weeks(current_monday, n=4)  # weeks 1–4 prior
    logger.info("Target week: %s | Fetching lags for: %s", args.week, needed_weeks)

    # Build area_polygons dict for point-in-polygon (loaded lazily from boundaries file)
    area_polygons = _load_area_polygons(data_dir)

    # Connect and query
    conn = get_db_conn(args)
    try:
        dengue_by_week = fetch_dengue_weekly(conn, needed_weeks, area_polygons)
        rainfall_by_week, temp_by_week = fetch_weather_weekly(conn, needed_weeks, station_map)
    finally:
        conn.close()

    # Build feature matrix (one row per planning area)
    features_df = build_feature_rows(
        current_week=args.week,
        all_areas=all_areas,
        dengue_by_week=dengue_by_week,
        rainfall_by_week=rainfall_by_week,
        temp_by_week=temp_by_week,
    )

    logger.info("Built %d feature rows, %d columns", len(features_df), len(features_df.columns))
    assert len(features_df) == len(all_areas), (
        f"Expected {len(all_areas)} rows, got {len(features_df)}"
    )
    assert features_df.isnull().sum().sum() == 0, "Feature matrix contains NaN values"

    write_output(features_df, args.output)


def _load_area_polygons(data_dir: Path) -> dict[str, object]:
    """
    Load planning area polygons from the cached GeoJSON file.
    Returns {planning_area_name: shapely_polygon}.
    """
    boundaries_path = data_dir / "raw" / "planning_boundaries.geojson"
    if not boundaries_path.exists():
        raise FileNotFoundError(
            f"{boundaries_path} not found.\n"
            "Run prepare_data.py first to download and cache planning area boundaries."
        )

    import geopandas as gpd
    gdf = gpd.read_file(str(boundaries_path))

    # Normalise column name
    for col in ("planning_area", "PLN_AREA_N", "pln_area_n", "Name", "name"):
        if col in gdf.columns:
            name_col = col
            break
    else:
        raise ValueError("Cannot find planning area name column in boundaries GeoDataFrame")

    return {
        str(row[name_col]).upper(): row.geometry
        for _, row in gdf.iterrows()
        if row.geometry is not None
    }


if __name__ == "__main__":
    main()
