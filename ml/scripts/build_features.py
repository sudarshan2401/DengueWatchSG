"""
DengueWatch SG — Weekly Feature Builder
-----------------------------------------
Reads raw ingestion data from S3 (populated by data-ingestion Lambda) and
produces a features CSV with one row per planning area, ready for inference.py.

Run this script once per week before running inference.py.

S3 data layout (bucket: dengue-ml-data-lake)
---------------------------------------------
  raw/dengue/date=YYYY-MM-DD/clusters.json      ← Monday's date
  raw/weather/date=YYYY-MM-DD/rainfall.json     ← Sunday's date (day before Monday)
  raw/weather/date=YYYY-MM-DD/air-temperature.json

clusters.json format: array of {case_size, geometry (GeoJSON dict), ...}
rainfall/air-temperature.json format: array of {station_id, metric, value, ...}
  (multiple readings per station — averaged per planning area)

Prerequisites
-------------
  Run prepare_data.py at least once to generate:
    ml/data/planning_areas.json
    ml/data/station_planning_area.json
    ml/data/raw/planning_boundaries.geojson

Usage
-----
    python ml/scripts/build_features.py \\
        --bucket dengue-ml-data-lake \\
        --week 2026-W12 \\
        --output ml/data/features_current.csv

    # Output to S3:
    python ml/scripts/build_features.py \\
        --bucket dengue-ml-data-lake \\
        --week 2026-W12 \\
        --output s3://dengue-ml-data-lake/features/week=2026-W12/features.csv
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
from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATA_DIR = Path(__file__).parent.parent / "data"

FEATURE_COLS = [
    "lag_cases_1w", "lag_cases_2w", "lag_cases_3w", "lag_cases_4w",
    "lag_cases_5w", "lag_cases_6w", "lag_cases_7w", "lag_cases_8w",
    "lag_national_1w", "lag_national_2w",
    "lag_rainfall_2w", "lag_rainfall_3w", "lag_rainfall_4w",
    "lag_temp_2w", "lag_temp_3w", "lag_temp_4w",
    "week_of_year",
]


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build weekly feature CSV for DengueWatch inference")
    p.add_argument("--bucket", default=os.environ.get("DATA_BUCKET", "dengue-ml-data-lake"),
                   help="S3 bucket containing raw ingestion data")
    p.add_argument("--output", required=True, help="Output path (local file or s3://bucket/key)")
    p.add_argument("--week", required=True, help="Target ISO week, e.g. 2026-W12")
    p.add_argument("--data-dir", default=str(DATA_DIR),
                   help="Directory containing planning_areas.json, station_planning_area.json, "
                        "and raw/planning_boundaries.geojson")
    return p.parse_args()


# ── Week helpers ──────────────────────────────────────────────────────────────

def parse_iso_week(week_str: str) -> tuple[int, int]:
    """Parse '2026-W12' → (2026, 12)."""
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError(f"Expected ISO week like '2026-W12', got: {week_str!r}")
    return int(parts[0]), int(parts[1])


def iso_week_to_monday(year: int, week: int) -> datetime:
    return datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)


def week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def prior_weeks(current_monday: datetime, n: int) -> list[str]:
    """Return week labels for the n weeks before current_monday."""
    return [week_label(current_monday - timedelta(weeks=i)) for i in range(1, n + 1)]


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _s3_read_json(s3_client, bucket: str, key: str) -> list | None:
    """Read a JSON file from S3. Returns None if the key does not exist."""
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())
    except s3_client.exceptions.NoSuchKey:
        logger.warning("S3 key not found: s3://%s/%s", bucket, key)
        return None
    except Exception as exc:
        logger.warning("Failed to read s3://%s/%s: %s", bucket, key, exc)
        return None


# ── Static reference data ─────────────────────────────────────────────────────

def load_planning_areas(data_dir: Path) -> list[str]:
    path = data_dir / "planning_areas.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run prepare_data.py first.")
    with open(path) as f:
        return json.load(f)


def load_station_map(data_dir: Path) -> dict[str, str]:
    """Return {station_id: planning_area}."""
    path = data_dir / "station_planning_area.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run prepare_data.py first.")
    with open(path) as f:
        return json.load(f)


def load_area_polygons(data_dir: Path) -> dict[str, object]:
    """Return {planning_area_name: shapely_polygon}. Reads GeoJSON directly via shapely."""
    boundaries_path = data_dir / "raw" / "planning_boundaries.geojson"
    if not boundaries_path.exists():
        raise FileNotFoundError(
            f"{boundaries_path} not found. Run prepare_data.py first."
        )
    with open(boundaries_path) as f:
        geojson = json.load(f)

    result = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        name = None
        for col in ("planning_area", "PLN_AREA_N", "pln_area_n", "Name", "name"):
            if col in props:
                name = str(props[col]).upper()
                break
        if name and feature.get("geometry"):
            result[name] = shape(feature["geometry"])
    if not result:
        raise ValueError("No planning area polygons found in boundaries GeoJSON")
    return result


# ── Spatial helpers ───────────────────────────────────────────────────────────

def _geojson_centroid(geometry: dict) -> tuple[float, float] | None:
    """Return (lat, lng) centroid of a GeoJSON geometry dict."""
    try:
        geom = shape(geometry)
        return geom.centroid.y, geom.centroid.x
    except Exception as exc:
        logger.debug("Failed to parse geometry: %s", exc)
        return None


def _point_in_planning_area(lat: float, lng: float, area_polygons: dict) -> str | None:
    pt = Point(lng, lat)
    for area_name, polygon in area_polygons.items():
        if polygon.contains(pt):
            return area_name
    return None


# ── Dengue data from S3 ───────────────────────────────────────────────────────

def fetch_dengue_weekly(
    s3, bucket: str, weeks: list[str], area_polygons: dict
) -> dict[str, dict[str, float]]:
    """
    For each lag week, read raw/dengue/date={monday}/clusters.json from S3.
    Returns {week_label: {planning_area: total_cases}}.
    Missing files (cold start) result in an empty dict for that week.
    """
    result: dict[str, dict[str, float]] = {}

    for w in weeks:
        year, iso_wk = parse_iso_week(w)
        monday = iso_week_to_monday(year, iso_wk)
        date_str = monday.strftime("%Y-%m-%d")
        key = f"raw/dengue/date={date_str}/clusters.json"

        clusters = _s3_read_json(s3, bucket, key)
        if not clusters:
            logger.info("No dengue data for week %s (date=%s)", w, date_str)
            result[w] = {}
            continue

        area_cases: dict[str, float] = {}
        for cluster in clusters:
            geometry = cluster.get("geometry")
            case_size = cluster.get("case_size", 0)
            if not geometry or not case_size:
                continue
            centroid = _geojson_centroid(geometry)
            if centroid is None:
                continue
            lat, lng = centroid
            area = _point_in_planning_area(lat, lng, area_polygons)
            if area:
                area_cases[area] = area_cases.get(area, 0.0) + float(case_size)

        result[w] = area_cases
        logger.info("Week %s: %d clusters → %d planning areas with cases",
                    w, len(clusters), len(area_cases))

    return result


# ── Weather data from S3 ──────────────────────────────────────────────────────

def fetch_weather_weekly(
    s3, bucket: str, weeks: list[str], station_map: dict[str, str]
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """
    For each lag week, read raw/weather/date={sunday}/rainfall.json and
    air-temperature.json from S3. Sunday = Monday of that week - 1 day.
    Returns (rainfall_by_week_area, temp_by_week_area).
    Multiple readings per station are averaged per planning area.
    """
    rainfall_result: dict[str, dict[str, float]] = {}
    temp_result: dict[str, dict[str, float]] = {}

    for w in weeks:
        year, iso_wk = parse_iso_week(w)
        monday = iso_week_to_monday(year, iso_wk)
        sunday = monday - timedelta(days=1)
        date_str = sunday.strftime("%Y-%m-%d")

        # Accumulate values per (planning_area) for averaging
        rainfall_accum: dict[str, list[float]] = {}
        temp_accum: dict[str, list[float]] = {}

        for filename, accum in [
            ("rainfall.json", rainfall_accum),
            ("air-temperature.json", temp_accum),
        ]:
            key = f"raw/weather/date={date_str}/{filename}"
            readings = _s3_read_json(s3, bucket, key)
            if not readings:
                logger.info("No weather data (%s) for week %s (date=%s)", filename, w, date_str)
                continue

            for reading in readings:
                station_id = reading.get("station_id")
                value = reading.get("value")
                if station_id is None or value is None:
                    continue
                area = station_map.get(station_id)
                if area is None:
                    continue
                accum.setdefault(area, []).append(float(value))

        rainfall_result[w] = {area: sum(vals) / len(vals) for area, vals in rainfall_accum.items()}
        temp_result[w] = {area: sum(vals) / len(vals) for area, vals in temp_accum.items()}

        logger.info("Week %s: rainfall → %d areas, temperature → %d areas",
                    w, len(rainfall_result[w]), len(temp_result[w]))

    return rainfall_result, temp_result


# ── Assemble feature rows ─────────────────────────────────────────────────────

def build_feature_rows(
    current_week: str,
    all_areas: list[str],
    dengue_by_week: dict[str, dict[str, float]],
    rainfall_by_week: dict[str, dict[str, float]],
    temp_by_week: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Build one feature row per planning area. Missing values filled with 0."""
    _, iso_wk = parse_iso_week(current_week)
    year_c, wk_c = parse_iso_week(current_week)
    monday_c = iso_week_to_monday(year_c, wk_c)

    # National cases = sum across all areas for that week
    national_by_lag: dict[int, float] = {}
    for lag in range(1, 9):
        lag_week = week_label(monday_c - timedelta(weeks=lag))
        national_by_lag[lag] = sum(dengue_by_week.get(lag_week, {}).values())

    rows = []
    for area in all_areas:
        row: dict[str, object] = {"planning_area": area, "week_of_year": iso_wk}

        for lag in range(1, 9):
            lag_week = week_label(monday_c - timedelta(weeks=lag))
            row[f"lag_cases_{lag}w"] = dengue_by_week.get(lag_week, {}).get(area, 0.0)

        for lag in (1, 2):
            row[f"lag_national_{lag}w"] = national_by_lag[lag]

        for lag in (2, 3, 4):
            lag_week = week_label(monday_c - timedelta(weeks=lag))
            row[f"lag_rainfall_{lag}w"] = rainfall_by_week.get(lag_week, {}).get(area, 0.0)
            row[f"lag_temp_{lag}w"] = temp_by_week.get(lag_week, {}).get(area, 0.0)

        rows.append(row)

    df = pd.DataFrame(rows)
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
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode())
        logger.info("Wrote features to s3://%s/%s", bucket, key)
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Wrote features to %s", output_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)

    all_areas = load_planning_areas(data_dir)
    station_map = load_station_map(data_dir)
    area_polygons = load_area_polygons(data_dir)
    logger.info("Loaded %d planning areas, %d station mappings", len(all_areas), len(station_map))

    year, iso_wk = parse_iso_week(args.week)
    current_monday = iso_week_to_monday(year, iso_wk)
    needed_weeks = prior_weeks(current_monday, n=8)
    logger.info("Target week: %s | Lag weeks: %s", args.week, needed_weeks)

    s3 = boto3.client("s3")
    dengue_by_week = fetch_dengue_weekly(s3, args.bucket, needed_weeks, area_polygons)
    rainfall_by_week, temp_by_week = fetch_weather_weekly(s3, args.bucket, needed_weeks, station_map)

    features_df = build_feature_rows(
        current_week=args.week,
        all_areas=all_areas,
        dengue_by_week=dengue_by_week,
        rainfall_by_week=rainfall_by_week,
        temp_by_week=temp_by_week,
    )

    logger.info("Built %d feature rows, %d columns", len(features_df), len(features_df.columns))
    assert len(features_df) == len(all_areas), f"Expected {len(all_areas)} rows, got {len(features_df)}"
    assert features_df.isnull().sum().sum() == 0, "Feature matrix contains NaN values"

    write_output(features_df, args.output)


if __name__ == "__main__":
    main()
