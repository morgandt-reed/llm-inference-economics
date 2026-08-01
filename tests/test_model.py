"""The cost arithmetic.

Expected values are computed by hand in the test, not copied from a run of the
code. A test that asserts the code returns what the code returned is a
regression test with no opinion about correctness.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from inference_economics.errors import ScenarioError
from inference_economics.model import (
    HOURS_PER_MONTH,
    ModelPrice,
    OpenWeights,
    PlatformSpec,
    TokenProfile,
    api_cost_per_developer_month,
    effective_devs_per_node,
    marginal_cost_per_developer,
    node_monthly_cost,
    nodes_required,
    self_host_cost_per_developer,
    self_host_monthly_cost,
    serving_weight,
)
from inference_economics.profiles import INTENSIVE, LIGHT, MEDIUM


class TestTokenProfile:
    def test_splits_input_by_cache_hit_ratio(self, simple_profile):
        assert simple_profile.fresh_input_mtok == pytest.approx(50.0)
        assert simple_profile.cached_input_mtok == pytest.approx(50.0)

    @pytest.mark.parametrize("ratio", [-0.01, 1.01])
    def test_rejects_cache_ratio_outside_unit_interval(self, ratio):
        with pytest.raises(ScenarioError, match="cache_hit_ratio"):
            TokenProfile(name="bad", input_mtok=1.0, output_mtok=1.0, cache_hit_ratio=ratio)

    def test_rejects_negative_token_volumes(self):
        with pytest.raises(ScenarioError, match="non-negative"):
            TokenProfile(name="bad", input_mtok=-1.0, output_mtok=1.0, cache_hit_ratio=0.5)


class TestApiCost:
    def test_matches_hand_computed_value(self, simple_profile, simple_price):
        # 50 Mtok fresh x $1 + 50 Mtok cached x $0.10 + 10 Mtok out x $10
        # = 50 + 5 + 100 = 155
        assert api_cost_per_developer_month(simple_profile, simple_price) == pytest.approx(155.0)

    def test_absent_cached_rate_bills_at_full_input_price(self, simple_profile, simple_price):
        no_cache = replace(simple_price, cached_input_per_mtok=None)
        # 50 x $1 + 50 x $1 + 10 x $10 = 200
        assert api_cost_per_developer_month(simple_profile, no_cache) == pytest.approx(200.0)

    def test_batch_discount_applies_only_to_the_batched_share(self, simple_profile, simple_price):
        # Half the traffic at 50% off: 155 x (1 - 0.5 x 0.5) = 155 x 0.75
        cost = api_cost_per_developer_month(simple_profile, simple_price, batch_fraction=0.5)
        assert cost == pytest.approx(116.25)

    def test_absent_batch_discount_changes_nothing(self, simple_profile, simple_price):
        no_batch = replace(simple_price, batch_discount=None)
        full = api_cost_per_developer_month(simple_profile, no_batch, batch_fraction=1.0)
        assert full == pytest.approx(api_cost_per_developer_month(simple_profile, no_batch))

    @pytest.mark.parametrize("fraction", [-0.1, 1.1])
    def test_rejects_batch_fraction_outside_unit_interval(
        self, simple_profile, simple_price, fraction
    ):
        with pytest.raises(ScenarioError, match="batch_fraction"):
            api_cost_per_developer_month(simple_profile, simple_price, batch_fraction=fraction)

    def test_cost_rises_with_output_price(self, simple_profile, simple_price):
        dearer = replace(simple_price, output_per_mtok=simple_price.output_per_mtok * 2)
        assert api_cost_per_developer_month(simple_profile, dearer) > api_cost_per_developer_month(
            simple_profile, simple_price
        )


class TestNodeCost:
    def test_sums_amortisation_energy_and_hosting(self, scenario):
        node = scenario.node
        expected = (
            node.capex_usd / node.amortisation_months
            + node.power_kw * node.pue * HOURS_PER_MONTH * node.power_price_per_kwh
            + node.colocation_per_node_month
        )
        assert node_monthly_cost(node) == pytest.approx(expected)

    def test_shorter_amortisation_costs_more_per_month(self, scenario):
        faster = replace(scenario.node, amortisation_months=24)
        assert node_monthly_cost(faster) > node_monthly_cost(scenario.node)

    @pytest.mark.parametrize(
        ("field", "value", "match"),
        [
            ("capex_usd", -1.0, "capex"),
            ("amortisation_months", 0, "amortisation"),
            ("pue", 0.9, "pue"),
            ("devs_per_node", 0.0, "devs_per_node"),
            ("power_kw", -1.0, "power"),
            ("colocation_per_node_month", -1.0, "colocation"),
            ("prefill_weight", -0.1, "prefill_weight"),
        ],
    )
    def test_rejects_out_of_range_parameters(self, scenario, field, value, match):
        with pytest.raises(ScenarioError, match=match):
            replace(scenario.node, **{field: value})


class TestCapacity:
    def test_reference_profile_gets_nameplate_capacity_times_utilisation(self, scenario):
        expected = scenario.node.devs_per_node * scenario.utilisation
        assert effective_devs_per_node(scenario, INTENSIVE) == pytest.approx(expected)

    def test_lighter_profiles_fit_more_developers_per_node(self, scenario):
        light = effective_devs_per_node(scenario, LIGHT)
        medium = effective_devs_per_node(scenario, MEDIUM)
        intensive = effective_devs_per_node(scenario, INTENSIVE)
        assert light > medium > intensive

    def test_serving_weight_ignores_cached_input(self):
        base = TokenProfile(name="a", input_mtok=100.0, output_mtok=10.0, cache_hit_ratio=0.0)
        cached = TokenProfile(name="b", input_mtok=100.0, output_mtok=10.0, cache_hit_ratio=1.0)
        assert serving_weight(cached, 0.05) < serving_weight(base, 0.05)
        # With every input token cached, only output tokens consume capacity.
        assert serving_weight(cached, 0.05) == pytest.approx(10.0)

    def test_profile_consuming_no_capacity_is_rejected(self):
        empty = TokenProfile(name="empty", input_mtok=10.0, output_mtok=0.0, cache_hit_ratio=1.0)
        with pytest.raises(ScenarioError, match="no serving capacity"):
            serving_weight(empty, 0.05)


class TestSelfHostCost:
    def test_marginal_cost_is_node_cost_over_effective_capacity(self, scenario):
        expected = node_monthly_cost(scenario.node) / effective_devs_per_node(scenario, INTENSIVE)
        assert marginal_cost_per_developer(scenario, INTENSIVE) == pytest.approx(expected)

    def test_zero_utilisation_gives_infinite_cost_per_developer(self, scenario):
        idle = replace(scenario, utilisation=0.0)
        assert marginal_cost_per_developer(idle, INTENSIVE) == math.inf
        assert self_host_cost_per_developer(idle, INTENSIVE, 100) == math.inf

    def test_zero_utilisation_makes_any_head_count_unservable(self, scenario):
        idle = replace(scenario, utilisation=0.0)
        with pytest.raises(ScenarioError, match="unservable"):
            nodes_required(idle, INTENSIVE, 100)

    def test_zero_developers_gives_infinite_cost_per_developer(self, scenario):
        assert self_host_cost_per_developer(scenario, INTENSIVE, 0) == math.inf

    def test_nodes_are_a_step_function_of_head_count(self, scenario):
        effective = effective_devs_per_node(scenario, INTENSIVE)  # 24.0 by default
        at_capacity = int(effective)
        assert nodes_required(scenario, INTENSIVE, at_capacity) == 1 + scenario.redundancy_nodes
        assert nodes_required(scenario, INTENSIVE, at_capacity + 1) == 2 + scenario.redundancy_nodes

    def test_redundant_nodes_cost_money_and_add_no_capacity(self, scenario):
        no_spare = replace(scenario, redundancy_nodes=0)
        assert nodes_required(no_spare, INTENSIVE, 100) + 1 == nodes_required(
            scenario, INTENSIVE, 100
        )
        assert self_host_monthly_cost(scenario, INTENSIVE, 100) - self_host_monthly_cost(
            no_spare, INTENSIVE, 100
        ) == pytest.approx(node_monthly_cost(scenario.node))

    def test_cost_per_developer_converges_downward_on_the_marginal_cost(self, scenario):
        marginal = marginal_cost_per_developer(scenario, INTENSIVE)
        small = self_host_cost_per_developer(scenario, INTENSIVE, 100)
        large = self_host_cost_per_developer(scenario, INTENSIVE, 100_000)
        assert small > large > marginal
        assert large == pytest.approx(marginal, rel=0.05)

    def test_cost_per_developer_never_falls_below_the_marginal_cost(self, scenario):
        marginal = marginal_cost_per_developer(scenario, INTENSIVE)
        for developers in range(1, 2_000, 7):
            assert self_host_cost_per_developer(scenario, INTENSIVE, developers) >= marginal

    def test_negative_head_count_is_rejected(self, scenario):
        with pytest.raises(ScenarioError, match="non-negative"):
            nodes_required(scenario, INTENSIVE, -1)


class TestScenarioValidation:
    @pytest.mark.parametrize("utilisation", [-0.1, 1.1])
    def test_rejects_utilisation_outside_unit_interval(self, scenario, utilisation):
        with pytest.raises(ScenarioError, match="utilisation"):
            replace(scenario, utilisation=utilisation)

    def test_rejects_negative_redundancy(self, scenario):
        with pytest.raises(ScenarioError, match="redundancy"):
            replace(scenario, redundancy_nodes=-1)

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"fte": -1.0, "loaded_cost_per_fte_month": 1.0}, "fte"),
            ({"fte": 1.0, "loaded_cost_per_fte_month": -1.0}, "loaded_cost"),
        ],
    )
    def test_rejects_negative_platform_costs(self, kwargs, match):
        with pytest.raises(ScenarioError, match=match):
            PlatformSpec(**kwargs)

    def test_platform_monthly_cost_multiplies_out(self):
        assert PlatformSpec(fte=2.5, loaded_cost_per_fte_month=10_000.0).monthly_cost == 25_000.0


class TestModelPriceDefaults:
    def test_defaults_to_not_self_hostable(self):
        price = ModelPrice(
            model_id="x",
            display_name="X",
            provider="P",
            tier="first-party",
            input_per_mtok=1.0,
            output_per_mtok=1.0,
        )
        assert price.open_weights == OpenWeights(available=False)
        assert price.effective_cached_rate == 1.0
