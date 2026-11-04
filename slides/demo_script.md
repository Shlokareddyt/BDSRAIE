# 3-Minute Demo Run Sheet

**0:00–0:25 — Problem and objective**  
"We compared Parquet, ORC and Avro to understand how file format, compression and partitioning affect storage, query speed and estimated energy."

**0:25–0:55 — Pipeline**  
Show the repository structure and README architecture diagram. Briefly point to:
- `01_prepare_data.py`
- `02_convert_formats.py`
- `03_query_benchmark.py`
- `04_energy_model.py`

**0:55–1:35 — Results notebook**  
Open `notebooks/results_analysis.ipynb`. Show the storage-size chart and query-performance chart. State the current notebook averages: Parquet ~113.04 MB and ~0.0788 s; ORC ~146.22 MB and ~0.4663 s; Avro ~325.96 MB and ~22.1315 s.

**1:35–2:15 — Partitioning and energy**  
Show the partitioning comparison and energy summary. Explain that partition pruning helps selective date-based queries, while full scans benefit less. Clearly state that energy is estimated using a model.

**2:15–2:45 — Recommendations**  
Recommend Parquet as the default analytical format; date partitioning for date-filtered workloads; Zstd for storage-sensitive cases after measuring CPU costs; Avro for record-oriented interchange/schema evolution.

**2:45–3:00 — Limitations**  
"This is a reproducible single-machine sample benchmark. Petabyte-scale numbers are linear estimates, not measurements from a petabyte cluster."

## Before recording/presenting
- Save the notebook and ensure outputs are visible.
- Close unrelated windows and terminal errors.
- Do not run the full benchmark live; show the saved results.
- Keep `results/` CSVs available in the repository.
