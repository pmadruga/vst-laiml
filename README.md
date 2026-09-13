# Structured Risk Intelligence pipeline

Turns one annual report (Vestas Annual Report 2025) into structured principal-risk records with provenance.

## Documents

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The product plan: who the user is, what the surface looks like, what is optimised for, the assumptions, and what is deferred. |
| [DESIGN.md](DESIGN.md) | How it is built: the three pipeline phases, the API, deployment, and where each part can fail. |
| [SPECS.md](SPECS.md) | The per-step specification behind DESIGN.md: for every step, what it does, how, and a worked example from the report. |
| [STRETCH.md](STRETCH.md) | What comes next with another week, each item with the trigger that would make it worth building. |
| [documentation/self/notes.md](documentation/self/notes.md) | My raw first-read notes on the brief, written by hand before any planning: the problem, the stakeholders, the constraints as I understood them. |
| [documentation/self/methodology.md](documentation/self/methodology.md) | The order I worked in, from reading the report to writing the plan, building and testing. |

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`; uv fetches it.

```sh
uv sync
```

The source PDF is `documentation/baseline/VestasAnnualReport2025.pdf`. It is AES-256 encrypted with an empty user password; the `cryptography` dependency handles that.

## Running the pipeline

`etl.py` is the one entry point. Each phase reads the previous phase's JSON from `runs/<run_id>/` and writes its own, so phases can be run one at a time against the same run id.

```sh
uv run python etl.py --list                      # phase -> step order
uv run python etl.py --extract                   # locate + parse        -> runs/<run_id>/locate.json, parse.json
uv run python etl.py --transform --run-id <id>   # identify + describe + merge + validate -> final.json   (Stage 2+, not built)
uv run python etl.py --load --run-id <id>        # sqlite                -> risk.db                       (Stage 5, not built)
uv run python etl.py                             # all phases in order
```

Options: `--pdf <file>` to point at another report, `--run-id <id>` to name or reuse a run directory (default: UTC timestamp), `--sections a,b` to parse only some located sections.

### Extract

```sh
uv run python etl.py --extract --run-id demo
```

What happens:

1. **locate** finds the table of contents by its dotted-leader pattern, matches each configured section title against every `title ···· page` entry, and derives the page range. TOC numbers are printed page numbers; the offset to PDF indices is measured from the footer number in the bottom-right corner and applied everywhere. A match is verified by finding the heading on the section's first page. Output: `runs/demo/locate.json`.
2. **parse** reconstructs the pages by word coordinates: the three-column "Main risks" table on p.51 and the ESRS impact/risk/opportunity tables on pp.71–74, reading the Risk/Opportunity arrow icon from the page graphics and cross-checking it against the text. Other pages are kept as plain text. Output: `runs/demo/parse.json`.

The console summary lists the located sections, block counts per page by marker (`risk`, `opportunity`, `impact`, `immaterial`), the risk blocks found, and any quality flags.

What the quality flags mean:

| Flag | Meaning |
| --- | --- |
| `toc_title_variant:'…'` | the TOC title carries a qualifier or punctuation the config does not, e.g. "Cyber security (entity-specific)"; matched anyway |
| `toc_title_fuzzy_match:0.xx` | matched below exact after normalisation; check the matched title |
| `toc_title_not_found:…` | no TOC entry resembles the configured title; the configured page range was used |
| `toc_page_differs_from_config:…` | the TOC and the config disagree on the first page; the TOC won |
| `heading_not_on_first_page:N` | the section heading text is not on page N; the range is suspect |
| `printed_page_mismatch:…` | the footer of the section's first page shows a different number than the TOC gave |
| `page_offset_unverified_for_printed_page:N` / `page_offset_disagreement:…` | the printed-number-to-PDF-index offset could not be confirmed from footers, or sections disagree; offset 0 assumed |
| `marker_disagreement:…` | the arrow icon and the row text disagree on risk vs opportunity; the icon won |
| `marker_icon_missing` | a financial row had no icon; the text decided |
| `layout_unreconstructed` | page kept as plain text, column order may be scrambled |

### Transform and Load

Not built yet. Stages, order and done-criteria are in [CLAUDE.md](CLAUDE.md).

## Tests

```sh
uv run pytest
```

The tests run against the real PDF: TOC matching including a mismatched title and wrong configured pages, the p.51 column reconstruction (with a test showing that naive text order attributes text to the wrong risk), and the pp.71–74 marker detection (exactly 7 financial-risk rows, 3 opportunities, immaterial and impact rows excluded).
