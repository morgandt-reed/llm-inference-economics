"""The command line, including a golden file for the table a reader actually sees.

The golden file pins the whole rendered comparison — columns, ordering,
formatting and, importantly, the caveats. It exists because the caveats are the
part most likely to be quietly dropped in a refactor, and a table of costs with
the warnings removed is exactly the artefact this repository argues against.

To update it deliberately after an intended change:

    inference-econ compare --prices data/prices-2026-07.yaml > tests/golden/compare.txt
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from inference_economics.cli import main

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def invoke(runner: CliRunner, price_file: Path, *args: str):
    return runner.invoke(main, [*args, "--prices", str(price_file)])


class TestGoldenOutput:
    def test_compare_matches_the_committed_table(self, runner, price_file):
        result = invoke(runner, price_file, "compare")
        assert result.exit_code == 0, result.output
        expected = (GOLDEN_DIR / "compare.txt").read_text(encoding="utf-8")
        assert result.output == expected


class TestCompare:
    def test_reports_the_self_hosted_marginal_cost(self, runner, price_file):
        result = invoke(runner, price_file, "compare")
        assert "Marginal cost per developer" in result.output

    def test_names_the_price_file_it_used(self, runner, price_file):
        result = invoke(runner, price_file, "compare")
        assert price_file.name in result.output

    def test_flags_promotional_rates(self, runner, price_file):
        result = invoke(runner, price_file, "compare")
        assert "promotional rate, not the rate card" in result.output

    def test_states_the_correct_comparator(self, runner, price_file):
        result = invoke(runner, price_file, "compare")
        assert "competes against that model's own API" in result.output

    def test_head_count_changes_the_per_developer_cost(self, runner, price_file):
        small = invoke(runner, price_file, "compare", "--developers", "50")
        large = invoke(runner, price_file, "compare", "--developers", "5000")
        assert small.output != large.output

    @pytest.mark.parametrize("profile", ["light", "medium", "intensive"])
    def test_runs_for_every_profile(self, runner, price_file, profile):
        result = invoke(runner, price_file, "compare", "--profile", profile)
        assert result.exit_code == 0, result.output
        assert f"{profile} profile" in result.output

    def test_scenario_flags_are_honoured(self, runner, price_file):
        cheap = invoke(runner, price_file, "compare", "--node-capex", "100000")
        dear = invoke(runner, price_file, "compare", "--node-capex", "900000")
        assert "$100,000" in cheap.output
        assert "$900,000" in dear.output
        assert cheap.output != dear.output


class TestBreakEven:
    def test_no_break_even_against_the_open_models_own_api(self, runner, price_file):
        result = invoke(runner, price_file, "breakeven", "--model", "glm-5.2")
        assert result.exit_code == 0, result.output
        assert "NO BREAK-EVEN" in result.output

    def test_break_even_against_a_frontier_api_is_shown_and_flagged_as_rigged(
        self, runner, price_file
    ):
        result = invoke(runner, price_file, "breakeven", "--model", "claude-opus-5")
        assert result.exit_code == 0, result.output
        assert "BREAK-EVEN AT" in result.output
        assert "THIS IS THE RIGGED COMPARISON" in result.output

    def test_unknown_model_fails_cleanly(self, runner, price_file):
        result = invoke(runner, price_file, "breakeven", "--model", "gpt-imaginary")
        assert result.exit_code == 2
        assert "no model" in result.output


class TestSensitivity:
    def test_produces_a_grid_over_both_parameters(self, runner, price_file):
        result = invoke(runner, price_file, "sensitivity")
        assert result.exit_code == 0, result.output
        for profile in ("light", "medium", "intensive"):
            assert profile in result.output
        assert "Devs/node" in result.output

    def test_reports_whether_the_verdict_flips(self, runner, price_file):
        result = invoke(runner, price_file, "sensitivity")
        assert "FLIPS" in result.output or "HOLDS" in result.output

    def test_custom_sweep_is_honoured(self, runner, price_file):
        result = invoke(runner, price_file, "sensitivity", "--devs-per-node-sweep", "10,1000")
        assert result.exit_code == 0, result.output
        assert "1000" in result.output

    def test_a_malformed_sweep_is_a_usage_error(self, runner, price_file):
        result = invoke(runner, price_file, "sensitivity", "--devs-per-node-sweep", "ten,twenty")
        assert result.exit_code == 2

    def test_an_empty_sweep_is_a_usage_error(self, runner, price_file):
        result = invoke(runner, price_file, "sensitivity", "--devs-per-node-sweep", " ")
        assert result.exit_code == 2


class TestPrices:
    def test_lists_every_route_with_its_source(self, runner, price_file, book):
        result = invoke(runner, price_file, "prices")
        assert result.exit_code == 0, result.output
        for price in book:
            assert price.model_id in result.output
            assert price.source_url in result.output

    def test_states_that_scores_are_dated_not_timeless(self, runner, price_file):
        result = invoke(runner, price_file, "prices")
        assert "not a timeless quality ranking" in result.output

    def test_marks_routes_that_cannot_be_self_hosted(self, runner, price_file):
        result = invoke(runner, price_file, "prices")
        assert "cannot be self-hosted" in result.output


class TestErrorHandling:
    def test_a_bad_profile_is_a_usage_error(self, runner, price_file):
        result = invoke(runner, price_file, "compare", "--profile", "gigantic")
        assert result.exit_code == 2

    def test_an_out_of_range_utilisation_exits_two_with_a_message(self, runner, price_file):
        result = invoke(runner, price_file, "compare", "--utilisation", "1.5")
        assert result.exit_code == 2
        assert "utilisation" in result.output

    def test_a_malformed_price_file_exits_two_with_a_message(self, runner, tmp_path):
        bad = tmp_path / "prices-bad.yaml"
        bad.write_text("version: 99\npublished: x\nmodels: []\n", encoding="utf-8")
        result = invoke(runner, bad, "compare")
        assert result.exit_code == 2
        assert "unsupported schema version" in result.output


def test_help_lists_all_four_commands(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("compare", "breakeven", "sensitivity", "prices"):
        assert command in result.output
