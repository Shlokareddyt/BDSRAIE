# File Format, Compression and Energy Trade-offs

**Big Data Systems & Responsible AI Engineering — Project 34, Track G (Governance, Compliance and Sustainability)**

Case study: a platform team choosing storage settings for petabytes of data.
We benchmark **Parquet, ORC and Avro** with multiple **compression codecs**
and **partitioning schemes** on real NYC TLC Yellow Taxi trip data, measure
**query time, storage size, and estimated energy**, and recommend settings
for three workload types: **interactive analytics, batch ETL, and archival**.

## Team

| GitHub | Role |
| --- | --- |
| [@Shlokareddyt](https://github.com/Shlokareddyt) | Benchmark pipeline, energy model |
| [@sirisanikop](https://github.com/sirisanikop) | Decision guide, presentation |

## Repository layout

```
.
├── README.md                  # this file
├── scripts/
│   ├── 01_prepare_data.py     # download-and-clean -> single tidy intermediate file
│   ├── 02_convert_formats.py  # writes Parquet/ORC/Avro x codecs x partitioning
│   ├── 03_query_benchmark.py  # runs 4 representative queries against every combo
│   └── 04_energy_model.py     # turns CPU/wall time into estimated energy (Wh)
├── data/
│   ├── raw/                   # downloaded NYC TLC CSVs (gitignored, see below)
│   └── converted/             # generated format/codec/partition combinations (gitignored)
├── results/                   # CSV outputs of every benchmark stage (checked in)
├── docs/
│   ├── decision_guide.md      # the deliverable: recommended settings + rationale
│   └── datasheet.md           # dataset data card (license, provenance, limitations)
└── slides/                    # 10-minute presentation
```

`data/raw` and `data/converted` are not checked into git (see `.gitignore`) —
they total several hundred MB and are fully reproducible by re-running the
scripts. `results/*.csv` (the actual benchmark numbers) **are** checked in,
so the decision guide and slides are reproducible from the repo without
re-running anything.

## Reproducing the benchmark

```bash
pip install -r requirements.txt

python scripts/01_prepare_data.py       # ~20s, produces data/converted/trips_clean.feather
python scripts/02_convert_formats.py    # ~10-15 min, writes 36 format/codec/partition combos
python scripts/03_query_benchmark.py    # ~2-5 min, runs 4 queries x 36 combos = 144 timed runs
python scripts/04_energy_model.py       # <1s, turns timings into results/*summary*.csv
```

Raw inputs: three months (Jan-Mar 2021) of NYC Yellow Taxi trip records,
~4.67M rows after cleaning, downloaded from the [DataTalksClub/nyc-tlc-data](https://github.com/DataTalksClub/nyc-tlc-data)
GitHub mirror of the official [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
release. See `docs/datasheet.md` for the full data card.

## What we tested

| Dimension | Values |
| --- | --- |
| **Format** | Parquet, ORC, Avro |
| **Codec** | Parquet: Snappy, Gzip, Zstd, none. ORC: Zlib, Zstd, uncompressed. Avro: Deflate, Snappy, null |
| **Partitioning** | none (single file), by pickup date (~90 partitions), by date + coarse pickup-zone group (~540 partitions) |
| **Queries** | point lookup, full-table column-pruned aggregate, wide multi-column scan, trailing-week range filter |

36 (format x codec x partitioning) combinations, 4 queries each = 144 timed
query runs, plus 36 timed write runs.

## Key result (see `docs/decision_guide.md` for the full writeup)

See `results/write_summary.csv` and `results/query_summary.csv` for the raw
numbers. In short: compression codec dominates storage cost and write time;
partitioning dominates query time and query energy once predicates can prune
whole files; Avro trades both away for schema-evolution flexibility, which
matters for streaming ingestion but not for analytical reads.

## Honest scope note

This ran on a single-machine sandbox, not a real petabyte-scale cluster.
We benchmarked on a real, representative ~4.67M-row / ~0.9 GB sample of the
actual public dataset and **extrapolated** the size and energy numbers to
petabyte scale using a documented, linear order-of-magnitude scaling factor
(see `docs/decision_guide.md`, "Scaling methodology and its limits") — this
is explicitly flagged as an estimate, not a cluster measurement. Energy is
likewise an *estimate* from CPU-time and I/O-time using a simple, documented
power model (no hardware power meter was available), not a wall-socket
measurement.
