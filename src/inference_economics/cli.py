"""Command line interface.

Three commands that answer three different questions:

* ``compare`` — what does a developer-month cost on each route, at a given head
  count, right now?
* ``breakeven`` — at what head count does building beat buying, if ever?
* ``sensitivity`` — does that answer survive the fact that two of its inputs are
  assumptions?

Plus ``prices``, which prints the price file with its sources so any number in
the other three can be traced to the page it came from.

Every scenario parameter is a flag with a documented default. Nothing is
hard-coded that a reader might reasonably disagree with.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import click

from . import scenario as scenario_defaults
from .breakeven import find_break_even
from .errors import InferenceEconomicsError
from .prices import default_price_file, load_price_book
from .profiles import DEFAULT_PROFILE, PROFILES, get_profile
from .render import render_breakeven, render_compare, render_prices, render_sensitivity
from .sensitivity import DEFAULT_DEVS_PER_NODE_SWEEP, sweep

DEFAULT_COMPARATOR = "glm-5.2"


def _scenario_options(func):
    """The self-hosting parameters, shared by every command that builds a scenario."""
    options = [
        click.option(
            "--devs-per-node",
            type=float,
            default=scenario_defaults.DEFAULT_DEVS_PER_NODE,
            show_default=True,
            help="Nameplate developers one node serves at the reference profile. "
            "An assumption, not a measurement — see 'sensitivity'.",
        ),
        click.option(
            "--utilisation",
            type=float,
            default=scenario_defaults.DEFAULT_UTILISATION,
            show_default=True,
            help="Fraction of nameplate capacity actually realised.",
        ),
        click.option(
            "--node-capex",
            type=float,
            default=scenario_defaults.DEFAULT_NODE_CAPEX_USD,
            show_default=True,
            help="Purchase price of one node, USD.",
        ),
        click.option(
            "--amortisation-months",
            type=int,
            default=scenario_defaults.DEFAULT_AMORTISATION_MONTHS,
            show_default=True,
            help="Capital amortisation period.",
        ),
        click.option(
            "--power-price",
            type=float,
            default=scenario_defaults.DEFAULT_POWER_PRICE_PER_KWH,
            show_default=True,
            help="Electricity, USD per kWh. Set this from your own bill.",
        ),
        click.option(
            "--pue",
            type=float,
            default=scenario_defaults.DEFAULT_PUE,
            show_default=True,
            help="Datacentre power usage effectiveness.",
        ),
        click.option(
            "--colocation",
            type=float,
            default=scenario_defaults.DEFAULT_COLOCATION_PER_NODE_MONTH,
            show_default=True,
            help="Hosting cost per node per month, USD.",
        ),
        click.option(
            "--platform-fte",
            type=float,
            default=scenario_defaults.DEFAULT_PLATFORM_FTE,
            show_default=True,
            help="Platform engineers required to operate the service.",
        ),
        click.option(
            "--fte-cost",
            type=float,
            default=scenario_defaults.DEFAULT_LOADED_COST_PER_FTE_MONTH,
            show_default=True,
            help="Fully loaded monthly cost per engineer, USD.",
        ),
        click.option(
            "--redundancy-nodes",
            type=int,
            default=scenario_defaults.DEFAULT_REDUNDANCY_NODES,
            show_default=True,
            help="Nodes carrying cost and contributing no capacity.",
        ),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _build_scenario(**kwargs):
    base = scenario_defaults.default_scenario()
    node = replace(
        base.node,
        capex_usd=kwargs["node_capex"],
        amortisation_months=kwargs["amortisation_months"],
        power_price_per_kwh=kwargs["power_price"],
        pue=kwargs["pue"],
        colocation_per_node_month=kwargs["colocation"],
        devs_per_node=kwargs["devs_per_node"],
    )
    platform = replace(
        base.platform,
        fte=kwargs["platform_fte"],
        loaded_cost_per_fte_month=kwargs["fte_cost"],
    )
    return replace(
        base,
        node=node,
        platform=platform,
        utilisation=kwargs["utilisation"],
        redundancy_nodes=kwargs["redundancy_nodes"],
    )


def _load(prices: Path | None):
    return load_price_book(prices if prices is not None else default_price_file())


_profile_option = click.option(
    "--profile",
    type=click.Choice(sorted(PROFILES)),
    default=DEFAULT_PROFILE,
    show_default=True,
    help="Token profile. All three are assumptions; replace them with your telemetry.",
)

_prices_option = click.option(
    "--prices",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Price file. Defaults to the newest data/prices-*.yaml in the repository.",
)

_batch_option = click.option(
    "--batch-fraction",
    type=float,
    default=0.0,
    show_default=True,
    help="Share of traffic routed through an asynchronous batch endpoint.",
)


class _ModelError(click.ClickException):
    """A modelling error, surfaced as a message and exit code 2 rather than a traceback."""

    exit_code = 2


class _ModelErrorGroup(click.Group):
    """Converts the package's own exceptions into clean CLI failures.

    A bad profile name, a malformed price file or an out-of-range parameter is a
    user error, not a bug, and should read like one.
    """

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except InferenceEconomicsError as exc:
            raise _ModelError(str(exc)) from exc


@click.group(cls=_ModelErrorGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="inference-economics")
def main() -> None:
    """A parameterised build-vs-buy model for LLM inference.

    Every number this prints is either a cited public price or an input
    parameter you can change. Nothing here was measured.
    """


@main.command()
@_profile_option
@click.option(
    "--developers",
    type=int,
    default=500,
    show_default=True,
    help="Head count to price the comparison at.",
)
@_prices_option
@_batch_option
@_scenario_options
def compare(profile: str, developers: int, prices: Path | None, batch_fraction: float, **kwargs):
    """Cost per developer-month across first-party API, aggregator and self-hosting."""
    book = _load(prices)
    click.echo(
        render_compare(
            book,
            _build_scenario(**kwargs),
            get_profile(profile),
            developers,
            batch_fraction,
        ),
        nl=False,
    )


@main.command()
@_profile_option
@click.option(
    "--model",
    default=DEFAULT_COMPARATOR,
    show_default=True,
    help="The API route to break even against. Default is the open model's own API, "
    "which is the correct comparator — see ADR-0001.",
)
@_prices_option
@_batch_option
@_scenario_options
def breakeven(profile: str, model: str, prices: Path | None, batch_fraction: float, **kwargs):
    """Head count at which self-hosting first becomes, and stays, cheaper."""
    book = _load(prices)
    price = book.get(model)
    resolved_profile = get_profile(profile)
    built = _build_scenario(**kwargs)
    result = find_break_even(built, resolved_profile, price, batch_fraction=batch_fraction)
    click.echo(render_breakeven(result, price, resolved_profile, built), nl=False)


@main.command()
@click.option(
    "--model",
    default=DEFAULT_COMPARATOR,
    show_default=True,
    help="The API route to break even against.",
)
@click.option(
    "--devs-per-node-sweep",
    default=",".join(f"{v:g}" for v in DEFAULT_DEVS_PER_NODE_SWEEP),
    show_default=True,
    help="Comma-separated node capacities to sweep.",
)
@_prices_option
@_batch_option
@_scenario_options
def sensitivity(
    model: str,
    devs_per_node_sweep: str,
    prices: Path | None,
    batch_fraction: float,
    **kwargs,
):
    """Sweep the two assumptions the conclusion actually depends on."""
    book = _load(prices)
    try:
        sweep_values = tuple(float(part) for part in devs_per_node_sweep.split(",") if part.strip())
    except ValueError as exc:
        raise click.BadParameter(f"not a comma-separated list of numbers: {exc}") from exc
    if not sweep_values:
        raise click.BadParameter("at least one devs-per-node value is required")

    grid = sweep(
        _build_scenario(**kwargs),
        tuple(PROFILES[name] for name in ("light", "medium", "intensive")),
        book.get(model),
        devs_per_node_values=sweep_values,
        batch_fraction=batch_fraction,
    )
    click.echo(render_sensitivity(grid), nl=False)


@main.command(name="prices")
@_prices_option
def prices_cmd(prices: Path | None):
    """Print the price file with its sources and as-of dates."""
    click.echo(render_prices(_load(prices)), nl=False)


if __name__ == "__main__":  # pragma: no cover
    main()
