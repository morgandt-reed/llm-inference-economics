# Price file schema

A price file is a dated snapshot of published list prices. The filename carries
the date (`prices-YYYY-MM.yaml`) so that a superseded file can be kept rather
than overwritten, and so a result can be traced to the snapshot that produced it.

The loader (`inference_economics.prices`) validates every field described here
and refuses to load a file that violates it. There is no permissive mode.

## Top level

| Key | Type | Required | Meaning |
|---|---|---|---|
| `version` | integer | yes | Schema version. Currently `1`. The loader rejects anything else rather than guessing. |
| `published` | string | yes | The snapshot's period, e.g. `2026-07`. |
| `description` | string | no | Free text. |
| `models` | list | yes | One entry per priced route. Must be non-empty. |

## Model entry

| Key | Type | Required | Meaning |
|---|---|---|---|
| `model_id` | string | yes | Stable identifier, unique within the file. This is what `--model` takes. |
| `display_name` | string | yes | Human-readable name for tables. |
| `provider` | string | yes | Who bills you. |
| `tier` | `first-party` \| `aggregator` | yes | Whether you are buying from the party that trained the model or from a routing marketplace. The distinction is load-bearing: see ADR-0001. |
| `input_per_mtok` | number ≥ 0 | yes | USD per million uncached input tokens. |
| `output_per_mtok` | number ≥ 0 | yes | USD per million output tokens. |
| `cached_input_per_mtok` | number ≥ 0 \| `null` | yes | USD per million input tokens served from a prompt cache. `null` means *no cached rate was verified at the as-of date*, and the model charges the full input rate for cache hits. |
| `batch_discount` | number in [0, 1] \| `null` | yes | Fractional reduction for asynchronous batch traffic — `0.50` is 50% off. `null` means no batch discount was verified, and the model applies none. |
| `source_url` | URL string | yes | The page the numbers were read from. **Enforced by the test suite.** |
| `as_of` | date (`YYYY-MM-DD`) | yes | When they were read. **Enforced by the test suite.** |
| `promotional` | boolean | no (default `false`) | The recorded price is a time-limited discount, not the rate card. The CLI marks these with `*`. |
| `context_window_tokens` | integer > 0 \| absent | no | Recorded for reference. The cost model does not use it. |
| `open_weights` | object | yes | See below. |
| `benchmark` | object | no | See below. |
| `notes` | string | no | Free text, rendered by `inference-econ prices`. |

### `open_weights`

| Key | Type | Required | Meaning |
|---|---|---|---|
| `available` | boolean | yes | Whether the weights can be downloaded and served. If `false`, the route cannot be self-hosted at any price, and the self-hosting comparison is not applicable to it. |
| `license` | string | required when `available` is true | The licence name as published — `MIT`, `Apache-2.0`, `Modified MIT`, `Llama Community License`, and so on. Not a category; the actual name. |
| `license_url` | URL string | required when `available` is true | Where to read the terms. |

Open weights are not the same thing as open source, and neither is the same
thing as unrestricted commercial use. The distinction, and why it decides
whether a self-hosting plan is legal before it decides whether it is
affordable, is in
[ADR-0004](../docs/adr/0004-open-weights-licensing.md).

### `benchmark`

Optional, and at most one entry. A single dated score with a source, not a
ranking.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | The benchmark, named exactly. |
| `score` | number | yes | The reported figure. |
| `as_of` | date | yes | When it was read. |
| `source_url` | URL string | yes | Where. |
| `notes` | string | no | Which standardisation, harness or split — the thing that makes two published numbers for the same model disagree. |

A score in this file means "this figure appeared on this page on this date". It
does not mean the model is better than another model, it does not carry across
benchmark revisions, and it says nothing about your workload. The cost model
never reads it. It exists so that a quality claim in a discussion has a citation
attached rather than a recollection.

## What the loader rejects

- An unknown `version`.
- An unknown key anywhere in the file — a typo in a field name is an error, not
  a silently ignored line.
- A missing required key, a `model_id` that repeats, a negative price, a
  `batch_discount` outside `[0, 1]`, a `tier` outside the two allowed values.
- `open_weights.available: true` without a `license` and `license_url`.
- An `as_of` that is not a date, or a `source_url` that is not an `http(s)` URL.

The intent is that a malformed price file fails loudly at load time rather than
producing a plausible-looking table with a hole in it.
