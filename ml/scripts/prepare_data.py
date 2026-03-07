"""
DengueWatch SG — Training Data Preparation
-------------------------------------------
Downloads historical dengue cluster data and NEA weather data, performs
spatial joins to assign clusters/stations to planning areas, computes
lagged features, and saves train.csv / validation.csv.

Also generates ml/data/station_planning_area.json and
ml/data/planning_areas.json as side effects.

Usage
-----
    python ml/scripts/prepare_data.py \\
        --output-dir ml/data/ \\
        --start-year 2013 \\
        --end-year 2020

    # Or supply a pre-downloaded dengue CSV:
    python ml/scripts/prepare_data.py \\
        --dengue-csv ml/data/raw/historical_dengue.csv \\
        --output-dir ml/data/

    # Or supply pre-downloaded URA boundaries GeoJSON:
    python ml/scripts/prepare_data.py \\
        --boundaries-geojson ml/data/raw/planning_boundaries.geojson \\
        --output-dir ml/data/

Dengue CSV format expected
--------------------------
    Date, Latitude, Longitude, CaseCount
    2016-01-04, 1.3521, 103.8198, 12
    ...

Note on OneMap API authentication
----------------------------------
The getAllPlanningarea endpoint may require a bearer token on the v3 API.
If you get a 401, pass a pre-downloaded GeoJSON via --boundaries-geojson.
Download manually from:
  https://www.onemap.gov.sg/api/public/popapi/getAllPlanningarea?year=2019
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import zipfile
from datetime import datetime as dt

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, shape
from shapely.wkt import loads as wkt_loads

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ONEMAP_ALL_AREAS_URL = "https://www.onemap.gov.sg/api/public/popapi/getAllPlanningarea"
DENGUE_ZIP_URL = "https://outbreak.sgcharts.com/sgcharts.zip"
NEA_RAINFALL_URL = "https://api.data.gov.sg/v1/environment/rainfall"
NEA_TEMPERATURE_URL = "https://api.data.gov.sg/v1/environment/air-temperature"

FEATURE_COLS = [
    "lag_cases_1w", "lag_cases_2w", "lag_cases_3w", "lag_cases_4w",
    "lag_national_1w", "lag_national_2w",
    "lag_rainfall_2w", "lag_rainfall_3w",
    "lag_temp_2w", "lag_temp_3w",
    "week_of_year",
]
OUTPUT_COLS = FEATURE_COLS + ["risk_level", "planning_area", "week"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare dengue ML training data")
    p.add_argument(
        "--dengue-csv", default=None,
        help="Path to pre-downloaded historical dengue CSV (Date,Latitude,Longitude,CaseCount)"
    )
    p.add_argument(
        "--boundaries-geojson", default=None,
        help="Path to pre-downloaded URA planning area boundaries GeoJSON"
    )
    p.add_argument("--output-dir", default="ml/data", help="Output directory for CSV files")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2020)
    p.add_argument("--train-end-year", type=int, default=2019,
                   help="Last year (inclusive) of training set")
    p.add_argument("--val-start-year", type=int, default=2020,
                   help="First year of validation set")
    p.add_argument(
        "--api-delay", type=float, default=0.5,
        help="Seconds to sleep between data.gov.sg API calls (rate limiting)"
    )
    p.add_argument(
        "--onemap-token", default=os.environ.get("ONEMAP_TOKEN", ""),
        help="OneMap v3 bearer token (or set ONEMAP_TOKEN env var)"
    )
    p.add_argument("--no-smote", action="store_true",
                   help="Skip SMOTE oversampling; rely on sample weights in train.py instead")
    return p.parse_args()


# ── Planning area boundaries ──────────────────────────────────────────────────

def fetch_planning_boundaries(
    cache_path: Path,
    boundaries_geojson_arg: str | None,
    onemap_token: str,
) -> gpd.GeoDataFrame:
    """
    Load URA planning area boundaries as a GeoDataFrame.

    Priority:
      1. --boundaries-geojson argument (user-supplied file)
      2. Cached GeoJSON from a previous run
      3. Live OneMap API download (getAllPlanningarea → getPlanningareaPolygon per area)
    """
    if boundaries_geojson_arg and Path(boundaries_geojson_arg).exists():
        logger.info("Loading planning boundaries from %s", boundaries_geojson_arg)
        gdf = gpd.read_file(boundaries_geojson_arg)
        _normalise_boundaries(gdf)
        return gdf

    if cache_path.exists():
        logger.info("Loading cached planning boundaries from %s", cache_path)
        return gpd.read_file(cache_path)

    if not onemap_token:
        raise RuntimeError(
            "No OneMap token found.\n"
            "Set ONEMAP_TOKEN env var or pass --onemap-token.\n"
            "Get a token: POST https://www.onemap.gov.sg/api/auth/post/getToken"
        )

    headers = {"Authorization": f"Bearer {onemap_token}"}

    # getAllPlanningarea returns all 55 polygons in one call.
    # Response: {"SearchResults": [{"pln_area_n": "BEDOK", "geojson": "{...}"}, ...]}
    # The "geojson" value is an escaped JSON string, not a dict.
    logger.info("Fetching all planning area polygons from OneMap (single call)…")
    resp = requests.get(ONEMAP_ALL_AREAS_URL, params={"year": 2019}, headers=headers, timeout=30)
    if resp.status_code == 401:
        raise RuntimeError("OneMap token rejected (401). Refresh your token and retry.")
    resp.raise_for_status()
    data = resp.json()

    items = data.get("SearchResults", [])
    logger.info("API returned %d planning area records", len(items))

    records = []
    for item in items:
        area_name = item.get("pln_area_n", "").upper()
        geojson_str = item.get("geojson")
        if not area_name or not geojson_str:
            logger.warning("Skipping incomplete record: %s", item.keys())
            continue
        try:
            geom = shape(json.loads(geojson_str))
            records.append({"planning_area": area_name, "geometry": geom})
        except Exception as exc:
            logger.warning("Failed to parse geometry for %s: %s", area_name, exc)

    if not records:
        raise RuntimeError("No planning area polygons could be parsed from OneMap response.")

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(str(cache_path), driver="GeoJSON")
    logger.info("Saved %d planning area polygons to %s", len(gdf), cache_path)
    return gdf


def _normalise_boundaries(gdf: gpd.GeoDataFrame) -> None:
    """Ensure 'planning_area' column exists and is upper-case."""
    for col in ("planning_area", "PLN_AREA_N", "pln_area_n", "Name", "name"):
        if col in gdf.columns:
            gdf["planning_area"] = gdf[col].str.upper()
            return
    raise ValueError("Cannot find planning area name column in boundaries GeoDataFrame")


# ── Dengue historical data ────────────────────────────────────────────────────

def fetch_dengue_data(dengue_csv_arg: str | None, cache_path: Path) -> pd.DataFrame:
    """
    Load historical dengue cluster data from outbreak.sgcharts.com.

    The zip contains ~256 biweekly snapshot CSVs (2015-07–2020-11).
    Each CSV has one row per building block within a cluster:
      col 0 : block_case_count
      col 1 : address  (may contain commas — parse from both ends)
      col -7: latitude
      col -6: longitude
      col -5: flag (always 1)
      col -4: cluster_case_size  (total cases for the whole cluster)
      col -3: cluster_id
      col -2: date YYMMDD        (redundant with filename)
      col -1: unknown

    Returns a DataFrame with columns:
      Date (datetime), cluster_id (str), Latitude, Longitude, CaseSize (int)
    One row per unique cluster per snapshot date.
    Already-cached parsed CSV is used on subsequent runs.
    """
    if dengue_csv_arg and Path(dengue_csv_arg).exists():
        logger.info("Loading dengue data from user-supplied %s", dengue_csv_arg)
        df = pd.read_csv(dengue_csv_arg, parse_dates=["Date"])
        return df

    if cache_path.exists():
        logger.info("Loading cached parsed dengue data from %s", cache_path)
        return pd.read_csv(cache_path, parse_dates=["Date"])

    # Download zip
    zip_path = cache_path.parent / "sgcharts.zip"
    if not zip_path.exists():
        logger.info("Downloading dengue cluster zip from %s …", DENGUE_ZIP_URL)
        resp = requests.get(DENGUE_ZIP_URL, timeout=120)
        resp.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(resp.content)
        logger.info("Saved zip to %s (%.1f MB)", zip_path, zip_path.stat().st_size / 1e6)

    logger.info("Parsing dengue snapshot CSVs from zip…")
    rows = []
    skipped = 0
    with zipfile.ZipFile(zip_path) as z:
        csv_files = sorted([
            n for n in z.namelist()
            if n.startswith("sgcharts/csv/") and n.endswith(".csv")
        ])
        logger.info("Found %d snapshot CSV files", len(csv_files))
        for fname in csv_files:
            date_str = Path(fname).stem.split("-")[0]  # YYMMDD
            try:
                snapshot_date = dt.strptime(date_str, "%y%m%d")
            except ValueError:
                skipped += 1
                continue

            with z.open(fname) as f:
                for line in f.read().decode("utf-8", errors="replace").splitlines():
                    parts = line.strip().split(",")
                    if len(parts) < 9:
                        skipped += 1
                        continue
                    try:
                        lat = float(parts[-7])
                        lng = float(parts[-6])
                        cluster_size = int(parts[-4])
                        cluster_id = parts[-3].strip()
                        rows.append({
                            "Date": snapshot_date,
                            "cluster_id": cluster_id,
                            "Latitude": lat,
                            "Longitude": lng,
                            "CaseSize": cluster_size,
                        })
                    except (ValueError, IndexError):
                        skipped += 1

    df = pd.DataFrame(rows)
    # One row per (snapshot_date, cluster_id) — take mean lat/lng, keep CaseSize
    df = (
        df.groupby(["Date", "cluster_id"])
        .agg(Latitude=("Latitude", "mean"), Longitude=("Longitude", "mean"),
             CaseSize=("CaseSize", "first"))
        .reset_index()
    )
    df["Date"] = pd.to_datetime(df["Date"])
    df.to_csv(cache_path, index=False)
    logger.info(
        "Parsed %d cluster-snapshots from %d files (%d lines skipped) → cached to %s",
        len(df), len(csv_files), skipped, cache_path,
    )
    return df


# ── Weather data ──────────────────────────────────────────────────────────────

def _fetch_weather_one_date(
    url: str, date_str: str, delay: float
) -> tuple[list[dict], list[dict]]:
    """Fetch weather readings + station metadata for one date. Returns (stations, readings)."""
    time.sleep(delay)
    api_key = os.environ.get("NEA_API_KEY", "")
    headers = {"api-key": api_key} if api_key else {}
    try:
        resp = requests.get(url, params={"date": date_str}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Weather API error for %s on %s: %s", url, date_str, exc)
        return [], []

    stations = [
        {
            "station_id": s["id"],
            "name": s.get("name", ""),
            "lat": s["location"]["latitude"],
            "lng": s["location"]["longitude"],
        }
        for s in data.get("metadata", {}).get("stations", [])
    ]
    readings = [
        {"station_id": r["station_id"], "value": r.get("value")}
        for item in data.get("items", [])
        for r in item.get("readings", [])
        if r.get("value") is not None
    ]
    return stations, readings


def build_weekly_weather(
    start_year: int, end_year: int, cache_dir: Path, delay: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fetch one day of weather per ISO week for all weeks in start_year..end_year.
    Returns (rainfall_df, temp_df, stations_df).
    Each row in rainfall_df/temp_df: (week, station_id, value).
    """
    rainfall_cache = cache_dir / "weather_rainfall.csv"
    temp_cache = cache_dir / "weather_temperature.csv"
    stations_cache = cache_dir / "weather_stations.csv"

    if rainfall_cache.exists() and temp_cache.exists() and stations_cache.exists():
        logger.info("Loading cached weather data from %s", cache_dir)
        return (
            pd.read_csv(rainfall_cache),
            pd.read_csv(temp_cache),
            pd.read_csv(stations_cache),
        )

    all_stations: dict[str, dict] = {}
    rainfall_rows: list[dict] = []
    temp_rows: list[dict] = []

    # One Monday per ISO week
    mondays = pd.date_range(
        start=f"{start_year}-01-01", end=f"{end_year}-12-31", freq="W-MON"
    )
    total = len(mondays)
    logger.info("Fetching weather for %d weeks (%d API calls)…", total, total * 2)

    for i, monday in enumerate(mondays):
        date_str = monday.strftime("%Y-%m-%d")
        iso_year, iso_week, _ = monday.isocalendar()
        week_label = f"{iso_year}-W{iso_week:02d}"

        if i % 20 == 0:
            logger.info("Weather progress: %d/%d (week %s)", i + 1, total, week_label)

        # Rainfall
        stations, readings = _fetch_weather_one_date(NEA_RAINFALL_URL, date_str, delay)
        for s in stations:
            all_stations[s["station_id"]] = s
        for r in readings:
            rainfall_rows.append({"week": week_label, "station_id": r["station_id"], "value": r["value"]})

        # Temperature
        stations, readings = _fetch_weather_one_date(NEA_TEMPERATURE_URL, date_str, delay)
        for s in stations:
            all_stations[s["station_id"]] = s
        for r in readings:
            temp_rows.append({"week": week_label, "station_id": r["station_id"], "value": r["value"]})

    rainfall_df = pd.DataFrame(rainfall_rows) if rainfall_rows else pd.DataFrame(columns=["week", "station_id", "value"])
    temp_df = pd.DataFrame(temp_rows) if temp_rows else pd.DataFrame(columns=["week", "station_id", "value"])
    stations_df = pd.DataFrame(list(all_stations.values())) if all_stations else pd.DataFrame(columns=["station_id", "name", "lat", "lng"])

    cache_dir.mkdir(parents=True, exist_ok=True)
    rainfall_df.to_csv(rainfall_cache, index=False)
    temp_df.to_csv(temp_cache, index=False)
    stations_df.to_csv(stations_cache, index=False)
    logger.info("Saved weather data (%d rainfall, %d temp rows)", len(rainfall_df), len(temp_df))
    return rainfall_df, temp_df, stations_df


# ── Spatial assignment ────────────────────────────────────────────────────────

def _point_to_planning_area(lat: float, lng: float, boundaries: gpd.GeoDataFrame) -> str | None:
    """Return the planning area containing (lat, lng), or None."""
    pt = Point(lng, lat)  # GeoJSON convention: (longitude, latitude)
    for _, row in boundaries.iterrows():
        if row.geometry and row.geometry.contains(pt):
            return row["planning_area"]
    return None


def assign_stations_to_planning_areas(
    stations_df: pd.DataFrame, boundaries: gpd.GeoDataFrame
) -> dict[str, str]:
    """Return {station_id: planning_area} mapping for all stations."""
    mapping: dict[str, str] = {}
    for _, row in stations_df.iterrows():
        area = _point_to_planning_area(row["lat"], row["lng"], boundaries)
        if area:
            mapping[row["station_id"]] = area
    n_mapped = len(mapping)
    logger.info("Mapped %d/%d weather stations to planning areas", n_mapped, len(stations_df))
    return mapping


def assign_dengue_to_planning_areas(
    dengue_df: pd.DataFrame, boundaries: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Add 'planning_area' column to dengue_df based on Latitude/Longitude."""
    df = dengue_df.copy()
    n_total = len(df)
    logger.info("Assigning %d dengue records to planning areas via spatial join…", n_total)
    areas = []
    for i, (_, row) in enumerate(df.iterrows()):
        if i % 500 == 0:
            logger.info("  spatial join progress: %d/%d rows", i, n_total)
        areas.append(_point_to_planning_area(row["Latitude"], row["Longitude"], boundaries))
    df["planning_area"] = areas
    df = df.dropna(subset=["planning_area"])
    logger.info("Assigned %d/%d dengue records to planning areas", len(df), n_total)
    return df


# ── Weekly aggregation ────────────────────────────────────────────────────────

def _iso_week_label(date: pd.Timestamp) -> str:
    iso = date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def aggregate_weekly_dengue(dengue_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate cluster-snapshot data to weekly cases per planning area.

    Each cluster may appear in multiple snapshots within one week.
    Strategy: for each (week, cluster_id), take the LAST recorded CaseSize
    (most recent snapshot), then sum across clusters per planning area.
    This avoids double-counting the same active cluster.
    """
    df = dengue_df.copy()
    df["week"] = df["Date"].apply(_iso_week_label)
    # Keep only the latest snapshot per cluster per week
    df = df.sort_values("Date")
    df = df.drop_duplicates(subset=["week", "cluster_id", "planning_area"], keep="last")
    return (
        df.groupby(["planning_area", "week"])["CaseSize"]
        .sum()
        .reset_index()
        .rename(columns={"CaseSize": "cases"})
    )


def aggregate_weekly_weather(
    weather_df: pd.DataFrame, station_map: dict[str, str], col_name: str
) -> pd.DataFrame:
    df = weather_df.copy()
    df["planning_area"] = df["station_id"].map(station_map)
    df = df.dropna(subset=["planning_area"])
    return (
        df.groupby(["planning_area", "week"])["value"]
        .mean()
        .reset_index()
        .rename(columns={"value": col_name})
    )


# ── Panel + feature engineering ───────────────────────────────────────────────

def build_panel(
    dengue_weekly: pd.DataFrame,
    rainfall_weekly: pd.DataFrame,
    temp_weekly: pd.DataFrame,
    all_planning_areas: list[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Build a full (planning_area, week) panel and join dengue + weather."""
    mondays = pd.date_range(
        start=f"{start_year}-01-01", end=f"{end_year}-12-31", freq="W-MON"
    )
    all_weeks = sorted({_iso_week_label(d) for d in mondays})

    idx = pd.MultiIndex.from_product(
        [all_planning_areas, all_weeks], names=["planning_area", "week"]
    )
    panel = pd.DataFrame(index=idx).reset_index()

    panel = panel.merge(dengue_weekly, on=["planning_area", "week"], how="left")
    panel["cases"] = panel["cases"].fillna(0).astype(float)

    # National active cases per week (sum across all areas — same value for every area in that week)
    national_weekly = (
        dengue_weekly.groupby("week")["cases"].sum()
        .reset_index().rename(columns={"cases": "national_cases"})
    )
    panel = panel.merge(national_weekly, on="week", how="left")
    panel["national_cases"] = panel["national_cases"].fillna(0).astype(float)

    panel = panel.merge(rainfall_weekly, on=["planning_area", "week"], how="left")
    panel = panel.merge(temp_weekly, on=["planning_area", "week"], how="left")

    panel = panel.sort_values(["planning_area", "week"]).reset_index(drop=True)
    panel["week_of_year"] = panel["week"].apply(lambda w: int(w.split("-W")[1]))
    return panel


def add_lagged_features(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    for lag in range(1, 5):
        df[f"lag_cases_{lag}w"] = df.groupby("planning_area")["cases"].shift(lag)
    for lag in (1, 2):
        df[f"lag_national_{lag}w"] = df.groupby("planning_area")["national_cases"].shift(lag)
    for lag in (2, 3):
        df[f"lag_rainfall_{lag}w"] = df.groupby("planning_area")["rainfall"].shift(lag)
        df[f"lag_temp_{lag}w"] = df.groupby("planning_area")["temperature"].shift(lag)
    return df


def label_risk(df: pd.DataFrame, train_mask: pd.Series) -> pd.DataFrame:
    """
    Assign risk_level using quantile thresholds derived from training data only.
    Zero-case rows → Low regardless of thresholds.
    """
    train_nonzero = df.loc[train_mask & (df["cases"] > 0), "cases"]
    q60 = float(train_nonzero.quantile(0.60))
    q90 = float(train_nonzero.quantile(0.90))
    logger.info("Risk thresholds — q60: %.1f cases, q90: %.1f cases", q60, q90)

    def _level(cases: float) -> str:
        if cases == 0:
            return "Low"
        if cases <= q60:
            return "Low"
        if cases <= q90:
            return "Medium"
        return "High"

    df = df.copy()
    df["risk_level"] = df["cases"].apply(_level)
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("DengueWatch SG — Training Data Preparation")
    logger.info("Output dir : %s", output_dir.resolve())
    logger.info("Date range : %d–%d", args.start_year, args.end_year)
    logger.info("=" * 60)

    # ── Stage 1: Planning area boundaries ────────────────────────────
    logger.info("[1/6] Fetching URA planning area boundaries…")
    boundaries = fetch_planning_boundaries(
        cache_path=raw_dir / "planning_boundaries.geojson",
        boundaries_geojson_arg=args.boundaries_geojson,
        onemap_token=args.onemap_token,
    )
    all_areas = sorted(boundaries["planning_area"].unique().tolist())
    logger.info("[1/6] Done — %d planning areas loaded", len(all_areas))

    with open(output_dir / "planning_areas.json", "w") as f:
        json.dump(all_areas, f, indent=2)

    # ── Stage 2: Historical dengue clusters ──────────────────────────
    logger.info("[2/6] Loading historical dengue cluster data…")
    dengue_raw = fetch_dengue_data(
        dengue_csv_arg=args.dengue_csv,
        cache_path=raw_dir / "historical_dengue.csv",
    )
    logger.info("[2/6] Loaded %d dengue records spanning %s to %s",
                len(dengue_raw), dengue_raw["Date"].min().date(), dengue_raw["Date"].max().date())
    dengue_with_areas = assign_dengue_to_planning_areas(dengue_raw, boundaries)
    dengue_weekly = aggregate_weekly_dengue(dengue_with_areas)
    logger.info("[2/6] Done — %d (planning_area, week) dengue rows", len(dengue_weekly))

    # ── Stage 3: Historical weather ───────────────────────────────────
    logger.info("[3/6] Fetching historical weather data from data.gov.sg…")
    logger.info("      (this makes ~%d API calls — may take several minutes)",
                (args.end_year - args.start_year + 1) * 52 * 2)
    rainfall_df, temp_df, stations_df = build_weekly_weather(
        start_year=args.start_year,
        end_year=args.end_year,
        cache_dir=raw_dir,
        delay=args.api_delay,
    )
    logger.info("[3/6] Done — %d rainfall rows, %d temperature rows, %d stations",
                len(rainfall_df), len(temp_df), len(stations_df))

    # ── Stage 4: Station → planning area mapping ──────────────────────
    logger.info("[4/6] Mapping weather stations to planning areas…")
    station_map = assign_stations_to_planning_areas(stations_df, boundaries)
    station_map_path = output_dir / "station_planning_area.json"
    with open(station_map_path, "w") as f:
        json.dump(station_map, f, indent=2)
    logger.info("[4/6] Done — %d/%d stations mapped, saved to %s",
                len(station_map), len(stations_df), station_map_path)

    rainfall_weekly = aggregate_weekly_weather(rainfall_df, station_map, "rainfall")
    temp_weekly = aggregate_weekly_weather(temp_df, station_map, "temperature")
    logger.info("      Weekly rainfall: %d rows | Weekly temperature: %d rows",
                len(rainfall_weekly), len(temp_weekly))

    # ── Stage 5: Build feature panel ─────────────────────────────────
    logger.info("[5/6] Building full (planning_area × week) panel and lag features…")
    panel = build_panel(
        dengue_weekly, rainfall_weekly, temp_weekly,
        all_areas, args.start_year, args.end_year,
    )
    panel = add_lagged_features(panel)
    logger.info("[5/6] Done — panel shape: %s", panel.shape)

    # ── Stage 6: Label + split ────────────────────────────────────────
    logger.info("[6/6] Labelling risk levels and splitting train/validation…")
    panel["year"] = panel["week"].apply(lambda w: int(w.split("-W")[0]))
    train_mask = panel["year"].isin(range(args.start_year, args.train_end_year + 1))
    val_mask = panel["year"].isin(range(args.val_start_year, args.end_year + 1))
    logger.info("Train years: %d–%d | Val years: %d–%d",
                args.start_year, args.train_end_year, args.val_start_year, args.end_year)

    panel = label_risk(panel, train_mask)

    # Drop incomplete lag rows (first 4 weeks per planning area have no lags)
    train_df = panel[train_mask][OUTPUT_COLS].dropna()
    val_df = panel[val_mask][OUTPUT_COLS].dropna()

    logger.info("Train distribution: %s", train_df["risk_level"].value_counts().to_dict())

    # Apply SMOTE to oversample minority classes in training set only.
    # SMOTE interpolates between existing minority samples in feature space.
    # Validation set is never modified.
    if args.no_smote:
        logger.info("SMOTE skipped (--no-smote). Sample weights in train.py will handle imbalance.")
        smote_df = train_df
    else:
      try:
        from imblearn.over_sampling import SMOTE
        label_map = {"Low": 0, "Medium": 1, "High": 2}
        X_tr = train_df[FEATURE_COLS].values
        y_tr = train_df["risk_level"].map(label_map).values
        meta_tr = train_df[["planning_area", "week"]].values

        # k_neighbors must be < smallest class count
        min_class_count = min(int((y_tr == v).sum()) for v in [0, 1, 2])
        k = min(5, min_class_count - 1)
        if k < 1:
            logger.warning("Not enough minority samples for SMOTE (min class=%d), skipping", min_class_count)
            smote_df = train_df
        else:
            sm = SMOTE(random_state=42, k_neighbors=k)
            X_res, y_res = sm.fit_resample(X_tr, y_tr)
            inv_map = {0: "Low", 1: "Medium", 2: "High"}
            n_synthetic = len(X_res) - len(X_tr)
            smote_df = pd.DataFrame(X_res, columns=FEATURE_COLS)
            smote_df["risk_level"] = [inv_map[y] for y in y_res]
            # Synthetic rows get placeholder metadata
            smote_df["planning_area"] = list(meta_tr[:, 0]) + ["SYNTHETIC"] * n_synthetic
            smote_df["week"] = list(meta_tr[:, 1]) + ["SYNTHETIC"] * n_synthetic
            logger.info("SMOTE added %d synthetic rows", n_synthetic)
      except Exception as exc:
        logger.warning("SMOTE failed (%s), using original training set", exc)
        smote_df = train_df

    train_path = output_dir / "train.csv"
    val_path = output_dir / "validation.csv"
    smote_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)

    logger.info("[6/6] Done")
    logger.info("=" * 60)
    logger.info("Output summary")
    logger.info("  train.csv      : %d rows → %s", len(smote_df), train_path)
    logger.info("  validation.csv : %d rows → %s", len(val_df), val_path)
    logger.info("  Train risk distribution : %s", smote_df["risk_level"].value_counts().to_dict())
    logger.info("  Val   risk distribution : %s", val_df["risk_level"].value_counts().to_dict())
    logger.info("=" * 60)
    logger.info("All done. Run train.py next:")


if __name__ == "__main__":
    main()
