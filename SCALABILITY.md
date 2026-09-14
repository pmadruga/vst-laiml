# SCALABILITY.md: what one report costs, and what 200 would

Measured on the Vestas 2025 report on one machine, with the gpt-oss 20B model running locally, on 2026-09-14. Model figures come from the recorded model calls (`eval/usage.py`); the rest are timings of each phase and of the API.

## One report

| Step | Time | Model calls | Tokens in / out |
| --- | --- | --- | --- |
| Reading the PDF and rebuilding the tables | 0.9 s | 0 | 0 |
| Model: finding, describing and fixing risks | 34.5 s | 17 | 13,223 / 3,183 |
| Checks, evaluation and loading the database | under 1 s | 0 | 0 |
| **Total** | **36 s** | **17** | **13,223 / 3,183** |

Tokens are the pieces of text a model reads (in) and writes (out); hosted providers charge by them. Almost all the time is the model. The number of calls moves between 16 and 17 from run to run, depending on how many descriptions need a second try. The API answers a filter query in 1 to 3 ms; a plain-English question takes about a second, because it calls the model.

## What it would cost at a hosted provider

The model runs locally, so there is no bill. At OpenRouter's list prices on 2026-09-14, the same tokens would cost:

| Model | One report | 200 reports |
| --- | --- | --- |
| gpt-oss-20b, the same model hosted | $0.0008 | $0.16 |
| gpt-5-mini | $0.01 | $1.93 |
| claude-sonnet-5, a frontier model | $0.06 | $11.66 |

These are estimates: other models count tokens differently, and the power for running the GPU locally is not included.

## From 10 to 200 reports

| Reports | One model server | Four model servers | Cost at gpt-oss-20b prices |
| --- | --- | --- | --- |
| 10 | 6 min | 1.5 min | $0.01 |
| 50 | 30 min | 7.5 min | $0.04 |
| 200, one quarter | 2 h | 30 min | $0.16 |

This assumes every report is like this one. Storage stays small: about 80 MB of run files and a database of a few MB for 200 reports.

## What actually limits it

- **New layouts, not computing power.** The table reader is built for Vestas's layout, and each new layout is engineering work.
- **Review work.** About one record per report is flagged for an analyst, so roughly 200 a quarter.
- **One model server handles one request at a time.** More servers, or a hosted provider, shorten the time.
- **Cost is not the limit:** under a dollar a quarter on a hosted small model.

## Reproduce

```sh
uv run python eval/usage.py eval/runs/baseline --reports 10 50 200
```
