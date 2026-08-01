"""The sensitivity sweep.

The property worth asserting is that the grid can detect a flip, because the
flip is the finding. A sweep that always agreed with itself would be decoration.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from inference_economics.model import ModelPrice, OpenWeights
from inference_economics.profiles import INTENSIVE, LIGHT, MEDIUM
from inference_economics.sensitivity import DEFAULT_DEVS_PER_NODE_SWEEP, sweep

ALL_PROFILES = (LIGHT, MEDIUM, INTENSIVE)


@pytest.fixture
def open_model_price() -> ModelPrice:
    return ModelPrice(
        model_id="open",
        display_name="Open Model",
        provider="Test",
        tier="first-party",
        input_per_mtok=1.40,
        output_per_mtok=4.40,
        cached_input_per_mtok=0.26,
        open_weights=OpenWeights(available=True, license="MIT", license_url="https://example.org"),
    )


def test_grid_covers_every_combination(scenario, open_model_price):
    grid = sweep(scenario, ALL_PROFILES, open_model_price)
    assert len(grid.cells) == len(ALL_PROFILES) * len(DEFAULT_DEVS_PER_NODE_SWEEP)


def test_cell_lookup_returns_the_matching_combination(scenario, open_model_price):
    grid = sweep(scenario, ALL_PROFILES, open_model_price, devs_per_node_values=(40.0, 80.0))
    cell = grid.cell("medium", 80.0)
    assert cell.profile is MEDIUM
    assert cell.devs_per_node == 80.0


def test_cell_lookup_raises_for_a_combination_not_swept(scenario, open_model_price):
    grid = sweep(scenario, ALL_PROFILES, open_model_price, devs_per_node_values=(40.0,))
    with pytest.raises(KeyError, match="no cell"):
        grid.cell("medium", 999.0)


def test_marginal_cost_falls_as_node_capacity_rises(scenario, open_model_price):
    grid = sweep(scenario, (INTENSIVE,), open_model_price, devs_per_node_values=(20.0, 40.0, 80.0))
    costs = [
        grid.cell("intensive", devs).marginal_self_host_cost_per_developer
        for devs in (20.0, 40.0, 80.0)
    ]
    assert costs[0] > costs[1] > costs[2]


def test_api_cost_does_not_depend_on_node_capacity(scenario, open_model_price):
    grid = sweep(scenario, (INTENSIVE,), open_model_price, devs_per_node_values=(20.0, 120.0))
    assert grid.cell("intensive", 20.0).api_cost_per_developer == pytest.approx(
        grid.cell("intensive", 120.0).api_cost_per_developer
    )


def test_the_default_sweep_detects_a_flip_against_an_open_models_own_api(
    scenario, open_model_price
):
    """The headline result: whether self-hosting ever wins is not settled here."""
    grid = sweep(scenario, ALL_PROFILES, open_model_price)
    assert grid.flips


def test_a_sweep_can_hold_a_single_verdict(scenario, open_model_price):
    """A narrow sweep well below any crossover agrees with itself."""
    grid = sweep(scenario, ALL_PROFILES, open_model_price, devs_per_node_values=(20.0, 25.0))
    assert not grid.flips
    assert not any(cell.self_host_ever_wins for cell in grid.cells)


def test_a_dear_enough_comparator_makes_self_hosting_win_everywhere(scenario, open_model_price):
    dear = replace(
        open_model_price,
        input_per_mtok=50.0,
        output_per_mtok=250.0,
        cached_input_per_mtok=5.0,
    )
    grid = sweep(scenario, ALL_PROFILES, dear)
    assert not grid.flips
    assert all(cell.self_host_ever_wins for cell in grid.cells)


def test_empty_inputs_are_rejected(scenario, open_model_price):
    with pytest.raises(ValueError, match="at least one profile"):
        sweep(scenario, (), open_model_price)
    with pytest.raises(ValueError, match="at least one devs-per-node"):
        sweep(scenario, ALL_PROFILES, open_model_price, devs_per_node_values=())
