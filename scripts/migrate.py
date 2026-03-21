#!/usr/bin/env python3
"""World migration trim tool — download, analyze, and trim Minecraft world chunks.

Downloads a Minecraft world from a remote host via SCP, analyzes chunk activity
using MCA Selector CLI, and trims low-activity chunks locally.
"""

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download and trim Minecraft world chunks using MCA Selector CLI.",
    )
    parser.add_argument("--host", required=True, help="SSH host (uses ~/.ssh/config)")
    parser.add_argument("--remote-path", required=True, help="Remote world directory path")
    parser.add_argument(
        "--dimensions", nargs="+", default=["overworld"],
        choices=["overworld", "nether", "end"],
        help="Dimensions to trim (default: overworld)",
    )

    query_group = parser.add_mutually_exclusive_group()
    query_group.add_argument(
        "--threshold", type=int,
        help="InhabitedTime threshold in ticks (shorthand for --query)",
    )
    query_group.add_argument(
        "--query",
        help="Raw MCA Selector query string (full syntax)",
    )

    parser.add_argument("--mcaselector", required=True, help="Path to MCA Selector JAR")
    parser.add_argument("--workdir", default="./migration-work", help="Local working directory")
    parser.add_argument("--headless", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--force", action="store_true", help="Override safety abort")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, do not trim")
    parser.add_argument(
        "--safety-pct", type=int, default=90,
        help="Abort if deletion exceeds this %% per dimension (default: 90)",
    )

    args = parser.parse_args(argv)

    # Default to threshold 120 if neither --threshold nor --query given
    if args.threshold is None and args.query is None:
        args.query = "InhabitedTime < 120"
    elif args.threshold is not None:
        args.query = f"InhabitedTime < {args.threshold}"

    args.mcaselector = Path(args.mcaselector)
    args.workdir = Path(args.workdir)

    return args
