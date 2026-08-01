"""Break-even behaviour.

Two properties matter more than any single number:

* A reported break-even must **hold**. Cost per developer is a sawtooth, so a
  crossing that reverts fifteen developers later is not a break-even, and a
  model that reported one would be worse than useless in a budget meeting.
* The direction of movement must be right. Nobody is going to verify a
  break-even by hand, but everybody has an intuition about which way it should
  move when the API gets dearer or the hardware gets cheaper. If the model
  violates that intuition, the model is wrong.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from inference_economics.breakeven import band_start, find_break_even
from inference_economics.model import (
    ModelPrice,
    OpenWeights,
    api_cost_per_developer_month,
    effective_devs_per_node,
    self_host_cost_per_developer,
)
from inference_economics.profiles import INTENSIVE
from inference_economics.scenario import with_devs_per_node


@pytest.fixture
def frontier_price() -> ModelPrice:
    """An expensive comparator, so a break-even exists and can be probed."""
    return ModelPrice(
        model_id="expensive",
        display_name="Expensive Model",
        provider="Test",
        tier="first-party",
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cached_input_per_mtok=0.50,
        open_weights=OpenWeights(available=True, license="MIT", license_url="https://example.org"),
    )


@pytest.fixture
def cheap_price() -> ModelPrice:
    """A cheap open model's own API — the correct comparator, and the one that wins."""
    return ModelPrice(
        model_id="cheap",
        display_name="Cheap Open Model",
        provider="Test",
        tier="first-party",
        input_per_mtok=1.40,
        output_per_mtok=4.40,
        cached_input_per_mtok=0.26,
        open_weights=OpenWeights(available=True, license="MIT", license_url="https://example.org"),
    )


class TestBandStart:
    def test_first_band_starts_at_one_developer(self):
        assert band_start(24.0, 1) == 1

    def test_each_band_starts_one_past_the_previous_capacity(self):
        assert band_start(24.0, 2) == 25
        assert band_start(24.0, 3) == 49

    def test_band_index_below_one_is_rejected(self):
        with pytest.raises(ValueError, match="band index"):
            band_start(24.0, 0)


class TestBreakEvenExistence:
    def test_no_break_even_against_the_open_models_own_api(self, scenario, cheap_price):
        result = find_break_even(scenario, INTENSIVE, cheap_price)
        assert not result.exists
        assert result.marginal_self_host_cost_per_developer > result.api_cost_per_developer
        assert "marginal cost" in result.reason

    def test_break_even_exists_against_a_dearer_api(self, scenario, frontier_price):
        result = find_break_even(scenario, INTENSIVE, frontier_price)
        assert result.exists
        assert result.developers > 0

    def test_break_even_is_computed_even_for_api_only_models(self, scenario, frontier_price):
        """The rigged comparison must be computable, so it can be shown and refuted."""
        api_only = replace(frontier_price, open_weights=OpenWeights(available=False))
        result = find_break_even(scenario, INTENSIVE, api_only)
        assert result.exists
        assert result.is_rigged_comparison
        assert not result.comparator_is_self_hostable

    def test_self_hostable_break_even_is_not_flagged_as_rigged(self, scenario, frontier_price):
        result = find_break_even(scenario, INTENSIVE, frontier_price)
        assert result.exists
        assert not result.is_rigged_comparison

    def test_zero_utilisation_never_breaks_even(self, scenario, frontier_price):
        idle = replace(scenario, utilisation=0.0)
        assert not find_break_even(idle, INTENSIVE, frontier_price).exists


class TestBreakEvenHolds:
    def test_self_hosting_is_never_dearer_above_the_break_even(self, scenario, frontier_price):
        result = find_break_even(scenario, INTENSIVE, frontier_price)
        api = result.api_cost_per_developer
        # Walk well past the reported point, crossing many node boundaries.
        for developers in range(result.developers, result.developers + 3_000, 13):
            assert self_host_cost_per_developer(scenario, INTENSIVE, developers) <= api

    def test_the_break_even_is_minimal(self, scenario, frontier_price):
        """Below the reported point there is at least one dearer head count.

        Without this, 'break-even at N' could be satisfied by any sufficiently
        large N and would carry no information.
        """
        result = find_break_even(scenario, INTENSIVE, frontier_price)
        api = result.api_cost_per_developer
        dearer_below = [
            n
            for n in range(1, result.developers)
            if self_host_cost_per_developer(scenario, INTENSIVE, n) > api
        ]
        assert dearer_below

    def test_the_reported_point_lands_on_a_node_boundary(self, scenario, frontier_price):
        """The worst head count in a band is its first, so that is where it can flip."""
        result = find_break_even(scenario, INTENSIVE, frontier_price)
        effective = effective_devs_per_node(scenario, INTENSIVE)
        bands = {band_start(effective, k) for k in range(1, 500)}
        assert result.developers in bands


class TestMonotonicity:
    def test_a_dearer_api_breaks_even_sooner(self, scenario, frontier_price):
        dearer = replace(
            frontier_price,
            input_per_mtok=frontier_price.input_per_mtok * 2,
            output_per_mtok=frontier_price.output_per_mtok * 2,
            cached_input_per_mtok=frontier_price.cached_input_per_mtok * 2,
        )
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        raised = find_break_even(scenario, INTENSIVE, dearer)
        assert raised.developers < base.developers

    def test_dearer_hardware_breaks_even_later(self, scenario, frontier_price):
        pricier = replace(
            scenario, node=replace(scenario.node, capex_usd=scenario.node.capex_usd * 2)
        )
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        raised = find_break_even(pricier, INTENSIVE, frontier_price)
        assert raised.developers > base.developers

    def test_more_developers_per_node_breaks_even_sooner(self, scenario, frontier_price):
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        roomier = find_break_even(
            with_devs_per_node(scenario, scenario.node.devs_per_node * 2),
            INTENSIVE,
            frontier_price,
        )
        assert roomier.developers < base.developers

    def test_a_bigger_platform_team_breaks_even_later(self, scenario, frontier_price):
        bigger = replace(
            scenario, platform=replace(scenario.platform, fte=scenario.platform.fte * 3)
        )
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        raised = find_break_even(bigger, INTENSIVE, frontier_price)
        assert raised.developers > base.developers

    def test_higher_utilisation_breaks_even_sooner(self, scenario, frontier_price):
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        better = find_break_even(replace(scenario, utilisation=1.0), INTENSIVE, frontier_price)
        assert better.developers < base.developers

    def test_more_redundancy_breaks_even_later(self, scenario, frontier_price):
        base = find_break_even(scenario, INTENSIVE, frontier_price)
        safer = find_break_even(replace(scenario, redundancy_nodes=4), INTENSIVE, frontier_price)
        assert safer.developers > base.developers


class TestSearchBound:
    def test_gives_up_rather_than_reporting_an_absurd_head_count(self, scenario, frontier_price):
        """Marginal cost below the API price is necessary but not sufficient.

        With large enough fixed costs the crossover exists arithmetically and
        sits at a head count no organisation will ever have. Reporting that
        number would be false precision, so the search is bounded and says so.
        """
        enormous_team = replace(scenario, platform=replace(scenario.platform, fte=1e12))
        result = find_break_even(enormous_team, INTENSIVE, frontier_price)
        assert not result.exists
        assert result.marginal_self_host_cost_per_developer < result.api_cost_per_developer
        assert "no break-even below" in result.reason


class TestBatchDiscountInteraction:
    def test_batching_lowers_the_api_price_and_delays_the_break_even(self, scenario):
        price = ModelPrice(
            model_id="batchable",
            display_name="Batchable",
            provider="Test",
            tier="first-party",
            input_per_mtok=5.0,
            output_per_mtok=25.0,
            cached_input_per_mtok=0.50,
            batch_discount=0.50,
            open_weights=OpenWeights(
                available=True, license="MIT", license_url="https://example.org"
            ),
        )
        base = find_break_even(scenario, INTENSIVE, price, batch_fraction=0.0)
        batched = find_break_even(scenario, INTENSIVE, price, batch_fraction=1.0)
        assert batched.api_cost_per_developer < base.api_cost_per_developer
        assert batched.api_cost_per_developer == pytest.approx(
            api_cost_per_developer_month(INTENSIVE, price) * 0.5
        )
        # Cheaper API means self-hosting has a lower bar to clear, so break-even
        # moves out — or disappears.
        assert batched.developers is None or batched.developers > base.developers
