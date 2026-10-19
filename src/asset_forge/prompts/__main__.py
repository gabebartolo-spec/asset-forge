"""CLI: python -m asset_forge.prompts "six-armed brute" --type monster [--view back]"""

from __future__ import annotations

import argparse
import sys

from . import ASSET_TYPES, TARGETS, PromptGenError, expand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="asset_forge.prompts", description="Expand my idea")
    ap.add_argument("idea")
    ap.add_argument("--type", dest="asset_type", required=True, choices=ASSET_TYPES)
    ap.add_argument("--view", default="front", choices=TARGETS)
    ap.add_argument("--fallback", action="store_true", help="use the plain template if no model")
    args = ap.parse_args(argv)
    try:
        print(expand(args.idea, args.asset_type, args.view, allow_fallback=args.fallback))
    except PromptGenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
