"""
01_prepare_data.py

Loads the raw NYC TLC Yellow Taxi trip-record CSVs (Jan-Mar 2021, ~4.07M rows,
downloaded from the DataTalksClub/nyc-tlc-data GitHub mirror of the official
TLC release) into a single clean pandas DataFrame with consistent dtypes, and
writes it out as an intermediate feather file so every later benchmark stage
starts from identical, already-cleaned data (keeps the comparison fair: we
are not timing CSV parsing or cleaning inside the format benchmark).

Usage:
    python scripts/01_prepare_data.py
"""
import glob
import os
import time

import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "converted", "trips_clean.feather")

# Columns we keep and their target dtypes. TLC files occasionally vary column
# capitalization/order release to release, so we normalize by name, not position.
COLUMN_MAP = {
    "vendorid": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "ratecodeid": "rate_code_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "pulocationid": "pu_location_id",
    "dolocationid": "do_location_id",
    "payment_type": "payment_type",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount",
    "congestion_surcharge": "congestion_surcharge",
}

DTYPES = {
    "vendor_id": "Int8",
    "passenger_count": "Int8",
    "trip_distance": "float32",
    "rate_code_id": "Int8",
    "store_and_fwd_flag": "category",
    "pu_location_id": "Int16",
    "do_location_id": "Int16",
    "payment_type": "Int8",
    "fare_amount": "float32",
    "extra": "float32",
    "mta_tax": "float32",
    "tip_amount": "float32",
    "tolls_amount": "float32",
    "improvement_surcharge": "float32",
    "total_amount": "float32",
    "congestion_surcharge": "float32",
}


def load_one(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)
    keep = [c for c in COLUMN_MAP.values() if c in df.columns]
    df = df[keep]

    df["pickup_datetime"] = pd.to_datetime(df["pickup_datetime"], errors="coerce")
    df["dropoff_datetime"] = pd.to_datetime(df["dropoff_datetime"], errors="coerce")

    for col, dtype in DTYPES.items():
        if col in df.columns:
            if dtype.startswith("Int"):
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(dtype)
            elif dtype == "category":
                df[col] = df[col].astype(dtype)
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(dtype)

    # Drop obviously corrupt rows: TLC meter clocks occasionally log a pickup
    # year wildly outside the file's actual month (seen here: a handful of
    # rows dated 2008 and 2021-05 inside the Jan-Mar 2021 files). We keep rows
    # within the three downloaded months and drop negative/absurd distances.
    df = df.dropna(subset=["pickup_datetime", "dropoff_datetime"])
    df = df[(df["trip_distance"] >= 0) & (df["trip_distance"] < 500)]
    df = df[(df["pickup_datetime"] >= "2021-01-01") & (df["pickup_datetime"] < "2021-04-01")]

    df["pickup_date"] = df["pickup_datetime"].dt.date.astype("string")
    return df


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "yellow_tripdata_*.csv.gz")))
    if not files:
        raise SystemExit(f"No raw files found in {RAW_DIR}")

    print(f"Found {len(files)} raw files:")
    for f in files:
        print(" -", os.path.basename(f))

    t0 = time.time()
    frames = [load_one(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    elapsed = time.time() - t0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.reset_index(drop=True).to_feather(OUT_PATH)

    print(f"\nLoaded + cleaned {len(df):,} rows in {elapsed:.1f}s")
    print(f"Columns: {list(df.columns)}")
    print(f"Date range: {df['pickup_date'].min()} to {df['pickup_date'].max()}")
    print(f"Wrote clean intermediate file: {OUT_PATH} "
          f"({os.path.getsize(OUT_PATH) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
