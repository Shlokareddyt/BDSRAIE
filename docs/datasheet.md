# Dataset Datasheet / Data Card

Following the course requirement to record every dataset used in a
datasheet inside the submission.

## Dataset

**NYC Taxi & Limousine Commission (TLC) Yellow Taxi Trip Records**
— January, February, and March 2021.

## Source and access

- **Official publisher:** NYC Taxi & Limousine Commission (TLC),
  https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- **Download mirror used:** [DataTalksClub/nyc-tlc-data](https://github.com/DataTalksClub/nyc-tlc-data)
  (GitHub releases), a widely-used backup of the official TLC files for the
  Data Engineering Zoomcamp course, created after the TLC's own CloudFront
  bucket became unreliable/rate-limited for programmatic bulk download. The
  mirrored files are the TLC's original CSVs, re-hosted unmodified.
- **Files used:** `yellow_tripdata_2021-01.csv.gz`, `yellow_tripdata_2021-02.csv.gz`,
  `yellow_tripdata_2021-03.csv.gz` (~25-35 MB each, gzip-compressed CSV).
- **License:** NYC Open Data / TLC trip records are published by a U.S.
  government agency and are public, free to use, with no registration or
  data-use agreement required. See the TLC page above for current terms;
  terms should be re-confirmed if this dataset is reused after this
  submission, per the course's "check licence and access terms" guidance.

## What's in it

Each row is one taxi trip: pickup/dropoff timestamps, pickup/dropoff
location IDs (TLC taxi zones, not street addresses or GPS), trip distance,
fare components (fare, tax, tip, tolls, surcharges, total), passenger count,
rate code, payment type, and vendor ID.

- **Rows used after cleaning:** 4,666,440 (out of ~4.9M raw rows across the
  three files; see "Cleaning" below for what was dropped).
- **Columns used:** 19 (see `scripts/01_prepare_data.py::COLUMN_MAP`).
- **Granularity:** one row per trip.
- **Time range:** 2021-01-01 to 2021-03-31.

## Why this dataset for this project

Project 34 (File Format and Compression Trade-offs) explicitly suggests NYC
TLC Trip Records as a benchmark dataset: it is real, large, column-rich,
has genuine data-quality anomalies (negative fares, implausible trip
distances, occasional mis-dated rows) that stress real-world cleaning and
partitioning logic, and is naturally partition-able by date and by
pickup/dropoff zone — the two partitioning schemes this project benchmarks.

## Personal / sensitive data

TLC trip records contain **no passenger names, driver names, license
plates, or GPS coordinates** — pickup/dropoff location is a coarse taxi
zone ID (one of ~260 zones covering NYC), not a street address. The TLC
redacts this by design specifically to avoid re-identifying riders or
drivers. We did not attempt, and this project does not require, any
re-identification of individuals, consistent with the course's "never
attempt to re-identify real people" instruction. We still treat the data as
potentially sensitive in principle (trip patterns can be loosely
correlated with people's movements) and did not join it to any external
identity data.

## Known data-quality issues (and how we handled them)

- A small number of rows in each monthly file have a `pickup_datetime` far
  outside that file's actual month (e.g., dated 2008 or several weeks into
  the next month) — a known TLC meter-clock artifact. We drop rows outside
  `[2021-01-01, 2021-04-01)`.
- A small number of rows have negative or implausibly large `trip_distance`
  values (meter malfunction or data entry errors). We drop trips with
  `trip_distance < 0` or `>= 500` miles.
- No other imputation or correction was performed; the remaining data is
  used as published.

## Scaling for this project

The case study is framed as "petabytes of data." We develop and benchmark
on this real multi-million-row sample (per the course guidance to "develop
on a small sample, then scale up") and document a linear order-of-magnitude
extrapolation methodology to petabyte scale in `docs/decision_guide.md`,
rather than fabricating or down-sampling a synthetic petabyte-scale dataset.
We did not substitute a different dataset — NYC TLC Trip Records, as
suggested for this project, was used directly.
