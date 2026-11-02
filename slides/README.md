# Presentation

The 10-minute presentation deck (11 slides) was built with Claude's slide
tool and is published here (private until shared, open it to export):

https://claude.ai/artifact/GV1QAjsXzeDwtzLu9CF8VR

**Before submitting:** open that link and use its Share/Export menu to
download a PDF or PowerPoint (.pptx) copy, and add that exported file to
this `slides/` folder (e.g. `slides/presentation.pdf`) so the deck is
included in the repo itself, not just linked. `content.md` in this folder
is a one-line-per-slide outline for reference/backup.

## Deck outline (~10 minutes, ~55s/slide)

1. Cover
2. The question — three settings a platform team must choose
3. Method — formats x codecs x partitioning, 4 queries, 30 combos / 120 runs
4. The dataset — real NYC TLC data, honest scope note
5. Result: codec drives size & write time (Zstd near-free-lunch)
6. Result: partitioning is a double-edged sword (small-files problem, measured)
7. Result: format decides pruning benefit (Avro 60-75s vs. sub-second)
8. Energy estimation methodology and its limits
9. Petabyte-scale extrapolation (~75x spread)
10. Recommendations by workload (3 concrete settings)
11. Scope, limitations, thank you / Q&A
