FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Skip geopandas and fiona — build_features.py reads GeoJSON directly via shapely
COPY requirements.txt .
RUN grep -v -E "^(fiona|geopandas)" requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY scripts/ /opt/ml/code/scripts/
COPY data/planning_areas.json /opt/ml/code/data/
COPY data/station_planning_area.json /opt/ml/code/data/
COPY data/raw/planning_boundaries.geojson /opt/ml/code/data/raw/
