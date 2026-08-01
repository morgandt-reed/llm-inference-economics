"""Shared fixtures.

The price file used across the suite is the committed one, not a stub. A test
suite that only ever exercises hand-made fixtures cannot tell you the shipped
data file is valid, and the shipped data file is half of what this repository
publishes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inference_economics.model import ModelPrice, OpenWeights, TokenProfile
from inference_economics.prices import load_price_book
from inference_economics.scenario import default_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
PRICE_FILE = REPO_ROOT / "data" / "prices-2026-07.yaml"


@pytest.fixture
def price_file() -> Path:
    return PRICE_FILE


@pytest.fixture
def book():
    return load_price_book(PRICE_FILE)


@pytest.fixture
def scenario():
    return default_scenario()


@pytest.fixture
def simple_profile() -> TokenProfile:
    """Round numbers, so expected costs can be computed in your head."""
    return TokenProfile(
        name="simple",
        input_mtok=100.0,
        output_mtok=10.0,
        cache_hit_ratio=0.50,
    )


@pytest.fixture
def simple_price() -> ModelPrice:
    """Round prices: $1 in, $10 out, $0.10 cached, 50% batch discount."""
    return ModelPrice(
        model_id="test-model",
        display_name="Test Model",
        provider="Test",
        tier="first-party",
        input_per_mtok=1.0,
        output_per_mtok=10.0,
        cached_input_per_mtok=0.10,
        batch_discount=0.50,
        open_weights=OpenWeights(available=True, license="MIT", license_url="https://example.org"),
    )
