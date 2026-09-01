"""Vertex smoke stub — documents cost ceiling; refuses to run without explicit flag.

Phase 8: do not execute live Vertex. This module exists so the command is
discoverable and fail-closed.
"""

from __future__ import annotations

import argparse
import sys

from eval.cloud_poc import VERTEX_SMOKE_COST_CEILING_USD, VERTEX_SMOKE_CMD


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ContextFlow Vertex smoke (cost-capped)")
    p.add_argument("--max-usd", type=float, default=VERTEX_SMOKE_COST_CEILING_USD)
    p.add_argument(
        "--i-accept-cost",
        action="store_true",
        help="Required to attempt a live smoke (still not implemented for Phase 8).",
    )
    args = p.parse_args(argv)
    if args.max_usd > VERTEX_SMOKE_COST_CEILING_USD:
        print(
            f"refusing: max-usd {args.max_usd} exceeds ceiling "
            f"{VERTEX_SMOKE_COST_CEILING_USD}",
            file=sys.stderr,
        )
        return 2
    if not args.i_accept_cost:
        print(
            "Vertex smoke not executed (Phase 8 stop). "
            f"Documented command:\n  {VERTEX_SMOKE_CMD}\n"
            "Re-run with --i-accept-cost only after approval.",
        )
        return 0
    print(
        "Live Vertex smoke is intentionally unimplemented in Phase 8. "
        "Approve a follow-up phase before spending.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
