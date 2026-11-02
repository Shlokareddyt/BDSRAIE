# Slide content reference (source of truth for the Slides artifact)

1. Title: File Format, Compression & Energy Trade-offs at Petabyte Scale
2. The question: platform team choosing default storage settings
3. Method: 3 formats x codecs x 3 partitioning schemes, real NYC TLC data
4. Dataset: 4.67M rows, 3 months, honest-scope note
5. Result 1: codec drives size & write time (table)
6. Result 2: partitioning drives query time, small-files problem
7. Result 3: format drives column-pruning benefit (Avro 60-75s vs sub-second)
8. Energy methodology (CPU+IO model, limits)
9. Petabyte extrapolation (75x spread)
10. Recommendations by workload (3 rows)
11. Scope/limitations, honest caveats
12. Q&A / repo link
