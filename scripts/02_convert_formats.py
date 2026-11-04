"""
02_convert_formats.py

Converts the cleaned trip dataset into Parquet, ORC and Avro, each with
multiple compression codecs, and with three partitioning schemes:
  - none        : one file
  - by_date     : one directory level, partitioned by pickup_date (~90 partitions)
  - by_date_zone: two directory levels, by pickup_date then PU location id

For every (format, codec, partitioning) combination we record:
  - wall-clock write time
  - total bytes on disk (sum of all part files)
  - number of files written

Results are appended to results/write_benchmark.csv.

Why these three formats/codecs:
  - Parquet: columnar, the de-facto lakehouse default (Snappy, Gzip, Zstd, none)
  - ORC: columnar, strong compression + built-in indexes, common in Hive/Hadoop
         shops (Zlib, Zstd, none -- pyarrow's ORC writer does not expose Snappy)
  - Avro: row-oriented, schema-evolution friendly, common for streaming/Kafka
          (Deflate, Snappy, null)

Usage:
    python scripts/02_convert_formats.py
"""
import glob
import json
import os
import shutil
import time

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyarrow.orc as orc
import fastavro

IN_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "converted", "trips_clean.feather")
OUT_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "converted")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "write_benchmark.csv")

PARQUET_CODECS = ["snappy", "gzip", "zstd", "none"]
ORC_CODECS = ["zlib", "zstd", "uncompressed"]
AVRO_CODECS = ["deflate", "snappy", "null"]

PARTITIONING = ["none", "by_date", "by_date_zone"]


def dir_size_bytes(path: str) -> tuple[int, int]:
    """Returns (total_bytes, file_count) for a file or directory tree."""
    if os.path.isfile(path):
        return os.path.getsize(path), 1
    total, count = 0, 0
    for root, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
            count += 1
    return total, count


def clear(path: str):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Parquet
# ---------------------------------------------------------------------------
def write_parquet(table: pa.Table, df: pd.DataFrame, codec: str, partitioning: str, out_dir: str):

    clear(out_dir)

    compression = None if codec == "none" else codec

    if partitioning == "none":
        pq.write_table(table, out_dir + ".parquet", compression=compression)
        return out_dir + ".parquet"

    elif partitioning == "by_date":
        pq.write_to_dataset(
            table,
            root_path=out_dir,
            partition_cols=["pickup_date"],
            compression=compression,
            max_open_files=64
        )
        return out_dir

    else:  # by_date_zone
        pq.write_to_dataset(
            table,
            root_path=out_dir,
            partition_cols=["pickup_date", "zone_group"],
            compression=compression,
            max_open_files=64
        )
        return out_dir


# ---------------------------------------------------------------------------
# ORC  (pyarrow's ORC writer has no native partition helper, so we partition
# manually by writing one file per partition key combination)
# ---------------------------------------------------------------------------
def _orc_safe_table(table: pa.Table) -> pa.Table:
    """pyarrow's ORC writer rejects dictionary-encoded (category) columns, so
    we decode them to plain strings first. Parquet and Avro both handle
    dictionary/category columns natively, so this cast is ORC-specific."""
    for i, field in enumerate(table.schema):
        if pa.types.is_dictionary(field.type):
            table = table.set_column(i, field.name, pc.cast(table.column(i), pa.string()))
    return table


def write_orc(table: pa.Table, df: pd.DataFrame, codec: str, partitioning: str, out_dir: str):
    clear(out_dir)
    compression = codec if codec != "uncompressed" else "uncompressed"
    table = _orc_safe_table(table)
    if partitioning == "none":
        path = out_dir + ".orc"
        orc.write_table(table, path, compression=compression)
        return path

    os.makedirs(out_dir, exist_ok=True)
    if partitioning == "by_date":
        keys = ["pickup_date"]
    else:
        keys = ["pickup_date", "zone_group"]

    for key_vals, group in df.groupby(keys, observed=True):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        sub = out_dir
        for k, v in zip(keys, key_vals):
            sub = os.path.join(sub, f"{k}={v}")
        os.makedirs(sub, exist_ok=True)
        group_table = _orc_safe_table(pa.Table.from_pandas(group, preserve_index=False))
        orc.write_table(group_table, os.path.join(sub, "part-0.orc"), compression=compression)
    return out_dir


# ---------------------------------------------------------------------------
# Avro
# ---------------------------------------------------------------------------
AVRO_SCHEMA_CACHE = {}


def avro_schema_for(df: pd.DataFrame):
    fields = []
    for col, dtype in df.dtypes.items():
        if "int" in str(dtype).lower():
            t = ["null", "long"]
        elif "float" in str(dtype).lower():
            t = ["null", "double"]
        elif "datetime" in str(dtype).lower():
            t = ["null", {"type": "long", "logicalType": "timestamp-micros"}]
        else:
            t = ["null", "string"]
        fields.append({"name": col, "type": t, "default": None})
    return {"type": "record", "name": "Trip", "fields": fields}


def avro_record_stream(df: pd.DataFrame, chunk_rows: int = 100_000):
    """Yields avro-ready record dicts in chunks, converting dtypes per-chunk
    rather than materializing the whole DataFrame as a Python list of dicts
    at once (which OOM'd the sandbox at 4.67M rows: df.to_dict(orient=
    'records') on a wide DataFrame roughly triples peak memory)."""
    datetime_cols = [c for c in df.columns if "datetime" in str(df[c].dtype).lower()]
    str_cols = [c for c in df.columns if str(df[c].dtype) in ("category", "string")]
    int_cols = [c for c in df.columns if pd.api.types.is_integer_dtype(df[c])
                and c not in datetime_cols]

    n = len(df)
    for start in range(0, n, chunk_rows):
        chunk = df.iloc[start:start + chunk_rows].copy()
        for col in datetime_cols:
            chunk[col] = chunk[col].astype("int64") // 1000  # ns -> us
        for col in str_cols:
            # astype(str) on a nullable/category column turns missing values
            # into the literal string "nan", which then fails Avro's
            # ['null','string'] union (fastavro expects a real None for the
            # null branch). Convert only the non-null values to str and
            # leave missing values as None explicitly.
            mask = chunk[col].notna()
            chunk[col] = chunk[col].astype(object)
            chunk.loc[mask, col] = chunk.loc[mask, col].astype(str)
            chunk.loc[~mask, col] = None
        for col in int_cols:
            vals = chunk[col]
            mask = vals.notna()
            chunk[col] = chunk[col].astype(object)
            chunk.loc[mask, col] = vals[mask].astype("int64")
            chunk.loc[~mask, col] = None
        yield from chunk.to_dict(orient="records")


def write_avro(df: pd.DataFrame, codec: str, partitioning: str, out_dir: str):
    clear(out_dir)
    codec_name = codec if codec != "null" else "null"
    schema = avro_schema_for(df)

    if partitioning == "none":
        path = out_dir + ".avro"
        with open(path, "wb") as f:
            fastavro.writer(f, schema, avro_record_stream(df), codec=codec_name)
        return path

    os.makedirs(out_dir, exist_ok=True)
    keys = ["pickup_date"] if partitioning == "by_date" else ["pickup_date", "zone_group"]
    for key_vals, group in df.groupby(keys, observed=True):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        sub = out_dir
        for k, v in zip(keys, key_vals):
            sub = os.path.join(sub, f"{k}={v}")
        os.makedirs(sub, exist_ok=True)
        path = os.path.join(sub, "part-0.avro")
        with open(path, "wb") as f:
            fastavro.writer(f, schema, avro_record_stream(group), codec=codec_name)
    return out_dir


def main():
    print("Loading clean dataset...")
    df = pd.read_feather(IN_PATH)
    df["pickup_date"] = df["pickup_date"].astype(str)
    # Second partition key for the "by_date_zone" scheme. Using the raw
    # pu_location_id (~260 distinct values) together with ~90 dates would
    # produce on the order of 10k-20k tiny partitions -- a real but extreme
    # instance of the "small files" problem that would make this benchmark
    # take hours to write with a naive per-partition writer loop. We bucket
    # location IDs into 6 coarse zone groups (zone_group = id // 50) so the
    # by_date_zone scheme still demonstrates a second partitioning level
    # (~540 partitions) while staying tractable; results/write_benchmark.csv
    # records file_count directly, so the small-files effect is still visible
    # and the methodology is documented in docs/decision_guide.md.
    df["zone_group"] = (df["pu_location_id"].fillna(0).astype(int) // 50).astype(str)
    table = pa.Table.from_pandas(df, preserve_index=False)
    print(f"Loaded {len(df):,} rows, {df.memory_usage(deep=True).sum() / 1e6:.1f} MB in memory")

    rows = []

    jobs = []
    for codec in PARQUET_CODECS:
        for part in PARTITIONING:
            jobs.append(("parquet", codec, part))
    for codec in ORC_CODECS:
        for part in PARTITIONING:
            jobs.append(("orc", codec, part))
    for codec in AVRO_CODECS:
        for part in PARTITIONING:
            jobs.append(("avro", codec, part))

    for fmt, codec, part in jobs:
        tag = f"{fmt}_{codec}_{part}"
        out_dir = os.path.join(OUT_ROOT, tag)
        print(f"Writing {tag} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            if fmt == "parquet":
                result_path = write_parquet(table, df, codec, part, out_dir)
            elif fmt == "orc":
                result_path = write_orc(table, df, codec, part, out_dir)
            else:
                result_path = write_avro(df, codec, part, out_dir)
            elapsed = time.time() - t0
            size_bytes, file_count = dir_size_bytes(result_path)
            print(f"{elapsed:.2f}s, {size_bytes/1e6:.1f} MB, {file_count} files")
            rows.append({
                "format": fmt, "codec": codec, "partitioning": part,
                "write_seconds": round(elapsed, 3),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / 1e6, 2),
                "file_count": file_count,
                "path": os.path.relpath(result_path, OUT_ROOT),
            })
        except Exception as e:
            print(f"FAILED: {e}")
            rows.append({
                "format": fmt, "codec": codec, "partitioning": part,
                "write_seconds": None, "size_bytes": None, "size_mb": None,
                "file_count": None, "path": None, "error": str(e),
            })

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(RESULTS_PATH, index=False)
    print(f"\nWrote {len(rows)} benchmark rows to {RESULTS_PATH}")

    # Raw CSV.gz baseline for reference
    raw_files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "*.csv.gz"))
    raw_size = sum(os.path.getsize(f) for f in raw_files)
    print(f"(Reference: original raw CSV.gz total size = {raw_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
