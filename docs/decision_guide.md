# Decision Guide: File Format, Compression and Partitioning for Petabyte-Scale Storage

**Project 34 — Big Data Systems & Responsible AI Engineering**

## 1. The question

A platform team is choosing default storage settings — file format,
compression codec, and partitioning scheme — for a lakehouse that will
eventually hold petabytes of data. The right answer is not one setting: it
depends on how the data will be *read*. This guide gives a specific
recommendation for three workload types and explains the measured
trade-offs behind each one.

## 2. Method, in brief

We benchmarked all combinations of:

- **Format:** Parquet, ORC, Avro
- **Codec:** Parquet {Snappy, Gzip, Zstd, none}; ORC {Zlib, Zstd,
  uncompressed}; Avro {Deflate, Snappy, null}
- **Partitioning:** none (1 file), by pickup date (~90 partitions), by
  pickup date + coarse pickup-zone group (~540 partitions)

against a real, cleaned sample of **4.67 million NYC Yellow Taxi trip
records** (Jan-Mar 2021, ~86 MB as gzip-compressed CSV), running 4
representative queries — a partition-pruning point lookup, a
column-pruning full aggregate, a wide multi-column scan, and a
trailing-range filter — against each of 30 successfully-written
format/codec/partitioning combinations (120 timed query runs total, zero
failures). Full methodology, raw numbers, and scripts are in the repo root
`README.md` and `results/*.csv`.

## 3. What we found

### 3.1 Compression codec drives storage size and write cost

Smallest to largest on disk (full numbers in `results/write_summary.csv`),
unpartitioned ("none") case:

| Format | Codec | Size (MB) | Write time (s) | vs. raw CSV.gz (85.3 MB) |
| --- | --- | --- | --- | --- |
| ORC | Zstd | 76.5 | 2.9 | smaller, 60x faster write than Gzip |
| Parquet | Zstd | 78.6 | 2.3 | smaller, 20x faster write than Gzip |
| Parquet | Snappy | 97.4 | 1.7 | fastest write, +14% size vs. Zstd |
| ORC | Zlib | 73.1 | 5.7 | smallest overall, still 8x faster than Parquet-Gzip |
| Parquet | Gzip | 74.3 | 45.7 | near-smallest, by far the slowest write |
| Parquet | uncompressed | 121.9 | 1.6 | fast but 43% larger than Gzip |
| ORC | uncompressed | 287.7 | 2.7 | ORC's row-group layout compresses far worse with no codec |
| Avro | Deflate | 136.5 | 113.0 | row-oriented: larger AND the slowest write of all three formats |
| Avro | Snappy | 218.5 | 104.2 | largest of the "compressed" options, still slow to write |
| Avro | null (none) | 590.5 | 99.7 | ~7x the raw CSV.gz size — Avro's per-record overhead with no columnar compression is severe at this row width |

**Takeaway:** Zstd is close to a free lunch for the columnar formats — it
lands within a few percent of Gzip's size at a fraction of the write time
(Parquet-Zstd: 2.3s vs. Parquet-Gzip: 45.7s for near-identical output size),
which matches published Zstd benchmarks and is why it has become the
default in several modern lakehouse engines. Gzip only wins when write
frequency is so low that its ~20-60x slower write time genuinely doesn't
matter (archival). Avro, being row-oriented, compresses noticeably worse
than either columnar format at every codec setting we tested on this
19-column dataset, and takes far longer to write — fastavro's pure-Python
record-at-a-time writer is the main cost, not the codec itself.

### 3.2 Partitioning drives query time and query energy, not storage size

The point-lookup query (one specific day) shows the clearest partition-
pruning win: Parquet-Snappy's point lookup takes **0.008s with by-date
partitioning vs. 0.181s unpartitioned** — a ~23x speedup from not having to
scan the whole dataset. ORC shows the same pattern (e.g. ORC-Zstd:
0.013s by-date vs. ~0.9-1.1s unpartitioned on the full-scan-style queries).
The trailing-range-filter query shows a smaller but real win (Parquet-Zstd:
0.10s by-date vs. the equivalent full scan).

The two-level `date + zone_group` scheme adds a second pruning dimension
(540 partitions vs. ~90 for date-only) but at a real cost: our full-scan
and wide-scan queries, which touch every partition anyway, got
**measurably slower** under `by_date_zone` than under `by_date` or no
partitioning at all (e.g. Parquet-Snappy wide_scan: 0.192s unpartitioned
vs. 1.110s under by_date_zone) — more, smaller files means more per-file
open/metadata overhead for queries that don't benefit from the extra
pruning. This is a direct, measured instance of the "small files problem":
partitioning helps only the queries whose predicates line up with the
partition keys, and actively hurts every other query by adding file-count
overhead.

**Takeaway:** partition only on columns that queries actually filter on,
and don't over-partition — each partitioning level should cut the data
scanned by a meaningful fraction for most of your actual query workload,
or it just adds file-count overhead with no offsetting pruning benefit.

### 3.3 Format changes which workloads actually benefit from partition/column pruning

Parquet and ORC are columnar: the column-pruning full_scan_agg query
(2 of 19 columns) consistently beat the column-heavy wide_scan query on
the same partitioning/codec (e.g. Parquet-none/none: 0.187s full_scan_agg
vs. 0.192s wide_scan — close here because both still read the whole file
line-by-line in our benchmark's un-partitioned case, but the gap widens
under partitioning, e.g. Parquet-none/by_date: 0.218s vs. 0.366s). Avro
is row-oriented and deserializes every field of every record regardless
of which columns a query needs — reflected directly in query time: **every
Avro full-table query took 60-75 seconds regardless of codec**, two to
three orders of magnitude slower than the equivalent Parquet/ORC query
(sub-second to low single-digit seconds), because Avro gives us no column
projection and fastavro's pure-Python record decoding has to touch every
field of every one of 4.67M rows. Avro's point lookups on partitioned
data are fast (0.1-0.6s) purely because partition pruning narrows the
*file set* before any row-level decoding happens — the moment a query
needs to touch an un-pruned full partition, Avro's cost is dramatically
higher than Parquet/ORC's.

**This is the central trade-off in format choice:** Avro's row-oriented
layout is what makes schema evolution and single-record writes/reads cheap
(exactly what a Kafka producer/consumer needs), but it is a poor fit for
anything resembling an analytical scan.

## 4. Recommendations by workload type

### Interactive analytics (dashboards, ad-hoc BI queries)

- **Format:** Parquet
- **Codec:** Zstd (or Snappy if write-side CPU is the bottleneck, e.g. on
  shared ingestion clusters)
- **Partitioning:** by the column(s) interactive queries filter on most
  often (here: pickup date), kept to a cardinality that yields partitions
  in the tens-to-low-hundreds-of-MB range — not finer
- **Why:** interactive queries are read-heavy, latency-sensitive, and
  usually selective (a dashboard filters to "this week," "this region").
  Parquet's columnar layout + partition pruning directly minimizes bytes
  read, which is the dominant cost (and energy cost) for this workload.

### Batch ETL (large scheduled transforms, feature pipelines)

- **Format:** Parquet or ORC (ORC if the downstream engine is
  Hive/Spark-on-Hadoop and benefits from ORC's built-in row-group
  statistics/indexes; Parquet otherwise for broader tool compatibility)
- **Codec:** Zstd for a balance of write throughput and output size; Gzip
  if the job runs infrequently and storage cost outweighs write-CPU cost
- **Partitioning:** date-based, matched to the batch granularity (daily/
  hourly jobs partition daily/hourly) — avoid high-cardinality secondary
  keys that create many small files for a job that already runs on a
  schedule, since ETL jobs read and rewrite large contiguous chunks rather
  than doing selective point lookups
- **Why:** batch jobs are throughput-bound and CPU-time-bound (hence
  energy-bound by our model's CPU term), not latency-bound per query; Zstd
  keeps both the write step and any downstream full/wide scans cheap.

### Archival (cold, rarely-read, retained for compliance/long-term)

- **Format:** Parquet or ORC, whichever this organization's tools already
  read, since archived data is rarely re-processed with new tools
- **Codec:** Gzip (or the slowest/highest-ratio codec available) — write
  cost is paid once, storage cost is paid for years, so this is the one
  workload where we deliberately trade write time for size
- **Partitioning:** coarse, date-only, sized for retention-policy deletion
  (e.g. one partition per month/year so an entire partition can be dropped
  when its retention period expires) rather than for query speed
- **Why:** archival data is written once and read rarely if ever; the
  energy and dollar cost that matters is *storage-months*, not query
  latency, so this is the one case where minimizing size dominates every
  other consideration, including write time.

## 5. Energy estimation methodology and its limits

We did not have access to hardware power metering in this sandbox. Energy
is **estimated**, not measured, from timing data using the model in
`scripts/04_energy_model.py`:

```
energy_joules = cpu_seconds * 15W                      (CPU term)
              + wall_seconds * 0.65 W/GB * size_gb      (I/O term)
```

The 15W figure is a mid-range estimate for the power draw attributable to
one fully-loaded CPU core on typical server/cloud hardware (published TDP
figures for one core of a modern multi-core server CPU range roughly
8-25W depending on the SKU and load; we use the midpoint and note the
range here rather than presenting a single number as precise). The I/O
term (0.65 W/GB/s) is a rough figure for SSD-backed block storage active
power scaled by throughput; it is far more uncertain than the CPU term and
is dominated, in our results, by the CPU term for CPU-bound codecs like
Gzip.

**This estimate should be read as directionally informative, not as a
dollar-accurate energy bill.** What we are confident the numbers show
correctly, because it follows from measured CPU/wall time regardless of
the exact wattage constants: *which* combinations use substantially more
or less CPU time and I/O time than others, and therefore the *ranking* of
formats/codecs/partitioning schemes by energy — which is what a
settings recommendation actually needs.

## 6. Scaling methodology and its limits (sample -> petabyte scale)

We benchmarked on ~4.67M rows / ~85 MB raw gzipped CSV (3 months of one
dataset). The case study is framed at petabyte scale.
`scripts/04_energy_model.py` extrapolates linearly by a fixed
`PB_SCALE_FACTOR = 1,000,000` (documented in that file; e.g. thousands of
data sources at much higher daily volume, retained for years) to produce
`results/petabyte_extrapolation.csv` as an order-of-magnitude projection.
At that scale, our ~73-78 MB best-case columnar outputs (ORC/Parquet with
Zstd or Zlib) project to **~73-78 TB**, our worst-case Avro-null output
(590 MB) projects to **~591 TB**, and the *projected write energy* ranges
from **~6.5 kWh** (Parquet, uncompressed or Snappy, by_date) up to
**~494 kWh** (Avro-Deflate, by_date_zone) — roughly a **75x spread**
between the cheapest and most expensive settings we tested, driven almost
entirely by format choice (Avro vs. columnar) rather than codec choice
within a format.

**Why linear scaling is a simplification, honestly stated:**

- **Compression ratio** typically does not scale perfectly linearly —
  larger datasets often compress *slightly better* as the codec's
  dictionary/window sees more repeated patterns (true for Gzip/Zstd on
  this kind of structured tabular data), so our projected sizes are likely
  a modest overestimate, not an underestimate.
- **Query selectivity** (what fraction of partitions a given query touches)
  does not automatically stay constant as data volume grows — at petabyte
  scale, the same "trailing 7 days" query touches a *smaller proportion*
  of a multi-year dataset than it does of our 3-month sample, meaning
  partitioning's *relative* benefit should be even larger at scale than
  what we measured, not smaller.
- **Small-files overhead** gets *worse*, not linearly worse, at scale on
  distributed object storage (more files means more metadata-service and
  listing calls, which don't parallelize as cleanly as raw byte transfer);
  our 540-partition scheme already shows this directionally, and it would
  be the first thing to re-validate before committing to a specific
  partitioning cardinality on a real petabyte-scale system.

We present the petabyte-scale numbers as **order-of-magnitude planning
inputs**, useful for comparing relative codec/format choices, not as a
cost or energy forecast precise enough to budget against without further
validation on a real cluster at intermediate scale.

## 7. Summary table

| Workload | Format | Codec | Partitioning |
| --- | --- | --- | --- |
| Interactive analytics | Parquet | Zstd | by date (fine-grained, matched to query selectivity) |
| Batch ETL | Parquet / ORC | Zstd (Gzip if infrequent) | by date, matched to job schedule |
| Archival | Parquet / ORC | Gzip | coarse, by retention period |
