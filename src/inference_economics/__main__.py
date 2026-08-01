"""Allow ``python -m inference_economics`` as well as the installed entry point."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":  # pragma: no cover
    main()
