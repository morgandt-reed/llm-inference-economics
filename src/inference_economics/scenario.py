"""The default self-hosting scenario, and where each of its numbers came from.

Two kinds of number live here, and the difference is the point:

**Public, cited.** The node capital cost and the GPU power draw are drawn from
published sources, recorded below with a URL and a date. They still move, and
the hardware one is a market survey rather than a manufacturer's list price —
NVIDIA does not publish one for this part.

**Input parameters with a default you are told to change.** Electricity tariff,
colocation, loaded engineer cost, utilisation, and above all developers-per-node
are site- and organisation-specific. The defaults are plausible planning
figures, chosen so the model runs out of the box. They are not findings. Every
one of them is exposed as a CLI flag, and the two that dominate the result are
swept by ``inference-econ sensitivity``.

Nothing here was measured by this repository.
"""

from __future__ import annotations

from dataclasses import replace

from .model import NodeSpec, PlatformSpec, SelfHostScenario, TokenProfile
from .profiles import INTENSIVE

# --- Public, cited -----------------------------------------------------------

# An 8-GPU HGX H200 system, integrated, from a major OEM. Market surveys in 2026
# put the range at roughly $320,000-$420,000 with ~$370,000 typical; the spread
# across OEM quotes for comparable configurations runs to about 25%, and volume
# orders come in below list. NVIDIA publishes no reference price for this part,
# so this is a survey of what buyers report paying, not a rate card.
#   https://www.mercatus-ai.com/blog/h200-server-price  (read 2026-08-01)
DEFAULT_NODE_CAPEX_USD = 370_000.0

# Eight H200 SXM modules at their 700 W published TDP is 5.6 kW; the host
# platform, NVLink fabric, networking and fans add roughly 4-5 kW at load. 10.2
# kW is a planning figure for the whole node at sustained load, not a measured
# draw of any particular chassis.
DEFAULT_NODE_POWER_KW = 10.2

# --- Input parameters: defaults you are expected to replace ------------------

# Three years. Long enough to be the usual finance answer, short enough that the
# hardware is still competitive at the end of it. Shorten it and the marginal
# cost rises; lengthen it and you are betting that a 2026 accelerator is still
# worth running in 2031.
DEFAULT_AMORTISATION_MONTHS = 36

# Datacentre power usage effectiveness. 1.4 is unremarkable for a conventional
# air-cooled facility. A modern liquid-cooled build does better; a retrofitted
# comms room does considerably worse.
DEFAULT_PUE = 1.4

# USD per kWh, all-in. Industrial tariffs vary by more than a factor of three
# across jurisdictions, and this is one of the largest single swings available
# in the whole model. Set it from your own bill.
DEFAULT_POWER_PRICE_PER_KWH = 0.12

# Rack space, cross-connects, remote hands, and the share of facility overhead a
# single high-density node attracts. Quote it; do not inherit this number.
DEFAULT_COLOCATION_PER_NODE_MONTH = 1_200.0

# Nameplate developers per node at the intensive profile. THE dominant
# assumption in the model, and the one with the widest honest uncertainty band:
# it depends on batching strategy, quantisation, speculative decoding, context
# length and the latency you are willing to serve. Treat the single number as a
# placeholder and read the sensitivity grid instead.
DEFAULT_DEVS_PER_NODE = 40.0

# Fraction of nameplate capacity actually realised. Demand is concentrated in
# working hours; a node sized for the daily average is saturated at 3pm. 0.6
# assumes a reasonably wide time-zone spread and some tolerance for queueing.
DEFAULT_UTILISATION = 0.60

# Serving, capacity planning, quantisation and tuning work, observability, and
# an on-call rotation that does not consist of one person. Two is a floor for
# something other people depend on, not a target.
DEFAULT_PLATFORM_FTE = 2.0

# Fully loaded monthly cost per engineer — salary, employer contributions,
# equipment, and the share of overhead an engineer attracts. Varies enormously
# by market and by how the finance function defines "loaded".
DEFAULT_LOADED_COST_PER_FTE_MONTH = 15_000.0

# Nodes carrying full cost and contributing no capacity. One is the minimum for
# a service with an availability expectation attached: a single node is a
# single maintenance window away from an outage.
DEFAULT_REDUNDANCY_NODES = 1


def default_node(reference_profile: TokenProfile = INTENSIVE) -> NodeSpec:
    """The default node, with capacity expressed against ``reference_profile``."""
    return NodeSpec(
        name="8x H200 SXM (owned, colocated)",
        capex_usd=DEFAULT_NODE_CAPEX_USD,
        amortisation_months=DEFAULT_AMORTISATION_MONTHS,
        power_kw=DEFAULT_NODE_POWER_KW,
        pue=DEFAULT_PUE,
        power_price_per_kwh=DEFAULT_POWER_PRICE_PER_KWH,
        colocation_per_node_month=DEFAULT_COLOCATION_PER_NODE_MONTH,
        devs_per_node=DEFAULT_DEVS_PER_NODE,
        reference_profile=reference_profile,
    )


def default_platform() -> PlatformSpec:
    return PlatformSpec(
        fte=DEFAULT_PLATFORM_FTE,
        loaded_cost_per_fte_month=DEFAULT_LOADED_COST_PER_FTE_MONTH,
    )


def default_scenario() -> SelfHostScenario:
    """The scenario every command starts from before CLI overrides are applied."""
    return SelfHostScenario(
        node=default_node(),
        platform=default_platform(),
        utilisation=DEFAULT_UTILISATION,
        redundancy_nodes=DEFAULT_REDUNDANCY_NODES,
    )


def with_devs_per_node(scenario: SelfHostScenario, devs_per_node: float) -> SelfHostScenario:
    """Return ``scenario`` with a different nameplate node capacity.

    Used by the sensitivity sweep, which varies this parameter and nothing else.
    """
    return replace(scenario, node=replace(scenario.node, devs_per_node=devs_per_node))
