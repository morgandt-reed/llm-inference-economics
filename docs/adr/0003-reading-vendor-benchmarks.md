# ADR-0003: A checklist for reading a published benchmark

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

Infrastructure decisions attract published benchmarks. A gateway vendor
demonstrates lower proxy latency than an alternative; a serving framework
demonstrates higher throughput; a leaderboard ranks models by a coding score.
These are frequently the most concrete evidence available, and they arrive
already formatted for a slide.

They are also, usually, correct and misleading at the same time. The numbers are
real, reproducible from the published repository, and measure something that is
not the thing the reader is about to decide.

This repository publishes benchmark scores of its own — a `benchmark` block on
some price entries — so it needs a stated position on how such figures should be
read, including its own.

## Decision

Apply the following checks before a published benchmark changes a decision. Each
one has, on its own, been sufficient to invalidate the conclusion of a
professionally produced comparison.

### 1. Was the backend mocked?

A proxy or gateway benchmark that routes to a stub responding in zero time
measures proxy overhead in isolation. That is a legitimate measurement and it is
usually reported honestly, often in a caveat near the end.

The caveat is the article. Real inference takes hundreds of milliseconds to tens
of seconds. Against that, the difference between a fraction of a millisecond and
thirty milliseconds of proxy overhead is not a competitive advantage; it is below
the noise floor of the thing it sits in front of. A chart showing a large ratio
between two small numbers is showing you a ratio, not an effect.

**The check:** what fraction of end-to-end latency does the measured component
account for under the real workload? If it is one percent, a doubling of it is
worth a quarter of one percent, and no amount of chart formatting changes that.

### 2. Is it feature-parity?

A comparison between a component with provider translation, spend tracking,
virtual keys, budget enforcement, guardrails and single sign-on, and a component
that forwards requests, will find the second one faster and lighter. It is doing
less. That is not a finding; it is the definition of the two things.

**The check:** list what each side does that the other does not, then ask whether
the workload needs any of it. If it does, the resource difference is the price of
a feature you are going to have to build, and building it will not be cheaper.

### 3. Are the resource figures plausible, or do they smell of misconfiguration?

An implausible number in a benchmark is information, but rarely the information
the author intended. A stateless pass-through consuming many gigabytes of
resident memory is not a design characteristic — it is verbose logging left on, a
buffer never flushed, an unreasonable worker count, or a genuine defect worth
investigating on its own terms.

**The check:** when a figure is far outside what the architecture would predict,
treat it as a question about the benchmark setup rather than an answer about the
software. Neither reading can be confirmed from a single run by an interested
party, which is itself the point.

### 4. Single run, or replicated?

One execution, no repetitions, no variance reported, no confidence interval. This
is the norm rather than the exception in vendor benchmarking, and it means the
difference between two reported numbers cannot be distinguished from run-to-run
noise — because the run-to-run noise was never measured.

**The check:** how many runs, and what was the spread? If the answer is one and
none, the appropriate precision for any reported difference is "no idea".

### 5. Who authored it, and against whom?

A benchmark published by one party comparing itself with a named competitor is
marketing that contains data. That is not an accusation of dishonesty — the
numbers are typically real — but the author chose the workload, the
configuration, the tuning effort applied to each side, and which results to
publish. Every one of those is a degree of freedom, and none of them was
exercised symmetrically.

**The check:** does an independent replication exist? If not, the appropriate
weight is "interesting, unverified" rather than "established".

### 6. Does the metric apply to the workload at all?

The most common failure, and the hardest to see, because it requires knowing your
own workload rather than reading the article more carefully.

A throughput figure at thousands of requests per second answers a question about
extreme concurrency. If the real system will see a small fraction of that, the
benchmark's entire operating region is somewhere the system will never be, and
the winner in that region is not evidence about the winner in the region that
matters. Ranking options by a metric that does not bind is a way of making a
decision look quantitative while remaining arbitrary.

**The check:** where on the axis will the real system sit? If the answer is far to
the left of everything measured, the benchmark is not about you.

### 7. Is a more important question being crowded out?

This is the check most worth running, because it is about what the benchmark
distracts from rather than what it says.

For a component that sits in the request path of a multi-tenant system handling
credentials and traffic on behalf of many users, the questions that decide
whether it is a good choice are: what is its vulnerability history and how fast
are fixes shipped; what is the blast radius of a compromise; can a low-privilege
user escalate; is traffic auditable; are secrets isolated per tenant. A serious
vulnerability in a gateway means an attacker in the path of every request and
every key. That is an outcome measured in incidents, not in milliseconds.

**The check:** rank the open questions by the size of the worst outcome. A
security posture question and a latency question are not on the same scale, and
attention spent on the one with a chart attached is attention not spent on the
one without.

## How this applies to the benchmark scores in this repository

The `benchmark` field in `data/prices-2026-07.yaml` records a name, a score, a
date and a URL. It is subject to the same checks, and specifically fails check 5
in the ordinary way: the figures come from an aggregate leaderboard compiled from
vendor-reported results, not from an independent evaluation run here.

The file also records, in the entry notes, that different standardisations of the
same benchmark report materially different numbers for the same model, depending
on the harness, the scaffolding and the data split. Two people can cite the same
benchmark, both accurately, and disagree by more than the gap they are arguing
about.

Consequently:

- **No calculation in this repository reads a benchmark score.** It is metadata
  for a human, not an input.
- A score means "this figure appeared on this page on this date". It does not
  mean the model is better than another model, and it does not survive a
  benchmark revision.
- Quality differences between models are listed in the README under *what this
  does not model*, because a cost model that silently priced them would be
  producing a number nobody could defend.

## Consequences

- Published comparisons are usable as evidence — after the checks, at reduced
  weight, and for the specific question they measured.
- **Cost: the checklist is a licence to dismiss inconvenient evidence.** Applied
  selectively, it becomes a way of rejecting any measurement that disagrees with
  a prior. It is only honest if it is run on results that support the preferred
  conclusion as well, which is the harder half.
- The strongest form of the argument is not "this benchmark is flawed" but "here
  is the measurement on our workload". Running the comparison on the real traffic
  shape settles it, and is usually a day of work rather than a debate.

## Alternatives considered

**Rely only on independently replicated benchmarks.** Rejected as impractical:
for most infrastructure components at most points in time, none exist. The
realistic choice is between using vendor benchmarks carefully and using nothing.

**Ignore benchmarks entirely and decide on architecture and posture.** Rejected.
Performance sometimes genuinely binds, and a decision made without measurement
because measurement is imperfect is not more rigorous — it is just less
informed.
