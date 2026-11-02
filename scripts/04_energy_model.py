"""
04_energy_model.py

Estimates energy consumption for the write and query workloads from CPU-time
measurements already collected, using a simple, transparent, documented
power model rather than hardware power-metering (not available in this
sandbox). This is explicitly an ESTIMATE, not a measurement -- the
methodology and its limits are written up in docs/decision_guide.md.

Model
-----
energy_joules = cpu_seconds * cpu_tdp_share_watts
              + wall_seconds * (storage_io_watts_per_gb * size_gb)

Where:
  cpu_tdp_share_watts   : average power draw attributable to one CPU core
                          under load, taken as 15 W (a mid-range server CPU
                          core share; see decision guide for the sensitivity
                          range we also report, 8-25 W).
  storage_io_watts_per_gb: incremental power draw of SSD-backed cloud block
                          storage per GB actively read/written per second of
                          wall time, taken as 0.65 W/GB (derived from
                          published SSD active-power figures; see guide).

For WRITE energy we also multiply by size_gb of the OUTPUT (what was
written). For QUERY energy we use the size_gb of bytes actually touched
(after partition pruning) when available, else the full dataset size --
this is what lets Parquet/ORC's partition+column pruning show up as an
energy win, not just a time win.

Then we extrapolate from the ~4.67M-row sample (3 months, ~141 MB clean
in-memory / tens of MB on disk per format) to a petabyte-scale annual
workload, by linear scaling of per-row costs -- documented and justified
(or challenged) in the decision guide, since compression ratios and query
selectivity do not always scale perfectly linearly with volume.

Usage:
    python scripts/04_energy_model.py
"""
import os

import pandas as pd

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
WRITE_RESULTS = os.path.join(RESULTS_DIR, "write_benchmark.csv")
QUERY_RESULTS = os.path.join(RESULTS_DIR, "query_benchmark.csv")

CPU_WATTS = 15.0          # watts attributable to one loaded CPU core (mid estimate)
IO_WATTS_PER_GB_S = 0.65  # watts per GB of data moved per second of wall time

# Sample -> petabyte-scale extrapolation factor.
# Sample: 3 months of 1 NYC taxi fleet ~4.67M rows, ~0.9 GB raw CSV.
# A petabyte-scale lakehouse workload (per the case study) is modeled as
# roughly 1,000,000x this sample (e.g. thousands of data sources at much
# higher daily volume, retained for years) -- see decision_guide.md for the
# full justification and why this is a rough order-of-magnitude scaling,
# not a precise projection.
PB_SCALE_FACTOR = 1_000_000


def energy_joules(cpu_seconds, wall_seconds, size_gb):
    if pd.isna(cpu_seconds) or pd.isna(size_gb):
        return None
    cpu_term = cpu_seconds * CPU_WATTS
    io_term = wall_seconds * IO_WATTS_PER_GB_S * max(size_gb, 0.001)
    return cpu_term + io_term


def main():
    # keep_default_na=False: the Avro codec named "null" (= no codec) would
    # otherwise be silently read as a missing value.
    write_df = pd.read_csv(WRITE_RESULTS, keep_default_na=False, na_values=[])
    query_df = pd.read_csv(QUERY_RESULTS, keep_default_na=False, na_values=[])
    for col in ["write_seconds", "size_bytes", "size_mb", "file_count"]:
        write_df[col] = pd.to_numeric(write_df[col], errors="coerce")
    for col in ["wall_seconds", "cpu_seconds"]:
        query_df[col] = pd.to_numeric(query_df[col], errors="coerce")

    # --- Write energy ---
    write_df["size_gb"] = write_df["size_bytes"] / 1e9
    write_df["write_energy_joules"] = write_df.apply(
        lambda r: energy_joules(r["write_seconds"], r["write_seconds"], r["size_gb"]), axis=1
    )
    write_df["write_energy_wh"] = write_df["write_energy_joules"] / 3600.0
    write_df.to_csv(os.path.join(RESULTS_DIR, "write_energy.csv"), index=False)

    # --- Query energy --- (merge in output size as a proxy for bytes touched
    # when we don't track pruned bytes directly; still format/codec/partition
    # specific, which is the comparison that matters here)
    merged = query_df.merge(
        write_df[["format", "codec", "partitioning", "size_gb"]],
        on=["format", "codec", "partitioning"], how="left"
    )
    merged["query_energy_joules"] = merged.apply(
        lambda r: energy_joules(r["cpu_seconds"], r["wall_seconds"], r["size_gb"]), axis=1
    )
    merged["query_energy_wh"] = merged["query_energy_joules"] / 3600.0
    merged.to_csv(os.path.join(RESULTS_DIR, "query_energy.csv"), index=False)

    # --- Summary rollups ---
    write_summary = (
        write_df.groupby(["format", "codec", "partitioning"])
        .agg(size_mb=("size_mb", "first"), write_seconds=("write_seconds", "first"),
             write_energy_wh=("write_energy_wh", "first"))
        .reset_index()
        .sort_values("size_mb")
    )
    write_summary.to_csv(os.path.join(RESULTS_DIR, "write_summary.csv"), index=False)

    query_summary = (
        merged.groupby(["format", "codec", "partitioning"])
        .agg(avg_wall_seconds=("wall_seconds", "mean"), avg_cpu_seconds=("cpu_seconds", "mean"),
             total_query_energy_wh=("query_energy_wh", "sum"))
        .reset_index()
        .sort_values("total_query_energy_wh")
    )
    query_summary.to_csv(os.path.join(RESULTS_DIR, "query_summary.csv"), index=False)

    # --- Petabyte-scale extrapolation (order of magnitude, annualized) ---
    extrap_rows = []
    for _, r in write_summary.iterrows():
        extrap_rows.append({
            "format": r["format"], "codec": r["codec"], "partitioning": r["partitioning"],
            "sample_size_mb": r["size_mb"],
            "projected_size_tb_at_pb_scale": round(r["size_mb"] * PB_SCALE_FACTOR / 1e6, 1),
            "projected_write_energy_kwh_at_pb_scale":
                round((r["write_energy_wh"] or 0) * PB_SCALE_FACTOR / 1000, 1),
        })
    extrap_df = pd.DataFrame(extrap_rows).sort_values("projected_size_tb_at_pb_scale")
    extrap_df.to_csv(os.path.join(RESULTS_DIR, "petabyte_extrapolation.csv"), index=False)

    print("Wrote: write_energy.csv, query_energy.csv, write_summary.csv, "
          "query_summary.csv, petabyte_extrapolation.csv")
    print("\n=== Write summary (sorted by size) ===")
    print(write_summary.to_string(index=False))
    print("\n=== Query summary (sorted by total energy) ===")
    print(query_summary.to_string(index=False))


if __name__ == "__main__":
    main()
