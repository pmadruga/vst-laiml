# SCALABILITY.md: measured cost of one report, extrapolated to 10, 20, 50 and 200

*What this is:* timings, token counts, hosted-equivalent cost and sizes measured at each point of the pipeline and the API on the Vestas Annual Report 2025 (one machine, gpt-oss 20B on llama-swap locally), and what they imply for a batch of reports. Model figures come from the recorded calls of the shipped baseline run (`eval/runs/baseline/llm/*.json`, recorded live on 2026-09-14) through `eval/usage.py`. The other figures are wall-clock measurements of the phases and `curl` timings against the API container, taken the same day.

## One report, measured

| Point | What was measured | Calls | Time | Tokens in / out | Size |
|---|---|---|---|---|---|
| E1–E8 extract | locate, parse, validate, all deterministic | 0 | 0.9 s | 0 | parse.json 196 KB |
| T1 identify, model strategy | the 4 pages with risk register rows (51, 71, 73, 74), one call each | 4 | 10.1 s | 3,440 / 899 | |
| T2 describe | one call per risk register risk | 10 | 19.1 s | 7,694 / 1,797 | |
| T4 repair | one retry per record failing grounding | 3 | 5.3 s | 2,089 / 487 | |
| T3, T5, T4, T6 code | merge, mitigation enrichment, grounding checks, set checks, replay comparison | 0 | 0.3 s | 0 | final.json 22 KB |
| Eval | five evaluators against the golden set | 0 | 0.2 s | 0 | |
| L1–L6 load | SQLite write, indexes, FTS, run record | 0 | 0.3 s | 0 | risk.db 160 KB |
| **Pipeline total** | | **17** | **36 s** | **13,223 / 3,183** | run dir 400 KB |
| API structured endpoints | `/health`, `/risks` with filters and `q`, `/questions/*`, `/runs/*/record` | 0 | 1–2.5 ms median, under 4 ms p95 | 0 | |
| API `/ask` | one intent call, then SQL | 1 | 0.8–1.7 s warm, 7.4 s cold | ~430 / ~115 | |

Notes. The model server is the whole cost: 34.5 of the 36 seconds. Identify calls are the longest per call (2.5 s against 1.9 s for describe) because each reads a full page. The cold `/ask` figure includes the server loading the model after it was unloaded; warm calls are around one second. Extract, load and the API's structured endpoints are effectively free at this scale.

Variance between live runs. The call count moves only with the number of repairs, which depends on how many first descriptions fail grounding and varies with sampling on the server. With the same code, prompts and model: the shipped baseline made 17 calls (three repairs); the previous day's recording, kept in `eval/attempts/2026-09-13/`, and the spaCy grounding run made 16 (two). The regression runs sit in the same range: 16 calls for the broken parser, 17 for the prompt without mitigation, and 19 calls and 68 s for the weaker ministral 14B, which is slower on this machine and needs five repairs.

## Token cost

The model runs locally, so no invoice exists. To give the token volume a price, the table applies hosted list prices to the same token counts. Prices are OpenRouter's, USD per million tokens, read from `openrouter.ai/api/v1/models` on 2026-09-14 and kept in `eval/usage.py`:

| Equivalent | Why this one | In / out per M | One report (17 calls) | One `/ask` |
|---|---|---|---|---|
| `openai/gpt-oss-20b` | the same weights as the local model, hosted | $0.03 / $0.13 | $0.0008 | $0.00003 |
| `mistralai/ministral-14b-2512` | the same weights as the weak-model regression, hosted | $0.20 / $0.20 | $0.0033 | $0.0001 |
| `openai/gpt-5-mini` | a small hosted proprietary model | $0.25 / $2.00 | $0.0097 | $0.0003 |
| `anthropic/claude-sonnet-5` | a frontier model; its batch tier is half | $2.00 / $10.00 | $0.058 | $0.002 |

Per step at the frontier price: identify $0.016, describe $0.033, repair $0.009. Describe is the largest line because it runs once per risk.

What these figures are and are not:

- **Token counts are the local tokenizer's.** GPT-5 mini uses a close tokenizer family; Claude's tokenizer counts the same text differently, typically higher, so the frontier column is a lower bound.
- **Output counts are what llama.cpp reported as completion tokens at reasoning effort `low`.** A hosted reasoning model at a higher effort bills more output tokens for the same answer.
- **No prompt caching is assumed.** The describe system prompt repeats across its ten calls; a provider with caching charges less for it.
- **OpenRouter's price is the cheapest route, not every provider's.** Direct providers of gpt-oss-20b list higher prices, for example $0.05 / $0.20 (Together AI) and $0.075 / $0.30 (Groq); still under a cent per report.
- **Local cost is not zero.** GPU power and hardware amortisation are not measured here.

## Extrapolation

Assumptions: cost is linear in reports (one report's pages and risk register rows are typical of a CSRD filer; a report with more risk register rows adds one describe call per row); extract, code and load run on CPU and parallelise across cores; model calls are serialised on one local server, so their time divides only by the number of model servers or by the concurrency a hosted provider allows; the "4 model workers" column assumes four servers or a provider allowing four concurrent requests; the database gains nine rows per report.

| Reports | Model calls | Tokens in / out | Sequential wall time | With 4 model workers | Run directories | Database rows |
|---|---|---|---|---|---|---|
| 1 | 17 | 13.2k / 3.2k | 36 s | 36 s | 0.4 MB | 9 risks |
| 10 | 170 | 132k / 32k | 6.0 min | 1.5 min | 4 MB | ~90 risks |
| 20 | 340 | 264k / 64k | 12 min | 3.0 min | 8 MB | ~180 risks |
| 50 | 850 | 661k / 159k | 30 min | 7.5 min | 20 MB | ~450 risks |
| 200 (one quarter) | 3,400 | 2.6M / 0.64M | 2.0 h | 30 min | 80 MB | ~1,800 risks |

Hosted-equivalent token cost of the same batches:

| Reports | gpt-oss-20b | ministral-14b | gpt-5-mini | claude-sonnet-5 |
|---|---|---|---|---|
| 1 | $0.0008 | $0.003 | $0.01 | $0.06 |
| 10 | $0.008 | $0.03 | $0.10 | $0.58 |
| 20 | $0.02 | $0.07 | $0.19 | $1.17 |
| 50 | $0.04 | $0.16 | $0.48 | $2.91 |
| 200 (one quarter) | $0.16 | $0.66 | $1.93 | $11.66 |

A thousand `/ask` questions cost $0.03 on hosted gpt-oss-20b and $2.01 on the frontier model.

What does not scale with reports: the API. Structured endpoints answer in 1–2.5 ms from SQLite with an index on every filter, and 450 or 1,800 rows are far below where SQLite would be a bottleneck; a single API process serves hundreds of requests per second. `/ask` is bound by the model call, about one second warm, and is independent of database size.

## What actually limits a batch

- **Parser coverage, not compute.** Every new layout costs engineering time, which no column above measures. STRETCH.md's second-report item records that the pipeline finds the 2024 report's sections but not yet its tables.
- **Review load.** One of nine records is pending review on the baseline, about one per report; the weaker model leaves three. At the baseline rate 50 reports produce about 50 records for analysts and a quarter about 200, which is analyst time, not machine time.
- **Model serialisation.** One local server handles one request at a time; the "4 workers" column is where a hosted provider or a second GPU changes the picture.
- **Cost is not the constraint.** A quarter's token volume is $0.16 on hosted gpt-oss-20b and about $12 at frontier list prices, before batch discounts.
- **Storage** is negligible: 80 MB of run directories and a database of a few MB for a full quarter.

## How to reproduce

```sh
uv run python etl.py --extract --run-id t --pdf documentation/baseline/VestasAnnualReport2025.pdf   # time this
uv run python etl.py --transform --run-id t                                                          # live model calls; each records elapsed_s and usage
uv run python etl.py --load --run-id t --db /tmp/t.db
uv run python eval/usage.py runs/t --reports 10 20 50 200                                            # calls, tokens, model time and cost per step
uv run python eval/usage.py eval/runs/baseline                                                       # the shipped figures above, including /ask intents
curl -s -o /dev/null -w '%{time_total}\n' 'localhost:8000/questions/top_enterprise_risks?company=vestas'
```

Prices change; update `PRICES` and `PRICES_AS_OF` in `eval/usage.py` and rerun it to refresh the cost tables.
