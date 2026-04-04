# Census Entity Disk-Read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace tmux log-scraping villager collection with direct reads of `world/entities/*.mca` files, plus an mtime-based noop gate.

**Architecture:** New `census_entities.py` module parses entity `.mca` files using the existing NBT reader from `census_poi.py`. The `census_collect.py` module gains `save_all()`, `get_entity_files()`, and `get_entity_mtimes()` functions. `census.py` drops the `--lazy`/forceload lifecycle and adds an mtime noop gate. `census_db.py` gains an `entity_mtimes` column on `census_runs`.

**Tech Stack:** Python stdlib (struct, zlib, io, json, sqlite3), existing NBT reader

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `villager-census/census_entities.py` | Create | Parse entity `.mca` files, extract villager dicts |
| `villager-census/census_collect.py` | Modify | Add `save_all()`, `get_entity_files()`, `get_entity_mtimes()`, `entity_region_coords()`; remove forceload functions |
| `villager-census/census_db.py` | Modify | Add `entity_mtimes` column migration to `census_runs` |
| `villager-census/census.py` | Modify | Replace tmux collection with disk reads, add mtime gate, remove `--lazy`/forceload |
| `villager-census/tests/test_census_entities.py` | Create | Tests for entity region parsing and NBT-to-villager mapping |
| `villager-census/tests/test_census_collect.py` | Modify | Add tests for `save_all`, `get_entity_files`, `get_entity_mtimes`; remove forceload tests |
| `villager-census/tests/test_census_cli.py` | Modify | Replace `--lazy`/forceload tests with mtime gate tests |
| `villager-census/tests/test_census_pipeline.py` | Modify | Update mocks to use entity disk-read functions |

---

### Task 1: Add `entity_mtimes` column migration to `census_db.py`

**Files:**
- Modify: `villager-census/census_db.py:161-178` (`_migrate` function)
- Modify: `villager-census/census_db.py:212-220` (`insert_census_run` function)
- Test: `villager-census/tests/test_census_db_migration.py`

- [ ] **Step 1: Write the failing test for the migration**

In `tests/test_census_db_migration.py`, add:

```python
def test_migrate_adds_entity_mtimes_column():
    """Migration adds entity_mtimes TEXT column to census_runs."""
    conn = init_db(":memory:")
    cur = conn.execute("PRAGMA table_info(census_runs)")
    cols = {row[1] for row in cur.fetchall()}
    assert "entity_mtimes" in cols
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd villager-census && python -m pytest tests/test_census_db_migration.py::test_migrate_adds_entity_mtimes_column -v`
Expected: FAIL with `AssertionError: assert 'entity_mtimes' in {...}`

- [ ] **Step 3: Add the migration**

In `census_db.py`, add to `_migrate()` after the existing bell_count migration:

```python
    cur = conn.execute("PRAGMA table_info(census_runs)")
    cols = {row[1] for row in cur.fetchall()}
    if "entity_mtimes" not in cols:
        conn.execute("ALTER TABLE census_runs ADD COLUMN entity_mtimes TEXT")
```

- [ ] **Step 4: Update `insert_census_run` to accept `entity_mtimes`**

Change the signature and SQL in `insert_census_run`:

```python
def insert_census_run(conn, *, timestamp, status, reason=None, snapshot_id=None, entity_mtimes=None):
    """Log a census run attempt. Status: 'completed', 'skipped_no_changes', etc."""
    cur = conn.execute(
        """
        INSERT INTO census_runs (timestamp, status, reason, snapshot_id, entity_mtimes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (timestamp, status, reason, snapshot_id, entity_mtimes),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd villager-census && python -m pytest tests/test_census_db_migration.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests to verify no regressions**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: 114 passed

- [ ] **Step 7: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census_db.py villager-census/tests/test_census_db_migration.py
git commit -m "feat(census): add entity_mtimes column to census_runs table"
```

---

### Task 2: Create `census_entities.py` with `nbt_to_villager()`

**Files:**
- Create: `villager-census/census_entities.py`
- Create: `villager-census/tests/test_census_entities.py`

This task implements the NBT-to-villager mapping function. The `.mca` region parser comes in Task 3.

- [ ] **Step 1: Write the failing test for basic field mapping**

Create `tests/test_census_entities.py`:

```python
"""Tests for census_entities.py — entity region file parser."""

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from census_entities import nbt_to_villager


def _make_villager_nbt(**overrides):
    """Build a minimal NBT compound dict for a villager entity."""
    nbt = {
        "id": "minecraft:villager",
        "UUID": [346464738, -1288157012, -1558611273, 949520682],
        "Pos": [3173.04, 70.0, -755.05],
        "Paper.Origin": [3145.95, 63.94, -1006.46],
        "Paper.SpawnReason": "BREEDING",
        "VillagerData": {
            "type": "minecraft:taiga",
            "profession": "minecraft:fisherman",
            "level": 1,
        },
        "Health": 16.0,
        "FoodLevel": 0,
        "Xp": 0,
        "Spigot.ticksLived": 821095,
        "Age": 0,
        "OnGround": 1,
        "RestocksToday": 0,
        "LastRestock": 1001127489,
        "LastGossipDecay": 1024984001,
        "Brain": {"memories": {}},
        "Offers": {"Recipes": []},
        "Inventory": [],
        "Gossips": [],
    }
    nbt.update(overrides)
    return nbt


def test_nbt_to_villager_basic():
    """All basic fields are extracted from a complete NBT dict."""
    nbt = _make_villager_nbt()
    v = nbt_to_villager(nbt)

    assert v["uuid"] == "14a5a2e2-b37a-6e2c-a302-f4b7389dc42a"
    assert v["pos_x"] == pytest.approx(3173.04)
    assert v["pos_y"] == pytest.approx(70.0)
    assert v["pos_z"] == pytest.approx(-755.05)
    assert v["origin_x"] == pytest.approx(3145.95)
    assert v["origin_y"] == pytest.approx(63.94)
    assert v["origin_z"] == pytest.approx(-1006.46)
    assert v["spawn_reason"] == "BREEDING"
    assert v["profession"] == "fisherman"
    assert v["profession_level"] == 1
    assert v["villager_type"] == "taiga"
    assert v["health"] == pytest.approx(16.0)
    assert v["food_level"] == 0
    assert v["xp"] == 0
    assert v["ticks_lived"] == 821095
    assert v["age"] == 0
    assert v["on_ground"] == 1
    assert v["restocks_today"] == 0
    assert v["last_restock"] == 1001127489
    assert v["last_gossip_decay"] == 1024984001
    assert v["trades"] == []
    assert v["inventory"] == []
    assert v["gossip"] == []


def test_nbt_to_villager_missing_fields():
    """Optional fields default to None/empty when absent."""
    nbt = {
        "id": "minecraft:villager",
        "UUID": [0, 0, 0, 1],
        "Pos": [0.0, 64.0, 0.0],
        "VillagerData": {
            "type": "minecraft:plains",
            "profession": "minecraft:none",
            "level": 1,
        },
        "Health": 20.0,
    }
    v = nbt_to_villager(nbt)

    assert v["uuid"] == "00000000-0000-0000-0000-000000000001"
    assert v["origin_x"] is None
    assert v["spawn_reason"] is None
    assert v["food_level"] is None
    assert v["ticks_lived"] is None
    assert v["home_x"] is None
    assert v["last_slept"] is None
    assert v["trades"] == []
    assert v["inventory"] == []
    assert v["gossip"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd villager-census && python -m pytest tests/test_census_entities.py::test_nbt_to_villager_basic -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'census_entities'`

- [ ] **Step 3: Implement `census_entities.py` with `nbt_to_villager()`**

Create `villager-census/census_entities.py`:

```python
"""Entity region file parser — extracts villager data from world/entities/*.mca files."""

from census_parse import ints_to_uuid


def _strip_ns(s):
    """Strip 'minecraft:' prefix from a namespaced ID."""
    if s and s.startswith("minecraft:"):
        return s[len("minecraft:"):]
    return s


def nbt_to_villager(nbt):
    """Convert an NBT compound dict for a villager entity to a villager dict.

    Returns the same dict shape as census_parse.parse_entity_line().
    """
    # UUID
    uuid_ints = nbt.get("UUID", [0, 0, 0, 0])
    uuid = ints_to_uuid(uuid_ints)

    # Position
    pos = nbt.get("Pos", [0.0, 0.0, 0.0])
    pos_x, pos_y, pos_z = pos[0], pos[1], pos[2]

    # Origin
    origin = nbt.get("Paper.Origin")
    origin_x = origin[0] if origin else None
    origin_y = origin[1] if origin else None
    origin_z = origin[2] if origin else None

    # Spawn reason
    spawn_reason = nbt.get("Paper.SpawnReason")

    # VillagerData
    vdata = nbt.get("VillagerData", {})
    profession = _strip_ns(vdata.get("profession"))
    profession_level = vdata.get("level")
    villager_type = _strip_ns(vdata.get("type"))

    # Scalar fields
    health = nbt.get("Health")
    food_level = nbt.get("FoodLevel")
    xp = nbt.get("Xp")
    ticks_lived = nbt.get("Spigot.ticksLived")
    age = nbt.get("Age")
    on_ground = nbt.get("OnGround")
    restocks_today = nbt.get("RestocksToday")
    last_restock = nbt.get("LastRestock")
    last_gossip_decay = nbt.get("LastGossipDecay")

    # Brain memories
    brain = nbt.get("Brain", {})
    memories = brain.get("memories", {})

    home_x, home_y, home_z = _extract_memory_pos(memories, "minecraft:home")
    job_site_x, job_site_y, job_site_z = _extract_memory_pos(memories, "minecraft:job_site")
    meeting_x, meeting_y, meeting_z = _extract_memory_pos(memories, "minecraft:meeting_point")
    last_slept = _extract_memory_value(memories, "minecraft:last_slept")
    last_woken = _extract_memory_value(memories, "minecraft:last_woken")
    last_worked = _extract_memory_value(memories, "minecraft:last_worked_at_poi")

    # Trades
    offers = nbt.get("Offers", {})
    recipes = offers.get("Recipes", [])
    trades = [_parse_trade(r, slot) for slot, r in enumerate(recipes)]

    # Inventory
    inv_raw = nbt.get("Inventory", [])
    inventory = [{"item": _strip_ns(i.get("id")), "count": i.get("count", 1)} for i in inv_raw]

    # Gossip
    gossip_raw = nbt.get("Gossips", [])
    gossip = [_parse_gossip_entry(g) for g in gossip_raw]

    return {
        "uuid": uuid,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "pos_z": pos_z,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "origin_z": origin_z,
        "spawn_reason": spawn_reason,
        "profession": profession,
        "profession_level": profession_level,
        "villager_type": villager_type,
        "health": health,
        "food_level": food_level,
        "xp": xp,
        "ticks_lived": ticks_lived,
        "age": age,
        "on_ground": on_ground,
        "restocks_today": restocks_today,
        "last_restock": last_restock,
        "last_gossip_decay": last_gossip_decay,
        "home_x": home_x,
        "home_y": home_y,
        "home_z": home_z,
        "job_site_x": job_site_x,
        "job_site_y": job_site_y,
        "job_site_z": job_site_z,
        "meeting_point_x": meeting_x,
        "meeting_point_y": meeting_y,
        "meeting_point_z": meeting_z,
        "last_slept": last_slept,
        "last_woken": last_woken,
        "last_worked": last_worked,
        "trades": trades,
        "inventory": inventory,
        "gossip": gossip,
    }


def _extract_memory_pos(memories, key):
    """Extract pos [x, y, z] from a brain memory entry, or (None, None, None)."""
    entry = memories.get(key)
    if not entry:
        return None, None, None
    value = entry.get("value", {})
    pos = value.get("pos") if isinstance(value, dict) else None
    if pos and len(pos) >= 3:
        return pos[0], pos[1], pos[2]
    return None, None, None


def _extract_memory_value(memories, key):
    """Extract a scalar value from a brain memory entry, or None."""
    entry = memories.get(key)
    if not entry:
        return None
    return entry.get("value")


def _parse_trade(recipe, slot):
    """Convert an NBT trade recipe dict to a trade dict."""
    buy = recipe.get("buy", {})
    sell = recipe.get("sell", {})
    buy_b = recipe.get("buyB", {})
    return {
        "slot": slot,
        "buy_item": _strip_ns(buy.get("id")),
        "buy_count": buy.get("count"),
        "buy_b_item": _strip_ns(buy_b.get("id")) if buy_b.get("id") else None,
        "buy_b_count": buy_b.get("count") if buy_b.get("id") else None,
        "sell_item": _strip_ns(sell.get("id")),
        "sell_count": sell.get("count"),
        "price_multiplier": recipe.get("priceMultiplier", 0.0),
        "max_uses": recipe.get("maxUses", 0),
        "xp": recipe.get("xp", 0),
    }


def _parse_gossip_entry(g):
    """Convert an NBT gossip dict to a gossip dict."""
    target = g.get("Target", [0, 0, 0, 0])
    return {
        "gossip_type": g.get("Type"),
        "target_uuid": ints_to_uuid(target) if target else None,
        "value": g.get("Value", 0),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_entities.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census_entities.py villager-census/tests/test_census_entities.py
git commit -m "feat(census): add nbt_to_villager() for entity disk-read"
```

---

### Task 3: Add trades, gossip, brain memory, and inventory tests to `census_entities.py`

**Files:**
- Test: `villager-census/tests/test_census_entities.py`

- [ ] **Step 1: Write the failing tests for trades**

Add to `tests/test_census_entities.py`:

```python
def test_nbt_to_villager_trades():
    """Trade recipes are parsed from Offers.Recipes."""
    nbt = _make_villager_nbt(Offers={"Recipes": [
        {
            "buy": {"id": "minecraft:emerald", "count": 1},
            "sell": {"id": "minecraft:cooked_cod", "count": 6},
            "priceMultiplier": 0.05,
            "buyB": {"id": "minecraft:cod", "count": 6},
            "maxUses": 16,
            "xp": 2,
        },
    ]})
    v = nbt_to_villager(nbt)
    assert len(v["trades"]) == 1
    t = v["trades"][0]
    assert t["slot"] == 0
    assert t["buy_item"] == "emerald"
    assert t["buy_count"] == 1
    assert t["buy_b_item"] == "cod"
    assert t["buy_b_count"] == 6
    assert t["sell_item"] == "cooked_cod"
    assert t["sell_count"] == 6
    assert t["price_multiplier"] == pytest.approx(0.05)
    assert t["max_uses"] == 16
    assert t["xp"] == 2


def test_nbt_to_villager_gossip():
    """Gossip entries are parsed with UUID conversion."""
    nbt = _make_villager_nbt(Gossips=[
        {
            "Type": "major_positive",
            "Target": [100, 200, 300, 400],
            "Value": 25,
        },
    ])
    v = nbt_to_villager(nbt)
    assert len(v["gossip"]) == 1
    g = v["gossip"][0]
    assert g["gossip_type"] == "major_positive"
    assert g["value"] == 25
    # UUID from [100, 200, 300, 400]
    assert g["target_uuid"] is not None
    assert len(g["target_uuid"]) == 36  # UUID format


def test_nbt_to_villager_brain_memories():
    """Brain memory positions and long values are extracted."""
    nbt = _make_villager_nbt(Brain={"memories": {
        "minecraft:home": {"value": {"pos": [3172, 69, -923], "dimension": "minecraft:overworld"}},
        "minecraft:job_site": {"value": {"pos": [3170, 70, -754], "dimension": "minecraft:overworld"}},
        "minecraft:meeting_point": {"value": {"pos": [3170, 66, -883], "dimension": "minecraft:overworld"}},
        "minecraft:last_slept": {"value": 1018111156},
        "minecraft:last_woken": {"value": 1018112423},
        "minecraft:last_worked_at_poi": {"value": 1001132966},
    }})
    v = nbt_to_villager(nbt)
    assert v["home_x"] == 3172
    assert v["home_y"] == 69
    assert v["home_z"] == -923
    assert v["job_site_x"] == 3170
    assert v["job_site_y"] == 70
    assert v["job_site_z"] == -754
    assert v["meeting_point_x"] == 3170
    assert v["meeting_point_y"] == 66
    assert v["meeting_point_z"] == -883
    assert v["last_slept"] == 1018111156
    assert v["last_woken"] == 1018112423
    assert v["last_worked"] == 1001132966


def test_nbt_to_villager_inventory():
    """Inventory items are parsed."""
    nbt = _make_villager_nbt(Inventory=[
        {"id": "minecraft:beetroot", "count": 2},
        {"id": "minecraft:bread", "count": 5},
    ])
    v = nbt_to_villager(nbt)
    assert len(v["inventory"]) == 2
    assert v["inventory"][0] == {"item": "beetroot", "count": 2}
    assert v["inventory"][1] == {"item": "bread", "count": 5}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_entities.py -v`
Expected: 6 PASSED (the implementation from Task 2 already handles these)

- [ ] **Step 3: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/tests/test_census_entities.py
git commit -m "test(census): add trade, gossip, brain, inventory tests for nbt_to_villager"
```

---

### Task 4: Add `parse_entity_region()` to `census_entities.py`

**Files:**
- Modify: `villager-census/census_entities.py`
- Modify: `villager-census/tests/test_census_entities.py`

- [ ] **Step 1: Write the failing test for `parse_entity_region`**

Add to `tests/test_census_entities.py`:

```python
import io
import struct
import zlib

from census_entities import parse_entity_region


def _make_entity_region(entities_by_slot):
    """Build a minimal valid .mca file with entity data in given slots.

    entities_by_slot: dict of {slot_index: [list of entity NBT dicts]}
    Returns bytes of a valid .mca file.
    """
    from census_poi import read_nbt  # verify our NBT is readable

    locations = bytearray(4096)
    timestamps = bytearray(4096)
    data_sectors = bytearray()
    next_sector = 2  # sectors 0-1 are headers

    for slot, entity_list in entities_by_slot.items():
        # Build the chunk NBT: root compound with Entities list
        chunk_nbt = _encode_nbt_compound("", {
            "Entities": entity_list,
        })
        compressed = zlib.compress(chunk_nbt)
        # Sector payload: 4-byte length + 1-byte compression type + data
        payload = struct.pack(">I", len(compressed) + 1) + b"\x02" + compressed
        # Pad to 4096-byte sectors
        sector_count = (len(payload) + 4095) // 4096
        payload = payload.ljust(sector_count * 4096, b"\x00")

        # Write location entry
        entry = ((next_sector & 0xFFFFFF) << 8) | (sector_count & 0xFF)
        struct.pack_into(">I", locations, slot * 4, entry)

        data_sectors += payload
        next_sector += sector_count

    return bytes(locations) + bytes(timestamps) + bytes(data_sectors)


def _encode_nbt_compound(name, data):
    """Encode a named TAG_Compound. Handles nested dicts, lists, ints, floats, strings."""
    buf = io.BytesIO()
    # Root tag header: type=10 (compound), name
    buf.write(struct.pack(">b", 10))
    name_bytes = name.encode("utf-8")
    buf.write(struct.pack(">H", len(name_bytes)))
    buf.write(name_bytes)
    _write_compound_payload(buf, data)
    return buf.getvalue()


def _write_compound_payload(buf, data):
    """Write the payload of a TAG_Compound (all children + TAG_End)."""
    for key, val in data.items():
        _write_named_tag(buf, key, val)
    buf.write(struct.pack(">b", 0))  # TAG_End


def _write_named_tag(buf, name, val):
    """Write a named tag (type byte + name + payload)."""
    tag_type = _infer_tag_type(val)
    buf.write(struct.pack(">b", tag_type))
    name_bytes = name.encode("utf-8")
    buf.write(struct.pack(">H", len(name_bytes)))
    buf.write(name_bytes)
    _write_payload(buf, tag_type, val)


def _infer_tag_type(val):
    if isinstance(val, dict):
        return 10  # TAG_Compound
    if isinstance(val, list):
        if val and isinstance(val[0], dict):
            return 9  # TAG_List of compounds
        if val and isinstance(val[0], int):
            return 11  # TAG_Int_Array
        if val and isinstance(val[0], float):
            return 9  # TAG_List of doubles
        return 9  # TAG_List (empty -> list of End)
    if isinstance(val, float):
        return 6  # TAG_Double
    if isinstance(val, int):
        return 3  # TAG_Int
    if isinstance(val, str):
        return 8  # TAG_String
    raise ValueError(f"Cannot infer NBT tag type for {type(val)}: {val!r}")


def _write_payload(buf, tag_type, val):
    if tag_type == 3:  # TAG_Int
        buf.write(struct.pack(">i", val))
    elif tag_type == 6:  # TAG_Double
        buf.write(struct.pack(">d", val))
    elif tag_type == 8:  # TAG_String
        s = val.encode("utf-8")
        buf.write(struct.pack(">H", len(s)))
        buf.write(s)
    elif tag_type == 9:  # TAG_List
        if not val:
            buf.write(struct.pack(">b", 0))  # list of End
            buf.write(struct.pack(">i", 0))
        elif isinstance(val[0], dict):
            buf.write(struct.pack(">b", 10))  # list of compounds
            buf.write(struct.pack(">i", len(val)))
            for item in val:
                _write_compound_payload(buf, item)
        elif isinstance(val[0], float):
            buf.write(struct.pack(">b", 6))  # list of doubles
            buf.write(struct.pack(">i", len(val)))
            for d in val:
                buf.write(struct.pack(">d", d))
        elif isinstance(val[0], int):
            # This branch won't be hit for TAG_Int_Array (type 11),
            # only for TAG_List of ints
            buf.write(struct.pack(">b", 3))
            buf.write(struct.pack(">i", len(val)))
            for i in val:
                buf.write(struct.pack(">i", i))
    elif tag_type == 10:  # TAG_Compound
        _write_compound_payload(buf, val)
    elif tag_type == 11:  # TAG_Int_Array
        buf.write(struct.pack(">i", len(val)))
        for i in val:
            buf.write(struct.pack(">i", i))


def test_parse_entity_region():
    """Round-trip: build .mca with one villager, verify parse extracts it."""
    villager_nbt = {
        "id": "minecraft:villager",
        "UUID": [1, 2, 3, 4],
        "Pos": [100.5, 64.0, -200.3],
        "VillagerData": {
            "type": "minecraft:plains",
            "profession": "minecraft:farmer",
            "level": 2,
        },
        "Health": 20.0,
    }
    mca_bytes = _make_entity_region({0: [villager_nbt]})

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".mca", delete=False) as f:
        f.write(mca_bytes)
        path = f.name

    try:
        villagers = parse_entity_region(path)
        assert len(villagers) == 1
        v = villagers[0]
        assert v["uuid"] == "00000001-0000-0002-0000-000300000004"
        assert v["profession"] == "farmer"
        assert v["pos_x"] == pytest.approx(100.5)
    finally:
        os.unlink(path)


def test_parse_entity_region_filters_non_villagers():
    """Non-villager entities (zombies, etc.) are excluded."""
    villager = {
        "id": "minecraft:villager",
        "UUID": [1, 0, 0, 0],
        "Pos": [0.0, 64.0, 0.0],
        "VillagerData": {"type": "minecraft:plains", "profession": "minecraft:none", "level": 1},
        "Health": 20.0,
    }
    zombie = {
        "id": "minecraft:zombie",
        "UUID": [2, 0, 0, 0],
        "Pos": [10.0, 64.0, 10.0],
        "Health": 20.0,
    }
    mca_bytes = _make_entity_region({0: [villager, zombie]})

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".mca", delete=False) as f:
        f.write(mca_bytes)
        path = f.name

    try:
        villagers = parse_entity_region(path)
        assert len(villagers) == 1
        assert villagers[0]["uuid"] == "00000001-0000-0000-0000-000000000000"
    finally:
        os.unlink(path)


def test_parse_entity_region_empty():
    """Empty region file (all zero location entries) returns empty list."""
    # 8192 bytes of zeros = valid .mca with no chunks
    mca_bytes = b"\x00" * 8192

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".mca", delete=False) as f:
        f.write(mca_bytes)
        path = f.name

    try:
        villagers = parse_entity_region(path)
        assert villagers == []
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd villager-census && python -m pytest tests/test_census_entities.py::test_parse_entity_region -v`
Expected: FAIL with `ImportError: cannot import name 'parse_entity_region'`

- [ ] **Step 3: Implement `parse_entity_region()`**

Add to `census_entities.py` at the top (after imports):

```python
import io
import struct
import zlib

from census_poi import read_nbt
```

Then add after `nbt_to_villager()`:

```python
def parse_entity_region(region_path):
    """Parse an entity .mca file. Returns list of villager dicts.

    Iterates chunk slots, decompresses each, reads NBT. Filters for
    entities where id == "minecraft:villager" and converts via nbt_to_villager().
    """
    results = []
    with open(region_path, "rb") as f:
        location_header = f.read(4096)
        f.read(4096)  # skip timestamp header

        for slot in range(1024):
            entry_bytes = location_header[slot * 4: slot * 4 + 4]
            entry = struct.unpack(">I", entry_bytes)[0]
            offset = (entry >> 8) & 0xFFFFFF
            sector_count = entry & 0xFF
            if offset == 0 and sector_count == 0:
                continue

            f.seek(offset * 4096)
            length = struct.unpack(">I", f.read(4))[0]
            compression_type = struct.unpack(">B", f.read(1))[0]
            compressed_data = f.read(length - 1)

            if compression_type == 2:
                raw = zlib.decompress(compressed_data)
            elif compression_type == 1:
                import gzip
                raw = gzip.decompress(compressed_data)
            else:
                raw = compressed_data

            nbt = read_nbt(io.BytesIO(raw))
            entities = nbt.get("Entities", [])
            for entity in entities:
                if entity.get("id") == "minecraft:villager":
                    results.append(nbt_to_villager(entity))

    return results


def parse_entity_regions(region_paths):
    """Parse multiple entity region files. Returns combined list of villager dicts."""
    results = []
    for path in region_paths:
        results.extend(parse_entity_region(path))
    return results
```

- [ ] **Step 4: Run all entity tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_entities.py -v`
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census_entities.py villager-census/tests/test_census_entities.py
git commit -m "feat(census): add parse_entity_region() for .mca entity files"
```

---

### Task 5: Add `save_all()`, `get_entity_files()`, `get_entity_mtimes()`, `entity_region_coords()` to `census_collect.py`

**Files:**
- Modify: `villager-census/census_collect.py`
- Modify: `villager-census/tests/test_census_collect.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_census_collect.py`:

```python
from census_collect import (
    # existing imports stay...
    save_all,
    get_entity_files,
    get_entity_mtimes,
    entity_region_coords,
)
from census_zones import make_single_zone

# --- save_all ---

def test_save_all_waits_for_confirmation():
    """save_all sends 'save-all' and waits for 'Saved the game' in log."""
    sent = []
    call_count = [0]

    def fake_run(cmd):
        call_count[0] += 1
        if call_count[0] == 1:
            return ["[12:00:05] [Server thread/INFO]: Saved the game"]
        return []

    with (
        patch("census_collect._send_tmux", side_effect=lambda c: sent.append(c)),
        patch("census_collect._run_command", side_effect=fake_run),
        patch("census_collect.time.sleep"),
        patch("census_collect.time.time", side_effect=[100, 101]),
    ):
        save_all()

    assert "save-all" in sent


def test_save_all_timeout():
    """save_all raises TimeoutError if 'Saved the game' never appears."""
    def fake_run(cmd):
        return ["[12:00:01] [Server thread/INFO]: some other log line"]

    with (
        patch("census_collect._send_tmux"),
        patch("census_collect._run_command", side_effect=fake_run),
        patch("census_collect.time.sleep"),
        patch("census_collect.time.time", side_effect=[100, 131]),
        pytest.raises(TimeoutError, match="save-all"),
    ):
        save_all()


# --- get_entity_mtimes ---

def test_get_entity_mtimes():
    """get_entity_mtimes returns {filename: mtime} dict from stat output."""
    def fake_run(cmd):
        return ["1712200000 r.6.-3.mca", "1712200100 r.6.-2.mca"]

    with patch("census_collect._run_command", side_effect=fake_run):
        result = get_entity_mtimes([(6, -3), (6, -2)])

    assert result == {"r.6.-3.mca": 1712200000, "r.6.-2.mca": 1712200100}


# --- get_entity_files ---

def test_get_entity_files_ssh(tmp_path):
    """get_entity_files downloads entity .mca files via SCP in SSH mode."""
    import census_collect
    old_host = census_collect._ssh_host
    census_collect._ssh_host = "minecraft"

    try:
        def fake_scp(cmd, **kwargs):
            # Create the file that scp would download
            local_path = cmd[-1]
            Path(local_path).write_bytes(b"fake mca data")
            return subprocess.CompletedProcess(cmd, 0)

        import subprocess
        with patch("census_collect.subprocess.run", side_effect=fake_scp):
            paths = get_entity_files([(6, -3)], tmp_path)

        assert len(paths) == 1
        assert paths[0].name == "r.6.-3.mca"
    finally:
        census_collect._ssh_host = old_host


# --- entity_region_coords ---

def test_entity_region_coords():
    """entity_region_coords computes region coords from zone bounding box."""
    zones = [
        {"name": "a", "type": "rect", "x_min": 3090, "z_min": -1040, "x_max": 3220, "z_max": -826},
    ]
    result = entity_region_coords(zones)
    # 3090 // 512 = 6, 3220 // 512 = 6, -1040 // 512 = -3 (floor div), -826 // 512 = -2
    assert (6, -3) in result
    assert (6, -2) in result


def test_entity_region_coords_circle():
    """entity_region_coords works with circle zones."""
    zones = [make_single_zone(center_x=3150, center_z=-950, radius=300)]
    result = entity_region_coords(zones)
    assert len(result) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd villager-census && python -m pytest tests/test_census_collect.py::test_save_all_waits_for_confirmation -v`
Expected: FAIL with `ImportError: cannot import name 'save_all'`

- [ ] **Step 3: Implement the new functions**

Add a new constant and functions to `census_collect.py`. Add this constant after the `POI_DIR` constant:

```python
ENTITY_DIR = "/home/minecraft/serverfiles/world_new/entities"
```

Add these functions after `get_poi_files()`:

```python
def save_all(timeout=30):
    """Send 'save-all' via tmux and wait for 'Saved the game' in the log."""
    _send_tmux("save-all")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(2)
        lines = _run_command(f"tail -n 20 {LOG_PATH}")
        for line in lines:
            if "Saved the game" in line:
                return
    raise TimeoutError(f"save-all did not complete within {timeout}s")


def get_entity_files(region_coords, local_dir):
    """Get entity .mca files — copy locally or download via SCP.

    Returns a list of Path objects for files that were successfully obtained.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for rx, rz in region_coords:
        filename = f"r.{rx}.{rz}.mca"
        local_path = local_dir / filename

        if _ssh_host:
            remote = f"{_ssh_host}:{ENTITY_DIR}/{filename}"
            result = subprocess.run(
                ["scp", remote, str(local_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and local_path.exists():
                downloaded.append(local_path)
        else:
            source = Path(ENTITY_DIR) / filename
            result = subprocess.run(
                ["sudo", "cp", str(source), str(local_path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and local_path.exists():
                subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", str(local_path)],
                               capture_output=True, timeout=5)
                downloaded.append(local_path)

    return downloaded


def get_entity_mtimes(region_coords):
    """Stat entity .mca files and return {filename: mtime_epoch} dict."""
    filenames = [f"r.{rx}.{rz}.mca" for rx, rz in region_coords]
    stat_cmd = " && ".join(
        f'stat -c "%Y {fn}" {ENTITY_DIR}/{fn}' for fn in filenames
    )
    lines = _run_command(stat_cmd)
    result = {}
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            mtime, fname = int(parts[0]), parts[1]
            result[fname] = mtime
    return result


def entity_region_coords(zones):
    """Compute the set of entity region (rx, rz) coords covering all zones."""
    from census_zones import bounding_box
    x_min, z_min, x_max, z_max = bounding_box(zones)
    regions = set()
    for x in range(x_min // 512, (x_max // 512) + 1):
        for z in range(z_min // 512, (z_max // 512) + 1):
            regions.add((x, z))
    return sorted(regions)
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_collect.py -v`
Expected: all PASSED (existing + new)

- [ ] **Step 5: Run all tests**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census_collect.py villager-census/tests/test_census_collect.py
git commit -m "feat(census): add save_all, get_entity_files, get_entity_mtimes, entity_region_coords"
```

---

### Task 6: Rewire `run_census()` to use entity disk reads

**Files:**
- Modify: `villager-census/census.py:10-39` (imports), `villager-census/census.py:56-119` (run_census steps 1-4)
- Modify: `villager-census/tests/test_census_pipeline.py`

- [ ] **Step 1: Update the pipeline test helper**

Replace `_run_with_mocks()` in `tests/test_census_pipeline.py`:

```python
def _run_with_mocks(db_path, *, villagers=None, beds=None, players=None, zones=None):
    """Helper to run census with standard mocks."""
    if villagers is None:
        # Parse the sample entity line to get a villager dict (backward compat)
        from census_parse import parse_entity_line
        villagers = [parse_entity_line(SAMPLE_ENTITY_LINE)]
    if beds is None:
        beds = SAMPLE_BEDS
    if players is None:
        players = []
    if zones is None:
        zones = TEST_ZONES

    with (
        patch("census.check_players_online", return_value=players),
        patch("census.get_entity_files", return_value=[]),
        patch("census.parse_entity_regions", return_value=villagers),
        patch("census.get_poi_files", return_value=[]),
        patch("census.parse_poi_regions", return_value=beds),
    ):
        return census.run_census(
            db_path=db_path,
            zones=zones,
            poi_regions=TEST_POI_REGIONS,
        )
```

Update the call sites that pass `entity_lines=` to pass `villagers=` instead. For the empty case (simulating no villagers), pass `villagers=[]`:

- `test_run_census_end_to_end`: change nothing (default is fine)
- `test_run_census_detects_deaths`: change `entity_lines=[]` to `villagers=[]`, `beds=[]` stays
- Others: update `entity_lines` -> `villagers` parameter name

Also update `test_run_census_stores_coverage` to use the new mocks:

```python
def test_run_census_stores_coverage():
    """Snapshot records which zones were scanned and skipped."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    import json
    from census_parse import parse_entity_line
    zones = [make_single_zone(center_x=3173, center_z=-755, radius=10, name="active")]
    skipped = ["inactive-a", "inactive-b"]
    villagers = [parse_entity_line(SAMPLE_ENTITY_LINE)]

    with (
        patch("census.check_players_online", return_value=[]),
        patch("census.get_entity_files", return_value=[]),
        patch("census.parse_entity_regions", return_value=villagers),
        patch("census.get_poi_files", return_value=[]),
        patch("census.parse_poi_regions", return_value=[]),
    ):
        summary = census.run_census(
            db_path=db_path, zones=zones, poi_regions=TEST_POI_REGIONS,
            skipped_zones=skipped,
        )

    conn = init_db(db_path)
    snap = conn.execute("SELECT zones_scanned, zones_skipped FROM snapshots WHERE id = ?",
                        (summary["snapshot_id"],)).fetchone()
    assert json.loads(snap["zones_scanned"]) == ["active"]
    assert json.loads(snap["zones_skipped"]) == ["inactive-a", "inactive-b"]
    conn.close()
```

- [ ] **Step 2: Run pipeline tests to verify they fail**

Run: `cd villager-census && python -m pytest tests/test_census_pipeline.py -v`
Expected: FAIL (census.py still imports old functions)

- [ ] **Step 3: Rewire `census.py` imports and `run_census()`**

Replace the imports at the top of `census.py`:

```python
from census_collect import (
    check_players_online,
    configure as configure_transport,
    entity_region_coords,
    get_entity_files,
    get_entity_mtimes,
    get_poi_files,
    get_player_position,
    save_all,
)
from census_db import (
    export_all_json,
    get_latest_snapshot,
    get_snapshot_villager_uuids,
    init_db,
    insert_bed,
    insert_bell,
    insert_census_run,
    insert_gossip,
    insert_inventory_item,
    insert_snapshot,
    insert_trade,
    insert_villager,
    insert_villager_state,
    mark_dead,
)
from census_entities import parse_entity_regions
from census_poi import parse_poi_regions
from census_zones import bounding_box, classify_bed, classify_villager, make_single_zone
```

Replace steps 3-4 in `run_census()` (the entity collection):

```python
    # Step 3: download and parse entity files
    x_min, z_min, x_max, z_max = bounding_box(zones)
    entity_regions = entity_region_coords(zones)
    entity_local_dir = Path("/tmp/census_entities")
    entity_paths = get_entity_files(entity_regions, entity_local_dir)
    villagers = parse_entity_regions(entity_paths)
```

Remove step 4 entirely (the `for line in entity_lines` loop). The `villagers` list is now ready to use directly.

- [ ] **Step 4: Run pipeline tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_pipeline.py -v`
Expected: all PASSED

- [ ] **Step 5: Run all tests**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: some CLI tests may fail (they still mock forceload). That's expected — Task 7 fixes those.

- [ ] **Step 6: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census.py villager-census/tests/test_census_pipeline.py
git commit -m "refactor(census): rewire run_census to use entity disk reads"
```

---

### Task 7: Replace `--lazy`/forceload CLI with mtime noop gate

**Files:**
- Modify: `villager-census/census.py:340-569` (CLI `main()` and `_build_cron_command()`)
- Modify: `villager-census/tests/test_census_cli.py`

- [ ] **Step 1: Write the failing tests for the mtime gate**

Replace the `--lazy` and force mode tests in `tests/test_census_cli.py`. Remove these test functions:
- `test_cli_lazy_no_loaded_chunks_skips`
- `test_cli_lazy_partial_zones`
- `test_cli_lazy_prints_skipped_zones`
- `test_cli_force_calls_forceload`
- `test_cli_force_unforceloads_on_error`

Add the new tests:

```python
# --- mtime noop gate ---

def test_cli_skips_when_mtimes_unchanged(toml_file, db_file, capsys):
    """When entity file mtimes match the last run, census is skipped."""
    # Seed a previous run with known mtimes
    conn = init_db(db_file)
    from census_db import insert_census_run
    insert_census_run(conn, timestamp="2026-04-04T00:00:00Z", status="completed",
                      entity_mtimes='{"r.6.-3.mca": 1000, "r.6.-2.mca": 2000}')
    conn.close()

    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--db", db_file]),
        patch("census.save_all"),
        patch("census.get_entity_mtimes", return_value={"r.6.-3.mca": 1000, "r.6.-2.mca": 2000}),
        patch("census.entity_region_coords", return_value=[(6, -3), (6, -2)]),
        patch("census.run_census") as mock_run,
    ):
        census.main()

    mock_run.assert_not_called()
    output = capsys.readouterr().out
    assert "Skipped" in output
    assert "no changes" in output.lower()


def test_cli_runs_when_mtimes_changed(toml_file, db_file, capsys):
    """When entity file mtimes differ from last run, full census runs."""
    conn = init_db(db_file)
    from census_db import insert_census_run
    insert_census_run(conn, timestamp="2026-04-04T00:00:00Z", status="completed",
                      entity_mtimes='{"r.6.-3.mca": 1000, "r.6.-2.mca": 2000}')
    conn.close()

    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--db", db_file]),
        patch("census.save_all"),
        patch("census.get_entity_mtimes", return_value={"r.6.-3.mca": 1000, "r.6.-2.mca": 3000}),
        patch("census.entity_region_coords", return_value=[(6, -3), (6, -2)]),
        patch("census.run_census", return_value=MOCK_SUMMARY) as mock_run,
    ):
        census.main()

    mock_run.assert_called_once()


def test_cli_runs_on_first_run(toml_file, db_file, capsys):
    """First run (no previous mtimes) always proceeds with full census."""
    with (
        patch("sys.argv", ["census.py", "--config", toml_file, "--db", db_file]),
        patch("census.save_all"),
        patch("census.get_entity_mtimes", return_value={"r.6.-3.mca": 1000}),
        patch("census.entity_region_coords", return_value=[(6, -3)]),
        patch("census.run_census", return_value=MOCK_SUMMARY) as mock_run,
    ):
        census.main()

    mock_run.assert_called_once()
```

Also update all remaining CLI tests that mock `forceload_zones`/`unforceload_zones` to mock `save_all`, `get_entity_mtimes`, and `entity_region_coords` instead. For each test that currently patches `census.forceload_zones` and `census.unforceload_zones`, replace those patches with:

```python
        patch("census.save_all"),
        patch("census.get_entity_mtimes", return_value={"r.1.2.mca": 9999}),
        patch("census.entity_region_coords", return_value=[(1, 2)]),
```

This applies to: `test_cli_config_first_place`, `test_cli_config_with_place`, `test_cli_center_with_radius`, `test_cli_center_default_name`, `test_cli_rect`, `test_cli_poi_regions_parsed`, `test_cli_prints_zone_table`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd villager-census && python -m pytest tests/test_census_cli.py::test_cli_skips_when_mtimes_unchanged -v`
Expected: FAIL

- [ ] **Step 3: Rewrite `main()` in `census.py`**

Replace the `main()` function's run logic. Remove the `--lazy` argument. Replace the `--lazy`/forceload branching with the mtime gate:

Remove this argument definition:
```python
    parser.add_argument("--lazy", action="store_true",
                        help="Skip zones with unloaded chunks instead of forceloading")
```

Replace everything after `poi_regions = ...` resolution (the `timestamp = ...` line onwards, before the summary print) with:

```python
    timestamp = datetime.now(timezone.utc).isoformat()

    # Mtime noop gate: save-all, then check entity file mtimes
    entity_regions = entity_region_coords(zones)
    save_all()
    current_mtimes = get_entity_mtimes(entity_regions)

    # Load previous mtimes from last successful census run
    conn = init_db(args.db)
    cur = conn.execute(
        "SELECT entity_mtimes FROM census_runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    prev_mtimes = json.loads(row["entity_mtimes"]) if row and row["entity_mtimes"] else None
    conn.close()

    if prev_mtimes is not None and current_mtimes == prev_mtimes:
        conn = init_db(args.db)
        insert_census_run(conn, timestamp=timestamp, status="skipped_no_changes",
                          reason="Entity file mtimes unchanged",
                          entity_mtimes=json.dumps(current_mtimes))
        conn.close()
        print(f"[{timestamp}] Skipped: no changes to entity files since last census")
        return

    # Full census run
    summary = run_census(
        db_path=args.db, zones=zones, poi_regions=poi_regions,
        notes=args.notes,
    )

    conn = init_db(args.db)
    insert_census_run(conn, timestamp=timestamp, status="completed",
                      snapshot_id=summary["snapshot_id"],
                      entity_mtimes=json.dumps(current_mtimes))
    conn.close()
```

Also update `_build_cron_command()` to remove the `--lazy` handling:

Remove these lines:
```python
    if args.lazy:
        parts.append("--lazy")
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `cd villager-census && python -m pytest tests/test_census_cli.py -v`
Expected: all PASSED

- [ ] **Step 5: Run all tests**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census.py villager-census/tests/test_census_cli.py
git commit -m "feat(census): replace --lazy/forceload with mtime noop gate"
```

---

### Task 8: Remove dead code from `census_collect.py`

**Files:**
- Modify: `villager-census/census_collect.py` (remove functions)
- Modify: `villager-census/tests/test_census_collect.py` (remove tests)

- [ ] **Step 1: Remove the dead functions from `census_collect.py`**

Remove these functions:
- `_forceload_cmd()` (lines 63-71)
- `forceload_zones()` (lines 74-78)
- `unforceload_zones()` (lines 81-83)
- `check_chunks_loaded()` (lines 86-129)
- `collect_villager_dumps()` (lines 172-179)
- `collect_villager_dumps_box()` (lines 182-189)
- `_collect_with_selector()` (lines 192-220)

- [ ] **Step 2: Remove the corresponding tests from `tests/test_census_collect.py`**

Remove these test functions:
- `test_check_chunks_loaded_all_loaded`
- `test_check_chunks_loaded_partial`
- `test_forceload_zones_sends_correct_commands`
- `test_forceload_zones_multiple_zones`
- `test_unforceload_zones_sends_remove`
- `test_forceload_zones_circle`
- `test_forceload_zones_sleeps_after`
- `test_check_chunks_loaded_none`

Remove the imports of `check_chunks_loaded`, `forceload_zones`, `unforceload_zones` from the test file.

- [ ] **Step 3: Run all tests**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add villager-census/census_collect.py villager-census/tests/test_census_collect.py
git commit -m "refactor(census): remove forceload, check_chunks_loaded, collect_villager_dumps"
```

---

### Task 9: Update cron install test and final cleanup

**Files:**
- Modify: `villager-census/tests/test_census_cli.py` (cron test)
- Verify: all tests pass, no stale imports

- [ ] **Step 1: Verify the cron install test no longer checks for `--lazy`**

The existing `test_cli_install_cron` already asserts `"--lazy" not in crontab`. Confirm this still passes. Also confirm the `_build_cron_command` no longer references `args.lazy`.

Run: `cd villager-census && python -m pytest tests/test_census_cli.py::test_cli_install_cron -v`
Expected: PASS

- [ ] **Step 2: Run the full test suite**

Run: `cd villager-census && python -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 3: Verify no stale imports remain**

Run: `cd villager-census && python -c "from census import main; print('OK')"` and `cd villager-census && python -c "from census_collect import save_all, get_entity_files, get_entity_mtimes, entity_region_coords; print('OK')"` and `cd villager-census && python -c "from census_entities import nbt_to_villager, parse_entity_region, parse_entity_regions; print('OK')"`

Expected: all print `OK`

- [ ] **Step 4: Commit if any fixes were needed**

```bash
cd /home/leo/documents/code/disqt.com/minecraft
git add -u villager-census/
git commit -m "chore(census): final cleanup after entity disk-read migration"
```
