# Dataset Data Card

## Dataset

**Name:** NYC TLC Yellow Taxi Trip Record Data  
**Period used:** January–March 2021  
**Source:** NYC Taxi & Limousine Commission (TLC) Trip Record Data, obtained through the DataTalksClub `nyc-tlc-data` GitHub mirror.

- Official source: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- Mirror: https://github.com/DataTalksClub/nyc-tlc-data

## Purpose of use

The dataset is used to benchmark file formats, compression codecs and partitioning strategies for big-data storage and analytical query workloads. It is not used to train a predictive model or make decisions about individual passengers or drivers.

## Data contents

Yellow Taxi trip records contain operational trip fields such as pickup and drop-off timestamps, passenger count, trip distance, rate/payment information, fare components and pickup/drop-off location identifiers. Exact fields may vary by source release and cleaning pipeline.

## Processing

The project preparation script downloads the selected monthly source files, cleans and combines records, and writes a tidy intermediate dataset. The conversion script produces Parquet, ORC and Avro files using supported codec and partitioning combinations.

The project README and preparation script should be treated as the authoritative description of the exact cleaning rules and resulting row count. The project notes report approximately 4.67 million cleaned rows; verify this against the current preparation output before submission.

## Intended use

- Comparing storage footprint across supported file formats and codecs.
- Comparing write time and representative analytical query latency.
- Studying the effect of date and zone partitioning.
- Estimating relative energy implications using a documented model.

## Limitations and risks

- The records represent taxi trips, not all urban travel.
- The selected three-month period may not represent seasonality or long-term changes.
- Data quality, missing values, outliers and TLC schema changes can affect results.
- Location identifiers and timestamps can carry sensitive contextual information; this project should report aggregate benchmark results, not attempt to identify individuals.
- Performance results depend on hardware, software versions, file sizes, caching and query implementation.
- Energy figures are model-based estimates, not direct power-meter measurements.
- Petabyte-scale numbers are linear extrapolations from a single-machine sample, not distributed-cluster measurements.

## Licensing and access

Consult the official TLC data page and its current terms before redistributing raw records. This repository excludes raw and converted data from Git; users reproduce them by running the preparation and conversion scripts.

## Maintenance

Record the source URLs, download date, script version, row counts and cleaning decisions when refreshing the dataset.
