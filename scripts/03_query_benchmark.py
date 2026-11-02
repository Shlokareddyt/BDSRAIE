"""
03_query_benchmark.py

Runs a fixed set of representative queries against every (format, codec,
partitioning) combination produced by 02_convert_formats.py, and records
wall-clock query time and process-level CPU time (user+sys) for each.

Query set (chosen to stress different access patterns):
  Q1 point_lookup   - single day, single pickup zone  (partition-pruning win)
  Q2 full_scan_agg  - average fare by payment_type over the whole dataset
                       (column-pruning win: touches only 2 of 18 columns)
  Q3 wide_scan      - monthly trip count + total revenue, all columns touched
                       except geo ids (medium column pruning)
  Q4 range_filter   - trips in the last 7 days of the window, all columns
                       (partition-pruning win on by_date / by_date_zone)

For Parquet we use pyarrow.dataset so partition pruning and column
projection are both exercised, matching how a real lakehouse query engine
(Spark/Trino/DuckDB) would read it. For ORC and Avro, which we hand-wrote
per-partition, we glob the matching files and read only those.

Usage:
    python scripts/03_query_benchmark.py
"""
import glob
import os
import resource
import time

import fastavro
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.orc as orc

CONVERTED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "converted")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "query_benchmark.csv")
WRITE_RESULTS = os.path.join(os.path.dirname(__file__), "..", "results", "write_benchmark.csv")

SAMPLE_DATE = "2021-02-15"          # used by Q1 / point_lookup
SAMPLE_ZONE_GROUP = "2"             # pu_location_id // 50 == 2  (covers ids 100-149)
RANGE_START = "2021-03-25"          # used by Q4 / range_filter


def cpu_time():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def timeit(fn, *a, **kw):
    t0, c0 = time.time(), cpu_time()
    result = fn(*a, **kw)
    return result, time.time() - t0, cpu_time() - c0


# ---------------------------------------------------------------------------
# Parquet queries (pyarrow.dataset handles partition pruning automatically)
# ---------------------------------------------------------------------------
def pq_point_lookup(path, partitioning):
    dataset = ds.dataset(path, format="parquet", partitioning="hive") if os.path.isdir(path) else ds.dataset(path, format="parquet")
    filt = (pc.field("pickup_date") == SAMPLE_DATE)
    if partitioning == "by_date_zone":
        # pyarrow.dataset's hive partition discovery infers the partition
        # column's type from the directory names (here, integer-looking
        # strings like "zone_group=2" are inferred as int32), so the filter
        # literal must match that inferred type, not the string we use for
        # ORC/Avro file-path globbing below.
        filt = filt & (pc.field("zone_group") == int(SAMPLE_ZONE_GROUP))
    table = dataset.to_table(filter=filt, columns=["pickup_datetime", "trip_distance", "fare_amount"])
    return len(table)


def pq_full_scan_agg(path):
    dataset = ds.dataset(path, format="parquet", partitioning="hive") if os.path.isdir(path) else ds.dataset(path, format="parquet")
    table = dataset.to_table(columns=["payment_type", "fare_amount"])
    df = table.to_pandas()
    return df.groupby("payment_type")["fare_amount"].mean().to_dict()


def pq_wide_scan(path):
    dataset = ds.dataset(path, format="parquet", partitioning="hive") if os.path.isdir(path) else ds.dataset(path, format="parquet")
    cols = ["pickup_datetime", "trip_distance", "fare_amount", "tip_amount", "total_amount",
            "passenger_count", "payment_type"]
    table = dataset.to_table(columns=[c for c in cols if c in dataset.schema.names])
    df = table.to_pandas()
    return {"count": len(df), "revenue": float(df["total_amount"].sum())}


def pq_range_filter(path, partitioning):
    dataset = ds.dataset(path, format="parquet", partitioning="hive") if os.path.isdir(path) else ds.dataset(path, format="parquet")
    filt = (pc.field("pickup_date") >= RANGE_START)
    table = dataset.to_table(filter=filt)
    return len(table)


# ---------------------------------------------------------------------------
# ORC queries (manual partition pruning via glob, since we hand-wrote the layout)
# ---------------------------------------------------------------------------
def orc_files_for(path, partitioning, date_filter=None, zone_filter=None, date_prefix_filter=None):
    if os.path.isfile(path):
        return [path]
    if partitioning == "none":
        return glob.glob(os.path.join(path, "*.orc"))
    pattern = os.path.join(path, "pickup_date=*", "*.orc") if partitioning == "by_date" \
        else os.path.join(path, "pickup_date=*", "zone_group=*", "*.orc")
    files = glob.glob(pattern)
    if date_filter:
        files = [f for f in files if f"pickup_date={date_filter}" in f]
    if date_prefix_filter:
        files = [f for f in files if _date_from_path(f) >= date_prefix_filter]
    if zone_filter and partitioning == "by_date_zone":
        files = [f for f in files if f"zone_group={zone_filter}" in f]
    return files


def _date_from_path(path):
    for part in path.split(os.sep):
        if part.startswith("pickup_date="):
            return part.split("=", 1)[1]
    return ""


def orc_read_concat(files, columns=None):
    if not files:
        return pd.DataFrame()
    tables = []
    for f in files:
        t = orc.read_table(f)
        if columns:
            t = t.select([c for c in columns if c in t.schema.names])
        tables.append(t)
    return pa.concat_tables(tables, promote_options="default").to_pandas()


def orc_point_lookup(path, partitioning):
    files = orc_files_for(path, partitioning, date_filter=SAMPLE_DATE, zone_filter=SAMPLE_ZONE_GROUP)
    df = orc_read_concat(files, columns=["pickup_datetime", "trip_distance", "fare_amount"])
    return len(df)


def orc_full_scan_agg(path, partitioning):
    files = orc_files_for(path, partitioning)
    df = orc_read_concat(files, columns=["payment_type", "fare_amount"])
    return df.groupby("payment_type")["fare_amount"].mean().to_dict() if len(df) else {}


def orc_wide_scan(path, partitioning):
    files = orc_files_for(path, partitioning)
    df = orc_read_concat(files)
    return {"count": len(df), "revenue": float(df["total_amount"].sum()) if len(df) else 0.0}


def orc_range_filter(path, partitioning):
    files = orc_files_for(path, partitioning, date_prefix_filter=RANGE_START)
    df = orc_read_concat(files)
    return len(df)


# ---------------------------------------------------------------------------
# Avro queries (row-oriented: no column pruning possible; we still prune
# partitions via file globbing where the layout allows it)
# ---------------------------------------------------------------------------
def avro_files_for(path, partitioning, date_filter=None, zone_filter=None, date_prefix_filter=None):
    if os.path.isfile(path):
        return [path]
    if partitioning == "none":
        return glob.glob(os.path.join(path, "*.avro"))
    pattern = os.path.join(path, "pickup_date=*", "*.avro") if partitioning == "by_date" \
        else os.path.join(path, "pickup_date=*", "zone_group=*", "*.avro")
    files = glob.glob(pattern)
    if date_filter:
        files = [f for f in files if f"pickup_date={date_filter}" in f]
    if date_prefix_filter:
        files = [f for f in files if _date_from_path(f) >= date_prefix_filter]
    if zone_filter and partitioning == "by_date_zone":
        files = [f for f in files if f"zone_group={zone_filter}" in f]
    return files


def avro_read_all(files):
    """Only safe for small, already-pruned file sets (a handful of
    partitions). For an un-pruned full scan (partitioning == "none", or any
    aggregate over the whole dataset) use avro_iter_chunks below instead --
    materializing all 4.67M rows as a Python list of dicts at once is what
    OOM'd this benchmark the first time."""
    records = []
    for f in files:
        with open(f, "rb") as fh:
            records.extend(list(fastavro.reader(fh)))
    return pd.DataFrame.from_records(records) if records else pd.DataFrame()


def avro_iter_chunks(files, chunk_size=200_000):
    """Streams Avro records in bounded-memory chunks, since Avro has no
    column projection to shrink what has to be read -- unlike Parquet/ORC,
    every full scan here really does deserialize every field of every row."""
    buffer = []
    for f in files:
        with open(f, "rb") as fh:
            for rec in fastavro.reader(fh):
                buffer.append(rec)
                if len(buffer) >= chunk_size:
                    yield pd.DataFrame.from_records(buffer)
                    buffer = []
    if buffer:
        yield pd.DataFrame.from_records(buffer)


def avro_point_lookup(path, partitioning):
    # Partition pruning (when the layout allows it) narrows the file set
    # first; within the remaining files we still need an exact-match filter
    # on the fields themselves, same as the Parquet/ORC point lookups.
    zone_filter = SAMPLE_ZONE_GROUP if partitioning == "by_date_zone" else None
    date_filter = SAMPLE_DATE if partitioning != "none" else None
    files = avro_files_for(path, partitioning, date_filter=date_filter, zone_filter=zone_filter)
    count = 0
    for chunk in avro_iter_chunks(files):
        sub = chunk[chunk["pickup_date"].astype(str) == SAMPLE_DATE]
        if partitioning == "by_date_zone":
            sub = sub[sub["zone_group"].astype(str) == str(SAMPLE_ZONE_GROUP)]
        count += len(sub)
    return count


def avro_full_scan_agg(path, partitioning):
    files = avro_files_for(path, partitioning)
    sums, counts = {}, {}
    for chunk in avro_iter_chunks(files):
        if len(chunk) == 0:
            continue
        g = chunk.groupby("payment_type")["fare_amount"].agg(["sum", "count"])
        for pt, row in g.iterrows():
            sums[pt] = sums.get(pt, 0.0) + float(row["sum"])
            counts[pt] = counts.get(pt, 0) + int(row["count"])
    return {pt: sums[pt] / counts[pt] for pt in sums if counts.get(pt)}


def avro_wide_scan(path, partitioning):
    files = avro_files_for(path, partitioning)
    total_count, total_revenue = 0, 0.0
    for chunk in avro_iter_chunks(files):
        total_count += len(chunk)
        if "total_amount" in chunk.columns:
            total_revenue += float(pd.to_numeric(chunk["total_amount"], errors="coerce").fillna(0).sum())
    return {"count": total_count, "revenue": total_revenue}


def avro_range_filter(path, partitioning):
    files = avro_files_for(path, partitioning, date_prefix_filter=RANGE_START)
    count = 0
    for chunk in avro_iter_chunks(files):
        count += int((chunk["pickup_date"].astype(str) >= RANGE_START).sum())
    return count


QUERIES = ["point_lookup", "full_scan_agg", "wide_scan", "range_filter"]


def run_query(fmt, path, partitioning, query):
    if fmt == "parquet":
        fn_map = {
            "point_lookup": lambda: pq_point_lookup(path, partitioning),
            "full_scan_agg": lambda: pq_full_scan_agg(path),
            "wide_scan": lambda: pq_wide_scan(path),
            "range_filter": lambda: pq_range_filter(path, partitioning),
        }
    elif fmt == "orc":
        fn_map = {
            "point_lookup": lambda: orc_point_lookup(path, partitioning),
            "full_scan_agg": lambda: orc_full_scan_agg(path, partitioning),
            "wide_scan": lambda: orc_wide_scan(path, partitioning),
            "range_filter": lambda: orc_range_filter(path, partitioning),
        }
    else:
        fn_map = {
            "point_lookup": lambda: avro_point_lookup(path, partitioning),
            "full_scan_agg": lambda: avro_full_scan_agg(path, partitioning),
            "wide_scan": lambda: avro_wide_scan(path, partitioning),
            "range_filter": lambda: avro_range_filter(path, partitioning),
        }
    return fn_map[query]()


def main():
    write_df = pd.read_csv(WRITE_RESULTS)
    write_df = write_df[write_df["path"].notna()]

    rows = []
    for _, r in write_df.iterrows():
        fmt, codec, partitioning, rel_path = r["format"], r["codec"], r["partitioning"], r["path"]
        full_path = os.path.join(CONVERTED_DIR, rel_path)
        for query in QUERIES:
            try:
                (result, wall, cpu) = timeit(run_query, fmt, full_path, partitioning, query)
                print(f"{fmt:8s} {codec:12s} {partitioning:14s} {query:15s} "
                      f"wall={wall:6.3f}s cpu={cpu:6.3f}s")
                rows.append({
                    "format": fmt, "codec": codec, "partitioning": partitioning,
                    "query": query, "wall_seconds": round(wall, 4), "cpu_seconds": round(cpu, 4),
                })
            except Exception as e:
                print(f"{fmt:8s} {codec:12s} {partitioning:14s} {query:15s} FAILED: {e}")
                rows.append({
                    "format": fmt, "codec": codec, "partitioning": partitioning,
                    "query": query, "wall_seconds": None, "cpu_seconds": None, "error": str(e),
                })

    out_df = pd.DataFrame(rows)
    out_df.to_csv(RESULTS_PATH, index=False)
    print(f"\nWrote {len(rows)} query benchmark rows to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
