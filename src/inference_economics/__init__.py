"""A parameterised build-vs-buy model for LLM inference.

The package is layered so that the argument can be audited independently of the
plumbing:

``model``
    Frozen dataclasses and pure functions. All the arithmetic, no I/O.
``profiles``
    Three named token profiles. Assumptions, clearly labelled as such.
``scenario``
    Default self-hosting parameters, each annotated with its source or with a
    note telling you to replace it.
``prices``
    The only module that reads a file. Strict schema validation.
``breakeven`` / ``sensitivity``
    The two analyses that turn the model into an answer.
``render`` / ``cli``
    Presentation. No calculation happens here.
"""

from __future__ import annotations

from .breakeven import BreakEven, find_break_even
from .errors import (
    InferenceEconomicsError,
    ModelNotFoundError,
    PriceDataError,
    ScenarioError,
)
from .model import (
    Benchmark,
    ModelPrice,
    NodeSpec,
    OpenWeights,
    PlatformSpec,
    SelfHostScenario,
    TokenProfile,
    api_cost_per_developer_month,
    effective_devs_per_node,
    marginal_cost_per_developer,
    node_monthly_cost,
    nodes_required,
    self_host_cost_per_developer,
    self_host_monthly_cost,
)
from .prices import PriceBook, load_price_book
from .profiles import INTENSIVE, LIGHT, MEDIUM, PROFILES, get_profile
from .scenario import default_scenario
from .sensitivity import SensitivityGrid, sweep

__version__ = "0.1.0"

__all__ = [
    "Benchmark",
    "BreakEven",
    "INTENSIVE",
    "InferenceEconomicsError",
    "LIGHT",
    "MEDIUM",
    "ModelNotFoundError",
    "ModelPrice",
    "NodeSpec",
    "OpenWeights",
    "PROFILES",
    "PlatformSpec",
    "PriceBook",
    "PriceDataError",
    "ScenarioError",
    "SelfHostScenario",
    "SensitivityGrid",
    "TokenProfile",
    "__version__",
    "api_cost_per_developer_month",
    "default_scenario",
    "effective_devs_per_node",
    "find_break_even",
    "get_profile",
    "load_price_book",
    "marginal_cost_per_developer",
    "node_monthly_cost",
    "nodes_required",
    "self_host_cost_per_developer",
    "self_host_monthly_cost",
    "sweep",
]
