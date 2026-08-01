# ADR-0002: Price self-hosting on compliance and SLA, not on token parity

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

[ADR-0001](0001-what-self-hosting-competes-with.md) concludes that at plausible
node capacities, self-hosting an open-weight model does not beat that model's own
API on cost. Taken alone that reads as "self-hosting is never worth it", which is
not the conclusion and would be wrong.

It is wrong because it assumes the alternative to self-hosting is always an API.
For some workloads it is not. There are organisations for which sending a prompt
containing regulated data to a third-party inference endpoint is not a
procurement decision with a price attached — it is prohibited, or permitted only
under conditions no public endpoint satisfies. Data residency obligations, a
sector regulator's stance on processing outside a defined boundary, a contract
with a customer that forbids sub-processors, an air-gapped environment.

When that is the situation, the comparison in ADR-0001 is not merely unfavourable
— it is not the comparison at all. The alternative is not a cheaper API. The
alternative is **not using the model**.

## Decision

Where a restriction genuinely forecloses the API route, price the self-hosted
service on what it makes possible and what it guarantees — compliance posture and
service level — rather than on cost per token.

This is not a rhetorical repositioning of an unfavourable number. It follows from
the structure of the decision. A cost-per-token comparison presupposes two
options that both deliver the outcome, differing in price. If one option cannot
be used, there is no ratio to compute, and the value of the remaining option is
whatever the capability is worth to the organisation. That is an entirely
different question, and it has a different and usually much larger answer.

The consequence for how such a service is designed and sold:

- **The deliverable is the boundary, not the tokens.** What is being bought is a
  guarantee about where data goes, who can see it, what is logged, what is
  retained, and what can be demonstrated to an auditor. The inference is the
  mechanism.
- **The evidence is the product.** Data-flow documentation, retention controls,
  access records, tenancy isolation, and the ability to answer a regulator's
  question with an artefact rather than an assurance. This is the expensive part,
  and it is expensive whether or not the GPU utilisation is any good.
- **The SLA is a commitment, not a marketing line.** A service someone is
  compelled to use because the alternative is nothing has no fallback when it
  degrades. That is a heavier operational obligation than a service whose users
  could switch endpoints, and it should be priced as one.

## This is a premium niche, not volume economics

Being explicit, because the temptation to generalise from this is strong and the
generalisation is where the money goes.

The case above justifies a *specific* service for a *specific* constraint. It
does not justify building a general inference platform and offering it broadly on
the theory that some customers value sovereignty. Those are different businesses
with different economics:

| | Compliance-driven | Volume inference |
|---|---|---|
| What is bought | A boundary and evidence for it | Tokens |
| Comparator | Not using the model at all | The cheapest route that works |
| Price sensitivity | Low — the alternative is zero capability | Extreme — routing marketplaces sort by price |
| Utilisation | Whatever the constrained workload happens to be | Must be high or the unit cost does not work |
| Wins on | Assurance, auditability, contractual position | Unit cost at scale |

The second column is the one ADR-0001 says not to enter. Nothing in this ADR
changes that. A platform built for the first column and then also offered into
the second is competing on unit cost against specialists, from a cost base
inflated by the compliance apparatus that justified the whole thing — the worst
of both positions.

Two further cautions worth stating plainly:

**Sovereignty claims must survive scrutiny.** "Runs on our hardware" is not by
itself a compliance position. What matters is the full data path — where
inference happens, what the serving stack logs, where those logs go, who can
reach the host, what the observability layer exports, and whether any of it
crosses a boundary. A deployment can be entirely on-premises and still fail the
requirement it was built for. This is engineering work, not a location.

**Regulated does not automatically mean self-host.** Major providers offer
regional processing, contractual data-handling commitments, and certifications
that satisfy many requirements at a fraction of the cost. The genuine cases are
the ones where a specific obligation genuinely cannot be met by any available
endpoint. Establish that this is true before designing anything — including by
reading what the providers actually commit to, which is often more than assumed.
The number of situations where self-hosting is *required* is considerably smaller
than the number where it is *preferred*, and the two get conflated early and
expensively.

## Consequences

- Cost-per-token modelling is the wrong instrument here, and this repository's
  tooling does not attempt to model this case. It computes an economic comparison
  between substitutable options; where the options are not substitutable, the
  output is not meaningful and no amount of parameter tuning makes it so.
- The cost model still has a use in this setting, in a different direction: it
  gives the cost floor. What the service costs to run is a real input to pricing
  it, even when the price is not derived from that cost.
- **Cost: this argument is very easy to abuse.** "The case is sovereignty" is
  precisely what someone says when the cost case has failed, and it is
  indistinguishable from the honest version unless the constraint is named
  specifically — which obligation, which data, which text in which regulation. An
  unnamed compliance justification should be treated as an absent one.
- The addressable population is small by construction. That is a feature of the
  position, not a problem to be solved by widening the definition.

## Alternatives considered

**Fold the compliance premium into the cost model as a monetised risk
adjustment.** Rejected. It would make the model produce a favourable answer by
adding a number that could not be sourced, which is the failure mode this whole
repository is built to avoid. A value that cannot be cited does not belong in a
calculation that claims every input can be.

**Treat compliance as a hard filter applied before any costing.** This is
effectively what the ADR recommends, and it is the right sequence: establish
whether an API route is available at all, and only run the economic comparison if
it is. It is not encoded in the tool because the filter is a question about a
specific legal obligation, and a tool that pretended to answer it would be
offering assurance it cannot support.
