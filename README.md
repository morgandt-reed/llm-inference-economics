# LLM Inference Economics

[![CI](https://github.com/morgandt-reed/llm-inference-economics/actions/workflows/ci.yml/badge.svg)](https://github.com/morgandt-reed/llm-inference-economics/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org/)
[![Price data](https://img.shields.io/badge/price%20data-2026--07-2c3e50)](data/prices-2026-07.yaml)

A parameterised build-vs-buy model for LLM inference: what a developer-month
costs on a first-party API, on an aggregator route, and on your own GPUs — and
at what head count, if any, the third option wins.

> **The headline, up front.**
>
> Self-hosting an open-weight model competes against **that same model's own
> API**, not against a frontier model's price. At the node capacities this model
> considers plausible, the marginal cost of serving one more developer on your
> own hardware is *higher* than the open model's API price — so there is no
> break-even at any head count. Scale dilutes fixed costs; it cannot go below
> the marginal cost.
>
> Compare the same self-hosted setup against a **frontier** API and a break-even
> appears at 145 developers. That number is arithmetically correct and it is the
> wrong comparison: the frontier model's weights are not downloadable, so
> nothing on those GPUs is the model whose price you just used as the benchmark.
> Somebody will build a business case on it if you let them.
>
> The real case for self-hosting is sovereignty, data residency and compliance —
> situations where the alternative is not a cheaper API but *not being able to
> use the model at all*. Price that on compliance and SLA, not on token parity.
> It is a premium niche, not volume economics.
>
> Full argument: [ADR-0001](docs/adr/0001-what-self-hosting-competes-with.md) and
> [ADR-0002](docs/adr/0002-where-the-real-case-is.md).

**And the caveat that comes with it:** the conclusion is sensitive to two inputs
that nobody measured here — the token profile and developers-per-node. Inside the
default sensitivity grid, the verdict **flips**. That is reported rather than
buried, because a build-vs-buy answer that hinges on two unmeasured parameters is
a modelling choice presented as a finding. See
[Sensitivity](#sensitivity-the-part-that-matters-most).

## What this computes

Given a token profile, a rate card and a hardware scenario, the model produces:

- **Cost per developer-month** on every priced route, with cache-hit ratios and
  batch discounts applied.
- **Marginal cost per developer** for self-hosting — one node's monthly cost
  divided by the developers it actually serves. This is the floor that decides
  whether a break-even exists at all.
- **Break-even head count**, defined as the smallest number of developers from
  which self-hosting is *never again* more expensive. Cost per developer is a
  sawtooth — it falls as a node fills and jumps when you buy the next one — so a
  crossing that reverts is not a break-even.
- **A sensitivity grid** over the two parameters the answer actually depends on.

Everything is a pure function over frozen dataclasses. The model layer does no
I/O, reads no clock and prints nothing.

## Quick start

```bash
git clone https://github.com/morgandt-reed/llm-inference-economics.git
cd llm-inference-economics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

inference-econ compare
```

## Worked example

Real output, produced by the command shown. The comparison table is committed at
[`tests/golden/compare.txt`](tests/golden/compare.txt) and CI fails if the CLI
stops matching it.

```console
$ inference-econ compare
Cost per developer-month — intensive profile, 500 developers
Price data: prices-2026-07.yaml (published 2026-07)

Assumptions — every one of these is an input you can change:
  Token profile      intensive: 500 Mtok in / 15 Mtok out per developer-month, 85% cache hits
  Head count         500 developers
  Node               8x H200 SXM (owned, colocated) — $370,000 over 36 months
  Node capacity      40 nameplate x 60% utilisation = 24.0 effective developers per node
  Node monthly cost  $12,729 (amortisation $10,278 + energy $1,251 + hosting $1,200)
  Platform team      2 FTE at $15,000/month = $30,000/month
  Redundancy         1 node(s) carrying full cost and no capacity
  Batch traffic      0% of traffic routed through a batch endpoint

BUY — published API list prices

Route                                 Provider       Tier         $/dev-month  Weights
------------------------------------  -------------  -----------  -----------  ------------
Claude Haiku 4.5                      Anthropic      first-party      $192.50  API only
Qwen3.7 Max*                          Alibaba Cloud  first-party      $256.25  API only
GLM-5.2 (Z.ai first-party)            Z.ai           first-party      $281.50  MIT
GLM-5.2 (cheapest aggregator route)*  OpenRouter     aggregator       $392.19  MIT
Kimi K2.6                             Moonshot AI    first-party      $535.00  Modified MIT
Claude Sonnet 5                       Anthropic      first-party      $577.50  API only
Kimi K3                               Moonshot AI    first-party      $577.50  Modified MIT
Claude Opus 4.8                       Anthropic      first-party      $962.50  API only
Claude Opus 5                         Anthropic      first-party      $962.50  API only
Claude Fable 5                        Anthropic      first-party    $1,925.00  API only

  * promotional rate, not the rate card. See the notes in the price file.

BUILD — self-hosted open-weight model, on your own hardware

Measure                                              Value
---------------------------  -----------------------------
Nodes required               22 (21 serving + 1 redundant)
Total monthly cost                                $310,032
Cost per developer at 500                          $620.06
Marginal cost per developer                        $530.36

  The marginal cost is the floor. Adding developers dilutes the platform team
  and the redundant node, but never takes the per-developer cost below it.

VERDICT — against every route whose weights you could actually run

Its own API                          API $/dev  Self-host $/dev  Ratio  Verdict
-----------------------------------  ---------  ---------------  -----  ---------------------
GLM-5.2 (Z.ai first-party)             $281.50          $620.06  2.20x  never breaks even
GLM-5.2 (cheapest aggregator route)    $392.19          $620.06  1.58x  never breaks even
Kimi K2.6                              $535.00          $620.06  1.16x  more expensive at 500
Kimi K3                                $577.50          $620.06  1.07x  more expensive at 500
```

Three things in that output are worth pausing on.

**The self-hosted marginal cost ($530.36) is above GLM-5.2's own API price
($281.50).** That single inequality is the conclusion. No head count fixes it.

**The cheapest aggregator route scores *worse* than the first-party API despite a
lower headline per-token price** — $392.19 against $281.50. No cached-input rate
was verified for that route, so the model charges the full input price for cache
hits, and on a workload that is 85% cache reads that dominates everything else. A
headline per-token number does not rank routes for a cache-heavy workload. If
your aggregator route does support prompt caching, add the rate to the price file
and the ordering changes.

**Kimi K3 costs more than Kimi K2.6 from the same vendor** — $577.50 against
$535.00, roughly triple the rate card. Worth noting against the assumption that
open-weight API prices only ever fall.

### The rigged comparison, on purpose

Both commands print a table of the underlying costs first; the excerpts below
start at the verdict.

```console
$ inference-econ breakeven                        # the correct comparator
NO BREAK-EVEN
  marginal cost per developer ($530.36) is at or above the API price ($281.50); scale dilutes fixed costs but cannot go below the marginal cost, so no head count closes the gap.

$ inference-econ breakeven --model claude-opus-5  # the flattering comparator
BREAK-EVEN AT 145 DEVELOPERS
  from 145 developers onward, self-hosting costs $909.17 per developer-month against $962.50 on the API.

  *** THIS IS THE RIGGED COMPARISON. ***

  Claude Opus 5 has no downloadable weights, so nothing above is
  self-hosting it. The self-hosted column is some *other* model running on
  your hardware, priced against this vendor's rate card. The arithmetic is
  correct and the comparison is meaningless: it prices two different
  products as though they were one.
```

The tool computes the flattering number deliberately rather than refusing to.
A reader who cannot see it has no reason to believe it is misleading, and will
reproduce it in a spreadsheet with no warning attached.

## Sensitivity: the part that matters most

```console
$ inference-econ sensitivity
Sensitivity — break-even head count vs GLM-5.2 (Z.ai first-party)

Cells are the developer count at which self-hosting first becomes and stays
cheaper. 'never' means the marginal cost per developer already exceeds the API
price, so no head count closes the gap.

Devs/node   light  medium  intensive
---------  ------  ------  ---------
20          never   never      never
30          never   never      never
40          never   never      never
60          never   never      never
80         57,001  17,031      3,409
120         5,143   1,662        577

Underlying costs per developer-month:

Devs/node  light marginal  medium marginal  intensive marginal
---------  --------------  ---------------  ------------------
20                   $119             $368              $1,061
30                    $79             $245                $707
40                    $59             $184                $530
60                    $40             $123                $354
80                    $30              $92                $265
120                   $20              $61                $177
API                   $31              $95                $282

THE VERDICT FLIPS INSIDE THIS GRID.
```

The flip sits between 60 and 80 nameplate developers per node. Below it, no head
count makes self-hosting pay against the open model's own API. Above it, one
does — though at 80 devs/node on the intensive profile the crossover is still
3,409 developers, which is a different kind of "no" for most organisations.

So the defensible claim is narrower than "self-hosting never pays":

> At the node capacities modelled here, self-hosting does not beat the open
> model's own API. At roughly double those capacities it does. Which regime you
> are in is a question about your serving stack that no spreadsheet can answer.

If that flip point sits inside your honest uncertainty, you do not have a
decision — you have a measurement to take.

## Assumptions, and how to change them

Every number is one of two things: **public and cited**, or **an input parameter
with a default you are told to change**. Nothing in this repository was measured
here.

### Public and cited

Recorded with a source URL and an as-of date in
[`data/prices-2026-07.yaml`](data/prices-2026-07.yaml) and
[`src/inference_economics/scenario.py`](src/inference_economics/scenario.py). Run
`inference-econ prices` to print them with their sources. A test asserts that
every price entry carries both, and it runs as its own CI job.

| Input | Default | Source |
|---|---|---|
| API list prices | 10 routes | Vendor pricing pages, read 2026-08-01 |
| Node capital cost | $370,000 | Market survey of 8-GPU HGX H200 systems, 2026 (no manufacturer list price exists for this part) |
| Node power draw | 10.2 kW | 8 × 700 W published GPU TDP plus platform overhead |

### Input parameters — change these

The two at the top decide the answer. The rest move it.

| Flag | Default | Why you should change it |
|---|---|---|
| `--devs-per-node` | 40 | **Dominant.** Depends on batching, quantisation, speculative decoding, context length and your latency target. The single number is a placeholder; read the sensitivity grid instead. |
| `--profile` | `intensive` | **Dominant.** Three tiers, all guesses. Replace with a month of real gateway telemetry — it is the only place a true number comes from. |
| `--utilisation` | 0.60 | Demand concentrates in working hours. A node sized for the average is saturated at 3pm. |
| `--power-price` | $0.12/kWh | Industrial tariffs vary by more than 3× across jurisdictions. Set from your own bill. |
| `--colocation` | $1,200/node/mo | Quote it; do not inherit this number. |
| `--platform-fte` / `--fte-cost` | 2.0 / $15,000 | Modelled flat. Real headcount is a staircase — raise it as you add nodes, which moves break-even out, never in. |
| `--node-capex` / `--amortisation-months` | $370,000 / 36 | Shorten amortisation and the marginal cost rises. |
| `--pue` | 1.4 | Conventional air-cooled facility. Liquid-cooled does better; a retrofitted comms room does much worse. |
| `--redundancy-nodes` | 1 | Nodes carrying full cost and no capacity. One is a floor for anything with an availability expectation. |
| `--batch-fraction` | 0.0 | Share of traffic through an async batch endpoint. |

The token profiles carry a further assumption worth arguing with: input dwarfs
output by one to two orders of magnitude, and most of that input is a cache hit.
That shape is what makes this an *agentic coding* model rather than a chatbot
model, and every conclusion depends on it. A harness that invalidates its prompt
prefix every turn gets none of the cache benefit and lands somewhere else
entirely.

There is one more modelling choice with no source behind it: node capacity is
re-scaled between profiles by weighting a fresh input token at `prefill_weight`
(default 0.05) of an output token, with cached input weighted at zero. Decode
dominates serving cost and a prefix cache hit costs the server close to nothing,
so the direction is right; the magnitude is a judgement.

## What this does not model

An honest list, because the gaps change what the numbers are good for.

- **Quality differences between models.** The single dated benchmark score in the
  price file is metadata for a human — no calculation reads it. Two models at the
  same price are treated as interchangeable, which they are not, and a model that
  needs fewer retries to finish a task is cheaper in a way this does not capture.
  See [ADR-0003](docs/adr/0003-reading-vendor-benchmarks.md).
- **Tokenizer differences.** The same text is a different number of tokens on
  different models. A single token profile priced across every route silently
  assumes it is not.
- **Fine-tuning, distillation and continued pre-training.** Both the cost of
  doing them and the value of the result. A fine-tune is one of the few genuine
  arguments for owning hardware, and it is entirely absent here.
- **Multi-region and failover topology.** One site, one pool. Two regions is more
  than twice the cost and changes the redundancy arithmetic.
- **Contract discounts, committed-use pricing and reserved capacity.** List
  prices only. Enterprise agreements move API pricing materially, and always in
  the direction that makes self-hosting look worse.
- **Egress, storage, and the data platform around inference.** Weights storage,
  model registry, evaluation infrastructure, the gateway itself.
- **Batch and caching interaction.** The batch discount is applied to the whole
  cost of the batched share, input and output alike. Vendors differ on how batch
  and cached-input pricing compose.
- **Rate limits and queueing.** An API route with limits you exceed at peak is
  not the route you priced.
- **GPU rental as a third option.** Only purchase-and-amortise is modelled.
  Rental changes the capital structure and is the right answer for lumpy demand.
- **Hardware compatibility.** A serving stack that supports one accelerator
  vendor and not another can make half a purchased fleet unusable for the model
  the business case was built on. The model prices a homogeneous fleet.
- **Migration and exit costs**, in either direction.
- **The residual value of the hardware** at the end of amortisation, and the
  risk that it is lower than assumed.

## Repository layout

```
src/inference_economics/
  model.py         Frozen dataclasses and pure cost functions. No I/O.
  profiles.py      Three token profiles. Assumptions, labelled as such.
  scenario.py      Default hardware scenario, each number sourced or flagged.
  prices.py        The only module that reads a file. Strict schema validation.
  breakeven.py     The band search, and why "break-even" means "and stays".
  sensitivity.py   The sweep over the two dominant parameters.
  render.py        Text tables. Pure functions, no calculation.
  cli.py           Four commands.
data/
  prices-2026-07.yaml   Dated price snapshot with per-entry provenance.
  SCHEMA.md             The schema, and what the loader rejects.
docs/adr/          Four decision records — the argument, not the code.
tests/             161 tests, 95% coverage floor, golden CLI output.
```

## Decision records

- [ADR-0001 — What self-hosting competes with](docs/adr/0001-what-self-hosting-competes-with.md)
  — the headline argument, the marginal-cost floor, and the rigged comparison.
- [ADR-0002 — Where the real case is](docs/adr/0002-where-the-real-case-is.md)
  — sovereignty and compliance, priced on SLA rather than token parity, and why
  it is a niche rather than a market.
- [ADR-0003 — Reading a published benchmark](docs/adr/0003-reading-vendor-benchmarks.md)
  — a seven-point checklist, applied to this repository's own scores.
- [ADR-0004 — Open weights, open source, free commercial use](docs/adr/0004-open-weights-licensing.md)
  — a decision table for anyone planning to serve a model.

## Development

```bash
pytest                    # 161 tests, 95% coverage floor
ruff check .              # pinned 0.6.9
ruff format --check .
```

CI runs lint, the test matrix on 3.11–3.13, the provenance suite as its own
visible job, and every command this README shows — including a diff of the
committed comparison table against live CLI output, so the README cannot drift
away from the tool.

## Roadmap

Not implemented, and named rather than implied:

- GPU rental as a third cost structure alongside purchase-and-amortise.
- A step-function platform-headcount model instead of a flat FTE count.
- Per-model tokenizer factors, so one profile can be priced honestly across
  routes that count tokens differently.
- Multi-region topology and its effect on redundancy.
- A JSON output mode, so the model can feed a spreadsheet without screen-scraping
  a text table.

## Licence

MIT. See [LICENSE](LICENSE).
