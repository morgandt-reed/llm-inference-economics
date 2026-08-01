"""Three named token profiles for agentic coding.

Every number here is an **assumption**, not a measurement. Nothing in this
repository observed a developer's token consumption. They are stated as
defaults so that a comparison has somewhere to start, and they are the first
thing you should replace with your own gateway telemetry — which is the only
place a real number for this can come from.

The shape of the assumption, which matters more than the magnitudes:

* Input dwarfs output by one to two orders of magnitude. An agentic coding loop
  re-reads files, tool results and prior turns on every step, and emits a
  comparatively small diff. A profile with a balanced input/output ratio is
  modelling a chatbot, not a coding agent.
* Most of that input is a cache hit. The re-read context is stable across turns
  within a session, so it hits a prompt cache. The cache-hit ratio is what makes
  the input side affordable, and it is also the assumption most likely to be
  wrong in either direction: a harness that invalidates its prefix on every turn
  gets none of it.

The cache-hit ratios below (0.70 / 0.80 / 0.85) rise with intensity on the
reasoning that longer sessions amortise their prefix better. That is a
plausible story, not a finding.
"""

from __future__ import annotations

from .errors import ScenarioError
from .model import TokenProfile

LIGHT = TokenProfile(
    name="light",
    input_mtok=40.0,
    output_mtok=1.5,
    cache_hit_ratio=0.70,
    description="Occasional assisted edits; the agent is a tool, not the workflow",
)

MEDIUM = TokenProfile(
    name="medium",
    input_mtok=150.0,
    output_mtok=5.0,
    cache_hit_ratio=0.80,
    description="Daily agentic use for a meaningful share of the working day",
)

INTENSIVE = TokenProfile(
    name="intensive",
    input_mtok=500.0,
    output_mtok=15.0,
    cache_hit_ratio=0.85,
    description="Agent-first development; long autonomous runs are routine",
)

PROFILES: dict[str, TokenProfile] = {
    LIGHT.name: LIGHT,
    MEDIUM.name: MEDIUM,
    INTENSIVE.name: INTENSIVE,
}

DEFAULT_PROFILE = INTENSIVE.name


def get_profile(name: str) -> TokenProfile:
    """Look up a named profile, or raise with the list of valid names."""
    try:
        return PROFILES[name]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ScenarioError(f"unknown profile {name!r}; known profiles: {known}") from None
