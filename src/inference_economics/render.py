"""Text rendering.

Pure functions from data to strings. No printing happens here and no data is
computed here — the CLI does the first, the model layer does the second. Keeping
rendering separate is what makes the golden-file test worth having: it pins the
output a reader actually sees, and it fails if a column, a caveat or a footnote
disappears.

Output is deterministic. Rows are sorted by a stable key, no timestamps are
emitted, and nothing depends on dictionary iteration order.
"""

from __future__ import annotations

import math

from .breakeven import BreakEven
from .model import (
    HOURS_PER_MONTH,
    ModelPrice,
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
from .prices import PriceBook
from .sensitivity import SensitivityGrid

SELF_HOST_LABEL = "Self-hosted open-weight model"


def money(value: float, places: int = 2) -> str:
    """Format USD, or ``n/a`` for a non-finite result."""
    if not math.isfinite(value):
        return "n/a"
    return f"${value:,.{places}f}"


def table(headers: list[str], rows: list[list[str]], right_align: set[int] | None = None) -> str:
    """A fixed-width text table with a dashed rule under the header."""
    right = right_align or set()
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        parts = [
            cells[i].rjust(widths[i]) if i in right else cells[i].ljust(widths[i])
            for i in range(len(cells))
        ]
        return "  ".join(parts).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def _profile_line(profile: TokenProfile) -> str:
    return (
        f"{profile.name}: {profile.input_mtok:,.0f} Mtok in / "
        f"{profile.output_mtok:,.0f} Mtok out per developer-month, "
        f"{profile.cache_hit_ratio:.0%} cache hits"
    )


def render_assumptions(
    scenario: SelfHostScenario,
    profile: TokenProfile,
    developers: int,
    batch_fraction: float,
) -> str:
    node = scenario.node
    amortisation = node.capex_usd / node.amortisation_months
    energy = node.power_kw * node.pue * HOURS_PER_MONTH * node.power_price_per_kwh
    effective = effective_devs_per_node(scenario, profile)

    rows = [
        ["Token profile", _profile_line(profile)],
        ["Head count", f"{developers:,} developers"],
        [
            "Node",
            f"{node.name} — {money(node.capex_usd, 0)} over {node.amortisation_months} months",
        ],
        [
            "Node capacity",
            f"{node.devs_per_node:,.0f} nameplate x {scenario.utilisation:.0%} utilisation "
            f"= {effective:,.1f} effective developers per node",
        ],
        [
            "Node monthly cost",
            f"{money(node_monthly_cost(node), 0)} "
            f"(amortisation {money(amortisation, 0)} + energy {money(energy, 0)} "
            f"+ hosting {money(node.colocation_per_node_month, 0)})",
        ],
        [
            "Platform team",
            f"{scenario.platform.fte:g} FTE at "
            f"{money(scenario.platform.loaded_cost_per_fte_month, 0)}/month "
            f"= {money(scenario.platform.monthly_cost, 0)}/month",
        ],
        [
            "Redundancy",
            f"{scenario.redundancy_nodes} node(s) carrying full cost and no capacity",
        ],
        ["Batch traffic", f"{batch_fraction:.0%} of traffic routed through a batch endpoint"],
    ]

    width = max(len(row[0]) for row in rows)
    lines = ["Assumptions — every one of these is an input you can change:"]
    lines.extend(f"  {label.ljust(width)}  {value}" for label, value in rows)
    return "\n".join(lines)


def render_compare(
    book: PriceBook,
    scenario: SelfHostScenario,
    profile: TokenProfile,
    developers: int,
    batch_fraction: float = 0.0,
) -> str:
    """The three-way comparison: first-party API, aggregator, self-hosted."""
    lines = [
        f"Cost per developer-month — {profile.name} profile, {developers:,} developers",
        f"Price data: {book.path.name} (published {book.published})",
        "",
        render_assumptions(scenario, profile, developers, batch_fraction),
        "",
        "BUY — published API list prices",
        "",
    ]

    priced = sorted(
        ((api_cost_per_developer_month(profile, price, batch_fraction), price) for price in book),
        key=lambda pair: (pair[0], pair[1].model_id),
    )

    rows = []
    for cost, price in priced:
        weights = price.open_weights.license if price.open_weights.available else "API only"
        rows.append(
            [
                price.display_name + ("*" if price.promotional else ""),
                price.provider,
                price.tier,
                money(cost),
                weights or "",
            ]
        )
    lines.append(
        table(
            ["Route", "Provider", "Tier", "$/dev-month", "Weights"],
            rows,
            right_align={3},
        )
    )

    if any(price.promotional for price in book):
        lines.append("")
        lines.append("  * promotional rate, not the rate card. See the notes in the price file.")

    per_dev = self_host_cost_per_developer(scenario, profile, developers)
    marginal = marginal_cost_per_developer(scenario, profile)
    nodes = nodes_required(scenario, profile, developers)
    total = self_host_monthly_cost(scenario, profile, developers)

    lines.extend(
        [
            "",
            f"BUILD — {SELF_HOST_LABEL.lower()}, on your own hardware",
            "",
            table(
                ["Measure", "Value"],
                [
                    [
                        "Nodes required",
                        f"{nodes} ({nodes - scenario.redundancy_nodes} serving "
                        f"+ {scenario.redundancy_nodes} redundant)",
                    ],
                    ["Total monthly cost", money(total, 0)],
                    [f"Cost per developer at {developers:,}", money(per_dev)],
                    ["Marginal cost per developer", money(marginal)],
                ],
                right_align={1},
            ),
            "",
            "  The marginal cost is the floor. Adding developers dilutes the platform team",
            "  and the redundant node, but never takes the per-developer cost below it.",
            "",
            "VERDICT — against every route whose weights you could actually run",
            "",
        ]
    )

    hostable = book.self_hostable()
    if not hostable:
        lines.append("  No route in this price file publishes downloadable weights.")
        return "\n".join(lines) + "\n"

    verdict_rows = []
    for price in sorted(hostable, key=lambda p: p.model_id):
        api = api_cost_per_developer_month(profile, price, batch_fraction)
        if marginal >= api:
            verdict = "never breaks even"
        elif per_dev <= api:
            verdict = f"cheaper at {developers:,}"
        else:
            verdict = f"more expensive at {developers:,}"
        ratio = per_dev / api if api > 0 and math.isfinite(per_dev) else math.inf
        verdict_rows.append(
            [
                price.display_name,
                money(api),
                money(per_dev),
                f"{ratio:,.2f}x" if math.isfinite(ratio) else "n/a",
                verdict,
            ]
        )

    lines.append(
        table(
            ["Its own API", "API $/dev", "Self-host $/dev", "Ratio", "Verdict"],
            verdict_rows,
            right_align={1, 2, 3},
        )
    )
    lines.extend(
        [
            "",
            "  Self-hosting an open-weight model competes against that model's own API,",
            "  not against a frontier model's price. Comparing it to the frontier price is",
            "  the comparison that manufactures a business case out of nothing.",
            "  See docs/adr/0001-what-self-hosting-competes-with.md.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_breakeven(
    result: BreakEven,
    price: ModelPrice,
    profile: TokenProfile,
    scenario: SelfHostScenario,
) -> str:
    """The break-even answer, with the arithmetic that produced it."""
    effective = effective_devs_per_node(scenario, profile)
    lines = [
        f"Break-even — self-hosted vs {price.display_name}",
        f"Profile: {_profile_line(profile)}",
        "",
        table(
            ["Measure", "Value"],
            [
                ["API cost per developer-month", money(result.api_cost_per_developer)],
                [
                    "Self-hosted marginal cost per developer",
                    money(result.marginal_self_host_cost_per_developer),
                ],
                ["Effective developers per node", f"{effective:,.1f}"],
                ["Node monthly cost", money(node_monthly_cost(scenario.node), 0)],
                ["Fixed platform cost per month", money(scenario.platform.monthly_cost, 0)],
            ],
            right_align={1},
        ),
        "",
    ]

    if result.exists:
        lines.append(f"BREAK-EVEN AT {result.developers:,} DEVELOPERS")
        lines.append(f"  {result.reason}.")
        lines.append("")
        lines.append("  This is the smallest head count from which self-hosting is never again")
        lines.append("  more expensive. Cost per developer is a sawtooth — it drops as a node")
        lines.append("  fills and jumps when you buy the next one — so an earlier crossing that")
        lines.append("  does not hold is not a break-even.")
    else:
        lines.append("NO BREAK-EVEN")
        lines.append(f"  {result.reason}.")

    if not price.open_weights.available:
        lines.extend(
            [
                "",
                "  *** THIS IS THE RIGGED COMPARISON. ***",
                "",
                f"  {price.display_name} has no downloadable weights, so nothing above is",
                "  self-hosting it. The self-hosted column is some *other* model running on",
                "  your hardware, priced against this vendor's rate card. The arithmetic is",
                "  correct and the comparison is meaningless: it prices two different",
                "  products as though they were one.",
                "",
                "  Run this again with --model glm-5.2 — the open model's own API — and the",
                "  break-even usually disappears entirely. That is the number a business",
                "  case has to clear. Somebody will build one on the figure above if you let",
                "  them. See docs/adr/0001-what-self-hosting-competes-with.md.",
            ]
        )

    return "\n".join(lines) + "\n"


def render_sensitivity(grid: SensitivityGrid) -> str:
    """The grid over the two dominant parameters, and whether the verdict flips."""
    lines = [
        f"Sensitivity — break-even head count vs {grid.price.display_name}",
        "",
        "Cells are the developer count at which self-hosting first becomes and stays",
        "cheaper. 'never' means the marginal cost per developer already exceeds the API",
        "price, so no head count closes the gap.",
        "",
    ]

    headers = ["Devs/node"] + [p.name for p in grid.profiles]
    rows = []
    for devs in grid.devs_per_node_values:
        row = [f"{devs:g}"]
        for profile in grid.profiles:
            cell = grid.cell(profile.name, devs)
            row.append(f"{cell.break_even_developers:,}" if cell.self_host_ever_wins else "never")
        rows.append(row)
    lines.append(table(headers, rows, right_align=set(range(1, len(headers)))))

    lines.extend(["", "Underlying costs per developer-month:", ""])
    cost_rows = []
    for devs in grid.devs_per_node_values:
        row = [f"{devs:g}"]
        for profile in grid.profiles:
            cell = grid.cell(profile.name, devs)
            row.append(money(cell.marginal_self_host_cost_per_developer, 0))
        cost_rows.append(row)

    api_row = ["API"]
    for profile in grid.profiles:
        cell = grid.cell(profile.name, grid.devs_per_node_values[0])
        api_row.append(money(cell.api_cost_per_developer, 0))
    cost_rows.append(api_row)

    lines.append(
        table(
            ["Devs/node"] + [f"{p.name} marginal" for p in grid.profiles],
            cost_rows,
            right_align=set(range(1, len(grid.profiles) + 1)),
        )
    )

    lines.append("")
    if grid.flips:
        lines.append("THE VERDICT FLIPS INSIDE THIS GRID.")
        lines.append(
            "  Which way the answer comes out depends on two numbers nobody here measured."
        )
        lines.append("  If your honest uncertainty spans the flip, you do not have an answer yet —")
        lines.append("  you have a measurement to take. Instrument your gateway for a month and")
        lines.append("  re-run this with a real token profile.")
    else:
        verdict = (
            "self-hosting wins somewhere"
            if grid.cells[0].self_host_ever_wins
            else ("self-hosting never wins")
        )
        lines.append(f"THE VERDICT HOLDS ACROSS THIS GRID: {verdict}.")
        lines.append("  That is a stronger result than any single cell, because it does not depend")
        lines.append("  on getting either assumption right.")

    return "\n".join(lines) + "\n"


def render_prices(book: PriceBook) -> str:
    """The price file with its provenance, so a number can be traced to a page."""
    lines = [
        f"{book.path.name} — published {book.published}, {len(book)} routes",
        "",
        "These are list prices transcribed from vendor pages on the dates below. They",
        "are not quotes, not negotiated rates, and not measurements. Re-check them.",
        "",
    ]

    rows = []
    for price in sorted(book, key=lambda p: p.model_id):
        cached = (
            money(price.cached_input_per_mtok)
            if price.cached_input_per_mtok is not None
            else "not verified"
        )
        batch = f"{price.batch_discount:.0%}" if price.batch_discount else "none"
        rows.append(
            [
                price.model_id + ("*" if price.promotional else ""),
                money(price.input_per_mtok),
                money(price.output_per_mtok),
                cached,
                batch,
                price.as_of.isoformat() if price.as_of else "",
            ]
        )
    lines.append(
        table(
            ["Model", "In /Mtok", "Out /Mtok", "Cached in", "Batch", "As of"],
            rows,
            right_align={1, 2, 3, 4},
        )
    )

    lines.extend(["", "Sources:", ""])
    for price in sorted(book, key=lambda p: p.model_id):
        lines.append(f"  {price.model_id}")
        lines.append(f"    {price.source_url}")
        if price.open_weights.available:
            weights = price.open_weights
            lines.append(f"    weights: {weights.license} ({weights.license_url})")
        else:
            lines.append("    weights: not published — cannot be self-hosted")
        if price.benchmark:
            b = price.benchmark
            lines.append(
                f"    benchmark: {b.name} {b.score:g} as of {b.as_of.isoformat()} — {b.source_url}"
            )
        if price.notes:
            lines.append(f"    note: {price.notes}")

    lines.extend(
        [
            "",
            "  A benchmark score here means 'this figure appeared on this page on this",
            "  date'. It is not a timeless quality ranking, it does not survive a",
            "  benchmark revision, and no calculation in this repository reads it.",
        ]
    )
    return "\n".join(lines) + "\n"
