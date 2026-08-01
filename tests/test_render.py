"""Rendering edge cases the CLI tests do not reach with the shipped price file."""

from __future__ import annotations

import math
from dataclasses import replace

from inference_economics.breakeven import find_break_even
from inference_economics.model import OpenWeights
from inference_economics.prices import PriceBook
from inference_economics.profiles import INTENSIVE
from inference_economics.render import money, render_breakeven, render_compare, table


class TestMoney:
    def test_formats_with_thousands_separators(self):
        assert money(1234.5) == "$1,234.50"

    def test_honours_the_requested_precision(self):
        assert money(1234.5, 0) == "$1,234"

    def test_renders_a_non_finite_cost_as_not_applicable(self):
        """An idle node has a real cost and no capacity. 'inf' is not a number to print."""
        assert money(math.inf) == "n/a"


class TestTable:
    def test_pads_columns_to_the_widest_cell(self):
        rendered = table(["a", "bbbb"], [["cccc", "d"]])
        header, rule, row = rendered.splitlines()
        assert header.startswith("a     bbbb")
        assert rule == "----  ----"
        assert row.startswith("cccc  d")

    def test_right_aligns_the_requested_columns(self):
        rendered = table(["n"], [["1"], ["100"]], right_align={0})
        assert rendered.splitlines()[2] == "  1"


class TestCompareWithNoSelfHostableRoutes:
    def test_says_so_rather_than_printing_an_empty_verdict_table(self, book, scenario):
        api_only = PriceBook(
            version=book.version,
            published=book.published,
            description=book.description,
            path=book.path,
            models=tuple(
                replace(m, open_weights=OpenWeights(available=False)) for m in book.models
            ),
        )
        output = render_compare(api_only, scenario, INTENSIVE, 500)
        assert "No route in this price file publishes downloadable weights." in output


class TestBreakEvenRendering:
    def test_an_existing_break_even_explains_the_sawtooth(self, book, scenario):
        price = book.get("claude-opus-5")
        result = find_break_even(scenario, INTENSIVE, price)
        output = render_breakeven(result, price, INTENSIVE, scenario)
        assert "sawtooth" in output

    def test_an_absent_break_even_gives_the_reason(self, book, scenario):
        price = book.get("glm-5.2")
        result = find_break_even(scenario, INTENSIVE, price)
        output = render_breakeven(result, price, INTENSIVE, scenario)
        assert "NO BREAK-EVEN" in output
        assert "marginal cost" in output
