"""Break-even between self-hosting and buying an API.

The question is: at what head count does self-hosting first become, and *stay*,
cheaper per developer than the API?

"And stay" is not pedantry. Self-hosted cost per developer is a sawtooth, not a
smooth curve: it falls as a node fills up and jumps the moment you add the next
one. Reporting the first head count that happens to sit in a trough would be
reporting a number that stops being true fifteen developers later. So a
break-even here means: from this head count onward, self-hosting is never again
more expensive.

That definition has a convenient consequence. Cost per developer is at its worst
at the *start* of each node band — one developer past the point where you bought
another node. Those band-start points are the local maxima, and their cost is
monotone in the band index, so finding the first band whose worst point beats
the API price finds the answer exactly. No scanning, no tolerance, no guessing
at an upper bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import (
    ModelPrice,
    SelfHostScenario,
    TokenProfile,
    api_cost_per_developer_month,
    effective_devs_per_node,
    marginal_cost_per_developer,
    self_host_cost_per_developer,
)

# A ceiling on the band search. If the crossover has not been found by the
# hundred-thousandth node, the answer that matters is "not at any head count you
# are going to have", and a number would be false precision.
_MAX_BANDS = 100_000


@dataclass(frozen=True)
class BreakEven:
    """The result of a break-even query.

    ``developers`` is ``None`` when no break-even exists — which is a real
    answer, not a failure, and is the answer the default scenario gives against
    an open model's own API.
    """

    developers: int | None
    api_cost_per_developer: float
    marginal_self_host_cost_per_developer: float
    self_host_cost_at_breakeven: float | None
    comparator_is_self_hostable: bool
    reason: str

    @property
    def exists(self) -> bool:
        return self.developers is not None

    @property
    def is_rigged_comparison(self) -> bool:
        """True when a break-even was found against a model you cannot self-host.

        The arithmetic is real; the comparison is not. A break-even against an
        API-only model says "our own hardware running some other model would be
        cheaper than this vendor" — which is a statement about two different
        products, priced as though it were one. This flag exists so the
        renderer can print the number and the warning together, rather than
        suppressing the number and losing the teaching moment.
        """
        return self.exists and not self.comparator_is_self_hostable


def band_start(effective_capacity: float, band: int) -> int:
    """The smallest head count served by ``band`` nodes.

    Band 1 starts at one developer. Band *k* starts one developer past the
    capacity of *k-1* nodes — the point where cost per developer is worst,
    because a whole node was just added for a single extra person.
    """
    if band < 1:
        raise ValueError("band index starts at 1")
    if band == 1:
        return 1
    return math.floor((band - 1) * effective_capacity) + 1


def find_break_even(
    scenario: SelfHostScenario,
    profile: TokenProfile,
    price: ModelPrice,
    batch_fraction: float = 0.0,
) -> BreakEven:
    """Smallest head count from which self-hosting is never again more expensive."""
    api = api_cost_per_developer_month(profile, price, batch_fraction=batch_fraction)
    marginal = marginal_cost_per_developer(scenario, profile)
    hostable = price.open_weights.available

    # The arithmetic runs whether or not the comparator's weights are downloadable.
    # Refusing to compute it for an API-only model would hide the result this
    # repository most wants to show: that a break-even against a frontier API
    # exists, is arithmetically correct, and is still the wrong comparison. The
    # warning belongs next to the number, not instead of it.
    if marginal >= api:
        return BreakEven(
            developers=None,
            api_cost_per_developer=api,
            marginal_self_host_cost_per_developer=marginal,
            self_host_cost_at_breakeven=None,
            comparator_is_self_hostable=hostable,
            reason=(
                f"marginal cost per developer (${marginal:,.2f}) is at or above the API "
                f"price (${api:,.2f}); scale dilutes fixed costs but cannot go below the "
                "marginal cost, so no head count closes the gap"
            ),
        )

    effective = effective_devs_per_node(scenario, profile)
    for band in range(1, _MAX_BANDS + 1):
        head_count = band_start(effective, band)
        cost = self_host_cost_per_developer(scenario, profile, head_count)
        if cost <= api:
            return BreakEven(
                developers=head_count,
                api_cost_per_developer=api,
                marginal_self_host_cost_per_developer=marginal,
                self_host_cost_at_breakeven=cost,
                comparator_is_self_hostable=hostable,
                reason=(
                    f"from {head_count:,} developers onward, self-hosting costs "
                    f"${cost:,.2f} per developer-month against ${api:,.2f} on the API"
                ),
            )

    return BreakEven(
        developers=None,
        api_cost_per_developer=api,
        marginal_self_host_cost_per_developer=marginal,
        self_host_cost_at_breakeven=None,
        comparator_is_self_hostable=hostable,
        reason=(
            f"no break-even below {_MAX_BANDS:,} nodes; the fixed costs are too large "
            "relative to the gap for any realistic head count to absorb them"
        ),
    )
