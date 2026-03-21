#!/usr/bin/env python3
"""World migration trim tool — download, analyze, and trim Minecraft world chunks."""

import argparse
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze and trim low-activity Minecraft world chunks.",
    )

    # Source: local world path OR SSH host + remote path
    parser.add_argument(
        "world_path", nargs="?", default=None,
        help="Local world directory path",
    )
    parser.add_argument("--host", default=None, help="SSH host (uses ~/.ssh/config)")
    parser.add_argument("--remote-path", default=None, help="Remote world directory path")

    # Dimensions
    parser.add_argument(
        "--dimensions", nargs="+", default=None,
        choices=["overworld", "nether", "end"],
        help="Dimensions to process (default: auto-detect)",
    )

    # Query mode: threshold shorthand OR raw query string (mutually exclusive)
    query_group = parser.add_mutually_exclusive_group()
    query_group.add_argument(
        "--threshold", type=int, default=None,
        help="InhabitedTime threshold in ticks",
    )
    query_group.add_argument(
        "--query", default=None,
        help="MCA Selector query string",
    )

    # Tool and output paths
    parser.add_argument("--mcaselector", default=None, help="Path to MCA Selector JAR")
    parser.add_argument("--html", default=None, help="HTML output path")
    parser.add_argument("--raw", default=None, help="Raw binary output path")

    # Safety / execution flags
    parser.add_argument(
        "--dangerously-perform-the-trim", action="store_true",
        help="Actually delete chunks (default: analyze only)",
    )
    parser.add_argument(
        "--safety-pct", type=int, default=90,
        help="Abort if deletion exceeds this %% per dimension (default: 90)",
    )
    parser.add_argument("--force", action="store_true", help="Override safety abort")

    args = parser.parse_args(argv)

    # --- Validation ---

    # Rule 1: exactly one of local path or SSH pair
    has_local = args.world_path is not None
    has_ssh = args.host is not None or args.remote_path is not None

    if has_local and has_ssh:
        parser.error("Specify either <world-path> or --host/--remote-path, not both.")
    if not has_local and not has_ssh:
        parser.error("Specify either <world-path> or --host + --remote-path.")
    if has_ssh and (args.host is None or args.remote_path is None):
        parser.error("--host and --remote-path must be used together.")

    # Rule 2: --threshold and --query are mutually exclusive (handled by argparse group above)

    # Rule 3: --query requires --mcaselector
    if args.query is not None and args.mcaselector is None:
        parser.error("--query requires --mcaselector.")

    # Rule 4: default threshold when neither is specified
    if args.threshold is None and args.query is None:
        args.threshold = 120

    return args
