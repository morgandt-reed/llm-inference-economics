"""The price file and its loader.

The first test class is the one that earns its place: it enforces, on the
committed data file, that every published number can be traced to a page and a
date. That is the difference between a price table and a rumour, and it is the
kind of discipline that decays silently unless a build fails when it lapses.
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from inference_economics.errors import ModelNotFoundError, PriceDataError
from inference_economics.prices import (
    SCHEMA_VERSION,
    VALID_TIERS,
    default_price_file,
    load_price_book,
)


class TestProvenanceIsEnforced:
    """Every entry in the shipped file must be traceable. No exceptions."""

    def test_every_entry_has_a_source_url(self, book):
        missing = [m.model_id for m in book if not m.source_url]
        assert not missing, f"entries without a source URL: {missing}"

    def test_every_source_url_is_an_http_url(self, book):
        bad = [m.model_id for m in book if not m.source_url.startswith(("http://", "https://"))]
        assert not bad, f"entries whose source is not a URL: {bad}"

    def test_every_entry_has_an_as_of_date(self, book):
        missing = [m.model_id for m in book if m.as_of is None]
        assert not missing, f"entries without an as-of date: {missing}"

    def test_every_as_of_date_is_a_real_date(self, book):
        assert all(isinstance(m.as_of, date) for m in book)

    def test_every_entry_declares_whether_weights_are_available(self, book):
        assert all(isinstance(m.open_weights.available, bool) for m in book)

    def test_every_downloadable_model_names_its_licence_and_links_to_it(self, book):
        for price in book.self_hostable():
            assert price.open_weights.license, f"{price.model_id} claims open weights, no licence"
            assert price.open_weights.license_url.startswith("http"), price.model_id

    def test_every_benchmark_score_carries_a_name_date_and_source(self, book):
        scored = [m for m in book if m.benchmark is not None]
        assert scored, "expected at least one benchmark score in the shipped file"
        for price in scored:
            benchmark = price.benchmark
            assert benchmark.name
            assert isinstance(benchmark.as_of, date)
            assert benchmark.source_url.startswith("http")


class TestShippedFile:
    def test_loads(self, book):
        assert book.version == SCHEMA_VERSION
        assert len(book) >= 8

    def test_model_ids_are_unique(self, book):
        ids = [m.model_id for m in book]
        assert len(ids) == len(set(ids))

    def test_every_tier_is_valid(self, book):
        assert {m.tier for m in book} <= VALID_TIERS

    def test_contains_both_a_first_party_and_an_aggregator_route(self, book):
        assert book.by_tier("first-party")
        assert book.by_tier("aggregator")

    def test_contains_a_self_hostable_route(self, book):
        assert book.self_hostable()

    def test_promotional_entries_are_flagged(self, book):
        assert any(m.promotional for m in book), (
            "the file records at least one promotional rate; if that stops being true, "
            "drop this test rather than the flag"
        )

    def test_lookup_by_id(self, book):
        assert book.get("glm-5.2").provider == "Z.ai"

    def test_unknown_id_lists_what_is_available(self, book):
        with pytest.raises(ModelNotFoundError, match="glm-5.2"):
            book.get("no-such-model")

    def test_default_price_file_finds_the_shipped_file(self, price_file):
        assert default_price_file().resolve() == price_file.resolve()

    def test_default_price_file_reports_clearly_when_nothing_is_found(self, tmp_path):
        with pytest.raises(PriceDataError, match="--prices"):
            default_price_file(start=tmp_path / "nowhere")


def _valid_entry(**overrides):
    entry = {
        "model_id": "m",
        "display_name": "M",
        "provider": "P",
        "tier": "first-party",
        "input_per_mtok": 1.0,
        "output_per_mtok": 2.0,
        "cached_input_per_mtok": 0.1,
        "batch_discount": 0.5,
        "source_url": "https://example.org/pricing",
        "as_of": "2026-08-01",
        "open_weights": {"available": False},
    }
    entry.update(overrides)
    return entry


def _write(tmp_path, *, models=None, **top_level):
    if models is None:
        models = [_valid_entry()]
    doc = {"version": SCHEMA_VERSION, "published": "2026-07", "models": models}
    doc.update(top_level)
    path = tmp_path / "prices-test.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


class TestLoaderRejects:
    def test_a_missing_file(self, tmp_path):
        with pytest.raises(PriceDataError, match="cannot read"):
            load_price_book(tmp_path / "absent.yaml")

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / "prices-bad.yaml"
        path.write_text("models: [\n  unterminated", encoding="utf-8")
        with pytest.raises(PriceDataError, match="not valid YAML"):
            load_price_book(path)

    def test_a_non_mapping_top_level(self, tmp_path):
        path = tmp_path / "prices-list.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(PriceDataError, match="must be a mapping"):
            load_price_book(path)

    def test_an_unknown_schema_version(self, tmp_path):
        with pytest.raises(PriceDataError, match="unsupported schema version"):
            load_price_book(_write(tmp_path, version=99))

    def test_a_missing_published_field(self, tmp_path):
        path = tmp_path / "prices-nopub.yaml"
        path.write_text(
            yaml.safe_dump({"version": SCHEMA_VERSION, "models": [_valid_entry()]}),
            encoding="utf-8",
        )
        with pytest.raises(PriceDataError, match="published"):
            load_price_book(path)

    def test_an_empty_model_list(self, tmp_path):
        with pytest.raises(PriceDataError, match="non-empty list"):
            load_price_book(_write(tmp_path, models=[]))

    def test_a_typo_in_a_field_name(self, tmp_path):
        """The failure this guards against: a silently dropped discount."""
        entry = _valid_entry()
        entry["batch_discout"] = 0.5  # codespell:ignore
        with pytest.raises(PriceDataError, match="unknown key"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_a_typo_at_the_top_level(self, tmp_path):
        with pytest.raises(PriceDataError, match="unknown key"):
            load_price_book(_write(tmp_path, descripton="typo"))

    def test_a_duplicate_model_id(self, tmp_path):
        with pytest.raises(PriceDataError, match="duplicate model_id"):
            load_price_book(_write(tmp_path, models=[_valid_entry(), _valid_entry()]))

    def test_an_unknown_tier(self, tmp_path):
        with pytest.raises(PriceDataError, match="tier must be one of"):
            load_price_book(_write(tmp_path, models=[_valid_entry(tier="wholesale")]))

    def test_a_negative_price(self, tmp_path):
        with pytest.raises(PriceDataError, match="non-negative"):
            load_price_book(_write(tmp_path, models=[_valid_entry(input_per_mtok=-1.0)]))

    def test_a_non_numeric_price(self, tmp_path):
        with pytest.raises(PriceDataError, match="must be a number"):
            load_price_book(_write(tmp_path, models=[_valid_entry(output_per_mtok="cheap")]))

    def test_a_missing_price(self, tmp_path):
        entry = _valid_entry()
        del entry["output_per_mtok"]
        with pytest.raises(PriceDataError, match="required"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_a_batch_discount_above_one(self, tmp_path):
        with pytest.raises(PriceDataError, match=r"batch_discount must be in \[0, 1\]"):
            load_price_book(_write(tmp_path, models=[_valid_entry(batch_discount=1.5)]))

    def test_a_source_that_is_not_a_url(self, tmp_path):
        with pytest.raises(PriceDataError, match="http"):
            load_price_book(_write(tmp_path, models=[_valid_entry(source_url="a vendor blog")]))

    def test_a_missing_as_of_date(self, tmp_path):
        entry = _valid_entry()
        del entry["as_of"]
        with pytest.raises(PriceDataError, match="rumour"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_an_unparseable_as_of_date(self, tmp_path):
        with pytest.raises(PriceDataError, match="not an ISO date"):
            load_price_book(_write(tmp_path, models=[_valid_entry(as_of="last Tuesday")]))

    def test_missing_open_weights(self, tmp_path):
        entry = _valid_entry()
        del entry["open_weights"]
        with pytest.raises(PriceDataError, match="open_weights"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_open_weights_without_a_licence(self, tmp_path):
        entry = _valid_entry(open_weights={"available": True})
        with pytest.raises(PriceDataError, match="not a licence"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_open_weights_without_a_licence_url(self, tmp_path):
        entry = _valid_entry(open_weights={"available": True, "license": "MIT"})
        with pytest.raises(PriceDataError, match="license_url"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_a_non_boolean_available_flag(self, tmp_path):
        entry = _valid_entry(open_weights={"available": "yes"})
        with pytest.raises(PriceDataError, match="must be a boolean"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_a_non_boolean_promotional_flag(self, tmp_path):
        with pytest.raises(PriceDataError, match="promotional must be a boolean"):
            load_price_book(_write(tmp_path, models=[_valid_entry(promotional="yes")]))

    def test_a_non_positive_context_window(self, tmp_path):
        with pytest.raises(PriceDataError, match="context_window_tokens"):
            load_price_book(_write(tmp_path, models=[_valid_entry(context_window_tokens=0)]))

    def test_a_benchmark_without_a_source(self, tmp_path):
        entry = _valid_entry(benchmark={"name": "Some Bench", "score": 50.0, "as_of": "2026-08-01"})
        with pytest.raises(PriceDataError, match="source_url"):
            load_price_book(_write(tmp_path, models=[entry]))

    def test_a_non_numeric_benchmark_score(self, tmp_path):
        entry = _valid_entry(
            benchmark={
                "name": "Some Bench",
                "score": "very good",
                "as_of": "2026-08-01",
                "source_url": "https://example.org",
            }
        )
        with pytest.raises(PriceDataError, match="score must be a number"):
            load_price_book(_write(tmp_path, models=[entry]))


class TestLoaderAccepts:
    def test_an_absent_cached_rate(self, tmp_path):
        loaded = load_price_book(
            _write(tmp_path, models=[_valid_entry(cached_input_per_mtok=None)])
        )
        entry = loaded.get("m")
        assert entry.cached_input_per_mtok is None
        assert entry.effective_cached_rate == entry.input_per_mtok

    def test_an_absent_batch_discount(self, tmp_path):
        loaded = load_price_book(_write(tmp_path, models=[_valid_entry(batch_discount=None)]))
        assert loaded.get("m").batch_discount is None

    def test_a_fully_populated_open_weight_entry(self, tmp_path):
        entry = _valid_entry(
            open_weights={
                "available": True,
                "license": "Apache-2.0",
                "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
            },
            benchmark={
                "name": "Some Bench",
                "score": 61.5,
                "as_of": "2026-08-01",
                "source_url": "https://example.org/leaderboard",
                "notes": "public split",
            },
            notes="a note",
        )
        loaded = load_price_book(_write(tmp_path, models=[entry])).get("m")
        assert loaded.open_weights.license == "Apache-2.0"
        assert loaded.benchmark.score == pytest.approx(61.5)
        assert loaded.notes == "a note"

    def test_iteration_and_length(self, tmp_path):
        loaded = load_price_book(_write(tmp_path))
        assert len(loaded) == 1
        assert [m.model_id for m in loaded] == ["m"]
