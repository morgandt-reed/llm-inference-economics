"""The cost model.

Everything in this module is a frozen dataclass or a pure function over frozen
dataclasses. No file access, no network, no clock, no printing. That constraint
is not tidiness for its own sake: a build-vs-buy model is an argument, and an
argument is only checkable if every number in it comes from an input you can
see, through arithmetic you can read.

The two halves of the model:

* **Buying** — a token profile priced against a published rate card. Linear in
  the number of developers, so cost per developer is a constant.
* **Building** — nodes with a fixed monthly cost each, serving a bounded number
  of developers, plus a platform team whose cost does not scale down. Cost per
  developer falls with scale and converges on a floor: the *marginal* cost of
  one more developer, which is one node's monthly cost divided by the number of
  developers a node actually serves.

That floor is the whole argument. If the marginal cost per developer exceeds the
API price, no amount of scale closes the gap — see
docs/adr/0001-what-self-hosting-competes-with.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .errors import ScenarioError

# Hours in an average month: 8760 / 12. Used to turn a node's power draw into a
# monthly energy bill. A calendar month is not 730 hours; an average one is, and
# amortisation is monthly.
HOURS_PER_MONTH = 730.0


# ---------------------------------------------------------------------------
# Demand side: what one developer consumes in a month
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenProfile:
    """Token consumption for one developer over one month.

    ``input_mtok`` and ``output_mtok`` are millions of tokens. ``cache_hit_ratio``
    is the fraction of input tokens served from a prompt cache rather than
    processed fresh.

    All three are assumptions. Nothing in this repository measured them. They
    are the single most sensitive input in the model, which is why
    ``inference-econ sensitivity`` sweeps them rather than reporting one number.
    """

    name: str
    input_mtok: float
    output_mtok: float
    cache_hit_ratio: float
    description: str = ""

    def __post_init__(self) -> None:
        if self.input_mtok < 0 or self.output_mtok < 0:
            raise ScenarioError(f"profile {self.name!r}: token volumes must be non-negative")
        if not 0.0 <= self.cache_hit_ratio <= 1.0:
            raise ScenarioError(f"profile {self.name!r}: cache_hit_ratio must be in [0, 1]")

    @property
    def fresh_input_mtok(self) -> float:
        """Input tokens that must actually be processed, in millions."""
        return self.input_mtok * (1.0 - self.cache_hit_ratio)

    @property
    def cached_input_mtok(self) -> float:
        """Input tokens served from cache, in millions."""
        return self.input_mtok * self.cache_hit_ratio


# ---------------------------------------------------------------------------
# Buy side: a published rate card
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenWeights:
    """Whether a model's weights can be downloaded, and under what terms.

    ``available`` is false for API-only models. A route whose weights are not
    available cannot be self-hosted at any price, which makes the whole
    build-vs-buy question moot for it — a fact worth establishing before pricing
    anything. See docs/adr/0004-open-weights-licensing.md.
    """

    available: bool
    license: str | None = None
    license_url: str | None = None


@dataclass(frozen=True)
class Benchmark:
    """A single dated benchmark score with a citation.

    Deliberately not used by any calculation in this module. It is here so that
    a quality claim made alongside a cost claim carries a source and a date
    instead of a recollection.
    """

    name: str
    score: float
    as_of: date
    source_url: str
    notes: str = ""


@dataclass(frozen=True)
class ModelPrice:
    """Published list prices for one route, per million tokens, in USD.

    ``cached_input_per_mtok`` of ``None`` means no cached rate was verified, and
    cache hits bill at the full input rate. ``batch_discount`` of ``None`` means
    no batch discount was verified, and batch traffic gets none. Both defaults
    are pessimistic on purpose: an unverified discount is not a discount, and a
    model that quietly assumed one would flatter every route whose rate card
    nobody read carefully.
    """

    model_id: str
    display_name: str
    provider: str
    tier: str
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float | None = None
    batch_discount: float | None = None
    source_url: str = ""
    as_of: date | None = None
    promotional: bool = False
    context_window_tokens: int | None = None
    open_weights: OpenWeights = field(default_factory=lambda: OpenWeights(available=False))
    benchmark: Benchmark | None = None
    notes: str = ""

    @property
    def effective_cached_rate(self) -> float:
        """The rate actually charged for a cache hit, falling back to full input price."""
        if self.cached_input_per_mtok is None:
            return self.input_per_mtok
        return self.cached_input_per_mtok


def api_cost_per_developer_month(
    profile: TokenProfile,
    price: ModelPrice,
    batch_fraction: float = 0.0,
) -> float:
    """Monthly API spend for one developer on ``profile`` at ``price``.

    ``batch_fraction`` is the share of traffic routed through an asynchronous
    batch endpoint. The discount is applied to the whole cost of that share,
    input and output alike — a simplification, since batch and caching interact
    in ways that vary by vendor. It is listed under "what this does not model"
    in the README rather than hidden here.
    """
    if not 0.0 <= batch_fraction <= 1.0:
        raise ScenarioError("batch_fraction must be in [0, 1]")

    cost = (
        profile.fresh_input_mtok * price.input_per_mtok
        + profile.cached_input_mtok * price.effective_cached_rate
        + profile.output_mtok * price.output_per_mtok
    )

    if batch_fraction > 0.0 and price.batch_discount:
        cost *= 1.0 - batch_fraction * price.batch_discount

    return cost


# ---------------------------------------------------------------------------
# Build side: nodes, power, hosting, people
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeSpec:
    """One inference node, and what it costs to own and run for a month.

    ``devs_per_node`` is the node's *nameplate* capacity: the number of
    developers it serves when saturated, at ``reference_profile``. It is an
    assumption, not a measurement, and it is the second of the two parameters
    the sensitivity analysis sweeps.

    ``prefill_weight`` is how much a fresh input token costs the server relative
    to an output token. Decode dominates: generating a token requires a full
    forward pass with no batching across positions, whereas prefill processes
    the prompt in parallel, and a cache hit costs the server close to nothing at
    all. The default of 0.05 says a fresh input token is worth about a twentieth
    of an output token in serving capacity. It is a modelling choice, stated so
    it can be argued with, and it only affects how capacity is re-scaled when
    you price a profile other than the reference one.
    """

    name: str
    capex_usd: float
    amortisation_months: int
    power_kw: float
    pue: float
    power_price_per_kwh: float
    colocation_per_node_month: float
    devs_per_node: float
    reference_profile: TokenProfile
    prefill_weight: float = 0.05

    def __post_init__(self) -> None:
        if self.capex_usd < 0:
            raise ScenarioError("capex_usd must be non-negative")
        if self.amortisation_months <= 0:
            raise ScenarioError("amortisation_months must be positive")
        if self.power_kw < 0 or self.power_price_per_kwh < 0:
            raise ScenarioError("power figures must be non-negative")
        if self.pue < 1.0:
            raise ScenarioError("pue must be at least 1.0")
        if self.colocation_per_node_month < 0:
            raise ScenarioError("colocation_per_node_month must be non-negative")
        if self.devs_per_node <= 0:
            raise ScenarioError("devs_per_node must be positive")
        if self.prefill_weight < 0:
            raise ScenarioError("prefill_weight must be non-negative")


@dataclass(frozen=True)
class PlatformSpec:
    """The people. A fixed monthly cost that does not scale down with usage.

    Modelled flat rather than as a step function. Real platform headcount is a
    staircase — one engineer cannot carry on-call alone, and the third node does
    not need a third engineer. Flat keeps the arithmetic legible; raise ``fte``
    yourself as you add nodes, and note that doing so moves the break-even
    further out, never nearer.
    """

    fte: float
    loaded_cost_per_fte_month: float

    def __post_init__(self) -> None:
        if self.fte < 0:
            raise ScenarioError("fte must be non-negative")
        if self.loaded_cost_per_fte_month < 0:
            raise ScenarioError("loaded_cost_per_fte_month must be non-negative")

    @property
    def monthly_cost(self) -> float:
        return self.fte * self.loaded_cost_per_fte_month


@dataclass(frozen=True)
class SelfHostScenario:
    """A complete self-hosting configuration.

    ``utilisation`` is the fraction of nameplate node capacity you actually
    realise. It is not a spare-capacity fudge factor: developer demand is
    concentrated in working hours across a narrow band of time zones, and a node
    sized for the average is saturated at the peak. Serving a latency target
    means leaving headroom, and headroom is capacity you paid for and do not
    use.

    ``redundancy_nodes`` are nodes that carry full cost and contribute no
    capacity. One is the minimum for a service anyone is expected to depend on.
    """

    node: NodeSpec
    platform: PlatformSpec
    utilisation: float
    redundancy_nodes: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.utilisation <= 1.0:
            raise ScenarioError("utilisation must be in [0, 1]")
        if self.redundancy_nodes < 0:
            raise ScenarioError("redundancy_nodes must be non-negative")


def serving_weight(profile: TokenProfile, prefill_weight: float) -> float:
    """Relative serving cost of one developer-month on ``profile``.

    Cached input contributes nothing: a prefix cache hit skips the forward pass
    on the server just as it skips the bill on an API. Fresh input contributes
    ``prefill_weight`` per token relative to output.
    """
    weight = profile.fresh_input_mtok * prefill_weight + profile.output_mtok
    if weight <= 0:
        raise ScenarioError(
            f"profile {profile.name!r} consumes no serving capacity "
            "(no output tokens and no fresh input); node capacity is undefined for it"
        )
    return weight


def node_monthly_cost(node: NodeSpec) -> float:
    """Amortised capital plus energy plus hosting, for one node, for one month."""
    amortisation = node.capex_usd / node.amortisation_months
    energy = node.power_kw * node.pue * HOURS_PER_MONTH * node.power_price_per_kwh
    return amortisation + energy + node.colocation_per_node_month


def effective_devs_per_node(scenario: SelfHostScenario, profile: TokenProfile) -> float:
    """Developers one node actually serves on ``profile``.

    Nameplate capacity, scaled down by utilisation, then re-scaled for a profile
    heavier or lighter than the node's reference profile. Returns ``0.0`` when
    utilisation is zero — a node you never use serves nobody.
    """
    node = scenario.node
    reference = serving_weight(node.reference_profile, node.prefill_weight)
    requested = serving_weight(profile, node.prefill_weight)
    return node.devs_per_node * scenario.utilisation * (reference / requested)


def marginal_cost_per_developer(scenario: SelfHostScenario, profile: TokenProfile) -> float:
    """The floor: what one more developer costs once the platform team is paid for.

    This is the number that decides whether a break-even exists at all. Scale
    dilutes the fixed costs but cannot go below this, so if it already exceeds
    the API price, there is no developer count at which self-hosting wins.

    Returns infinity at zero utilisation, which is the correct answer rather
    than an error: the cost is real and the capacity is zero.
    """
    effective = effective_devs_per_node(scenario, profile)
    if effective <= 0:
        return math.inf
    return node_monthly_cost(scenario.node) / effective


def nodes_required(scenario: SelfHostScenario, profile: TokenProfile, developers: int) -> int:
    """Serving nodes plus redundancy nodes for ``developers`` on ``profile``."""
    if developers < 0:
        raise ScenarioError("developers must be non-negative")
    effective = effective_devs_per_node(scenario, profile)
    if effective <= 0:
        raise ScenarioError(
            "node capacity is zero at this utilisation; the developer count is unservable"
        )
    return math.ceil(developers / effective) + scenario.redundancy_nodes


def self_host_monthly_cost(
    scenario: SelfHostScenario, profile: TokenProfile, developers: int
) -> float:
    """Total monthly cost of the self-hosted platform serving ``developers``."""
    nodes = nodes_required(scenario, profile, developers)
    return nodes * node_monthly_cost(scenario.node) + scenario.platform.monthly_cost


def self_host_cost_per_developer(
    scenario: SelfHostScenario, profile: TokenProfile, developers: int
) -> float:
    """Monthly self-hosting cost divided by head count.

    Infinite for zero developers (a real cost divided by nobody) and for zero
    utilisation (a real cost divided by no capacity). Both are returned rather
    than raised, so a curve can be plotted through them.
    """
    if developers <= 0:
        return math.inf
    if effective_devs_per_node(scenario, profile) <= 0:
        return math.inf
    return self_host_monthly_cost(scenario, profile, developers) / developers
