"""Loading and validating a dated price file.

The only module in the package that touches the filesystem. It is strict on
purpose: an unknown key is an error rather than an ignored line, because the
failure mode this guards against is a typo in a field name producing a
plausible-looking table with a silently missing discount in it.

The schema is documented in ``data/SCHEMA.md``; this module is its enforcement.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .errors import ModelNotFoundError, PriceDataError
from .model import Benchmark, ModelPrice, OpenWeights

SCHEMA_VERSION = 1
VALID_TIERS = frozenset({"first-party", "aggregator"})

_TOP_LEVEL_KEYS = frozenset({"version", "published", "description", "models"})
_MODEL_KEYS = frozenset(
    {
        "model_id",
        "display_name",
        "provider",
        "tier",
        "input_per_mtok",
        "output_per_mtok",
        "cached_input_per_mtok",
        "batch_discount",
        "source_url",
        "as_of",
        "promotional",
        "context_window_tokens",
        "open_weights",
        "benchmark",
        "notes",
    }
)
_OPEN_WEIGHTS_KEYS = frozenset({"available", "license", "license_url"})
_BENCHMARK_KEYS = frozenset({"name", "score", "as_of", "source_url", "notes"})


@dataclass(frozen=True)
class PriceBook:
    """A loaded price file: the snapshot plus where it came from."""

    version: int
    published: str
    description: str
    path: Path
    models: tuple[ModelPrice, ...]

    def __iter__(self) -> Iterator[ModelPrice]:
        return iter(self.models)

    def __len__(self) -> int:
        return len(self.models)

    def get(self, model_id: str) -> ModelPrice:
        for price in self.models:
            if price.model_id == model_id:
                return price
        known = ", ".join(sorted(m.model_id for m in self.models))
        raise ModelNotFoundError(f"no model {model_id!r} in {self.path.name}; known: {known}")

    def by_tier(self, tier: str) -> tuple[ModelPrice, ...]:
        return tuple(m for m in self.models if m.tier == tier)

    def self_hostable(self) -> tuple[ModelPrice, ...]:
        """Routes whose weights can actually be downloaded and served."""
        return tuple(m for m in self.models if m.open_weights.available)


def default_price_file(start: Path | None = None) -> Path:
    """Find the newest ``data/prices-*.yaml`` by walking up from this package.

    Works for a source checkout and for an editable install, which is how this
    repository is used. For a non-editable install the data directory is outside
    the package and this will not find it — pass ``--prices`` explicitly, which
    is why the error below says so rather than failing obscurely.
    """
    origin = start if start is not None else Path(__file__).resolve()
    for parent in [origin, *origin.parents]:
        candidates = sorted((parent / "data").glob("prices-*.yaml"))
        if candidates:
            return candidates[-1]
    raise PriceDataError(
        "could not locate a data/prices-*.yaml file by searching upward from "
        f"{origin}. Pass one explicitly with --prices."
    )


def load_price_book(path: Path | str) -> PriceBook:
    """Read and validate a price file. Raises ``PriceDataError`` on any violation."""
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PriceDataError(f"cannot read price file {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise PriceDataError(f"{path}: not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise PriceDataError(f"{path}: top level must be a mapping")

    _reject_unknown(raw, _TOP_LEVEL_KEYS, path, "top level")

    version = raw.get("version")
    if version != SCHEMA_VERSION:
        raise PriceDataError(
            f"{path}: unsupported schema version {version!r}; this build understands "
            f"version {SCHEMA_VERSION}"
        )

    published = raw.get("published")
    if not isinstance(published, str) or not published:
        raise PriceDataError(f"{path}: 'published' must be a non-empty string")

    entries = raw.get("models")
    if not isinstance(entries, list) or not entries:
        raise PriceDataError(f"{path}: 'models' must be a non-empty list")

    models: list[ModelPrice] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        price = _parse_model(entry, path, index)
        if price.model_id in seen:
            raise PriceDataError(f"{path}: duplicate model_id {price.model_id!r}")
        seen.add(price.model_id)
        models.append(price)

    return PriceBook(
        version=version,
        published=published,
        description=str(raw.get("description", "")).strip(),
        path=path,
        models=tuple(models),
    )


def _reject_unknown(
    mapping: dict[str, Any], allowed: frozenset[str], path: Path, where: str
) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise PriceDataError(
            f"{path}: unknown key(s) at {where}: {', '.join(unknown)}. "
            "Field names are validated so a typo fails loudly instead of being ignored."
        )


def _parse_model(entry: Any, path: Path, index: int) -> ModelPrice:
    where = f"models[{index}]"
    if not isinstance(entry, dict):
        raise PriceDataError(f"{path}: {where} must be a mapping")
    _reject_unknown(entry, _MODEL_KEYS, path, where)

    model_id = _require_str(entry, "model_id", path, where)
    where = f"model {model_id!r}"

    tier = _require_str(entry, "tier", path, where)
    if tier not in VALID_TIERS:
        raise PriceDataError(
            f"{path}: {where}: tier must be one of {', '.join(sorted(VALID_TIERS))}, got {tier!r}"
        )

    input_price = _require_price(entry, "input_per_mtok", path, where)
    output_price = _require_price(entry, "output_per_mtok", path, where)

    cached = entry.get("cached_input_per_mtok", None)
    if cached is not None:
        cached = _coerce_price(cached, "cached_input_per_mtok", path, where)

    batch = entry.get("batch_discount", None)
    if batch is not None:
        batch = _coerce_price(batch, "batch_discount", path, where)
        if not 0.0 <= batch <= 1.0:
            raise PriceDataError(f"{path}: {where}: batch_discount must be in [0, 1]")

    source_url = _require_url(entry, "source_url", path, where)
    as_of = _require_date(entry, "as_of", path, where)

    context_window = entry.get("context_window_tokens", None)
    if context_window is not None:
        if not isinstance(context_window, int) or context_window <= 0:
            raise PriceDataError(f"{path}: {where}: context_window_tokens must be a positive int")

    promotional = entry.get("promotional", False)
    if not isinstance(promotional, bool):
        raise PriceDataError(f"{path}: {where}: promotional must be a boolean")

    return ModelPrice(
        model_id=model_id,
        display_name=_require_str(entry, "display_name", path, where),
        provider=_require_str(entry, "provider", path, where),
        tier=tier,
        input_per_mtok=input_price,
        output_per_mtok=output_price,
        cached_input_per_mtok=cached,
        batch_discount=batch,
        source_url=source_url,
        as_of=as_of,
        promotional=promotional,
        context_window_tokens=context_window,
        open_weights=_parse_open_weights(entry.get("open_weights"), path, where),
        benchmark=_parse_benchmark(entry.get("benchmark"), path, where),
        notes=str(entry.get("notes", "")).strip(),
    )


def _parse_open_weights(raw: Any, path: Path, where: str) -> OpenWeights:
    if raw is None:
        raise PriceDataError(
            f"{path}: {where}: 'open_weights' is required. Whether the weights can be "
            "downloaded decides whether self-hosting is possible at all, so it is not "
            "something the file is allowed to leave unsaid."
        )
    if not isinstance(raw, dict):
        raise PriceDataError(f"{path}: {where}: 'open_weights' must be a mapping")
    _reject_unknown(raw, _OPEN_WEIGHTS_KEYS, path, f"{where}.open_weights")

    available = raw.get("available")
    if not isinstance(available, bool):
        raise PriceDataError(f"{path}: {where}: open_weights.available must be a boolean")

    licence = raw.get("license")
    licence_url = raw.get("license_url")
    if available:
        if not isinstance(licence, str) or not licence:
            raise PriceDataError(
                f"{path}: {where}: open_weights.license is required when weights are "
                "available. 'Open weights' is not a licence; name the actual one."
            )
        if not isinstance(licence_url, str) or not licence_url.startswith(("http://", "https://")):
            raise PriceDataError(
                f"{path}: {where}: open_weights.license_url must be an http(s) URL"
            )

    return OpenWeights(available=available, license=licence, license_url=licence_url)


def _parse_benchmark(raw: Any, path: Path, where: str) -> Benchmark | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PriceDataError(f"{path}: {where}: 'benchmark' must be a mapping")
    _reject_unknown(raw, _BENCHMARK_KEYS, path, f"{where}.benchmark")

    score = raw.get("score")
    if not isinstance(score, int | float) or isinstance(score, bool):
        raise PriceDataError(f"{path}: {where}: benchmark.score must be a number")

    return Benchmark(
        name=_require_str(raw, "name", path, f"{where}.benchmark"),
        score=float(score),
        as_of=_require_date(raw, "as_of", path, f"{where}.benchmark"),
        source_url=_require_url(raw, "source_url", path, f"{where}.benchmark"),
        notes=str(raw.get("notes", "")).strip(),
    )


def _require_str(mapping: dict[str, Any], key: str, path: Path, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PriceDataError(f"{path}: {where}: '{key}' must be a non-empty string")
    return value.strip()


def _require_url(mapping: dict[str, Any], key: str, path: Path, where: str) -> str:
    value = _require_str(mapping, key, path, where)
    if not value.startswith(("http://", "https://")):
        raise PriceDataError(
            f"{path}: {where}: '{key}' must be an http(s) URL so the number can be "
            f"traced back to the page it was read from; got {value!r}"
        )
    return value


def _require_date(mapping: dict[str, Any], key: str, path: Path, where: str) -> date:
    value = mapping.get(key)
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PriceDataError(f"{path}: {where}: '{key}' is not an ISO date: {exc}") from exc
    raise PriceDataError(
        f"{path}: {where}: '{key}' is required and must be a date (YYYY-MM-DD). "
        "A price without a date is a rumour."
    )


def _require_price(mapping: dict[str, Any], key: str, path: Path, where: str) -> float:
    if key not in mapping:
        raise PriceDataError(f"{path}: {where}: '{key}' is required")
    return _coerce_price(mapping[key], key, path, where)


def _coerce_price(value: Any, key: str, path: Path, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PriceDataError(f"{path}: {where}: '{key}' must be a number")
    if value < 0:
        raise PriceDataError(f"{path}: {where}: '{key}' must be non-negative")
    return float(value)
