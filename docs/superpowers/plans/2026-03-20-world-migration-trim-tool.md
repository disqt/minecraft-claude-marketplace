# World Migration Trim Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that downloads a Minecraft world via SCP, analyzes chunk usage, trims low-activity chunks with MCA Selector CLI, and leaves the result locally.

**Architecture:** Multi-module under `scripts/` with `migrate.py` as the entry point. Linear pipeline: validate -> download -> analyze -> safety check -> checkpoint -> trim -> report. Each pipeline step is a function. Tests use pytest with mocked subprocess/SCP calls. Requires running from repo root (`python -m pytest` adds CWD to sys.path so `scripts.*` imports resolve).

**Tech Stack:** Python 3.10+ stdlib (argparse, subprocess, pathlib, struct, shutil, sys), MCA Selector JAR (external), SSH/SCP

**Spec:** `docs/superpowers/specs/2026-03-20-world-migration-trim-tool-design.md`

---

## File Structure

```
scripts/
  migrate.py              # Main CLI script — argument parsing, pipeline orchestration
  migrate_regions.py      # Region file analysis — parse .mca headers, count chunks
  migrate_mca.py          # MCA Selector wrapper — select/delete commands
  migrate_remote.py       # SSH/SCP operations — download world files
  migrate_display.py      # Output formatting — stats table, report, prompts
tests/
  test_migrate_args.py    # CLI argument parsing and validation
  test_migrate_regions.py # Region header parsing and chunk counting
  test_migrate_mca.py     # MCA Selector command building
  test_migrate_remote.py  # SCP command building and dimension path mapping
  test_migrate_display.py # Table formatting and report generation
  test_migrate_e2e.py     # End-to-end pipeline with mocked externals
  fixtures/
    r.0.0.mca             # Tiny valid region file (32-chunk header, few populated entries)
    r.empty.mca            # Region file with all-zero header (no chunks)
```

Each module has one responsibility. `migrate.py` imports the others and wires the pipeline.

---

## Task 1: Region Header Parsing

**Files:**
- Create: `scripts/migrate_regions.py`
- Create: `tests/test_migrate_regions.py`
- Create: `tests/fixtures/r.0.0.mca`
- Create: `tests/fixtures/r.empty.mca`

- [ ] **Step 1: Create test fixtures — minimal .mca region files**

A region file header is 8192 bytes: 4096 bytes of location entries (1024 x 4-byte) + 4096 bytes of timestamp entries. Each location entry is 3 bytes offset + 1 byte sector count. Non-zero = chunk exists.

Create `tests/conftest.py` with a helper to generate fixtures at test collection time:

```python
# tests/conftest.py
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    """Generate binary .mca fixtures if they don't exist."""
    FIXTURES.mkdir(exist_ok=True)

    # r.0.0.mca — 5 populated chunks out of 1024
    path_5 = FIXTURES / "r.0.0.mca"
    if not path_5.exists():
        header = bytearray(8192)
        for i in range(5):
            offset = 4 * i
            header[offset + 2] = 1  # non-zero offset byte
            header[offset + 3] = 1  # sector count
        path_5.write_bytes(bytes(header))

    # r.empty.mca — all zeros (no chunks)
    path_empty = FIXTURES / "r.empty.mca"
    if not path_empty.exists():
        path_empty.write_bytes(bytes(8192))
```

- [ ] **Step 2: Write failing tests for count_chunks_in_region and count_chunks_in_directory**

```python
# tests/test_migrate_regions.py
from pathlib import Path
from scripts.migrate_regions import count_chunks_in_region, count_chunks_in_directory

FIXTURES = Path(__file__).parent / "fixtures"


def test_count_chunks_populated_region():
    assert count_chunks_in_region(FIXTURES / "r.0.0.mca") == 5


def test_count_chunks_empty_region():
    assert count_chunks_in_region(FIXTURES / "r.empty.mca") == 0


def test_count_chunks_in_directory(tmp_path):
    import shutil
    region_dir = tmp_path / "region"
    region_dir.mkdir()
    shutil.copy(FIXTURES / "r.0.0.mca", region_dir / "r.0.0.mca")
    shutil.copy(FIXTURES / "r.empty.mca", region_dir / "r.-1.0.mca")
    assert count_chunks_in_directory(region_dir) == 5


def test_count_chunks_nonexistent_dir(tmp_path):
    assert count_chunks_in_directory(tmp_path / "nope") == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_regions.py -v`
Expected: FAIL — module not found

- [ ] **Step 4: Implement migrate_regions.py**

```python
# scripts/migrate_regions.py
"""Parse Minecraft .mca region file headers to count existing chunks."""

import struct
from pathlib import Path

HEADER_ENTRIES = 1024
ENTRY_SIZE = 4  # bytes per location entry
HEADER_SIZE = HEADER_ENTRIES * ENTRY_SIZE  # 4096 bytes


def count_chunks_in_region(region_path: Path) -> int:
    """Count non-empty chunks in a single .mca file by reading its location header.

    Each region file starts with 1024 4-byte location entries.
    A non-zero entry means the chunk exists.
    """
    data = region_path.read_bytes()[:HEADER_SIZE]
    if len(data) < HEADER_SIZE:
        return 0
    count = 0
    for i in range(HEADER_ENTRIES):
        offset = i * ENTRY_SIZE
        entry = struct.unpack_from(">I", data, offset)[0]
        if entry != 0:
            count += 1
    return count


def count_chunks_in_directory(region_dir: Path) -> int:
    """Count all existing chunks across all .mca files in a region directory."""
    if not region_dir.is_dir():
        return 0
    total = 0
    for mca_file in sorted(region_dir.glob("r.*.*.mca")):
        total += count_chunks_in_region(mca_file)
    return total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_regions.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_regions.py tests/test_migrate_regions.py tests/conftest.py
git commit -m "feat: region header parser for chunk counting"
```

---

## Task 2: Dimension Path Mapping

**Files:**
- Create: `scripts/migrate_remote.py`
- Create: `tests/test_migrate_remote.py`

- [ ] **Step 1: Write failing tests for dimension path mapping and SCP command building**

```python
# tests/test_migrate_remote.py
from scripts.migrate_remote import dimension_region_subpath, build_scp_commands


def test_overworld_subpath():
    assert dimension_region_subpath("overworld") == "region"


def test_nether_subpath():
    assert dimension_region_subpath("nether") == "DIM-1/region"


def test_end_subpath():
    assert dimension_region_subpath("end") == "DIM1/region"


def test_build_scp_commands_overworld_only():
    cmds = build_scp_commands(
        host="minecraft",
        remote_path="/home/minecraft/serverfiles/world_new",
        local_path="/tmp/work/world_new",
        dimensions=["overworld"],
    )
    # level.dat + overworld region contents
    assert len(cmds) == 2
    assert any("level.dat" in cmd[1] for cmd in cmds)
    # Overworld: downloads region/* contents into local region/ dir
    region_cmd = [c for c in cmds if "region" in c[1]][0]
    assert "region/*" in region_cmd[0][-2]  # remote source has glob
    assert region_cmd[0][-1].endswith("region")  # local target is the dir


def test_build_scp_commands_all_dimensions():
    cmds = build_scp_commands(
        host="minecraft",
        remote_path="/home/minecraft/serverfiles/world_new",
        local_path="/tmp/work/world_new",
        dimensions=["overworld", "nether", "end"],
    )
    # level.dat + 3 dimension region dirs
    assert len(cmds) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_remote.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement migrate_remote.py**

```python
# scripts/migrate_remote.py
"""SSH/SCP operations for downloading Minecraft world files."""

import subprocess
import sys
from pathlib import Path

DIMENSION_SUBPATHS = {
    "overworld": "region",
    "nether": "DIM-1/region",
    "end": "DIM1/region",
}


def dimension_region_subpath(dimension: str) -> str:
    """Return the relative path from world root to the region dir for a dimension."""
    return DIMENSION_SUBPATHS[dimension]


def build_scp_commands(
    host: str,
    remote_path: str,
    local_path: str,
    dimensions: list[str],
) -> list[tuple[list[str], str]]:
    """Build SCP commands to download world files.

    Returns a list of (command_args, description) tuples.
    """
    commands = []

    # Always download level.dat
    commands.append((
        ["scp", f"{host}:{remote_path}/level.dat", f"{local_path}/level.dat"],
        f"level.dat",
    ))

    for dim in dimensions:
        subpath = dimension_region_subpath(dim)
        # Download region/* contents into local region/ dir (not the dir itself)
        # This avoids the scp -r nesting problem (region/region/)
        remote_region = f"{host}:{remote_path}/{subpath}/*"
        local_region = f"{local_path}/{subpath}"
        commands.append((
            ["scp", "-r", remote_region, local_region],
            f"{dim} region ({subpath})",
        ))

    return commands


def run_scp_commands(
    commands: list[tuple[list[str], str]],
    local_path: Path,
) -> None:
    """Execute SCP commands, creating local directories as needed."""
    for cmd_args, description in commands:
        # Ensure parent directory exists for the target
        target = Path(cmd_args[-1])
        target.parent.mkdir(parents=True, exist_ok=True)

        print(f"  Downloading {description}...", file=sys.stderr)
        result = subprocess.run(cmd_args, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"ERROR: SCP failed for {description}: {result.stderr}",
                file=sys.stderr,
            )
            sys.exit(3)


def check_ssh_connectivity(host: str) -> bool:
    """Test SSH connectivity to the host. Returns True if reachable."""
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", host, "echo ok"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "ok" in result.stdout
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_remote.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_remote.py tests/test_migrate_remote.py
git commit -m "feat: dimension path mapping and SCP command builder"
```

---

## Task 3: MCA Selector Wrapper

**Files:**
- Create: `scripts/migrate_mca.py`
- Create: `tests/test_migrate_mca.py`

- [ ] **Step 1: Write failing tests for MCA Selector command building**

```python
# tests/test_migrate_mca.py
from pathlib import Path
from scripts.migrate_mca import build_select_command, build_delete_command


def test_build_select_overworld(tmp_path):
    jar = tmp_path / "mcaselector.jar"
    world = tmp_path / "world_new"
    csv = tmp_path / "selection-overworld.csv"
    cmd = build_select_command(
        mcaselector_jar=jar, world_dir=world,
        dimension="overworld", query="InhabitedTime < 120",
        output_csv=csv,
    )
    assert cmd[0] == "java"
    assert "-jar" in cmd
    assert str(jar) == cmd[cmd.index("-jar") + 1]
    assert "--mode" in cmd
    assert "select" in cmd
    assert "--query" in cmd
    assert "InhabitedTime < 120" in cmd
    # Overworld should NOT have --region flag
    assert "--region" not in cmd


def test_build_select_nether_uses_region_flag(tmp_path):
    jar = tmp_path / "mcaselector.jar"
    world = tmp_path / "world_new"
    csv = tmp_path / "selection-nether.csv"
    cmd = build_select_command(
        mcaselector_jar=jar, world_dir=world,
        dimension="nether", query="InhabitedTime < 120",
        output_csv=csv,
    )
    assert "--region" in cmd
    region_path = Path(cmd[cmd.index("--region") + 1])
    assert region_path == world / "DIM-1" / "region"


def test_build_delete_overworld(tmp_path):
    jar = tmp_path / "mcaselector.jar"
    world = tmp_path / "world_new"
    cmd = build_delete_command(
        mcaselector_jar=jar, world_dir=world,
        dimension="overworld", query="InhabitedTime < 120",
    )
    assert "delete" in cmd
    assert "--region" not in cmd


def test_build_delete_end_uses_region_flag(tmp_path):
    jar = tmp_path / "mcaselector.jar"
    world = tmp_path / "world_new"
    cmd = build_delete_command(
        mcaselector_jar=jar, world_dir=world,
        dimension="end", query="InhabitedTime < 120",
    )
    assert "--region" in cmd
    region_path = Path(cmd[cmd.index("--region") + 1])
    assert region_path == world / "DIM1" / "region"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_mca.py -v`
Expected: FAIL — module not found

- [ ] **Step 2b: Write failing tests for count_selected_chunks**

```python
# append to tests/test_migrate_mca.py
from scripts.migrate_mca import count_selected_chunks


def test_count_selected_chunks_nonexistent(tmp_path):
    assert count_selected_chunks(tmp_path / "nope.csv") == 0


def test_count_selected_chunks_empty(tmp_path):
    csv = tmp_path / "empty.csv"
    csv.write_text("")
    assert count_selected_chunks(csv) == 0


def test_count_selected_chunks_with_entries(tmp_path):
    csv = tmp_path / "sel.csv"
    csv.write_text("0;0\n1;0\n2;0\n")
    assert count_selected_chunks(csv) == 3
```

- [ ] **Step 3: Implement migrate_mca.py**

```python
# scripts/migrate_mca.py
"""MCA Selector CLI wrapper — build and run select/delete commands."""

import subprocess
import sys
from pathlib import Path

from scripts.migrate_remote import dimension_region_subpath


def _base_command(
    mcaselector_jar: Path,
    world_dir: Path,
    dimension: str,
    mode: str,
    query: str,
) -> list[str]:
    """Build the base MCA Selector command with common flags."""
    cmd = [
        "java", "-jar", str(mcaselector_jar),
        "--mode", mode,
        "--world", str(world_dir),
        "--query", query,
    ]
    if dimension != "overworld":
        region_path = world_dir / dimension_region_subpath(dimension)
        cmd.extend(["--region", str(region_path)])
    return cmd


def build_select_command(
    mcaselector_jar: Path,
    world_dir: Path,
    dimension: str,
    query: str,
    output_csv: Path,
) -> list[str]:
    """Build MCA Selector --mode select command."""
    cmd = _base_command(mcaselector_jar, world_dir, dimension, "select", query)
    cmd.extend(["--output", str(output_csv)])
    return cmd


def build_delete_command(
    mcaselector_jar: Path,
    world_dir: Path,
    dimension: str,
    query: str,
) -> list[str]:
    """Build MCA Selector --mode delete command."""
    return _base_command(mcaselector_jar, world_dir, dimension, "delete", query)


def run_mcaselector(cmd: list[str], description: str) -> None:
    """Execute an MCA Selector command, exit on failure."""
    print(f"  {description}...", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"ERROR: MCA Selector failed: {result.stderr}",
            file=sys.stderr,
        )
        sys.exit(3)


def count_selected_chunks(csv_path: Path) -> int:
    """Count chunks in a MCA Selector selection CSV (one x;z pair per line)."""
    if not csv_path.exists():
        return 0
    text = csv_path.read_text().strip()
    if not text:
        return 0
    return len(text.splitlines())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_mca.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_mca.py tests/test_migrate_mca.py
git commit -m "feat: MCA Selector CLI command builder"
```

---

## Task 4: Display Formatting

**Files:**
- Create: `scripts/migrate_display.py`
- Create: `tests/test_migrate_display.py`

- [ ] **Step 1: Write failing tests for stats table and report formatting**

```python
# tests/test_migrate_display.py
from scripts.migrate_display import format_stats_table, format_report


def test_format_stats_table_single_dimension():
    stats = [{"dimension": "Overworld", "total": 12847, "delete": 8203, "keep": 4644}]
    table = format_stats_table(stats)
    assert "Overworld" in table
    assert "12,847" in table
    assert "8,203" in table
    assert "63.8%" in table


def test_format_stats_table_multiple_dimensions():
    stats = [
        {"dimension": "Overworld", "total": 12847, "delete": 8203, "keep": 4644},
        {"dimension": "Nether", "total": 2104, "delete": 1456, "keep": 648},
        {"dimension": "End", "total": 891, "delete": 834, "keep": 57},
    ]
    table = format_stats_table(stats)
    assert "Overworld" in table
    assert "Nether" in table
    assert "End" in table
    assert "Total" in table  # aggregate row


def test_format_stats_table_zero_chunks():
    stats = [{"dimension": "End", "total": 0, "delete": 0, "keep": 0}]
    table = format_stats_table(stats)
    assert "0.0%" in table


def test_format_safety_abort():
    from scripts.migrate_display import format_safety_abort
    msg = format_safety_abort("End", 93.6)
    assert "93.6%" in msg
    assert "End" in msg
    assert "SAFETY ABORT" in msg
    assert "--force" in msg


def test_format_report():
    stats = [
        {"dimension": "Overworld", "total": 100, "delete": 60, "keep": 40},
    ]
    report = format_report(stats, "/tmp/work/world_new", ["overworld"])
    assert "Trim complete" in report
    assert "Overworld" in report
    assert "60" in report
    assert "Next steps" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_display.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement migrate_display.py**

```python
# scripts/migrate_display.py
"""Output formatting — stats table, report, prompts."""


def format_stats_table(stats: list[dict]) -> str:
    """Format dimension stats as an aligned table.

    Each stats dict has: dimension, total, delete, keep.
    """
    header = f"{'Dimension':<15} {'Total':>8} {'Delete':>8} {'Keep':>8} {'Delete %':>10}"
    separator = "\u2500" * len(header)

    lines = [header, separator]
    agg_total = 0
    agg_delete = 0

    for s in stats:
        total = s["total"]
        delete = s["delete"]
        keep = s["keep"]
        pct = (delete / total * 100) if total > 0 else 0.0
        lines.append(
            f"{s['dimension']:<15} {total:>8,} {delete:>8,} {keep:>8,} {pct:>9.1f}%"
        )
        agg_total += total
        agg_delete += delete

    if len(stats) > 1:
        agg_keep = agg_total - agg_delete
        agg_pct = (agg_delete / agg_total * 100) if agg_total > 0 else 0.0
        lines.append(separator)
        lines.append(
            f"{'Total':<15} {agg_total:>8,} {agg_delete:>8,} {agg_keep:>8,} {agg_pct:>9.1f}%"
        )

    return "\n".join(lines)


def format_report(
    stats: list[dict],
    world_path: str,
    dimensions: list[str],
) -> str:
    """Format the post-trim report with next steps."""
    lines = ["Trim complete."]
    for s in stats:
        lines.append(f"  {s['dimension']}: deleted {s['delete']:,} chunks")

    lines.append(f"\nTrimmed world at: {world_path}/")
    lines.append("\nNext steps:")
    lines.append("  1. (Optional) Open in MCA Selector GUI to visually verify")
    lines.append("  2. Stop the Minecraft server")
    lines.append("  3. Back up the current world on the server")
    lines.append("  4. Delete server region dirs and upload trimmed ones")
    lines.append("  5. Start the server")
    lines.append("  6. Run Chunky pre-generation for the trimmed areas")
    lines.append("  7. Purge and re-render BlueMap")

    return "\n".join(lines)


def format_safety_abort(dimension: str, pct: float) -> str:
    """Format the safety abort message."""
    return (
        f"SAFETY ABORT: Would delete {pct:.1f}% of {dimension} chunks "
        f"\u2014 this looks wrong.\n"
        f"Use --force to override, or adjust --threshold / --query."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_display.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_display.py tests/test_migrate_display.py
git commit -m "feat: stats table and report formatting"
```

---

## Task 5: CLI Argument Parsing

**Files:**
- Create: `tests/test_migrate_args.py`
- Create: `scripts/migrate.py` (partial — just arg parsing)

- [ ] **Step 1: Write failing tests for argument parsing**

```python
# tests/test_migrate_args.py
import pytest
from scripts.migrate import parse_args


def test_minimal_args():
    args = parse_args([
        "--host", "minecraft",
        "--remote-path", "/home/minecraft/serverfiles/world_new",
        "--mcaselector", "./mcaselector.jar",
    ])
    assert args.host == "minecraft"
    assert args.remote_path == "/home/minecraft/serverfiles/world_new"
    assert args.dimensions == ["overworld"]
    assert args.query == "InhabitedTime < 120"  # default threshold
    assert args.headless is False
    assert args.force is False
    assert args.dry_run is False
    assert args.safety_pct == 90


def test_threshold_converts_to_query():
    args = parse_args([
        "--host", "mc", "--remote-path", "/world",
        "--mcaselector", "./mca.jar",
        "--threshold", "600",
    ])
    assert args.query == "InhabitedTime < 600"


def test_query_overrides_threshold():
    args = parse_args([
        "--host", "mc", "--remote-path", "/world",
        "--mcaselector", "./mca.jar",
        "--query", "InhabitedTime < 120 AND DataVersion < 2860",
    ])
    assert args.query == "InhabitedTime < 120 AND DataVersion < 2860"


def test_threshold_and_query_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args([
            "--host", "mc", "--remote-path", "/world",
            "--mcaselector", "./mca.jar",
            "--threshold", "120",
            "--query", "InhabitedTime < 120",
        ])


def test_all_dimensions():
    args = parse_args([
        "--host", "mc", "--remote-path", "/world",
        "--mcaselector", "./mca.jar",
        "--dimensions", "overworld", "nether", "end",
    ])
    assert args.dimensions == ["overworld", "nether", "end"]


def test_headless_and_force_flags():
    args = parse_args([
        "--host", "mc", "--remote-path", "/world",
        "--mcaselector", "./mca.jar",
        "--headless", "--force",
    ])
    assert args.headless is True
    assert args.force is True


def test_dry_run_flag():
    args = parse_args([
        "--host", "mc", "--remote-path", "/world",
        "--mcaselector", "./mca.jar",
        "--dry-run",
    ])
    assert args.dry_run is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_args.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement parse_args in migrate.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_args.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate.py tests/test_migrate_args.py
git commit -m "feat: CLI argument parsing with threshold/query handling"
```

---

## Task 6: Pipeline Orchestration

**Files:**
- Modify: `scripts/migrate.py` — add `validate`, `download`, `analyze`, `safety_check`, `checkpoint`, `trim`, `report`, and `main`
- Create: `tests/test_migrate_e2e.py`

- [ ] **Step 1: Write failing end-to-end tests with mocked externals**

```python
# tests/test_migrate_e2e.py
"""End-to-end pipeline tests with mocked SSH/SCP and MCA Selector."""
import shutil
import struct
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def make_region_dir(base: Path, dim: str, chunk_counts: list[int]) -> None:
    """Create a fake region dir with .mca files having given chunk counts."""
    from scripts.migrate_remote import dimension_region_subpath
    subpath = dimension_region_subpath(dim) if dim != "overworld" else "region"
    region_dir = base / subpath
    region_dir.mkdir(parents=True, exist_ok=True)
    for i, count in enumerate(chunk_counts):
        header = bytearray(8192)
        for j in range(count):
            offset = j * 4
            header[offset + 2] = 1  # non-zero offset
            header[offset + 3] = 1  # sector count
        (region_dir / f"r.{i}.0.mca").write_bytes(bytes(header))
    # level.dat stub
    (base / "level.dat").write_bytes(b"\x00" * 16)


def test_pipeline_dry_run(tmp_path):
    """Dry run should analyze and exit 0 without trimming."""
    world_dir = tmp_path / "world_new"
    make_region_dir(world_dir, "overworld", [100, 50])  # 150 total chunks

    # Mock SCP to do nothing (world already in place)
    # Mock MCA select to write a CSV with 80 entries
    def mock_select_run(cmd, **kwargs):
        # Find --output arg and write CSV
        if "--output" in cmd:
            csv_path = Path(cmd[cmd.index("--output") + 1])
            csv_path.write_text("\n".join(f"{i};0" for i in range(80)))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("scripts.migrate_remote.subprocess.run", return_value=MagicMock(returncode=0, stdout="ok")), \
         patch("scripts.migrate_remote.run_scp_commands"), \
         patch("scripts.migrate_mca.subprocess.run", side_effect=mock_select_run):

        from scripts.migrate import run_pipeline, parse_args
        args = parse_args([
            "--host", "mc",
            "--remote-path", "/world",
            "--mcaselector", str(tmp_path / "fake.jar"),
            "--workdir", str(tmp_path / "work"),
            "--dry-run", "--headless",
        ])
        # Point workdir at our pre-built world
        args._world_dir = world_dir
        code = run_pipeline(args)
        assert code == 0


def test_pipeline_force_overrides_safety(tmp_path):
    """--force should bypass safety abort and proceed to trim."""
    world_dir = tmp_path / "world_new"
    make_region_dir(world_dir, "overworld", [100])  # 100 total chunks

    # 95 chunks match — 95% deletion, would normally abort
    def mock_run(cmd, **kwargs):
        if "--output" in cmd:
            csv_path = Path(cmd[cmd.index("--output") + 1])
            csv_path.write_text("\n".join(f"{i};0" for i in range(95)))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("scripts.migrate_remote.subprocess.run", return_value=MagicMock(returncode=0, stdout="ok")), \
         patch("scripts.migrate_remote.run_scp_commands"), \
         patch("scripts.migrate_mca.subprocess.run", side_effect=mock_run):

        from scripts.migrate import run_pipeline, parse_args
        args = parse_args([
            "--host", "mc",
            "--remote-path", "/world",
            "--mcaselector", str(tmp_path / "fake.jar"),
            "--workdir", str(tmp_path / "work"),
            "--headless", "--force",
        ])
        args._world_dir = world_dir
        code = run_pipeline(args)
        assert code == 0  # proceeds despite 95% deletion


def test_pipeline_safety_abort(tmp_path):
    """Should abort when deletion % exceeds safety threshold."""
    world_dir = tmp_path / "world_new"
    make_region_dir(world_dir, "overworld", [100])  # 100 total chunks

    # 95 chunks match — 95% deletion
    def mock_select_run(cmd, **kwargs):
        if "--output" in cmd:
            csv_path = Path(cmd[cmd.index("--output") + 1])
            csv_path.write_text("\n".join(f"{i};0" for i in range(95)))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("scripts.migrate_remote.subprocess.run", return_value=MagicMock(returncode=0, stdout="ok")), \
         patch("scripts.migrate_remote.run_scp_commands"), \
         patch("scripts.migrate_mca.subprocess.run", side_effect=mock_select_run):

        from scripts.migrate import run_pipeline, parse_args
        args = parse_args([
            "--host", "mc",
            "--remote-path", "/world",
            "--mcaselector", str(tmp_path / "fake.jar"),
            "--workdir", str(tmp_path / "work"),
            "--headless",
            "--safety-pct", "90",
        ])
        args._world_dir = world_dir
        code = run_pipeline(args)
        assert code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_e2e.py -v`
Expected: FAIL — `run_pipeline` not found

- [ ] **Step 3: Implement the pipeline in migrate.py**

Add the following to `scripts/migrate.py` after `parse_args`:

```python
from scripts.migrate_regions import count_chunks_in_directory
from scripts.migrate_remote import (
    build_scp_commands,
    check_ssh_connectivity,
    dimension_region_subpath,
    run_scp_commands,
)
from scripts.migrate_mca import (
    build_select_command,
    build_delete_command,
    count_selected_chunks,
    run_mcaselector,
)
from scripts.migrate_display import (
    format_report,
    format_safety_abort,
    format_stats_table,
)

DIMENSION_LABELS = {
    "overworld": "Overworld",
    "nether": "Nether",
    "end": "End",
}


def validate_environment(args: argparse.Namespace) -> None:
    """Check dependencies exist. Exit 3 on failure."""
    if not args.mcaselector.exists():
        print(f"ERROR: MCA Selector JAR not found: {args.mcaselector}", file=sys.stderr)
        sys.exit(3)

    # Check java
    import subprocess
    result = subprocess.run(["java", "-version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: Java not found. MCA Selector requires Java.", file=sys.stderr)
        sys.exit(3)

    # Check SSH
    if not check_ssh_connectivity(args.host):
        print(f"ERROR: Cannot connect to SSH host: {args.host}", file=sys.stderr)
        sys.exit(3)


def check_workdir(args: argparse.Namespace) -> Path:
    """Check/create workdir. Returns the world directory path."""
    world_name = Path(args.remote_path).name
    world_dir = args.workdir / world_name

    if world_dir.exists():
        if args.headless:
            print(
                f"ERROR: Work directory exists: {world_dir}\n"
                f"Use --workdir with a different path, or remove it manually.",
                file=sys.stderr,
            )
            sys.exit(3)
        response = input(f"Previous work directory exists: {world_dir}. Overwrite? [y/N] ")
        if response.lower() != "y":
            sys.exit(1)
        import shutil
        shutil.rmtree(world_dir)

    world_dir.mkdir(parents=True, exist_ok=True)
    return world_dir


def download_world(args: argparse.Namespace, world_dir: Path) -> None:
    """Download world files from remote host."""
    print("Downloading world files...", file=sys.stderr)
    cmds = build_scp_commands(
        host=args.host,
        remote_path=args.remote_path,
        local_path=str(world_dir),
        dimensions=args.dimensions,
    )
    run_scp_commands(cmds, world_dir)
    print("Download complete.", file=sys.stderr)


def analyze_world(
    args: argparse.Namespace,
    world_dir: Path,
) -> list[dict]:
    """Analyze each dimension: count total and matching chunks."""
    print("Analyzing chunks...", file=sys.stderr)
    stats = []

    for dim in args.dimensions:
        if dim == "overworld":
            region_dir = world_dir / "region"
        else:
            region_dir = world_dir / dimension_region_subpath(dim)

        total = count_chunks_in_directory(region_dir)

        csv_path = args.workdir / f"selection-{dim}.csv"
        select_cmd = build_select_command(
            mcaselector_jar=args.mcaselector,
            world_dir=world_dir,
            dimension=dim,
            query=args.query,
            output_csv=csv_path,
        )
        run_mcaselector(select_cmd, f"Selecting {DIMENSION_LABELS[dim]} chunks")
        delete_count = count_selected_chunks(csv_path)

        stats.append({
            "dimension": DIMENSION_LABELS[dim],
            "dimension_key": dim,
            "total": total,
            "delete": delete_count,
            "keep": total - delete_count,
        })

    return stats


def safety_check(args: argparse.Namespace, stats: list[dict]) -> int | None:
    """Check deletion percentages. Returns exit code 2 if abort needed, None otherwise."""
    if args.force:
        return None

    for s in stats:
        if s["total"] == 0:
            continue
        pct = s["delete"] / s["total"] * 100
        if pct > args.safety_pct:
            msg = format_safety_abort(s["dimension"], pct)
            print(msg, file=sys.stderr)
            return 2

    return None


def checkpoint(args: argparse.Namespace, stats: list[dict]) -> int | None:
    """Interactive confirmation. Returns exit code 1 if user declines, None to proceed."""
    if args.dry_run:
        return 0
    if args.headless:
        return None

    response = input("\nProceed with trim? [y/N] ")
    if response.lower() != "y":
        return 1

    return None


def trim_world(args: argparse.Namespace, world_dir: Path) -> None:
    """Run MCA Selector delete for each dimension."""
    print("Trimming chunks...", file=sys.stderr)
    for dim in args.dimensions:
        delete_cmd = build_delete_command(
            mcaselector_jar=args.mcaselector,
            world_dir=world_dir,
            dimension=dim,
            query=args.query,
        )
        run_mcaselector(delete_cmd, f"Trimming {DIMENSION_LABELS[dim]}")
    print("Trim complete.", file=sys.stderr)


def run_pipeline(args: argparse.Namespace) -> int:
    """Execute the full migration pipeline. Returns exit code."""
    # Use pre-set world_dir for testing, otherwise check/create
    world_dir = getattr(args, "_world_dir", None)

    if world_dir is None:
        validate_environment(args)
        world_dir = check_workdir(args)
        download_world(args, world_dir)

    stats = analyze_world(args, world_dir)

    # Print stats table
    table = format_stats_table(stats)
    print(f"\n{table}\n", file=sys.stderr)

    # Safety check
    abort_code = safety_check(args, stats)
    if abort_code is not None:
        return abort_code

    # Checkpoint / dry-run gate
    gate_code = checkpoint(args, stats)
    if gate_code is not None:
        return gate_code

    # Trim
    trim_world(args, world_dir)

    # Report
    if args.headless:
        print(str(world_dir))  # stdout: just the path
        report = format_report(stats, str(world_dir), args.dimensions)
        print(report, file=sys.stderr)
    else:
        report = format_report(stats, str(world_dir), args.dimensions)
        print(f"\n{report}")

    return 0


def main() -> None:
    args = parse_args()
    code = run_pipeline(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/test_migrate_e2e.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full test suite**

Run: `cd C:/Users/leole/Documents/code/minecraft && python -m pytest tests/ -v`
Expected: All tests pass (should be ~21 tests total)

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate.py tests/test_migrate_e2e.py
git commit -m "feat: pipeline orchestration — validate, download, analyze, trim, report"
```

---

## Task 7: Manual Smoke Test

**Files:** None (verification only)

- [ ] **Step 1: Verify --help works**

Run: `cd C:/Users/leole/Documents/code/minecraft && python scripts/migrate.py --help`
Expected: Full help text with all arguments listed

- [ ] **Step 2: Verify --dry-run against real server**

This requires MCA Selector JAR to be downloaded. If not available, skip.

```bash
python scripts/migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --mcaselector /path/to/mcaselector.jar \
  --dimensions overworld \
  --dry-run
```

Expected: Downloads overworld, prints stats table, exits 0 without trimming.

- [ ] **Step 3: Commit any fixes from smoke test**

```bash
git add -A && git commit -m "fix: smoke test adjustments"
```

---

## Task Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Region header parsing | 4 |
| 2 | Dimension path mapping + SCP builder | 4 |
| 3 | MCA Selector command builder | 7 |
| 4 | Display formatting | 5 |
| 5 | CLI argument parsing | 7 |
| 6 | Pipeline orchestration (wires everything together) | 3 |
| 7 | Manual smoke test | — |
