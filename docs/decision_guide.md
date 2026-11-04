# Decision Guide: Choosing a Format, Codec and Partitioning Strategy

## Executive recommendation

For the tested analytical workloads, **Parquet is the default recommendation** because it delivered the lowest average query latency and smallest average output size in the current benchmark. Use partitioning when queries repeatedly filter on the partition columns. Keep Avro for event-oriented interchange or schema-evolution use cases where its row-oriented representation is valuable; it is not the preferred format for the analytical scans tested here.

These recommendations apply to the tested dataset, software stack and single-machine environment. They are starting points, not universal guarantees.

## Recommendations by workload

| Workload | Recommended starting point | Why | Trade-off |
|---|---|---|---|
| Interactive analytics | Parquet + Snappy or Zstd; partition by date when date filters are common | Columnar reads and predicate/partition pruning suit selective analytical queries | Too many small partitions/files can hurt metadata and planning overhead |
| Batch ETL | Parquet + Snappy for balanced throughput; benchmark Zstd when storage is more important | Good analytical compatibility and compression/performance balance | Stronger compression can increase CPU time |
| Archival | Parquet + Zstd or the smallest validated codec configuration | Prioritizes storage reduction while retaining broad analytical support | Compression/decompression costs and future access latency |
| Streaming/event interchange | Avro where schema evolution and record-oriented processing are central | Row-oriented serialization and schema support | Less efficient for the analytical scans in this experiment |

## Evidence from this experiment

The current notebook summary reports average query execution times of approximately:

- Parquet: **0.0788 s**
- ORC: **0.4663 s**
- Avro: **22.1315 s**

Average output sizes in the same analysis are approximately:

- Parquet: **113.04 MB**
- ORC: **146.22 MB**
- Avro: **325.96 MB**

The workload-level table shows Parquet faster than ORC and Avro for all four tested query types. Partitioning results show a strong improvement for point lookups and range filters when the data is partitioned by date or date plus zone. Full scans remain close across partitioning strategies, and partitioning can add overhead.

The notebook's per-workload best-query table should be used when selecting a precise codec and partition layout. Do not infer a single global winner from one query.

## How to choose partitioning

- **No partitioning:** sensible for full-scan workloads, small datasets, or when queries do not filter on a stable key.
- **By date:** a practical default for time-series data queried by date range. It can reduce the amount of data read for time-bounded queries.
- **By date and zone:** may improve selective lookups when queries consistently filter by both date and zone, but creates many more files/partitions. Validate file sizes and metadata overhead.

Avoid over-partitioning. Hundreds or thousands of tiny files can make planning, listing and maintenance expensive.

## Energy interpretation

The energy model estimates consumption from measured CPU time and I/O or wall time using assumed power values. It is useful for **relative comparison under consistent assumptions**, but it is not a direct measurement of electricity consumed at the wall. Report energy values as estimates and disclose the model assumptions.

## Petabyte-scale interpretation

The extrapolation scales sample measurements linearly to a petabyte-scale scenario. This is an order-of-magnitude planning aid only. Real distributed systems introduce parallelism, replication, network transfer, metadata, skew, compaction, fault tolerance and storage-tier effects. Do not present the extrapolated figures as observed cluster performance.

## Final decision

Adopt **Parquet as the default analytical storage format** for this case study. Start with Snappy for balanced interactive and ETL workloads; evaluate Zstd for storage-sensitive or archival workloads. Partition by date only when date predicates are common, and add zone partitioning only when measured query benefits justify the extra file and metadata overhead. Retain Avro for ingestion/interchange requirements rather than analytical serving.
