# Presentation Content — File Format, Compression and Energy Trade-offs

Suggested 8–9 slides for a short class presentation.

## Slide 1 — Title
**File Format, Compression and Energy Trade-offs**  
Choosing storage settings for large-scale data platforms  
Team: @Shlokareddyt and @sirisanikop

## Slide 2 — The problem
A platform team must balance:
- Storage footprint and cost
- Query latency
- Write throughput
- Energy consumption

There is no single setting that is best for every workload.

## Slide 3 — Dataset and experiment
- NYC TLC Yellow Taxi records, Jan–Mar 2021
- Project notes: approximately 4.67M cleaned rows
- Formats: Parquet, ORC, Avro
- Supported compression codecs
- Partitioning: none, date, date + coarse zone
- Four query workloads

## Slide 4 — Reproducible pipeline
CSV source → prepare/clean → convert formats → benchmark queries → estimate energy → CSV results → analysis notebook → decision guide

Mention the four scripts and that raw/converted data can be regenerated.

## Slide 5 — Storage results
Notebook summary:
- Parquet: ~113.04 MB average
- ORC: ~146.22 MB average
- Avro: ~325.96 MB average

Interpretation: Parquet had the smallest average output in this experiment. Codec and partition choices still matter.

## Slide 6 — Query results
Notebook summary:
- Parquet: ~0.0788 s average
- ORC: ~0.4663 s average
- Avro: ~22.1315 s average

Parquet was fastest across the tested analytical workloads in this implementation.

## Slide 7 — Partitioning and energy
- Date partitioning helps point lookups and date-range filters.
- Date + zone can further help queries filtering on both keys.
- Full scans see less benefit.
- Energy is estimated from CPU/I/O timing and assumed power values; it is not a wall-socket measurement.

## Slide 8 — Recommendations
- Interactive analytics: Parquet + Snappy; date partition if date filters are frequent.
- Batch ETL: Parquet + Snappy; evaluate Zstd for storage-sensitive pipelines.
- Archival: Parquet + Zstd after validating CPU/decompression trade-offs.
- Streaming/interchange: Avro when schema evolution and row-oriented serialization matter.

## Slide 9 — Limitations and conclusion
- Single-machine sample benchmark.
- Petabyte numbers are linear extrapolations, not cluster measurements.
- Results depend on hardware, readers, caching and workload.
- Conclusion: Parquet is the best default for the tested analytical use case; partition only to match query predicates.
