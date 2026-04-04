# Census Forceload Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `--auto` with `--force` (default) and `--lazy` chunk strategies so the census can run unattended on cron.

**Architecture:** Default mode forceloads zone chunks via tmux `/forceload` commands before the pipeline and unforceloads after. `--lazy` probes chunks and skips unloaded zones. The players-online gate is removed entirely.

**Tech Stack:** Python 3, SQLite, PaperMC tmux console

**Spec:** `docs/superpowers/specs/2026-04-04-census-forceload-design.md`

**Census tool:** `/home/leo/documents/code/disqt.com/minecraft/villager-census/`

---

## File Structure

```
villager-census/
  census_zones.py            # Modify: add zone_bounds() helper
  census_collect.py          # Modify: add forceload_zones(), unforceload_zones()
  census.py                  # Modify: replace --auto with --lazy, wire forceload lifecycle
  tests/test_census_zones.py # Modify: add zone_bounds tests
  tests/test_census_collect.py # Modify: add forceload tests
  tests/test_census_cli.py   # Modify: replace --auto tests with --lazy and force tests
```

---

### Task 1: Add `zone_bounds` helper to census_zones.py

**Files:**
- Modify: `villager-census/census_zones.py:73-92` (add after existing `bounding_box`)
- Modify: `villager-census/tests/test_census_zones.py`

- [ ] **Step 1: Write test for zone_bounds**

Add to `tests/test_census_zones.py`:

```python
from census_zones import zone_bounds

def test_zone_bounds_rect():
    zone = {"name": "a", "type": "rect", "x_min": 100, "z_min": -200, "x_max": 300, "z_max": -50}
    assert zone_bounds(zone) == (100, -200, 300, -50)

def test_zone_bounds_circle():
    zone = {"name": "b", "type": "circle", "center_x": 150, "center_z": -100, "radius": 50}
    assert zone_bounds(zone) == (100, -150, 200, -50)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/leo/documents/code/disqt.com/minecraft/villager-census
python -m pytest tests/test_census_zones.py::test_zone_bounds_rect tests/test_census_zones.py::test_zone_bounds_circle -v
```

Expected: FAIL — `zone_bounds` not found.

- [ ] **Step 3: Implement zone_bounds**

In `census_zones.py`, add after `bounding_box`:

```python
def zone_bounds(zone):
    """Return (x_min, z_min, x_max, z_max) for a single zone."""
    if zone["type"] == "rect":
        return zone["x_min"], zone["z_min"], zone["x_max"], zone["z_max"]
    elif zone["type"] == "circle":
        r = zone["radius"]
        return (zone["center_x"] - r, zone["center_z"] - r,
                zone["center_x"] + r, zone["center_z"] + r)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_census_zones.py -v
```

Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add census_zones.py tests/test_census_zones.py
git commit -m "feat(census): add zone_bounds helper for single-zone bounding box"
```

---

### Task 2: Add forceload/unforceload to census_collect.py

**Files:**
- Modify: `villager-census/census_collect.py:63` (add before `check_chunks_loaded`)
- Modify: `villager-census/tests/test_census_collect.py`

- [ ] **Step 1: Write tests for forceload_zones and unforceload_zones**

Add to `tests/test_census_collect.py`:

```python
from census_collect import forceload_zones, unforceload_zones

def test_forceload_zones_sends_correct_commands():
    """forceload_zones sends /forceload add with chunk coords for each zone."""
    zones = [
        {"name": "a", "type": "rect", "x_min": 3090, "z_min": -1040, "x_max": 3220, "z_max": -980},
    ]
    sent = []
    with (
        patch("census_collect._send_tmux", side_effect=lambda cmd: sent.append(cmd)),
        patch("census_collect.time.sleep"),
    ):
        forceload_zones(zones)

    # Block coords >> 4 = chunk coords
    # 3090 >> 4 = 193, -1040 >> 4 = -65, 3220 >> 4 = 201, -980 >> 4 = -62 (arithmetic shift)
    assert any("forceload add 193 -65 201 -62" in cmd for cmd in sent), f"Commands: {sent}"


def test_forceload_zones_multiple_zones():
    """forceload_zones sends one command per zone."""
    zones = [
        {"name": "a", "type": "rect", "x_min": 0, "z_min": 0, "x_max": 160, "z_max": 160},
        {"name": "b", "type": "rect", "x_min": 320, "z_min": 320, "x_max": 480, "z_max": 480},
    ]
    sent = []
    with (
        patch("census_collect._send_tmux", side_effect=lambda cmd: sent.append(cmd)),
        patch("census_collect.time.sleep"),
    ):
        forceload_zones(zones)

    forceload_cmds = [c for c in sent if "forceload add" in c]
    assert len(forceload_cmds) == 2


def test_unforceload_zones_sends_remove():
    """unforceload_zones sends /forceload remove for each zone."""
    zones = [
        {"name": "a", "type": "rect", "x_min": 3090, "z_min": -1040, "x_max": 3220, "z_max": -980},
    ]
    sent = []
    with (
        patch("census_collect._send_tmux", side_effect=lambda cmd: sent.append(cmd)),
        patch("census_collect.time.sleep"),
    ):
        unforceload_zones(zones)

    assert any("forceload remove 193 -65 201 -62" in cmd for cmd in sent), f"Commands: {sent}"


def test_forceload_zones_circle():
    """Circle zones use their bounding box for forceload."""
    zones = [
        {"name": "c", "type": "circle", "center_x": 160, "center_z": -160, "radius": 80},
    ]
    sent = []
    with (
        patch("census_collect._send_tmux", side_effect=lambda cmd: sent.append(cmd)),
        patch("census_collect.time.sleep"),
    ):
        forceload_zones(zones)

    # bounds: (80, -240, 240, -80) >> 4 = (5, -15, 15, -5)
    assert any("forceload add 5 -15 15 -5" in cmd for cmd in sent), f"Commands: {sent}"


def test_forceload_zones_sleeps_after():
    """forceload_zones sleeps 2s after all commands for chunks to load."""
    zones = [
        {"name": "a", "type": "rect", "x_min": 0, "z_min": 0, "x_max": 16, "z_max": 16},
    ]
    sleep_calls = []
    with (
        patch("census_collect._send_tmux"),
        patch("census_collect.time.sleep", side_effect=lambda s: sleep_calls.append(s)),
    ):
        forceload_zones(zones)

    # Last sleep should be 2s (chunk load wait)
    assert sleep_calls[-1] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_census_collect.py::test_forceload_zones_sends_correct_commands -v
```

Expected: FAIL — `forceload_zones` not found.

- [ ] **Step 3: Implement forceload_zones and unforceload_zones**

In `census_collect.py`, add before `check_chunks_loaded` (line 63):

```python
def forceload_zones(zones):
    """Send /forceload add for each zone's bounding box in chunk coordinates."""
    from census_zones import zone_bounds

    for zone in zones:
        x_min, z_min, x_max, z_max = zone_bounds(zone)
        cx_min, cz_min = x_min >> 4, z_min >> 4
        cx_max, cz_max = x_max >> 4, z_max >> 4
        _send_tmux(f"forceload add {cx_min} {cz_min} {cx_max} {cz_max}")
        time.sleep(0.3)

    time.sleep(2)  # wait for chunks to load


def unforceload_zones(zones):
    """Send /forceload remove for each zone's bounding box in chunk coordinates."""
    from census_zones import zone_bounds

    for zone in zones:
        x_min, z_min, x_max, z_max = zone_bounds(zone)
        cx_min, cz_min = x_min >> 4, z_min >> 4
        cx_max, cz_max = x_max >> 4, z_max >> 4
        _send_tmux(f"forceload remove {cx_min} {cz_min} {cx_max} {cz_max}")
        time.sleep(0.3)
```

- [ ] **Step 4: Run all forceload tests**

```bash
python -m pytest tests/test_census_collect.py -v
```

Expected: ALL PASS (new forceload tests + existing tests).

- [ ] **Step 5: Commit**

```bash
git add census_collect.py tests/test_census_collect.py
git commit -m "feat(census): add forceload_zones and unforceload_zones"
```

---

### Task 3: Replace --auto with --lazy and forceload in census.py

**Files:**
- Modify: `villager-census/census.py:345-374` (`_build_cron_command`), `:425-540` (CLI `main()`)
- Modify: `villager-census/census.py:10-36` (imports)

- [ ] **Step 1: Update imports**

In `census.py`, add `forceload_zones` and `unforceload_zones` to the imports from `census_collect`:

```python
from census_collect import (
    check_chunks_loaded,
    check_players_online,
    collect_villager_dumps,
    collect_villager_dumps_box,
    configure as configure_transport,
    forceload_zones,
    get_poi_files,
    get_player_position,
    unforceload_zones,
)
```

- [ ] **Step 2: Replace `--auto` flag with `--lazy`**

In `main()`, replace line 432:

```python
    parser.add_argument("--auto", action="store_true",
                        help="Cron-friendly: check chunk loading, skip gracefully, log runs")
```

With:

```python
    parser.add_argument("--lazy", action="store_true",
                        help="Skip zones with unloaded chunks instead of forceloading")
```

- [ ] **Step 3: Rewrite the chunk strategy block in main()**

Replace the block from `timestamp = datetime.now(...)` through `summary = run_census(...)` and the `if args.auto:` census_run logging (lines 507-544) with:

```python
    timestamp = datetime.now(timezone.utc).isoformat()
    skipped_zones = []

    if args.lazy:
        # Lazy mode: probe chunks, skip unloaded zones
        loaded_names = check_chunks_loaded(zones)
        if not loaded_names:
            conn = init_db(args.db)
            insert_census_run(conn, timestamp=timestamp,
                              status="skipped_no_chunks",
                              reason="No zones have loaded chunks")
            conn.close()
            print(f"[{timestamp}] Skipped: no zones have loaded chunks")
            return

        all_zone_names = {z["name"] for z in zones}
        skipped_zones = sorted(all_zone_names - set(loaded_names))
        zones = [z for z in zones if z["name"] in loaded_names]

        summary = run_census(
            db_path=args.db, zones=zones, poi_regions=poi_regions,
            notes=args.notes, skipped_zones=skipped_zones,
        )

        conn = init_db(args.db)
        insert_census_run(conn, timestamp=timestamp, status="completed",
                          snapshot_id=summary["snapshot_id"])
        conn.close()
    else:
        # Force mode (default): forceload chunks, run census, unforceload
        forceload_zones(zones)
        try:
            summary = run_census(
                db_path=args.db, zones=zones, poi_regions=poi_regions,
                notes=args.notes, skipped_zones=skipped_zones,
            )
        finally:
            unforceload_zones(zones)
```

- [ ] **Step 4: Update `_build_cron_command` to use `--lazy`**

In `_build_cron_command`, replace line 351:

```python
    parts = [python, script, "--auto", "--db", db]
```

With:

```python
    parts = [python, script, "--lazy", "--db", db]
```

- [ ] **Step 5: Run existing tests to check what breaks**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: Several `--auto` tests fail (expected — we'll fix them in Task 4).

- [ ] **Step 6: Commit**

```bash
git add census.py
git commit -m "feat(census): replace --auto with --lazy flag and forceload default"
```

---

### Task 4: Update CLI tests for --lazy and force modes

**Files:**
- Modify: `villager-census/tests/test_census_cli.py:243-322` (replace --auto tests)

- [ ] **Step 1: Replace the `--auto` test section**

Replace the entire `# --- --auto mode ---` section (lines 243-321) with:

```python
# --- --lazy mode ---

def test_cli_lazy_no_loaded_chunks_skips(toml_file, db_file, capsys):
    """--lazy with no loaded chunks logs a skip and exits cleanly."""
    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--lazy", "--db", db_file]),
        patch("census.check_chunks_loaded", return_value=[]),
    ):
        census.main()

    output = capsys.readouterr().out
    assert "Skipped: no zones have loaded chunks" in output

    conn = init_db(db_file)
    cur = conn.execute("SELECT status FROM census_runs")
    assert cur.fetchone()["status"] == "skipped_no_chunks"
    conn.close()


def test_cli_lazy_partial_zones(toml_file, db_file, capsys):
    """--lazy with only some zones loaded runs a partial census."""
    partial_summary = {**MOCK_SUMMARY, "zones": {"center": {"villagers": 5, "beds": 3, "bells": 0}}}

    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--lazy", "--db", db_file]),
        patch("census.check_chunks_loaded", return_value=["center"]),
        patch("census.run_census", return_value=partial_summary) as mock_run,
    ):
        census.main()

    zones = mock_run.call_args.kwargs["zones"]
    assert len(zones) == 1
    assert zones[0]["name"] == "center"
    assert "outskirts" in mock_run.call_args.kwargs["skipped_zones"]

    conn = init_db(db_file)
    cur = conn.execute("SELECT status, snapshot_id FROM census_runs")
    row = cur.fetchone()
    assert row["status"] == "completed"
    assert row["snapshot_id"] == partial_summary["snapshot_id"]
    conn.close()


def test_cli_lazy_prints_skipped_zones(toml_file, db_file, capsys):
    """--lazy prints which zones were skipped."""
    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--lazy", "--db", db_file]),
        patch("census.check_chunks_loaded", return_value=["center"]),
        patch("census.run_census", return_value=MOCK_SUMMARY),
    ):
        census.main()

    output = capsys.readouterr().out
    assert "Skipped (chunks not loaded): outskirts" in output


# --- force mode (default) ---

def test_cli_force_calls_forceload(toml_file, db_file, capsys):
    """Default mode forceloads zones before census and unforceloads after."""
    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--db", db_file]),
        patch("census.forceload_zones") as mock_fl,
        patch("census.unforceload_zones") as mock_ufl,
        patch("census.run_census", return_value=MOCK_SUMMARY),
    ):
        census.main()

    mock_fl.assert_called_once()
    mock_ufl.assert_called_once()
    # Zones passed to forceload match the config
    zones = mock_fl.call_args[0][0]
    zone_names = {z["name"] for z in zones}
    assert "center" in zone_names


def test_cli_force_unforceloads_on_error(toml_file, db_file):
    """Force mode unforceloads even if the census pipeline raises."""
    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--db", db_file]),
        patch("census.forceload_zones"),
        patch("census.unforceload_zones") as mock_ufl,
        patch("census.run_census", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
    ):
        census.main()

    mock_ufl.assert_called_once()
```

- [ ] **Step 2: Update the cron install test**

In `test_cli_install_cron`, change line 350:

```python
    assert "--auto" in crontab
```

To:

```python
    assert "--lazy" in crontab
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_census_cli.py
git commit -m "test(census): replace --auto tests with --lazy and force mode tests"
```

---

### Task 5: Update pipeline tests for removed players-online gate

**Files:**
- Modify: `villager-census/tests/test_census_pipeline.py:206-215` (if any auto-mode pipeline tests exist)

- [ ] **Step 1: Check for stale mocks**

Search for `check_players_online` in pipeline tests. The mock in `_run_with_mocks` (line 42) is still needed because `run_census` calls `check_players_online` internally for snapshot metadata. Verify this mock still works correctly.

```bash
python -m pytest tests/test_census_pipeline.py -v
```

Expected: ALL PASS (no changes needed if mocks are correct).

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS.

- [ ] **Step 3: Commit (only if changes were needed)**

```bash
git add tests/test_census_pipeline.py
git commit -m "test(census): update pipeline tests for forceload mode"
```

---

### Task 6: Update existing cron on VPS

- [ ] **Step 1: Re-install the cron job**

```bash
ssh dev "cd /home/dev/villager-census && python census.py --config zones.toml --install 30 --db census.db"
```

Expected: `Installed cron: every 30 min` with `--lazy` in the cron line.

- [ ] **Step 2: Verify cron was updated**

```bash
ssh dev "crontab -l | grep villager-census"
```

Expected: Shows `--lazy` instead of `--auto`.

- [ ] **Step 3: Run a manual force-mode census**

```bash
ssh dev "cd /home/dev/villager-census && python census.py --config zones.toml --db census.db"
```

Expected: Census completes with forceload messages. Bell and villager data populated.

- [ ] **Step 4: Verify bells in output**

Check that the summary includes `Bells:` count in the zone table.
