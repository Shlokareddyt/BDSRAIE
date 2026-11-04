# Technical Report: File Format, Compression and Energy Trade-offs

**Course:** Big Data Systems & Responsible AI Engineering  
**Project:** Project 34, Track G — Governance, Compliance and Sustainability

## Abstract

This study evaluates Parquet, ORC and Avro as storage formats for analytical data workloads. Using NYC TLC Yellow Taxi trip records from January to March 2021, the pipeline varies format-supported compression codecs and partitioning strategies, then measures write duration, storage size, query latency and estimated energy consumption. Four query patterns are considered: point lookup, full-scan aggregation, wide scan and date-range filtering. The current single-machine results favor Parquet for the tested analytical workloads: it has the lowest reported average query time and average storage footprint. Partitioning is most useful for selective queries whose predicates align with partition columns. Energy and petabyte-scale values are estimates and extrapolations, not direct measurements on a production cluster.

## 1. Problem statement and objectives

A data platform team must choose storage settings that balance storage cost, query responsiveness, write throughput and energy use. These objectives can conflict. Strong compression can reduce storage but require more CPU time; partitioning can reduce scanned data but create more files and metadata overhead; a format optimized for record-oriented interchange may not be ideal for column-pruned analytical queries.

The objectives are to:
1. Compare Parquet, ORC and Avro on a common dataset.
2. Evaluate supported compression codecs and three partitioning layouts.
3. Measure write time, file size and representative query execution time.
4. Estimate energy consistently from measured resource timings.
5. Recommend configurations for interactive analytics, batch ETL and archival workloads.

## 2. Dataset and experimental design

The experiment uses public NYC TLC Yellow Taxi trip records for January–March 2021. The project preparation pipeline cleans and combines the source records into an intermediate dataset. Project notes report approximately 4.67 million cleaned rows; the final row count should be taken from the latest successful preparation run.

The tested dimensions are:

| Dimension | Values |
|---|---|
| Format | Parquet, ORC, Avro |
| Codec | Supported options including Snappy, Gzip, Zstd, Deflate, Zlib and uncompressed/none |
| Partitioning | None; pickup date; pickup date plus coarse pickup-zone group |
| Queries | Point lookup; full-scan aggregate; wide scan; trailing-week range filter |

Codec support differs by format, so the experiment compares only valid combinations. The pipeline includes four stages: data preparation, format conversion, query benchmarking and energy estimation. Results are written to CSV files and analyzed in `notebooks/results_analysis.ipynb`.

## 3. Methodology

### 3.1 Storage and write benchmarking

For each valid format/codec/partitioning combination, the conversion script writes the dataset and records elapsed write time and output size. Partitioning creates multiple files according to the selected keys. File size is summarized in MB/GB for comparison.

### 3.2 Query benchmarking

The query script runs four representative workloads against each generated configuration:
- **Point lookup:** retrieve a narrowly selected record or small result.
- **Full-scan aggregation:** scan the dataset to compute an aggregate.
- **Wide scan:** read multiple columns across a broad portion of the dataset.
- **Range filter:** retrieve records within a recent date interval.

Wall-clock and CPU execution times are recorded. The query benchmark contains repeated measurements/configurations; summary tables aggregate these for format-level and workload-level comparisons.

### 3.3 Energy estimation

The energy script converts measured CPU and I/O/wall time into estimated energy using assumed power values. This enables relative comparisons when the same assumptions are applied to all configurations. Since no external power meter is used, the resulting Wh values are estimates rather than measured electrical consumption.

### 3.4 Petabyte-scale projection

The project scales sample storage and energy figures linearly to a petabyte-scale scenario. This is a simple extrapolation to illustrate magnitude. It does not model distributed execution, replication, network traffic, cluster utilization, storage tiering, compaction or operational overhead.

## 4. Results and discussion

### 4.1 Average storage footprint

The current analysis notebook reports average output sizes of approximately 113.04 MB for Parquet, 146.22 MB for ORC and 325.96 MB for Avro. In this experiment, Parquet has the smallest average footprint, followed by ORC. Avro is substantially larger for the tested data and configurations.

Codec choice also changes storage size. The best codec depends on the format and the desired balance between compression ratio and CPU cost. Codec names should not be compared as if they were interchangeable across formats.

### 4.2 Query performance

The notebook reports average query execution times of approximately 0.0788 seconds for Parquet, 0.4663 seconds for ORC and 22.1315 seconds for Avro. Parquet is the fastest on average in this setup. The workload-level results show the same broad pattern: Parquet is fastest for point lookup, full-scan aggregation, range filtering and wide scans in the measured implementation.

The large gap should be interpreted in context. The result reflects the specific file readers, query implementation, dataset layout, hardware and caching state used by this project. It is not a claim that Avro is always tens or hundreds of times slower in every system.

### 4.3 Partitioning

Partitioning by date or date plus zone substantially improves selective point lookups and range filters when the query predicates match those partition columns. For full scans, the benefit is much smaller because most or all partitions must still be read. The unpartitioned layout can be competitive for broad scans and avoids creating many files.

Date-plus-zone partitioning creates more partitions than date-only partitioning. That can improve pruning for queries that filter on both fields, but it also increases metadata and small-file management costs. Partitioning should follow actual query patterns rather than be applied automatically.

### 4.4 Energy

The energy results follow the CPU and I/O time measurements under the model's assumptions. Faster queries generally reduce estimated energy for the same workload, but compression can trade additional CPU work for fewer bytes read or written. The energy ranking is therefore workload- and model-dependent. Values should be presented as estimated Wh, with the assumed power model documented.

## 5. Recommendations

| Workload | Recommendation | Rationale |
|---|---|---|
| Interactive analytics | Parquet with Snappy as a balanced starting point; partition by date for frequent date filters | Columnar access and partition pruning support low-latency reads |
| Batch ETL | Parquet with Snappy; evaluate Zstd where storage savings justify extra CPU | Good general-purpose balance for writes and downstream analytics |
| Archival | Parquet with Zstd after validating decompression and compatibility needs | Prioritizes compact storage while preserving analytical usability |
| Streaming/interchange | Avro where schema evolution and record-oriented serialization are requirements | Avro serves a different role from analytical columnar storage |

Avoid excessive partitioning. Use date-plus-zone only if the workload frequently filters on both dimensions and measured savings exceed file/metadata overhead. Keep Avro where interoperability or schema-evolution needs justify it, rather than using it as the default analytical format.

## 6. Limitations, reproducibility and future work

This is a single-machine benchmark on a sample dataset. Performance can change with hardware, operating system, library versions, cache state, file size, query engine and data distribution. The petabyte projections are linear estimates, not cluster-scale tests. The energy model uses assumed power values and does not replace power-meter measurements.

To improve the study, repeat tests with multiple runs and randomized execution order, report medians and variability, control cold/warm cache conditions, test a distributed query engine, include network and replication costs, measure power directly where possible, and validate on a larger representative dataset.

The benchmark is reproducible using the four scripts in `scripts/` and the dependency list in `requirements.txt`. The CSV outputs in `results/` support the analysis notebook and decision guide. Raw and converted data are excluded from version control and can be regenerated from the documented public source.

## Conclusion

For the workloads and environment tested, Parquet is the strongest default for analytical storage because it provides the best observed combination of compact output and fast query execution. Partitioning by date is valuable when time filters are common, while additional zone partitioning should be justified by workload-specific measurements. Snappy is a balanced general-purpose starting point, with Zstd worth evaluating for storage-sensitive workloads. Avro remains useful for record-oriented interchange and schema evolution. All conclusions are bounded by the single-machine experimental scope and the estimated nature of the energy and petabyte-scale results.
