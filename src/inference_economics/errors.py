"""Exception types.

One base class so a caller can catch everything this package raises, and three
specific ones so a caller can tell a bad price file from a bad scenario without
matching on message text.
"""

from __future__ import annotations


class InferenceEconomicsError(Exception):
    """Base class for every error this package raises deliberately."""


class PriceDataError(InferenceEconomicsError):
    """A price file is missing, malformed, or violates the documented schema."""


class ScenarioError(InferenceEconomicsError):
    """A scenario or profile parameter is outside its permitted range."""


class ModelNotFoundError(InferenceEconomicsError):
    """A requested model_id is not present in the loaded price file."""
