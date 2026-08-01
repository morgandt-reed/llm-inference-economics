# ADR-0004: Open weights, open source, and free commercial use are three different things

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

The economic analysis in [ADR-0001](0001-what-self-hosting-competes-with.md)
assumes that if the arithmetic favoured self-hosting, self-hosting would be
available. For a majority of interesting models that assumption needs checking
first, and the check is legal rather than technical.

"Open model" is used as though it named one category. It names at least three,
and the differences decide what you are allowed to do:

- **Open weights** — the parameters can be downloaded. Says nothing about what
  you may do with them.
- **Open source** — the licence meets an open-source definition: use for any
  purpose, by anyone, without additional permission or field-of-use restriction.
- **Free commercial use** — you may serve the model to paying customers. Implied
  by an open-source licence; permitted with conditions by several licences that
  are not open source; and not permitted at all by some models distributed with
  downloadable weights.

The order in which these get checked matters. Licence terms decide whether a
deployment is permitted; economics decide whether it is sensible. Running the
economics first means the licence question arrives after a business case exists,
at which point it is a problem to be worked around rather than a constraint on
the design.

## Decision

Establish the licence position before modelling anything, and record it as a
field rather than an assumption.

In this repository, `open_weights` is a **required** block on every price entry.
Its `available` flag drives which routes appear in the self-hosting comparison at
all, and when `available` is true the loader requires both a licence name and a
URL:

```
open_weights:
  available: true
  license: MIT
  license_url: https://opensource.org/licenses/MIT
```

The loader rejects `available: true` without a licence with the message *"'Open
weights' is not a licence; name the actual one."* The categories below are for
orientation; the entry records the specific terms, because the categories are
where the mistakes live.

## The decision table

For anyone planning to serve a model — internally at scale, or commercially.

| Category | Representative licences | Commercial serving | What to check before committing |
|---|---|---|---|
| **Permissive open source** | MIT, Apache-2.0, BSD | Yes, unconditionally | Attribution and notice requirements. Apache-2.0 additionally carries an express patent grant and a termination clause triggered by patent litigation — read it if patents are a live consideration. |
| **Community / bespoke vendor licences** | Vendor-specific "community licence" terms | Yes, with conditions | User or revenue thresholds above which separate permission is required; naming and attribution obligations on derivative models and on the product itself; an acceptable-use policy incorporated by reference that can be updated by the licensor. |
| **Modified permissive** | A permissive licence with added clauses | Usually yes | *What was modified.* The base licence name tells you nothing here; the added clauses are the licence. Attribution obligations conditioned on deployment scale are a common addition. |
| **Model-specific terms of use** | Vendor terms accompanying a weights release | Varies | Whether the terms are a licence or an agreement you accept on download; whether they bind downstream recipients; use restrictions; and whether the terms can change under you. |
| **Research / non-commercial** | Non-commercial licences, evaluation-only terms | **No** | Nothing to check — this forecloses the plan. Confirm the category early. |
| **API-only, no weights** | No public weights release | Not applicable | There is nothing to host. Confirm before designing anything around it. |

Two of these have caused real problems often enough to state separately.

**A "community licence" is not open source.** A licence containing a user
threshold, a field-of-use restriction, or a licensor-updatable acceptable-use
policy fails an open-source definition by design. That is a legitimate choice by
the publisher and it is often perfectly workable. But if a plan was built on
"it's open source, so we can", the plan was built on a false premise, and the
threshold clause is the sort of thing that becomes relevant precisely when the
deployment succeeds.

**A model family is not uniformly licensed.** Publishers change licences between
releases, and the flagship and the smaller models in the same family frequently
differ. The check is per model and per version, against the terms shipped with
the weights you actually downloaded — not against a recollection of the family's
reputation. `data/prices-2026-07.yaml` records licences at the entry level for
exactly this reason.

## The distinction that decides commercial resale

Serving a model to your own employees and reselling inference to third parties
are different activities under several of these licences. Attribution clauses,
user thresholds and acceptable-use terms typically bind the second more tightly
than the first, and thresholds phrased in monthly active users are reached by a
product, not by an engineering department.

Independently of licensing: reselling inference of a commodity open-weight model
means competing on unit cost against providers who already serve the same weights
at scale, into marketplaces that route on price. ADR-0001 explains why that
position is difficult on economics alone. The licence check tells you whether it
is permitted; the economics tell you whether it is advisable; and the two
questions have to be answered in that order, because a permitted plan that loses
money is a smaller problem than a profitable plan that breaches its licence.

## Consequences

- Whether a model can be self-hosted is a data field, so the tooling can
  distinguish "expensive" from "not an option" and does not silently price the
  latter.
- The licence question is forced to the front, before a business case exists to
  argue with it.
- **Cost: the table is orientation, not legal advice.** Licences differ in
  material detail, terms change between releases, and the consequences of getting
  it wrong are not engineering consequences. A deployment that matters gets read
  by someone qualified to read it. Nothing here substitutes for that.
- **Cost: recording a licence name in a data file creates a maintenance
  obligation.** A licence that changes on a subsequent release makes the recorded
  value quietly wrong, in a file whose whole purpose is to be trustworthy. The
  `as_of` date bounds the claim; it does not refresh it.
- Category is not enough to act on. Two licences in the same row of the table can
  differ in exactly the clause that matters, which is why the schema requires the
  name and the URL rather than a category.

## Alternatives considered

**Record a boolean "commercially usable" instead of a licence name.** Rejected.
It collapses "yes", "yes above a threshold you may cross", and "yes if you
display attribution" into one value, and the collapsed distinctions are the ones
that cause the problems.

**Omit licensing from the price data and treat it as a separate concern.**
Rejected. Licence and price are consumed by the same decision, and separating
them is what allows an economic analysis to be completed for a model that cannot
lawfully be deployed. Requiring the field makes that mistake impossible to make
silently.
