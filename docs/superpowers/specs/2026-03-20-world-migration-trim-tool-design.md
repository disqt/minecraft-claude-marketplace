# World Migration Trim Tool

## Purpose

A Python CLI tool that downloads a Minecraft world from a remote host, analyzes and trims low-activity chunks using MCA Selector CLI, and leaves the trimmed world locally. Designed for major version migrations where old terrain should regenerate with new world generation.

The tool is read-only with respect to the remote host — it downloads via SCP but never modifies remote files.

## CLI Interface

```
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --dimensions overworld nether end \
  --threshold 120 \
  --mcaselector /path/to/mcaselector.jar \
  --workdir ./migration-work \
  --headless \
  --force \
  --dry-run \
  --safety-pct 90
```

### Arguments

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--host` | yes | — | SSH host (uses ~/.ssh/config) |
| `--remote-path` | yes | — | Remote world directory path |
| `--dimensions` | no | `overworld` | Space-separated list: `overworld`, `nether`, `end` |
| `--threshold` | no | — | InhabitedTime threshold in ticks. Shorthand for `--query "InhabitedTime < {n}"` |
| `--query` | no | — | Raw MCA Selector query string (full syntax). Mutually exclusive with `--threshold` |
| `--mcaselector` | yes | — | Path to MCA Selector JAR |
| `--workdir` | no | `./migration-work` | Local working directory for downloaded/trimmed world |
| `--headless` | no | `false` | Skip all interactive prompts |
| `--force` | no | `false` | Override safety abort |
| `--dry-run` | no | `false` | Run analysis and safety check only, do not trim |
| `--safety-pct` | no | `90` | Abort if trim would delete more than this % of chunks |

If neither `--threshold` nor `--query` is given, defaults to `--threshold 120`. Providing `--query` suppresses the default threshold. The two flags are mutually exclusive.

### Examples

```bash
# Simple — trim chunks with less than 6 seconds of player activity
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --mcaselector ./mcaselector.jar

# All dimensions, custom threshold
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --dimensions overworld nether end \
  --threshold 600 \
  --mcaselector ./mcaselector.jar

# Precise query — target pre-1.18 chunks only
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --query "InhabitedTime < 120 AND DataVersion < 2860" \
  --mcaselector ./mcaselector.jar

# Headless for scripting
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --dimensions overworld nether end \
  --threshold 120 \
  --mcaselector ./mcaselector.jar \
  --headless

# Dry run — analyze only, don't trim
python migrate.py \
  --host minecraft \
  --remote-path /home/minecraft/serverfiles/world_new \
  --dimensions overworld nether end \
  --mcaselector ./mcaselector.jar \
  --dry-run
```

## Pipeline

### Step 1: Validate Environment

Check that Java is available, the MCA Selector JAR exists, and SSH connectivity to the host works. Fail with exit code 3 if any dependency is missing.

If `{workdir}/{world_name}/` already exists from a previous run, prompt for confirmation in interactive mode ("Previous work directory exists. Overwrite? [y/N]"). In headless mode, abort with exit code 3 and a message suggesting `--workdir` with a different path or manual cleanup.

### Step 2: Download

SCP the world files from the remote host to `{workdir}/{world_name}/`.

Downloads:
- `{remote-path}/level.dat` (required by MCA Selector's `--world` flag)
- `{remote-path}/region/*.mca` (if overworld selected)
- `{remote-path}/DIM-1/region/*.mca` (if nether selected)
- `{remote-path}/DIM1/region/*.mca` (if end selected)

Nothing else is downloaded — no playerdata, datapacks, or other world files. The local directory mirrors the remote structure.

Note: world region folders can be large (5-20+ GB). The script prints download progress. If the download is interrupted, the partial workdir is left in place for manual cleanup.

### Step 3: Analyze

For each selected dimension, count total chunks and chunks matching the query.

**Total chunk count**: Parse `.mca` region file headers using Python's `struct` module. Each region file has a 4096-byte header containing 1024 4-byte entries (one per chunk). Non-zero entries indicate existing chunks. Sum across all region files for the dimension.

**Matching chunk count**: Run MCA Selector CLI `--mode select` to produce a selection file, then count entries:

```bash
java -jar mcaselector.jar \
  --mode select \
  --world {workdir}/{world_name} \
  --region {dimension_region_path} \
  --query "{query}" \
  --output {workdir}/selection-{dimension}.csv
```

The selection CSV contains one `x;z` pair per line per matching chunk. Line count = matching chunks.

For non-overworld dimensions, use `--region` to point MCA Selector at the correct region directory (e.g., `--region {workdir}/{world_name}/DIM-1/region`).

Output:
```
Dimension      Total    Delete    Keep    Delete %
─────────────────────────────────────────────────
Overworld      12,847   8,203     4,644   63.8%
Nether          2,104   1,456       648   69.2%
End               891     834        57   93.6%
─────────────────────────────────────────────────
Total          15,842  10,493     5,349   66.2%
```

In headless mode, the same table is printed to stderr.

### Step 4: Safety Check

If any single dimension's deletion percentage exceeds `--safety-pct` (default 90%), the script aborts with exit code 2:

```
SAFETY ABORT: Would delete 93.6% of End chunks — this looks wrong.
Use --force to override, or adjust --threshold / --query.
```

The check is per-dimension, not aggregate.

In headless mode without `--force`, a safety check violation still causes exit code 2. Both `--headless --force` are needed for fully unattended operation that ignores safety thresholds.

### Step 5: Checkpoint / Dry-Run Gate

If `--dry-run` is set, print the analysis table and exit with code 0. No trim is performed.

In interactive mode (no `--dry-run`), prompt:

```
Proceed with trim? [y/N]
```

If the user declines, exit with code 1.

In headless mode, proceed automatically.

### Step 6: Trim

Run MCA Selector CLI `--mode delete` for each selected dimension:

```bash
# Overworld
java -jar mcaselector.jar \
  --mode delete \
  --world {workdir}/{world_name} \
  --query "{query}"

# Nether (use --region to target DIM-1)
java -jar mcaselector.jar \
  --mode delete \
  --world {workdir}/{world_name} \
  --region {workdir}/{world_name}/DIM-1/region \
  --query "{query}"

# End (use --region to target DIM1)
java -jar mcaselector.jar \
  --mode delete \
  --world {workdir}/{world_name} \
  --region {workdir}/{world_name}/DIM1/region \
  --query "{query}"
```

### Step 7: Report

Print a summary and the path to the trimmed world.

Interactive mode:
```
Trim complete.
  Overworld: deleted 8,203 chunks
  Nether:    deleted 1,456 chunks
  End:       deleted 834 chunks

Trimmed world at: ./migration-work/world_new/

Next steps:
  1. (Optional) Open in MCA Selector GUI to visually verify
  2. Stop the Minecraft server
  3. Back up the current world on the server
  4. Delete server region dirs and upload trimmed ones:
       ssh minecraft "rm -rf /home/.../world_new/region"
       scp -r ./migration-work/world_new/region minecraft:/home/.../world_new/
       (repeat for DIM-1/region, DIM1/region as applicable)
  5. Start the server
  6. Run Chunky pre-generation for the trimmed areas
  7. Purge and re-render BlueMap
```

Headless mode: print only the trimmed world path to stdout, summary to stderr.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (or dry-run complete) |
| 1 | User aborted at checkpoint |
| 2 | Safety abort — deletion % exceeded safety-pct |
| 3 | Dependency/environment error (missing JAR, SSH failed, workdir conflict) |

## Dimension Folder Structure

Minecraft stores dimensions within the world folder:

```
world_new/
  level.dat         ← World metadata (downloaded, not modified)
  region/           ← Overworld .mca files
  DIM-1/
    region/         ← Nether .mca files
  DIM1/
    region/         ← End .mca files
```

## Scope Boundaries

The script does NOT:
- Stop or start the Minecraft server
- Upload the trimmed world back to the remote host
- Trigger Chunky pre-generation
- Trigger BlueMap purge/re-render
- Modify any files on the remote host

These are left to the operator (or a wrapping skill/script) because they involve shared server state and should be done with awareness of who's online.

## Dependencies

- **Python 3.10+** (stdlib only — argparse, subprocess, pathlib, shutil, struct)
- **Java** (for MCA Selector CLI)
- **MCA Selector JAR** (user provides path)
- **SSH/SCP** (configured in ~/.ssh/config for the target host)

No pip dependencies. The script uses only the Python standard library.

## Claude Code Skill

A companion skill (`/migrate-world` or similar) serves as the knowledge layer:
- Knows when to suggest running the script (major MC version update, terrain generation changes)
- Knows the right parameters for the user's server setup
- Can adapt if MCA Selector CLI syntax changes or a better tool emerges
- Provides the "what to do next" guidance after the trim

The skill invokes the script but does not duplicate its logic.

## File Location

`scripts/migrate.py` in the minecraft repository root.
