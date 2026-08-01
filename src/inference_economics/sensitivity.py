"""Sensitivity over the two parameters that decide the answer.

The conclusion of this model is sensitive to exactly two inputs, and neither of
them is a price:

1. **The token profile.** How many tokens a developer actually consumes in a
   month, and what fraction of the input is a cache hit.
2. **Developers per node.** How many people one node serves at an acceptable
   latency.

Both are assumptions. Neither was measured here. A single-scenario answer to a
build-vs-buy question that hinges on two unmeasured parameters is a number
dressed up as a finding, so this module produces a grid instead: every
combination, and where in that grid the conclusion flips.

Reading the grid is the deliverable. If the cells you consider plausible all say
one thing, you have an answer. If the flip sits inside your uncertainty band,
you do not have an answer yet — you have a measurement to go and take.
"""

from __future__ import annotations

from dataclasses import dataclass

from .breakeven import find_break_even
from .model import (
    ModelPrice,
    SelfHostScenario,
    TokenProfile,
    api_cost_per_developer_month,
    marginal_cost_per_developer,
)
from .scenario import with_devs_per_node

# The default sweep. Spans an order of magnitude, because the honest uncertainty
# on developers-per-node is close to that wide.
DEFAULT_DEVS_PER_NODE_SWEEP: tuple[float, ...] = (20.0, 30.0, 40.0, 60.0, 80.0, 120.0)


@dataclass(frozen=True)
class SensitivityCell:
    """One (profile, devs-per-node) combination."""

    profile: TokenProfile
    devs_per_node: float
    api_cost_per_developer: float
    marginal_self_host_cost_per_developer: float
    break_even_developers: int | None

    @property
    def self_host_ever_wins(self) -> bool:
        return self.break_even_developers is not None


@dataclass(frozen=True)
class SensitivityGrid:
    """The full sweep against one comparator model."""

    price: ModelPrice
    profiles: tuple[TokenProfile, ...]
    devs_per_node_values: tuple[float, ...]
    cells: tuple[SensitivityCell, ...]

    def cell(self, profile_name: str, devs_per_node: float) -> SensitivityCell:
        for candidate in self.cells:
            if candidate.profile.name == profile_name and candidate.devs_per_node == devs_per_node:
                return candidate
        raise KeyError(f"no cell for profile {profile_name!r} at {devs_per_node} devs/node")

    @property
    def flips(self) -> bool:
        """True when the conclusion is not the same across the whole grid.

        The single most useful property of the sweep. If this is true, the
        headline is an artefact of where you happened to set two assumptions.
        """
        verdicts = {cell.self_host_ever_wins for cell in self.cells}
        return len(verdicts) > 1


def sweep(
    scenario: SelfHostScenario,
    profiles: tuple[TokenProfile, ...],
    price: ModelPrice,
    devs_per_node_values: tuple[float, ...] = DEFAULT_DEVS_PER_NODE_SWEEP,
    batch_fraction: float = 0.0,
) -> SensitivityGrid:
    """Evaluate every (profile, devs-per-node) combination against ``price``."""
    if not profiles:
        raise ValueError("at least one profile is required")
    if not devs_per_node_values:
        raise ValueError("at least one devs-per-node value is required")

    cells: list[SensitivityCell] = []
    for devs in devs_per_node_values:
        variant = with_devs_per_node(scenario, devs)
        for profile in profiles:
            result = find_break_even(variant, profile, price, batch_fraction=batch_fraction)
            cells.append(
                SensitivityCell(
                    profile=profile,
                    devs_per_node=devs,
                    api_cost_per_developer=api_cost_per_developer_month(
                        profile, price, batch_fraction=batch_fraction
                    ),
                    marginal_self_host_cost_per_developer=marginal_cost_per_developer(
                        variant, profile
                    ),
                    break_even_developers=result.developers,
                )
            )

    return SensitivityGrid(
        price=price,
        profiles=tuple(profiles),
        devs_per_node_values=tuple(devs_per_node_values),
        cells=tuple(cells),
    )
