"""The three token profiles.

The tests here are mostly about the *shape* of the assumptions rather than their
magnitudes. The magnitudes are guesses and are documented as guesses; the shape
— input dominating output by an order of magnitude, most of it cached — is the
part that says "this is an agentic coding workload and not a chatbot", and a
change to that shape would silently change what the whole repository is about.
"""

from __future__ import annotations

import pytest

from inference_economics.errors import ScenarioError
from inference_economics.profiles import (
    DEFAULT_PROFILE,
    INTENSIVE,
    LIGHT,
    MEDIUM,
    PROFILES,
    get_profile,
)


def test_three_profiles_are_registered():
    assert set(PROFILES) == {"light", "medium", "intensive"}


def test_the_default_profile_exists():
    assert DEFAULT_PROFILE in PROFILES


def test_lookup_returns_the_registered_object():
    assert get_profile("medium") is MEDIUM


def test_unknown_profile_lists_the_valid_names():
    with pytest.raises(ScenarioError, match="intensive, light, medium"):
        get_profile("enormous")


@pytest.mark.parametrize("profile", [LIGHT, MEDIUM, INTENSIVE])
def test_input_dominates_output_by_an_order_of_magnitude(profile):
    """An agentic loop re-reads context and emits a small diff.

    A profile with a balanced ratio is modelling a different workload, and every
    conclusion downstream would be about that other workload instead.
    """
    assert profile.input_mtok >= 10 * profile.output_mtok


@pytest.mark.parametrize("profile", [LIGHT, MEDIUM, INTENSIVE])
def test_most_input_is_a_cache_hit(profile):
    assert profile.cache_hit_ratio >= 0.5


@pytest.mark.parametrize("profile", [LIGHT, MEDIUM, INTENSIVE])
def test_every_profile_is_described(profile):
    assert profile.description


def test_the_tiers_are_ordered_by_intensity():
    assert LIGHT.input_mtok < MEDIUM.input_mtok < INTENSIVE.input_mtok
    assert LIGHT.output_mtok < MEDIUM.output_mtok < INTENSIVE.output_mtok
