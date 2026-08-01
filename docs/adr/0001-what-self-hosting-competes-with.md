# ADR-0001: Self-hosting an open-weight model competes against that model's own API

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

The build-vs-buy question for LLM inference is usually posed as: *our developers
are spending a lot on a frontier API; what if we bought GPUs and ran an
open-weight model instead?*

Posed that way, the arithmetic is encouraging. Frontier API pricing is
several dollars per million input tokens and tens of dollars per million output
tokens. A node's amortised monthly cost divided across the developers it serves
produces a per-developer figure that, at a plausible head count, comes in below
that. A crossover exists, it can be plotted, and it lands somewhere a
sufficiently large organisation could reach.

The model in this repository reproduces exactly that result. With its default
scenario — an eight-GPU node at a surveyed market price of $370,000 amortised
over three years, forty nameplate developers per node at sixty percent
utilisation, two platform engineers — self-hosting breaks even against a
frontier API at **145 developers** on the intensive token profile:

```
$ inference-econ breakeven --model claude-opus-5
BREAK-EVEN AT 145 DEVELOPERS
```

The number is arithmetically correct. The comparison is wrong, and the reason it
is wrong is not subtle once stated: **you are not self-hosting that model.** Its
weights are not downloadable. Nothing on those GPUs is the model whose price you
just used as the benchmark. The calculation prices one product's rate card
against a different product's running costs and reports the difference as a
saving.

## Decision

Treat the correct comparator for self-hosting a model as **that same model's own
API**, and build the tooling so that this is the default rather than something a
careful reader has to remember.

Concretely, in this repository:

- `inference-econ breakeven` defaults to `--model glm-5.2` — an open-weight
  model's first-party API — not to a frontier model.
- The price schema requires an `open_weights` block on every entry, so whether a
  route can be self-hosted at all is a field rather than an assumption. The
  loader rejects a file that omits it.
- `inference-econ compare` prints its verdict table over *only* the routes whose
  weights are downloadable.
- The break-even against an API-only model is still computed, deliberately, and
  printed with a warning next to it. Suppressing the number would hide the
  finding; the point is to show that the encouraging figure and the correct
  figure are different figures.

With the correct comparator, the default scenario gives a different answer:

```
$ inference-econ breakeven
NO BREAK-EVEN
  marginal cost per developer ($530.36) is at or above the API price ($281.50);
  scale dilutes fixed costs but cannot go below the marginal cost, so no head
  count closes the gap.
```

## Why there is no break-even, structurally

The mechanism matters more than the number, because the number moves and the
mechanism does not.

Self-hosted cost per developer has two components. Fixed costs — the platform
team, the redundant node — are diluted by scale and tend to zero per developer.
Variable cost does not: every additional block of developers needs another node,
so the per-developer cost converges downward on a floor equal to one node's
monthly cost divided by the developers that node actually serves. This
repository calls that the **marginal cost per developer**, and it is the whole
argument:

> If the marginal cost per developer already exceeds the API price, no head
> count closes the gap. Scale is not a lever on this. It is a horizontal
> asymptote, and the API price is below it.

Against a frontier API the marginal cost sits below the price, so scale
eventually wins. Against the open model's own API it sits above, and scale wins
nothing at any size.

The reason it sits above is not that the operator is doing anything wrong. It is
that a provider serving one model to the entire market runs at a utilisation and
a batch size a single organisation's working-hours demand cannot reach, on
hardware bought at a scale that changes the price. Competing with that on unit
cost means beating a specialist at the one thing they optimise for, using
capacity that sits idle two-thirds of the day.

There is a second effect pushing the same way. Open-weight inference is a
commodity: the weights are the same weights, many providers serve them, and
routing marketplaces send traffic to whoever is cheapest. Prices in that market
fall, and they fall on a schedule nobody buying hardware controls. A capital
commitment amortised over three years is a bet that a competitive market's floor
price will not fall underneath it — and the direction of travel over the period
this price data covers has been downward, sharply. That is a bet against the
structure of the market, not merely against a competitor.

## The rigged comparison, and how it gets built

This is the part worth being blunt about, because it is a failure mode that
survives review.

A comparison of self-hosted open weights against a frontier API's price will
show a break-even. It will be arithmetically defensible. Every input can be
sourced. And it will still be wrong, because it silently prices a quality
difference at zero.

If the organisation genuinely accepts open-model output quality, then its
alternative to self-hosting is that open model's API — not the frontier one — and
the correct comparison is the one with no break-even in it. If the organisation
does *not* accept open-model quality, then self-hosting does not deliver what the
frontier API delivers, and the comparison is between two different things
regardless of what the spreadsheet says.

Either way the frontier price is the wrong number. There is no reading under
which it is the right one. But it is the *flattering* number, and a business
case built on it can be assembled entirely from citable public figures, which
makes it very hard to argue with after the fact. Somebody will build it if
nobody puts the correct comparator in front of them first.

That is why the tool prints the warning next to the figure rather than instead
of it:

```
*** THIS IS THE RIGGED COMPARISON. ***
Claude Opus 5 has no downloadable weights, so nothing above is self-hosting it.
```

## The honest counter-question

**Is this conclusion robust, or is it an artefact of the default parameters?**

It is an artefact of the parameters, and the repository says so rather than
hiding it. Two inputs decide the answer — the token profile and
developers-per-node — and neither was measured here. `inference-econ sensitivity`
sweeps both, and against an open model's own API the verdict flips inside the
default grid: at eighty nameplate developers per node and above, a break-even
appears.

So the defensible claim is narrower than "self-hosting never pays", and it is
this:

> At the node capacities this repository considers plausible, self-hosting does
> not beat the open model's own API. At roughly double those capacities it does.
> Which regime you are in is a question about your serving stack that nobody can
> answer from a spreadsheet.

If the sweep's flip point sits inside your honest uncertainty, you do not have a
decision yet — you have a measurement to take. Instrument the gateway for a
month, get a real token profile, load-test the serving stack for a real capacity
figure, and re-run. That is a smaller and more useful piece of work than
arguing about the conclusion.

## Consequences

- The headline result reverses relative to the intuitive framing, and reverses
  again if node capacity turns out to be much higher than assumed. Both are
  reported.
- A quality difference between models is never priced at zero by accident,
  because comparing a model to itself removes the question rather than answering
  it.
- **Cost: the tool refuses to give the encouraging answer without a caveat
  attached.** That is friction in exactly the setting where a clean number would
  be most welcome, and it will be unwelcome.
- **Cost: the correct comparator is only available while the open model has a
  first-party API.** A model published as weights with no hosted endpoint has no
  natural comparator, and the analysis falls back to aggregator pricing —
  which is a market price, not the vendor's, and moves faster still.
- The economics say nothing about the cases in
  [ADR-0002](0002-where-the-real-case-is.md), where the alternative to
  self-hosting is not a cheaper API but no LLM at all. That case is real. It is
  just not this one.

## Alternatives considered

**Compare against a blended market rate rather than a specific model's API.**
Rejected. A blended rate is an average over models of different quality, so it
reintroduces the priced-at-zero quality difference in a form that is harder to
see.

**Refuse to compute a break-even against models with no downloadable weights.**
This was implemented first and then removed. It is tidier, and it loses the
argument: a reader who cannot see the flattering number has no reason to believe
it is misleading, and will produce it themselves in a spreadsheet with no warning
attached. Showing the number and refuting it in the same output is the stronger
position.

**Report a single break-even figure and omit the sensitivity analysis.**
Rejected. The conclusion is sensitive to two unmeasured parameters, and a single
figure would present a modelling choice as a finding. The sweep is the more
honest deliverable even though it is a less quotable one.
