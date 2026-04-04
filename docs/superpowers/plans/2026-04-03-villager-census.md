# Villager Census Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a villager census system that collects, stores, and visualizes Minecraft villager population data over time via a Claude Code skill.

**Architecture:** Python CLI tools (stdlib only) collect villager entity data from PaperMC via SSH/tmux console commands and POI region file parsing, store everything in a local SQLite database, and produce an interactive HTML playground for inspection. A Claude Code skill (`/villager-census`) orchestrates the pipeline.

**Tech Stack:** Python 3.11 (stdlib only — sqlite3, struct, zlib, re, json), SQLite 3.40, HTML/CSS/JS (single-file playground)

---

### Task 1: SQLite schema and database module

**Files:**
- Create: `villager-census/census_db.py`
- Create: `villager-census/tests/test_census_db.py`

- [ ] **Step 1: Write tests for schema creation and basic inserts**

```python
# villager-census/tests/test_census_db.py
import sqlite3
from census_db import init_db, insert_snapshot, insert_villager, insert_villager_state, insert_trade, insert_inventory_item, insert_gossip, insert_bed, get_latest_snapshot, get_villager, mark_dead

def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    assert tables == ["beds", "snapshots", "villager_gossip", "villager_inventory", "villager_states", "villager_trades", "villagers"]
    conn.close()

def test_insert_snapshot(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, timestamp="2026-04-03T19:44:00Z", players_online='["Termiduck"]', area_center_x=3150, area_center_z=-950, scan_radius=300, villager_count=130, bed_count=38, notes="test")
    assert snap_id == 1
    snap_id2 = insert_snapshot(conn, timestamp="2026-04-04T12:00:00Z", players_online='[]', area_center_x=3150, area_center_z=-950, scan_radius=300, villager_count=131, bed_count=38, notes=None)
    assert snap_id2 == 2
    conn.close()

def test_insert_and_get_villager(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 1, 0, None)
    insert_villager(conn, uuid="0a077d31-a230-41b5-bf50-c74d83892338", first_seen_snapshot=snap_id, last_seen_snapshot=snap_id, spawn_reason="BREEDING", origin_x=3145.9, origin_y=63.9, origin_z=-1006.4)
    v = get_villager(conn, "0a077d31-a230-41b5-bf50-c74d83892338")
    assert v["uuid"] == "0a077d31-a230-41b5-bf50-c74d83892338"
    assert v["spawn_reason"] == "BREEDING"
    assert v["presumed_dead"] == 0
    conn.close()

def test_insert_villager_state_unique_constraint(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 1, 0, None)
    uuid = "0a077d31-a230-41b5-bf50-c74d83892338"
    insert_villager(conn, uuid=uuid, first_seen_snapshot=snap_id, last_seen_snapshot=snap_id, spawn_reason="BREEDING", origin_x=0, origin_y=0, origin_z=0)
    state = dict(snapshot_id=snap_id, villager_uuid=uuid, pos_x=3150.0, pos_y=64.0, pos_z=-950.0, health=20.0, food_level=0, profession="farmer", profession_level=1, villager_type="plains", xp=0, ticks_lived=100, age=0, home_x=None, home_y=None, home_z=None, job_site_x=None, job_site_y=None, job_site_z=None, meeting_point_x=None, meeting_point_y=None, meeting_point_z=None, last_slept=None, last_woken=None, last_worked=None, last_restock=None, restocks_today=0, on_ground=1, last_gossip_decay=None)
    insert_villager_state(conn, **state)
    # Duplicate insert should fail
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        insert_villager_state(conn, **state)
    conn.close()

def test_mark_dead(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 1, 0, None)
    uuid = "0a077d31-a230-41b5-bf50-c74d83892338"
    insert_villager(conn, uuid=uuid, first_seen_snapshot=snap_id, last_seen_snapshot=snap_id, spawn_reason="DEFAULT", origin_x=0, origin_y=0, origin_z=0)
    mark_dead(conn, uuid, death_snapshot=snap_id)
    v = get_villager(conn, uuid)
    assert v["presumed_dead"] == 1
    assert v["death_snapshot"] == snap_id
    conn.close()

def test_get_latest_snapshot(tmp_path):
    conn = init_db(tmp_path / "test.db")
    assert get_latest_snapshot(conn) is None
    insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 130, 38, None)
    insert_snapshot(conn, "2026-04-05T12:00:00Z", '[]', 3150, -950, 300, 135, 40, None)
    latest = get_latest_snapshot(conn)
    assert latest["id"] == 2
    assert latest["villager_count"] == 135
    conn.close()

def test_insert_trade(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 1, 0, None)
    uuid = "0a077d31-a230-41b5-bf50-c74d83892338"
    insert_villager(conn, uuid=uuid, first_seen_snapshot=snap_id, last_seen_snapshot=snap_id, spawn_reason="BREEDING", origin_x=0, origin_y=0, origin_z=0)
    insert_trade(conn, snapshot_id=snap_id, villager_uuid=uuid, slot=0, buy_item="emerald", buy_count=1, buy_b_item="cod", buy_b_count=6, sell_item="cooked_cod", sell_count=6, price_multiplier=0.05, max_uses=16, xp=2)
    rows = conn.execute("SELECT * FROM villager_trades WHERE villager_uuid=?", (uuid,)).fetchall()
    assert len(rows) == 1
    conn.close()

def test_insert_bed_with_claimed_by(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(conn, "2026-04-03T19:44:00Z", '[]', 3150, -950, 300, 1, 1, None)
    uuid = "0a077d31-a230-41b5-bf50-c74d83892338"
    insert_villager(conn, uuid=uuid, first_seen_snapshot=snap_id, last_seen_snapshot=snap_id, spawn_reason="BREEDING", origin_x=0, origin_y=0, origin_z=0)
    insert_bed(conn, snapshot_id=snap_id, pos_x=3140, pos_y=67, pos_z=-1042, free_tickets=0, claimed_by=uuid)
    bed = conn.execute("SELECT * FROM beds WHERE snapshot_id=?", (snap_id,)).fetchone()
    assert bed is not None
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd villager-census && python -m pytest tests/test_census_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'census_db'`

- [ ] **Step 3: Implement census_db.py**

```python
# villager-census/census_db.py
"""SQLite schema and data access for villager census."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    players_online TEXT,
    area_center_x INTEGER,
    area_center_z INTEGER,
    scan_radius INTEGER,
    villager_count INTEGER,
    bed_count INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS villagers (
    uuid TEXT PRIMARY KEY,
    first_seen_snapshot INTEGER REFERENCES snapshots(id),
    last_seen_snapshot INTEGER REFERENCES snapshots(id),
    spawn_reason TEXT,
    origin_x REAL,
    origin_y REAL,
    origin_z REAL,
    presumed_dead INTEGER DEFAULT 0,
    death_snapshot INTEGER REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS villager_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    villager_uuid TEXT NOT NULL REFERENCES villagers(uuid),
    pos_x REAL,
    pos_y REAL,
    pos_z REAL,
    health REAL,
    food_level INTEGER,
    profession TEXT,
    profession_level INTEGER,
    villager_type TEXT,
    xp INTEGER,
    ticks_lived INTEGER,
    age INTEGER,
    home_x INTEGER,
    home_y INTEGER,
    home_z INTEGER,
    job_site_x INTEGER,
    job_site_y INTEGER,
    job_site_z INTEGER,
    meeting_point_x INTEGER,
    meeting_point_y INTEGER,
    meeting_point_z INTEGER,
    last_slept INTEGER,
    last_woken INTEGER,
    last_worked INTEGER,
    last_restock INTEGER,
    restocks_today INTEGER,
    on_ground INTEGER,
    last_gossip_decay INTEGER,
    UNIQUE(snapshot_id, villager_uuid)
);

CREATE TABLE IF NOT EXISTS villager_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    villager_uuid TEXT NOT NULL REFERENCES villagers(uuid),
    slot INTEGER,
    buy_item TEXT,
    buy_count INTEGER,
    buy_b_item TEXT,
    buy_b_count INTEGER,
    sell_item TEXT,
    sell_count INTEGER,
    price_multiplier REAL,
    max_uses INTEGER,
    xp INTEGER
);

CREATE TABLE IF NOT EXISTS villager_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    villager_uuid TEXT NOT NULL REFERENCES villagers(uuid),
    item TEXT,
    count INTEGER
);

CREATE TABLE IF NOT EXISTS villager_gossip (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    villager_uuid TEXT NOT NULL REFERENCES villagers(uuid),
    gossip_type TEXT,
    target_uuid TEXT,
    value INTEGER
);

CREATE TABLE IF NOT EXISTS beds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    pos_x INTEGER,
    pos_y INTEGER,
    pos_z INTEGER,
    free_tickets INTEGER,
    claimed_by TEXT,
    UNIQUE(snapshot_id, pos_x, pos_y, pos_z)
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create database and all tables. Returns connection with row_factory set."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_snapshot(conn, *, timestamp, players_online, area_center_x, area_center_z, scan_radius, villager_count, bed_count, notes):
    """Insert a census snapshot. Returns the new snapshot id."""
    cursor = conn.execute(
        "INSERT INTO snapshots (timestamp, players_online, area_center_x, area_center_z, scan_radius, villager_count, bed_count, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (timestamp, players_online, area_center_x, area_center_z, scan_radius, villager_count, bed_count, notes),
    )
    conn.commit()
    return cursor.lastrowid


def insert_villager(conn, *, uuid, first_seen_snapshot, last_seen_snapshot, spawn_reason, origin_x, origin_y, origin_z):
    """Insert or update a villager identity record. First-seen stays, last-seen updates."""
    conn.execute(
        """INSERT INTO villagers (uuid, first_seen_snapshot, last_seen_snapshot, spawn_reason, origin_x, origin_y, origin_z)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(uuid) DO UPDATE SET last_seen_snapshot=excluded.last_seen_snapshot""",
        (uuid, first_seen_snapshot, last_seen_snapshot, spawn_reason, origin_x, origin_y, origin_z),
    )
    conn.commit()


def insert_villager_state(conn, *, snapshot_id, villager_uuid, pos_x, pos_y, pos_z, health, food_level, profession, profession_level, villager_type, xp, ticks_lived, age, home_x, home_y, home_z, job_site_x, job_site_y, job_site_z, meeting_point_x, meeting_point_y, meeting_point_z, last_slept, last_woken, last_worked, last_restock, restocks_today, on_ground, last_gossip_decay):
    """Insert a villager state row for a specific snapshot."""
    conn.execute(
        """INSERT INTO villager_states (snapshot_id, villager_uuid, pos_x, pos_y, pos_z, health, food_level, profession, profession_level, villager_type, xp, ticks_lived, age, home_x, home_y, home_z, job_site_x, job_site_y, job_site_z, meeting_point_x, meeting_point_y, meeting_point_z, last_slept, last_woken, last_worked, last_restock, restocks_today, on_ground, last_gossip_decay)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (snapshot_id, villager_uuid, pos_x, pos_y, pos_z, health, food_level, profession, profession_level, villager_type, xp, ticks_lived, age, home_x, home_y, home_z, job_site_x, job_site_y, job_site_z, meeting_point_x, meeting_point_y, meeting_point_z, last_slept, last_woken, last_worked, last_restock, restocks_today, on_ground, last_gossip_decay),
    )
    conn.commit()


def insert_trade(conn, *, snapshot_id, villager_uuid, slot, buy_item, buy_count, buy_b_item, buy_b_count, sell_item, sell_count, price_multiplier, max_uses, xp):
    """Insert a trade offer row."""
    conn.execute(
        "INSERT INTO villager_trades (snapshot_id, villager_uuid, slot, buy_item, buy_count, buy_b_item, buy_b_count, sell_item, sell_count, price_multiplier, max_uses, xp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (snapshot_id, villager_uuid, slot, buy_item, buy_count, buy_b_item, buy_b_count, sell_item, sell_count, price_multiplier, max_uses, xp),
    )
    conn.commit()


def insert_inventory_item(conn, *, snapshot_id, villager_uuid, item, count):
    """Insert an inventory item row."""
    conn.execute(
        "INSERT INTO villager_inventory (snapshot_id, villager_uuid, item, count) VALUES (?, ?, ?, ?)",
        (snapshot_id, villager_uuid, item, count),
    )
    conn.commit()


def insert_gossip(conn, *, snapshot_id, villager_uuid, gossip_type, target_uuid, value):
    """Insert a gossip entry row."""
    conn.execute(
        "INSERT INTO villager_gossip (snapshot_id, villager_uuid, gossip_type, target_uuid, value) VALUES (?, ?, ?, ?, ?)",
        (snapshot_id, villager_uuid, gossip_type, target_uuid, value),
    )
    conn.commit()


def insert_bed(conn, *, snapshot_id, pos_x, pos_y, pos_z, free_tickets, claimed_by):
    """Insert a bed POI row."""
    conn.execute(
        "INSERT INTO beds (snapshot_id, pos_x, pos_y, pos_z, free_tickets, claimed_by) VALUES (?, ?, ?, ?, ?, ?)",
        (snapshot_id, pos_x, pos_y, pos_z, free_tickets, claimed_by),
    )
    conn.commit()


def get_villager(conn, uuid):
    """Get a villager identity record by UUID. Returns dict or None."""
    row = conn.execute("SELECT * FROM villagers WHERE uuid=?", (uuid,)).fetchone()
    return dict(row) if row else None


def get_latest_snapshot(conn):
    """Get the most recent snapshot. Returns dict or None."""
    row = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def mark_dead(conn, uuid, death_snapshot):
    """Mark a villager as presumed dead."""
    conn.execute("UPDATE villagers SET presumed_dead=1, death_snapshot=? WHERE uuid=?", (death_snapshot, uuid))
    conn.commit()


def get_snapshot_villager_uuids(conn, snapshot_id):
    """Get all villager UUIDs present in a specific snapshot."""
    rows = conn.execute("SELECT villager_uuid FROM villager_states WHERE snapshot_id=?", (snapshot_id,)).fetchall()
    return {row[0] for row in rows}


def get_all_snapshots(conn):
    """Get all snapshots ordered by timestamp."""
    rows = conn.execute("SELECT * FROM snapshots ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_villager_history(conn, uuid):
    """Get all states for a villager across snapshots."""
    rows = conn.execute(
        "SELECT vs.*, s.timestamp FROM villager_states vs JOIN snapshots s ON vs.snapshot_id=s.id WHERE vs.villager_uuid=? ORDER BY vs.snapshot_id",
        (uuid,),
    ).fetchall()
    return [dict(r) for r in rows]


def export_snapshot_json(conn, snapshot_id):
    """Export a full snapshot as a JSON-serializable dict (for playground embedding)."""
    snap = dict(conn.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone())
    states = [dict(r) for r in conn.execute("SELECT * FROM villager_states WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
    trades = [dict(r) for r in conn.execute("SELECT * FROM villager_trades WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
    inventory = [dict(r) for r in conn.execute("SELECT * FROM villager_inventory WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
    gossip = [dict(r) for r in conn.execute("SELECT * FROM villager_gossip WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
    beds = [dict(r) for r in conn.execute("SELECT * FROM beds WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
    villager_uuids = {s["villager_uuid"] for s in states}
    villagers = [dict(r) for r in conn.execute("SELECT * FROM villagers WHERE uuid IN ({})".format(",".join("?" * len(villager_uuids))), list(villager_uuids)).fetchall()] if villager_uuids else []
    return {"snapshot": snap, "villagers": villagers, "states": states, "trades": trades, "inventory": inventory, "gossip": gossip, "beds": beds}


def export_all_json(conn):
    """Export entire database as JSON-serializable dict (for playground)."""
    snapshots = get_all_snapshots(conn)
    villagers = [dict(r) for r in conn.execute("SELECT * FROM villagers ORDER BY uuid").fetchall()]
    data = {"snapshots": snapshots, "villagers": villagers, "snapshot_data": {}}
    for snap in snapshots:
        data["snapshot_data"][snap["id"]] = export_snapshot_json(conn, snap["id"])
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_db.py -v
```

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census_db.py villager-census/tests/test_census_db.py
git commit -m "feat(census): add SQLite schema and data access module"
```

---

### Task 2: SNBT parser for villager entity data

**Files:**
- Create: `villager-census/census_parse.py`
- Create: `villager-census/tests/test_census_parse.py`

The server logs output Minecraft's SNBT (Stringified NBT) format. This is NOT JSON — it has type suffixes (`0b`, `0.5f`, `100L`, `0.0d`), int arrays (`[I; 1, 2, 3, 4]`), and unquoted keys. We need regex-based extraction of specific fields.

- [ ] **Step 1: Write tests with real SNBT data**

```python
# villager-census/tests/test_census_parse.py
from census_parse import parse_entity_line, ints_to_uuid, extract_int_array_pos

# Real line from server log (truncated for test, but structurally complete)
SAMPLE_LINE = """[19:44:53] [Server thread/INFO]: Fisherman has the following entity data: {Paper.SpawnReason: "BREEDING", DeathTime: 0s, Bukkit.updateLevel: 2, RestocksToday: 0, Xp: 0, OnGround: 1b, LeftHanded: 0b, AbsorptionAmount: 0.0f, FoodLevel: 0b, LastRestock: 1001127489L, AgeLocked: 0b, Invulnerable: 0b, Brain: {memories: {"minecraft:last_woken": {value: 1018112423L}, "minecraft:job_site": {value: {pos: [I; 3172, 70, -754], dimension: "minecraft:overworld"}}, "minecraft:last_slept": {value: 1018111156L}, "minecraft:last_worked_at_poi": {value: 1001132966L}, "minecraft:meeting_point": {value: {pos: [I; 3170, 66, -883], dimension: "minecraft:overworld"}}}}, Paper.Origin: [3145.9453962812213d, 63.9375d, -1006.4578843209587d], Age: 0, Rotation: [44.46672f, 0.0f], HurtByTimestamp: 0, Bukkit.Aware: 1b, ForcedAge: 0, attributes: [{base: 0.5d, id: "minecraft:movement_speed"}, {base: 16.0d, id: "minecraft:follow_range", modifiers: [{operation: "add_multiplied_base", amount: -0.04554609496891499d, id: "minecraft:random_spawn_bonus"}]}], WorldUUIDMost: -8821679170295479734L, fall_distance: 0.0d, Air: 300s, Offers: {Recipes: [{buy: {id: "minecraft:emerald", count: 1}, sell: {id: "minecraft:cooked_cod", count: 6}, priceMultiplier: 0.05f, buyB: {id: "minecraft:cod", count: 6}, maxUses: 16}, {xp: 2, buy: {id: "minecraft:string", count: 20}, sell: {id: "minecraft:emerald", count: 1}, priceMultiplier: 0.05f, maxUses: 16}]}, UUID: [I; 346464738, -1288157012, -1558611273, 949520682], Inventory: [{id: "minecraft:beetroot", count: 2}, {id: "minecraft:beetroot_seeds", count: 7}, {id: "minecraft:wheat_seeds", count: 2}], Spigot.ticksLived: 821095, Paper.OriginWorld: [I; -2053957240, -1408023990, -1113309832, -1718626039], Gossips: [], VillagerData: {type: "minecraft:taiga", profession: "minecraft:fisherman", level: 1}, WorldUUIDLeast: -4781629316178913015L, Motion: [0.0d, -0.0784000015258789d, 0.0d], Pos: [3173.038130397757d, 70.0d, -755.0478646574805d], Fire: 0s, CanPickUpLoot: 1b, Health: 16.0f, HurtTime: 0s, FallFlying: 0b, PersistenceRequired: 0b, LastGossipDecay: 1024984001L, PortalCooldown: 0}"""

SAMPLE_LINE_WITH_GOSSIP = """[19:44:53] [Server thread/INFO]: Villager has the following entity data: {Paper.SpawnReason: "DEFAULT", DeathTime: 0s, Bukkit.updateLevel: 2, RestocksToday: 0, Xp: 0, OnGround: 1b, LeftHanded: 0b, AbsorptionAmount: 0.0f, FoodLevel: 0b, LastRestock: 991883132L, AgeLocked: 0b, Invulnerable: 0b, Brain: {memories: {"minecraft:last_worked_at_poi": {value: 991884047L}}}, Paper.Origin: [135.74785481367292d, 66.0d, 223.8206487666246d], Age: 0, Rotation: [92.51944f, 0.0f], HurtByTimestamp: 0, Bukkit.Aware: 1b, ForcedAge: 0, attributes: [{base: 20.0d, id: "minecraft:max_health"}, {base: 0.5d, id: "minecraft:movement_speed"}, {base: 16.0d, id: "minecraft:follow_range", modifiers: [{operation: "add_multiplied_base", amount: 0.026338384861324084d, id: "minecraft:random_spawn_bonus"}]}], WorldUUIDMost: -8821679170295479734L, fall_distance: 0.0d, Air: 300s, UUID: [I; -1857840997, 1245274443, -1362517790, 67902458], Inventory: [], Spigot.ticksLived: 3703310, Paper.OriginWorld: [I; -1845599319, -946321560, -1589277455, 1153834771], Gossips: [{Type: "minor_negative", Target: [I; -2075606571, 174605987, -2012950428, -563128421], Value: 5}, {Type: "major_negative", Target: [I; 456626118, 894125023, -1403978413, 486402248], Value: 25}], VillagerData: {type: "minecraft:plains", profession: "minecraft:none", level: 1}, WorldUUIDLeast: -4781629316178913015L, Motion: [0.0d, -0.0784000015258789d, 0.0d], Pos: [3177.0658599948592d, 70.0d, -763.9250000119209d], Fire: 0s, CanPickUpLoot: 1b, Health: 12.0f, HurtTime: 0s, FallFlying: 0b, PersistenceRequired: 0b, LastGossipDecay: 1025345203L, PortalCooldown: 0}"""


def test_ints_to_uuid():
    assert ints_to_uuid([346464738, -1288157012, -1558611273, 949520682]) == "14a5a2e2-b37a-6e2c-a302-f4b7389dc42a"


def test_parse_core_fields():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["uuid"] == "14a5a2e2-b37a-6e2c-a302-f4b7389dc42a"
    assert v["profession"] == "fisherman"
    assert v["profession_level"] == 1
    assert v["villager_type"] == "taiga"
    assert v["spawn_reason"] == "BREEDING"
    assert v["health"] == 16.0
    assert v["food_level"] == 0
    assert v["ticks_lived"] == 821095
    assert v["age"] == 0
    assert v["on_ground"] == 1
    assert v["xp"] == 0
    assert v["restocks_today"] == 0


def test_parse_position():
    v = parse_entity_line(SAMPLE_LINE)
    assert abs(v["pos_x"] - 3173.04) < 0.1
    assert abs(v["pos_y"] - 70.0) < 0.1
    assert abs(v["pos_z"] - (-755.05)) < 0.1


def test_parse_origin():
    v = parse_entity_line(SAMPLE_LINE)
    assert abs(v["origin_x"] - 3145.95) < 0.1
    assert abs(v["origin_y"] - 63.94) < 0.1
    assert abs(v["origin_z"] - (-1006.46)) < 0.1


def test_parse_brain_job_site():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["job_site_x"] == 3172
    assert v["job_site_y"] == 70
    assert v["job_site_z"] == -754


def test_parse_brain_meeting_point():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["meeting_point_x"] == 3170
    assert v["meeting_point_y"] == 66
    assert v["meeting_point_z"] == -883


def test_parse_brain_no_home():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["home_x"] is None
    assert v["home_y"] is None
    assert v["home_z"] is None


def test_parse_brain_sleep_ticks():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["last_slept"] == 1018111156
    assert v["last_woken"] == 1018112423
    assert v["last_worked"] == 1001132966


def test_parse_trades():
    v = parse_entity_line(SAMPLE_LINE)
    assert len(v["trades"]) == 2
    assert v["trades"][0]["buy_item"] == "emerald"
    assert v["trades"][0]["buy_count"] == 1
    assert v["trades"][0]["sell_item"] == "cooked_cod"
    assert v["trades"][0]["sell_count"] == 6
    assert v["trades"][0]["buy_b_item"] == "cod"
    assert v["trades"][0]["buy_b_count"] == 6
    assert v["trades"][1]["buy_item"] == "string"
    assert v["trades"][1]["sell_item"] == "emerald"


def test_parse_inventory():
    v = parse_entity_line(SAMPLE_LINE)
    assert len(v["inventory"]) == 3
    items = {i["item"]: i["count"] for i in v["inventory"]}
    assert items["beetroot"] == 2
    assert items["beetroot_seeds"] == 7
    assert items["wheat_seeds"] == 2


def test_parse_empty_inventory():
    v = parse_entity_line(SAMPLE_LINE_WITH_GOSSIP)
    assert v["inventory"] == []


def test_parse_gossip():
    v = parse_entity_line(SAMPLE_LINE_WITH_GOSSIP)
    assert len(v["gossip"]) == 2
    assert v["gossip"][0]["gossip_type"] == "minor_negative"
    assert v["gossip"][0]["value"] == 5
    assert v["gossip"][1]["gossip_type"] == "major_negative"
    assert v["gossip"][1]["value"] == 25
    # Target UUIDs should be hex strings
    assert "-" in v["gossip"][0]["target_uuid"]


def test_parse_empty_gossip():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["gossip"] == []


def test_parse_last_gossip_decay():
    v = parse_entity_line(SAMPLE_LINE)
    assert v["last_gossip_decay"] == 1024984001
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd villager-census && python -m pytest tests/test_census_parse.py -v
```

Expected: `ModuleNotFoundError: No module named 'census_parse'`

- [ ] **Step 3: Implement census_parse.py**

```python
# villager-census/census_parse.py
"""Parse Minecraft SNBT entity data from server log lines."""

import re


def ints_to_uuid(ints):
    """Convert 4 signed int32s to a hex UUID string."""
    parts = [i & 0xFFFFFFFF for i in ints]
    h = "".join(f"{p:08x}" for p in parts)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _extract_int_array(snbt, key):
    """Extract [I; a, b, c, ...] array following a key in SNBT."""
    pat = rf'"{key}":\s*\{{value:\s*\{{pos:\s*\[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\]'
    m = re.search(pat, snbt)
    if m:
        return [int(m.group(1)), int(m.group(2)), int(m.group(3))]
    return None


def _extract_brain(snbt):
    """Extract brain memory fields from SNBT."""
    result = {
        "home_x": None, "home_y": None, "home_z": None,
        "job_site_x": None, "job_site_y": None, "job_site_z": None,
        "meeting_point_x": None, "meeting_point_y": None, "meeting_point_z": None,
        "last_slept": None, "last_woken": None, "last_worked": None,
    }

    for mem_key, prefix in [("minecraft:home", "home"), ("minecraft:job_site", "job_site"), ("minecraft:meeting_point", "meeting_point")]:
        pos = _extract_int_array(snbt, mem_key)
        if pos:
            result[f"{prefix}_x"] = pos[0]
            result[f"{prefix}_y"] = pos[1]
            result[f"{prefix}_z"] = pos[2]

    for mem_key, field in [("minecraft:last_slept", "last_slept"), ("minecraft:last_woken", "last_woken"), ("minecraft:last_worked_at_poi", "last_worked")]:
        m = re.search(rf'"{mem_key}":\s*\{{value:\s*(-?\d+)L?\}}', snbt)
        if m:
            result[field] = int(m.group(1))

    return result


def _extract_trades(snbt):
    """Extract trade offers from Offers.Recipes in SNBT."""
    trades = []
    # Find each recipe block — they start with { and contain buy/sell
    recipes_match = re.search(r"Offers:\s*\{Recipes:\s*\[(.+?)\]\}", snbt)
    if not recipes_match:
        return trades

    recipes_str = recipes_match.group(1)
    # Split on },\s*{ at recipe boundaries — tricky because nested.
    # Instead, find each buy/sell pair
    slot = 0
    for recipe_m in re.finditer(r"\{[^{}]*buy:\s*\{[^}]+\}[^}]*sell:\s*\{[^}]+\}[^}]*\}", recipes_str):
        recipe = recipe_m.group(0)
        buy_m = re.search(r'buy:\s*\{id:\s*"minecraft:(\w+)",\s*count:\s*(\d+)\}', recipe)
        sell_m = re.search(r'sell:\s*\{id:\s*"minecraft:(\w+)",\s*count:\s*(\d+)\}', recipe)
        buyb_m = re.search(r'buyB:\s*\{id:\s*"minecraft:(\w+)",\s*count:\s*(\d+)\}', recipe)
        price_m = re.search(r'priceMultiplier:\s*([\d.]+)f', recipe)
        max_m = re.search(r'maxUses:\s*(\d+)', recipe)
        xp_m = re.search(r'xp:\s*(\d+)', recipe)
        if buy_m and sell_m:
            trades.append({
                "slot": slot,
                "buy_item": buy_m.group(1),
                "buy_count": int(buy_m.group(2)),
                "buy_b_item": buyb_m.group(1) if buyb_m else None,
                "buy_b_count": int(buyb_m.group(2)) if buyb_m else None,
                "sell_item": sell_m.group(1),
                "sell_count": int(sell_m.group(2)),
                "price_multiplier": float(price_m.group(1)) if price_m else None,
                "max_uses": int(max_m.group(1)) if max_m else None,
                "xp": int(xp_m.group(1)) if xp_m else None,
            })
            slot += 1
    return trades


def _extract_inventory(snbt):
    """Extract inventory items from SNBT."""
    inv_m = re.search(r"Inventory:\s*\[([^\]]*)\]", snbt)
    if not inv_m or not inv_m.group(1).strip():
        return []
    items = []
    for item_m in re.finditer(r'id:\s*"minecraft:(\w+)",\s*count:\s*(\d+)', inv_m.group(1)):
        items.append({"item": item_m.group(1), "count": int(item_m.group(2))})
    return items


def _extract_gossip(snbt):
    """Extract gossip entries from SNBT."""
    gossip_m = re.search(r"Gossips:\s*\[([^\]]*(?:\[I;[^\]]*\][^\]]*)*)\]", snbt)
    if not gossip_m or not gossip_m.group(1).strip():
        return []
    entries = []
    for entry_m in re.finditer(
        r'Type:\s*"(\w+)",\s*Target:\s*\[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\],\s*Value:\s*(\d+)',
        gossip_m.group(1),
    ):
        entries.append({
            "gossip_type": entry_m.group(1),
            "target_uuid": ints_to_uuid([int(entry_m.group(i)) for i in range(2, 6)]),
            "value": int(entry_m.group(6)),
        })
    return entries


def parse_entity_line(line):
    """Parse a server log line containing villager entity data.

    Args:
        line: A full log line like '[HH:MM:SS] [Server thread/INFO]: Farmer has the following entity data: {...}'

    Returns:
        Dict with all extracted villager fields, or None if line can't be parsed.
    """
    m = re.search(r"has the following entity data: (.+)$", line.strip())
    if not m:
        return None
    snbt = m.group(1)

    # UUID
    uuid_m = re.search(r"UUID:\s*\[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\]", snbt)
    if not uuid_m:
        return None
    uuid = ints_to_uuid([int(uuid_m.group(i)) for i in range(1, 5)])

    # Position
    pos_m = re.search(r"Pos:\s*\[(-?[\d.]+)d,\s*(-?[\d.]+)d,\s*(-?[\d.]+)d\]", snbt)
    pos = [float(pos_m.group(i)) for i in range(1, 4)] if pos_m else [None, None, None]

    # Origin
    origin_m = re.search(r"Paper\.Origin:\s*\[(-?[\d.]+)d,\s*(-?[\d.]+)d,\s*(-?[\d.]+)d\]", snbt)
    origin = [float(origin_m.group(i)) for i in range(1, 4)] if origin_m else [None, None, None]

    # VillagerData
    prof_m = re.search(r'profession:\s*"minecraft:(\w+)"', snbt)
    type_m = re.search(r'VillagerData:\s*\{type:\s*"minecraft:(\w+)"', snbt)
    level_m = re.search(r'VillagerData:\s*\{[^}]*level:\s*(\d+)', snbt)

    # Simple fields
    def int_field(key):
        m = re.search(rf"{key}:\s*(-?\d+)", snbt)
        return int(m.group(1)) if m else None

    def float_field(key):
        m = re.search(rf"{key}:\s*(-?[\d.]+)f?", snbt)
        return float(m.group(1)) if m else None

    def long_field(key):
        m = re.search(rf"{key}:\s*(-?\d+)L", snbt)
        return int(m.group(1)) if m else None

    def bool_field(key):
        m = re.search(rf"{key}:\s*([01])b", snbt)
        return int(m.group(1)) if m else None

    def str_field(key):
        m = re.search(rf'{key}:\s*"([^"]*)"', snbt)
        return m.group(1) if m else None

    brain = _extract_brain(snbt)

    return {
        "uuid": uuid,
        "pos_x": pos[0],
        "pos_y": pos[1],
        "pos_z": pos[2],
        "origin_x": origin[0],
        "origin_y": origin[1],
        "origin_z": origin[2],
        "spawn_reason": str_field("Paper.SpawnReason"),
        "profession": prof_m.group(1) if prof_m else None,
        "profession_level": int(level_m.group(1)) if level_m else None,
        "villager_type": type_m.group(1) if type_m else None,
        "health": float_field("Health"),
        "food_level": int_field("FoodLevel"),
        "xp": int_field("Xp"),
        "ticks_lived": int_field("Spigot.ticksLived"),
        "age": int_field("Age"),
        "on_ground": bool_field("OnGround"),
        "restocks_today": int_field("RestocksToday"),
        "last_restock": long_field("LastRestock"),
        "last_gossip_decay": long_field("LastGossipDecay"),
        **brain,
        "trades": _extract_trades(snbt),
        "inventory": _extract_inventory(snbt),
        "gossip": _extract_gossip(snbt),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_parse.py -v
```

Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census_parse.py villager-census/tests/test_census_parse.py
git commit -m "feat(census): add SNBT parser for villager entity data"
```

---

### Task 3: POI region file parser for beds

**Files:**
- Create: `villager-census/census_poi.py`
- Create: `villager-census/tests/test_census_poi.py`

Reuses the same approach as `world-migration-cli/migrate_regions.py` for reading .mca headers and decompressing chunks, but parses the full NBT to extract `minecraft:home` POI entries with positions and free_tickets.

- [ ] **Step 1: Write tests**

```python
# villager-census/tests/test_census_poi.py
import struct
import zlib
from pathlib import Path
from census_poi import parse_poi_region, read_nbt


def _build_poi_nbt(sections):
    """Build minimal POI chunk NBT bytes.

    sections: dict of {y_section_str: [{"type": str, "pos": [x,y,z], "free_tickets": int}]}
    """
    import io

    def write_tag(buf, tag_type, name, value):
        buf.write(struct.pack(">b", tag_type))
        encoded = name.encode("utf-8")
        buf.write(struct.pack(">H", len(encoded)))
        buf.write(encoded)
        _write_payload(buf, tag_type, value)

    def _write_payload(buf, tag_type, value):
        if tag_type == 1:  # Byte
            buf.write(struct.pack(">b", value))
        elif tag_type == 3:  # Int
            buf.write(struct.pack(">i", value))
        elif tag_type == 8:  # String
            encoded = value.encode("utf-8")
            buf.write(struct.pack(">H", len(encoded)))
            buf.write(encoded)
        elif tag_type == 9:  # List
            list_type, items = value
            buf.write(struct.pack(">b", list_type))
            buf.write(struct.pack(">i", len(items)))
            for item in items:
                _write_payload(buf, list_type, item)
        elif tag_type == 10:  # Compound
            for child_type, child_name, child_value in value:
                write_tag(buf, child_type, child_name, child_value)
            buf.write(struct.pack(">b", 0))  # TAG_End
        elif tag_type == 11:  # Int Array
            buf.write(struct.pack(">i", len(value)))
            for v in value:
                buf.write(struct.pack(">i", v))

    buf = io.BytesIO()
    # Root compound (unnamed in file, but named for write_tag)
    buf.write(struct.pack(">b", 10))  # TAG_Compound
    buf.write(struct.pack(">H", 0))   # Empty name

    # DataVersion
    write_tag(buf, 3, "DataVersion", 4671)

    # Sections compound
    write_tag(buf, 10, "Sections", [])  # start Sections
    # Actually we need to build Sections as a compound with string keys
    # Rewind and do it properly
    buf = io.BytesIO()
    buf.write(struct.pack(">b", 10))  # Root TAG_Compound
    buf.write(struct.pack(">H", 0))   # Empty name

    write_tag(buf, 3, "DataVersion", 4671)

    # Sections compound
    buf.write(struct.pack(">b", 10))  # TAG_Compound for Sections
    encoded = "Sections".encode("utf-8")
    buf.write(struct.pack(">H", len(encoded)))
    buf.write(encoded)

    for sec_key, records in sections.items():
        # Each section is a compound
        buf.write(struct.pack(">b", 10))  # TAG_Compound
        encoded = sec_key.encode("utf-8")
        buf.write(struct.pack(">H", len(encoded)))
        buf.write(encoded)

        # Valid byte
        write_tag(buf, 1, "Valid", 1)

        # Records list of compounds
        record_compounds = []
        for rec in records:
            record_compounds.append([
                (8, "type", rec["type"]),
                (11, "pos", rec["pos"]),
                (3, "free_tickets", rec["free_tickets"]),
            ])
        write_tag(buf, 9, "Records", (10, record_compounds))

        buf.write(struct.pack(">b", 0))  # End section compound

    buf.write(struct.pack(">b", 0))  # End Sections compound
    buf.write(struct.pack(">b", 0))  # End root compound

    return buf.getvalue()


def _build_poi_region(tmp_path, chunks):
    """Build a .mca file with POI chunks.

    chunks: list of {"slot": int, "sections": {sec_key: [records]}}
    """
    path = tmp_path / "r.0.0.mca"
    header = bytearray(8192)  # Location + timestamp headers
    sectors = bytearray()
    next_sector = 2  # First 2 sectors are headers

    for chunk in chunks:
        slot = chunk["slot"]
        nbt_data = _build_poi_nbt(chunk["sections"])
        compressed = zlib.compress(nbt_data)
        chunk_data = struct.pack(">I", len(compressed) + 1) + bytes([2]) + compressed

        # Pad to sector boundary
        padded_len = ((len(chunk_data) + 4095) // 4096) * 4096
        chunk_data = chunk_data.ljust(padded_len, b"\x00")
        sector_count = padded_len // 4096

        # Write location entry
        offset_bytes = next_sector.to_bytes(3, "big")
        struct.pack_into(">3sB", header, slot * 4, offset_bytes, sector_count)

        sectors += chunk_data
        next_sector += sector_count

    with open(path, "wb") as f:
        f.write(header)
        f.write(sectors)

    return path


def test_parse_poi_region_finds_beds(tmp_path):
    region_path = _build_poi_region(tmp_path, [
        {"slot": 0, "sections": {"4": [
            {"type": "minecraft:home", "pos": [100, 64, 200], "free_tickets": 0},
            {"type": "minecraft:home", "pos": [101, 64, 200], "free_tickets": 1},
            {"type": "minecraft:armorer", "pos": [102, 64, 200], "free_tickets": 0},
        ]}},
    ])
    beds = parse_poi_region(region_path)
    assert len(beds) == 2
    assert beds[0]["pos"] == [100, 64, 200]
    assert beds[0]["free_tickets"] == 0
    assert beds[1]["pos"] == [101, 64, 200]
    assert beds[1]["free_tickets"] == 1


def test_parse_poi_region_empty(tmp_path):
    region_path = _build_poi_region(tmp_path, [])
    beds = parse_poi_region(region_path)
    assert beds == []


def test_parse_poi_region_multiple_sections(tmp_path):
    region_path = _build_poi_region(tmp_path, [
        {"slot": 0, "sections": {
            "3": [{"type": "minecraft:home", "pos": [10, 48, 20], "free_tickets": 0}],
            "4": [{"type": "minecraft:home", "pos": [10, 65, 20], "free_tickets": 1}],
        }},
    ])
    beds = parse_poi_region(region_path)
    assert len(beds) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd villager-census && python -m pytest tests/test_census_poi.py -v
```

Expected: `ModuleNotFoundError: No module named 'census_poi'`

- [ ] **Step 3: Implement census_poi.py**

```python
# villager-census/census_poi.py
"""Parse POI region files (.mca) to extract bed (minecraft:home) locations."""

import io
import struct
import zlib
from pathlib import Path

SECTOR_SIZE = 4096


def read_nbt(f):
    """Read NBT data from a file-like object. Returns the root compound dict."""

    def _read_payload(f, tag_type):
        if tag_type == 0:
            return None
        if tag_type == 1:  # Byte
            return struct.unpack(">b", f.read(1))[0]
        if tag_type == 2:  # Short
            return struct.unpack(">h", f.read(2))[0]
        if tag_type == 3:  # Int
            return struct.unpack(">i", f.read(4))[0]
        if tag_type == 4:  # Long
            return struct.unpack(">q", f.read(8))[0]
        if tag_type == 5:  # Float
            return struct.unpack(">f", f.read(4))[0]
        if tag_type == 6:  # Double
            return struct.unpack(">d", f.read(8))[0]
        if tag_type == 7:  # Byte array
            length = struct.unpack(">i", f.read(4))[0]
            return f.read(length)
        if tag_type == 8:  # String
            length = struct.unpack(">H", f.read(2))[0]
            return f.read(length).decode("utf-8", errors="replace")
        if tag_type == 9:  # List
            list_type = struct.unpack(">b", f.read(1))[0]
            length = struct.unpack(">i", f.read(4))[0]
            return [_read_payload(f, list_type) for _ in range(length)]
        if tag_type == 10:  # Compound
            result = {}
            while True:
                child_type = struct.unpack(">b", f.read(1))[0]
                if child_type == 0:
                    break
                name_len = struct.unpack(">H", f.read(2))[0]
                name = f.read(name_len).decode("utf-8", errors="replace")
                result[name] = _read_payload(f, child_type)
            return result
        if tag_type == 11:  # Int array
            length = struct.unpack(">i", f.read(4))[0]
            return [struct.unpack(">i", f.read(4))[0] for _ in range(length)]
        if tag_type == 12:  # Long array
            length = struct.unpack(">i", f.read(4))[0]
            return [struct.unpack(">q", f.read(8))[0] for _ in range(length)]
        return None

    tag_type = struct.unpack(">b", f.read(1))[0]
    if tag_type == 0:
        return None
    name_len = struct.unpack(">H", f.read(2))[0]
    f.read(name_len)  # Root name (usually empty)
    return _read_payload(f, tag_type)


def parse_poi_region(region_path):
    """Parse a POI .mca file and return all bed (minecraft:home) entries.

    Returns:
        List of {"pos": [x, y, z], "free_tickets": int} dicts.
    """
    path = Path(region_path)
    beds = []

    with open(path, "rb") as f:
        locations = f.read(4096)

        for i in range(1024):
            offset = int.from_bytes(locations[i * 4 : i * 4 + 3], "big")
            if offset == 0:
                continue

            f.seek(offset * SECTOR_SIZE)
            length = struct.unpack(">I", f.read(4))[0]
            compression = f.read(1)[0]
            raw = f.read(length - 1)

            try:
                if compression == 2:
                    data = zlib.decompress(raw)
                elif compression == 1:
                    import gzip
                    data = gzip.decompress(raw)
                else:
                    data = raw
            except Exception:
                continue

            if b"minecraft:home" not in data:
                continue

            try:
                nbt = read_nbt(io.BytesIO(data))
            except Exception:
                continue

            if not nbt or "Sections" not in nbt:
                continue

            for sec_key, sec_val in nbt["Sections"].items():
                if not isinstance(sec_val, dict):
                    continue
                for record in sec_val.get("Records", []):
                    if not isinstance(record, dict):
                        continue
                    if record.get("type") == "minecraft:home":
                        pos = record.get("pos")
                        if isinstance(pos, list) and len(pos) == 3:
                            beds.append({
                                "pos": pos,
                                "free_tickets": record.get("free_tickets", 0),
                            })

    return beds


def parse_poi_regions(region_paths):
    """Parse multiple POI region files and return all beds."""
    all_beds = []
    for path in region_paths:
        all_beds.extend(parse_poi_region(path))
    return all_beds
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_poi.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census_poi.py villager-census/tests/test_census_poi.py
git commit -m "feat(census): add POI region parser for bed extraction"
```

---

### Task 4: Data collection module (SSH + tmux + log parsing)

**Files:**
- Create: `villager-census/census_collect.py`
- Create: `villager-census/tests/test_census_collect.py`

This module handles the SSH interaction: sending commands to the server console via tmux, waiting for output in the log, and parsing the results. Tests use mock subprocess calls.

- [ ] **Step 1: Write tests**

```python
# villager-census/tests/test_census_collect.py
from unittest.mock import patch, MagicMock
from census_collect import (
    check_players_online,
    get_player_position,
    send_console_command,
    collect_villager_dumps,
    download_poi_files,
    parse_death_log,
)


SAMPLE_LIST_OUTPUT = '[19:20:22] [Server thread/INFO]: There are 1 of a max of 20 players online: Termiduck'
SAMPLE_POS_OUTPUT = '[19:20:31] [Server thread/INFO]: Termiduck has the following entity data: [3159.209198957126d, 58.0d, -930.0230847671345d]'
SAMPLE_DEATH_LINE = "[19:54:24] [Server thread/INFO]: Villager Villager['Villager'/15678, uuid='d68d9d96-4802-4899-9b8e-bb8709eda5c0', l='ServerLevel[world_new]', x=3145.37, y=63.00, z=-965.30, cpos=[196, -61], tl=59771, v=true] died, message: 'Villager was killed'"
SAMPLE_DEATH_LINE_NAMED = "[18:32:16] [Server thread/INFO]: Villager Villager['Villager'/214, uuid='0a077d31-a230-41b5-bf50-c74d83892338', l='ServerLevel[world_new]', x=3158.63, y=64.00, z=-917.15, cpos=[197, -58], tl=708, v=true] died, message: 'Villager hit the ground too hard'"


def test_parse_death_log_extracts_fields():
    result = parse_death_log(SAMPLE_DEATH_LINE)
    assert result["uuid"] == "d68d9d96-4802-4899-9b8e-bb8709eda5c0"
    assert abs(result["x"] - 3145.37) < 0.01
    assert abs(result["y"] - 63.0) < 0.01
    assert abs(result["z"] - (-965.30)) < 0.01
    assert result["ticks_lived"] == 59771
    assert result["message"] == "Villager was killed"


def test_parse_death_log_hit_ground():
    result = parse_death_log(SAMPLE_DEATH_LINE_NAMED)
    assert result["uuid"] == "0a077d31-a230-41b5-bf50-c74d83892338"
    assert result["message"] == "Villager hit the ground too hard"
    assert result["ticks_lived"] == 708


def test_check_players_online():
    with patch("census_collect._ssh_command", return_value=SAMPLE_LIST_OUTPUT):
        players = check_players_online()
    assert players == ["Termiduck"]


def test_check_players_online_empty():
    with patch("census_collect._ssh_command", return_value='[19:20:22] [Server thread/INFO]: There are 0 of a max of 20 players online: '):
        players = check_players_online()
    assert players == []


def test_get_player_position():
    with patch("census_collect._tail_log_after_command", return_value=[SAMPLE_POS_OUTPUT]):
        pos = get_player_position("Termiduck")
    assert abs(pos[0] - 3159.21) < 0.1
    assert abs(pos[1] - 58.0) < 0.1
    assert abs(pos[2] - (-930.02)) < 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd villager-census && python -m pytest tests/test_census_collect.py -v
```

Expected: `ModuleNotFoundError: No module named 'census_collect'`

- [ ] **Step 3: Implement census_collect.py**

```python
# villager-census/census_collect.py
"""Collect villager data from PaperMC server via SSH and tmux."""

import re
import subprocess
import time
from pathlib import Path

SSH_HOST = "minecraft"
TMUX_SOCKET = "/tmp/tmux-1000/pmcserver-bb664df1"
TMUX_SESSION = "pmcserver"
LOG_PATH = "/home/minecraft/serverfiles/logs/latest.log"
POI_DIR = "/home/minecraft/serverfiles/world_new/poi"


def _ssh_command(cmd):
    """Run a command on the minecraft server via SSH and return stdout."""
    result = subprocess.run(
        ["ssh", SSH_HOST, cmd],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def _send_tmux(command):
    """Send a command to the server console via tmux."""
    subprocess.run(
        ["ssh", SSH_HOST, f"tmux -S {TMUX_SOCKET} send-keys -t {TMUX_SESSION} '{command}' Enter"],
        capture_output=True, text=True, timeout=10,
    )


def _tail_log_after_command(command, wait_seconds=5, tail_lines=200):
    """Send a console command, wait, then tail the log for output."""
    _send_tmux(command)
    time.sleep(wait_seconds)
    output = _ssh_command(f"tail -{tail_lines} {LOG_PATH}")
    return output.split("\n")


def check_players_online():
    """Get list of players currently online."""
    lines = _tail_log_after_command("list", wait_seconds=2, tail_lines=10)
    for line in lines:
        m = re.search(r"There are (\d+) of a max of \d+ players online:\s*(.*)", line)
        if m:
            count = int(m.group(1))
            if count == 0:
                return []
            names = [n.strip() for n in m.group(2).split(",") if n.strip()]
            return names
    return []


def get_player_position(player_name):
    """Get a player's current position. Returns (x, y, z) or None."""
    lines = _tail_log_after_command(
        f"data get entity {player_name} Pos", wait_seconds=2, tail_lines=10,
    )
    for line in lines:
        m = re.search(
            rf"{player_name} has the following entity data: \[(-?[\d.]+)d,\s*(-?[\d.]+)d,\s*(-?[\d.]+)d\]",
            line,
        )
        if m:
            return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


def collect_villager_dumps(center_x, center_z, radius):
    """Dump all villager entity data in the area and return raw log lines.

    Returns list of lines containing 'has the following entity data: {'
    """
    # Use a unique marker to find our output
    marker = f"CENSUS_{int(time.time())}"
    _send_tmux(f"say {marker}_START")
    time.sleep(1)

    _send_tmux(
        f"execute as @e[type=minecraft:villager,x={center_x},y=70,z={center_z},distance=..{radius}] run data get entity @s"
    )
    time.sleep(8)

    _send_tmux(f"say {marker}_END")
    time.sleep(2)

    output = _ssh_command(f"tail -500 {LOG_PATH}")
    lines = output.split("\n")

    # Find lines between markers
    in_range = False
    entity_lines = []
    for line in lines:
        if marker + "_START" in line:
            in_range = True
            continue
        if marker + "_END" in line:
            break
        if in_range and "has the following entity data: {" in line:
            entity_lines.append(line)

    return entity_lines


def download_poi_files(region_coords, local_dir):
    """Download POI region files from the server.

    Args:
        region_coords: List of (rx, rz) tuples, e.g. [(5, -3), (6, -2)]
        local_dir: Local directory to save files to

    Returns:
        List of local file paths
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for rx, rz in region_coords:
        filename = f"r.{rx}.{rz}.mca"
        remote_path = f"{POI_DIR}/{filename}"
        local_path = local_dir / filename
        subprocess.run(
            ["scp", f"{SSH_HOST}:{remote_path}", str(local_path)],
            capture_output=True, timeout=30,
        )
        if local_path.exists():
            paths.append(local_path)
    return paths


def parse_death_log(line):
    """Parse a villager death log line.

    Returns dict with: uuid, x, y, z, ticks_lived, message
    """
    m = re.search(
        r"uuid='([0-9a-f-]+)'.*?x=(-?[\d.]+),\s*y=(-?[\d.]+),\s*z=(-?[\d.]+).*?tl=(\d+).*?message:\s*'(.+?)'",
        line,
    )
    if not m:
        return None
    return {
        "uuid": m.group(1),
        "x": float(m.group(2)),
        "y": float(m.group(3)),
        "z": float(m.group(4)),
        "ticks_lived": int(m.group(5)),
        "message": m.group(6),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_collect.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census_collect.py villager-census/tests/test_census_collect.py
git commit -m "feat(census): add SSH/tmux data collection module"
```

---

### Task 5: Census pipeline orchestrator

**Files:**
- Create: `villager-census/census.py`
- Create: `villager-census/tests/test_census_pipeline.py`

This is the CLI entry point that wires together collection, parsing, POI, and database modules.

- [ ] **Step 1: Write integration test**

```python
# villager-census/tests/test_census_pipeline.py
from unittest.mock import patch
from pathlib import Path
from census import run_census
from census_db import init_db, get_all_snapshots, get_villager

# Use the real SNBT sample from test_census_parse.py
SAMPLE_ENTITY_LINE = """[19:44:53] [Server thread/INFO]: Fisherman has the following entity data: {Paper.SpawnReason: "BREEDING", DeathTime: 0s, Bukkit.updateLevel: 2, RestocksToday: 0, Xp: 0, OnGround: 1b, LeftHanded: 0b, AbsorptionAmount: 0.0f, FoodLevel: 0b, LastRestock: 1001127489L, AgeLocked: 0b, Invulnerable: 0b, Brain: {memories: {"minecraft:last_woken": {value: 1018112423L}, "minecraft:job_site": {value: {pos: [I; 3172, 70, -754], dimension: "minecraft:overworld"}}, "minecraft:last_slept": {value: 1018111156L}, "minecraft:last_worked_at_poi": {value: 1001132966L}, "minecraft:meeting_point": {value: {pos: [I; 3170, 66, -883], dimension: "minecraft:overworld"}}}}, Paper.Origin: [3145.9453962812213d, 63.9375d, -1006.4578843209587d], Age: 0, Rotation: [44.46672f, 0.0f], HurtByTimestamp: 0, Bukkit.Aware: 1b, ForcedAge: 0, attributes: [{base: 0.5d, id: "minecraft:movement_speed"}], WorldUUIDMost: -8821679170295479734L, fall_distance: 0.0d, Air: 300s, Offers: {Recipes: [{buy: {id: "minecraft:emerald", count: 1}, sell: {id: "minecraft:cooked_cod", count: 6}, priceMultiplier: 0.05f, buyB: {id: "minecraft:cod", count: 6}, maxUses: 16}]}, UUID: [I; 346464738, -1288157012, -1558611273, 949520682], Inventory: [{id: "minecraft:beetroot", count: 2}], Spigot.ticksLived: 821095, Paper.OriginWorld: [I; -2053957240, -1408023990, -1113309832, -1718626039], Gossips: [], VillagerData: {type: "minecraft:taiga", profession: "minecraft:fisherman", level: 1}, WorldUUIDLeast: -4781629316178913015L, Motion: [0.0d, -0.0784000015258789d, 0.0d], Pos: [3173.038130397757d, 70.0d, -755.0478646574805d], Fire: 0s, CanPickUpLoot: 1b, Health: 16.0f, HurtTime: 0s, FallFlying: 0b, PersistenceRequired: 0b, LastGossipDecay: 1024984001L, PortalCooldown: 0}"""


def test_run_census_end_to_end(tmp_path):
    db_path = tmp_path / "census.db"

    mock_beds = [
        {"pos": [3172, 69, -923], "free_tickets": 0},
        {"pos": [3140, 67, -1042], "free_tickets": 1},
    ]

    with patch("census.collect_villager_dumps", return_value=[SAMPLE_ENTITY_LINE]), \
         patch("census.check_players_online", return_value=["Termiduck"]), \
         patch("census.get_player_position", return_value=(3159.0, 58.0, -930.0)), \
         patch("census.download_poi_files", return_value=[]), \
         patch("census.parse_poi_regions", return_value=mock_beds):

        summary = run_census(
            db_path=db_path,
            center_x=3150,
            center_z=-950,
            radius=300,
        )

    assert summary["villager_count"] == 1
    assert summary["bed_count"] == 2
    assert summary["births"] == 1  # First census, all are new
    assert summary["deaths"] == 0

    # Verify database
    conn = init_db(db_path)
    snaps = get_all_snapshots(conn)
    assert len(snaps) == 1
    v = get_villager(conn, "14a5a2e2-b37a-6e2c-a302-f4b7389dc42a")
    assert v is not None
    assert v["spawn_reason"] == "BREEDING"

    # Verify trades were stored
    trades = conn.execute("SELECT * FROM villager_trades").fetchall()
    assert len(trades) == 1

    # Verify inventory was stored
    inv = conn.execute("SELECT * FROM villager_inventory").fetchall()
    assert len(inv) == 1

    # Verify beds were stored with claimed_by cross-ref
    beds = conn.execute("SELECT * FROM beds").fetchall()
    assert len(beds) == 2
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd villager-census && python -m pytest tests/test_census_pipeline.py -v
```

Expected: `ModuleNotFoundError: No module named 'census'`

- [ ] **Step 3: Implement census.py**

```python
# villager-census/census.py
"""Villager census pipeline orchestrator."""

import json
from datetime import datetime, timezone
from pathlib import Path

from census_collect import (
    check_players_online,
    collect_villager_dumps,
    download_poi_files,
    get_player_position,
)
from census_db import (
    export_all_json,
    get_latest_snapshot,
    get_snapshot_villager_uuids,
    init_db,
    insert_bed,
    insert_gossip,
    insert_inventory_item,
    insert_snapshot,
    insert_trade,
    insert_villager,
    insert_villager_state,
    mark_dead,
)
from census_parse import parse_entity_line
from census_poi import parse_poi_regions

# Default Piwigord area
DEFAULT_CENTER_X = 3150
DEFAULT_CENTER_Z = -950
DEFAULT_RADIUS = 300
DEFAULT_POI_REGIONS = [(5, -3), (5, -2), (6, -3), (6, -2)]


def run_census(*, db_path, center_x=DEFAULT_CENTER_X, center_z=DEFAULT_CENTER_Z, radius=DEFAULT_RADIUS, poi_regions=DEFAULT_POI_REGIONS, notes=None):
    """Run a full villager census.

    Returns a summary dict with population stats and deltas.
    """
    conn = init_db(db_path)
    previous = get_latest_snapshot(conn)
    prev_uuids = get_snapshot_villager_uuids(conn, previous["id"]) if previous else set()

    # Collect data
    players = check_players_online()
    entity_lines = collect_villager_dumps(center_x, center_z, radius)

    # Parse entities
    villagers = []
    for line in entity_lines:
        parsed = parse_entity_line(line)
        if parsed:
            villagers.append(parsed)

    # Collect beds from POI
    poi_paths = download_poi_files(poi_regions, Path("/tmp/census_poi"))
    beds = parse_poi_regions(poi_paths)

    # Filter beds to area bounds
    margin = 50
    beds = [b for b in beds if (center_x - radius - margin) <= b["pos"][0] <= (center_x + radius + margin) and (center_z - radius - margin) <= b["pos"][2] <= (center_z + radius + margin)]

    # Create snapshot
    timestamp = datetime.now(timezone.utc).isoformat()
    snap_id = insert_snapshot(
        conn,
        timestamp=timestamp,
        players_online=json.dumps(players),
        area_center_x=center_x,
        area_center_z=center_z,
        scan_radius=radius,
        villager_count=len(villagers),
        bed_count=len(beds),
        notes=notes,
    )

    # Build home->uuid lookup for bed cross-ref
    home_to_uuid = {}
    current_uuids = set()

    for v in villagers:
        uuid = v["uuid"]
        current_uuids.add(uuid)

        # Upsert villager identity
        insert_villager(
            conn,
            uuid=uuid,
            first_seen_snapshot=snap_id,
            last_seen_snapshot=snap_id,
            spawn_reason=v["spawn_reason"],
            origin_x=v["origin_x"],
            origin_y=v["origin_y"],
            origin_z=v["origin_z"],
        )

        # Insert state
        insert_villager_state(
            conn,
            snapshot_id=snap_id,
            villager_uuid=uuid,
            pos_x=v["pos_x"],
            pos_y=v["pos_y"],
            pos_z=v["pos_z"],
            health=v["health"],
            food_level=v["food_level"],
            profession=v["profession"],
            profession_level=v["profession_level"],
            villager_type=v["villager_type"],
            xp=v["xp"],
            ticks_lived=v["ticks_lived"],
            age=v["age"],
            home_x=v["home_x"],
            home_y=v["home_y"],
            home_z=v["home_z"],
            job_site_x=v["job_site_x"],
            job_site_y=v["job_site_y"],
            job_site_z=v["job_site_z"],
            meeting_point_x=v["meeting_point_x"],
            meeting_point_y=v["meeting_point_y"],
            meeting_point_z=v["meeting_point_z"],
            last_slept=v["last_slept"],
            last_woken=v["last_woken"],
            last_worked=v["last_worked"],
            last_restock=v["last_restock"],
            restocks_today=v["restocks_today"],
            on_ground=v["on_ground"],
            last_gossip_decay=v["last_gossip_decay"],
        )

        # Track bed assignment for cross-ref
        if v["home_x"] is not None:
            home_to_uuid[(v["home_x"], v["home_y"], v["home_z"])] = uuid

        # Insert trades
        for trade in v["trades"]:
            insert_trade(conn, snapshot_id=snap_id, villager_uuid=uuid, **trade)

        # Insert inventory
        for item in v["inventory"]:
            insert_inventory_item(conn, snapshot_id=snap_id, villager_uuid=uuid, **item)

        # Insert gossip
        for g in v["gossip"]:
            insert_gossip(conn, snapshot_id=snap_id, villager_uuid=uuid, **g)

    # Insert beds with cross-reference
    for bed in beds:
        pos_tuple = (bed["pos"][0], bed["pos"][1], bed["pos"][2])
        claimed_by = home_to_uuid.get(pos_tuple)
        insert_bed(
            conn,
            snapshot_id=snap_id,
            pos_x=bed["pos"][0],
            pos_y=bed["pos"][1],
            pos_z=bed["pos"][2],
            free_tickets=bed["free_tickets"],
            claimed_by=claimed_by,
        )

    # Detect deaths
    deaths = prev_uuids - current_uuids
    for uuid in deaths:
        mark_dead(conn, uuid, death_snapshot=previous["id"] if previous else snap_id)

    # Detect births
    births = current_uuids - prev_uuids

    conn.close()

    return {
        "snapshot_id": snap_id,
        "timestamp": timestamp,
        "villager_count": len(villagers),
        "bed_count": len(beds),
        "births": len(births),
        "deaths": len(deaths),
        "homeless": sum(1 for v in villagers if v["home_x"] is None),
        "players_online": players,
    }


def export_census_json(db_path):
    """Export entire census database as JSON for playground embedding."""
    conn = init_db(db_path)
    data = export_all_json(conn)
    conn.close()
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_pipeline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census.py villager-census/tests/test_census_pipeline.py
git commit -m "feat(census): add pipeline orchestrator with death/birth detection"
```

---

### Task 6: Historical seeding from culling logs

**Files:**
- Create: `villager-census/census_seed.py`
- Create: `villager-census/tests/test_census_seed.py`

Seeds the database with reconstructed snapshots from the March 30 culling event.

- [ ] **Step 1: Write tests**

```python
# villager-census/tests/test_census_seed.py
from census_seed import parse_death_logs, build_seed_snapshots
from census_db import init_db, get_all_snapshots, get_villager, get_snapshot_villager_uuids

SAMPLE_DEATHS = [
    "[19:54:24] [Server thread/INFO]: Villager Villager['Villager'/15678, uuid='d68d9d96-4802-4899-9b8e-bb8709eda5c0', l='ServerLevel[world_new]', x=3145.37, y=63.00, z=-965.30, cpos=[196, -61], tl=59771, v=true] died, message: 'Villager was killed'",
    "[18:32:16] [Server thread/INFO]: Villager Villager['Villager'/214, uuid='0a077d31-a230-41b5-bf50-c74d83892338', l='ServerLevel[world_new]', x=3158.63, y=64.00, z=-917.15, cpos=[197, -58], tl=708, v=true] died, message: 'Villager hit the ground too hard'",
]

# A survivor (DEFAULT spawn, still alive in current census)
SURVIVOR = {
    "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "spawn_reason": "DEFAULT",
    "origin_x": 135.7, "origin_y": 66.0, "origin_z": 223.8,
    "pos_x": 3177.0, "pos_y": 70.0, "pos_z": -763.9,
    "profession": "none", "profession_level": 1, "villager_type": "plains",
    "health": 12.0, "food_level": 0, "xp": 0, "ticks_lived": 3703310,
    "age": 0, "on_ground": 1, "restocks_today": 0,
    "home_x": None, "home_y": None, "home_z": None,
    "job_site_x": None, "job_site_y": None, "job_site_z": None,
    "meeting_point_x": None, "meeting_point_y": None, "meeting_point_z": None,
    "last_slept": None, "last_woken": None, "last_worked": 991884047,
    "last_restock": None, "last_gossip_decay": 1025345203,
    "trades": [], "inventory": [], "gossip": [],
}


def test_parse_death_logs():
    deaths = parse_death_logs(SAMPLE_DEATHS)
    assert len(deaths) == 2
    assert deaths[0]["uuid"] == "d68d9d96-4802-4899-9b8e-bb8709eda5c0"
    assert deaths[1]["uuid"] == "0a077d31-a230-41b5-bf50-c74d83892338"


def test_build_seed_snapshots(tmp_path):
    db_path = tmp_path / "census.db"
    deaths = parse_death_logs(SAMPLE_DEATHS)
    current_villagers = [SURVIVOR]

    build_seed_snapshots(db_path, deaths, current_villagers)

    conn = init_db(db_path)
    snaps = get_all_snapshots(conn)
    assert len(snaps) == 2  # Pre-culling and post-culling

    # Pre-culling should have dead villagers + survivors
    pre_uuids = get_snapshot_villager_uuids(conn, snaps[0]["id"])
    assert len(pre_uuids) == 3  # 2 dead + 1 survivor

    # Post-culling should only have survivors
    post_uuids = get_snapshot_villager_uuids(conn, snaps[1]["id"])
    assert len(post_uuids) == 1

    # Dead villagers should be marked
    dead1 = get_villager(conn, "d68d9d96-4802-4899-9b8e-bb8709eda5c0")
    assert dead1["presumed_dead"] == 1

    # Survivor should not be dead
    surv = get_villager(conn, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert surv["presumed_dead"] == 0

    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd villager-census && python -m pytest tests/test_census_seed.py -v
```

Expected: `ModuleNotFoundError: No module named 'census_seed'`

- [ ] **Step 3: Implement census_seed.py**

```python
# villager-census/census_seed.py
"""Seed the census database with historical data from the March 30 culling."""

import json
from pathlib import Path

from census_collect import parse_death_log
from census_db import (
    init_db,
    insert_bed,
    insert_gossip,
    insert_inventory_item,
    insert_snapshot,
    insert_trade,
    insert_villager,
    insert_villager_state,
    mark_dead,
)


def parse_death_logs(lines):
    """Parse death log lines into structured dicts."""
    deaths = []
    for line in lines:
        parsed = parse_death_log(line)
        if parsed:
            deaths.append(parsed)
    return deaths


def build_seed_snapshots(db_path, deaths, current_villagers):
    """Create pre-culling and post-culling seed snapshots.

    Args:
        db_path: Path to SQLite database
        deaths: List of dicts from parse_death_logs
        current_villagers: List of parsed villager dicts from the current census
    """
    conn = init_db(db_path)

    # Identify survivors: current DEFAULT villagers who were alive pre-culling
    dead_uuids = {d["uuid"] for d in deaths}
    survivors = [v for v in current_villagers if v["uuid"] not in dead_uuids]

    # Snapshot 0: Pre-culling (all dead + all survivors)
    pre_snap = insert_snapshot(
        conn,
        timestamp="2026-03-30T18:30:00Z",
        players_online=json.dumps(["Termiduck"]),
        area_center_x=3150,
        area_center_z=-950,
        scan_radius=300,
        villager_count=len(deaths) + len(survivors),
        bed_count=None,
        notes="Reconstructed from death logs. Partial data — only UUIDs and positions known.",
    )

    # Insert dead villagers into pre-culling snapshot
    for d in deaths:
        insert_villager(
            conn,
            uuid=d["uuid"],
            first_seen_snapshot=pre_snap,
            last_seen_snapshot=pre_snap,
            spawn_reason=None,
            origin_x=None,
            origin_y=None,
            origin_z=None,
        )
        insert_villager_state(
            conn,
            snapshot_id=pre_snap,
            villager_uuid=d["uuid"],
            pos_x=d["x"],
            pos_y=d["y"],
            pos_z=d["z"],
            health=None,
            food_level=None,
            profession=None,
            profession_level=None,
            villager_type=None,
            xp=None,
            ticks_lived=d["ticks_lived"],
            age=None,
            home_x=None, home_y=None, home_z=None,
            job_site_x=None, job_site_y=None, job_site_z=None,
            meeting_point_x=None, meeting_point_y=None, meeting_point_z=None,
            last_slept=None, last_woken=None, last_worked=None,
            last_restock=None, restocks_today=None, on_ground=None,
            last_gossip_decay=None,
        )
        mark_dead(conn, d["uuid"], death_snapshot=pre_snap)

    # Insert survivors into pre-culling snapshot (with origin as position)
    for v in survivors:
        insert_villager(
            conn,
            uuid=v["uuid"],
            first_seen_snapshot=pre_snap,
            last_seen_snapshot=pre_snap,
            spawn_reason=v["spawn_reason"],
            origin_x=v["origin_x"],
            origin_y=v["origin_y"],
            origin_z=v["origin_z"],
        )
        insert_villager_state(
            conn,
            snapshot_id=pre_snap,
            villager_uuid=v["uuid"],
            pos_x=v.get("origin_x") or v["pos_x"],
            pos_y=v.get("origin_y") or v["pos_y"],
            pos_z=v.get("origin_z") or v["pos_z"],
            health=None,
            food_level=None,
            profession=v["profession"],
            profession_level=v["profession_level"],
            villager_type=v["villager_type"],
            xp=None,
            ticks_lived=None,
            age=None,
            home_x=None, home_y=None, home_z=None,
            job_site_x=None, job_site_y=None, job_site_z=None,
            meeting_point_x=None, meeting_point_y=None, meeting_point_z=None,
            last_slept=None, last_woken=None, last_worked=None,
            last_restock=None, restocks_today=None, on_ground=None,
            last_gossip_decay=None,
        )

    # Snapshot 1: Post-culling (survivors only)
    post_snap = insert_snapshot(
        conn,
        timestamp="2026-03-30T19:55:00Z",
        players_online=json.dumps(["Termiduck"]),
        area_center_x=3150,
        area_center_z=-950,
        scan_radius=300,
        villager_count=len(survivors),
        bed_count=None,
        notes="Reconstructed. Survivors inferred from current census DEFAULT villagers + death log subtraction.",
    )

    for v in survivors:
        insert_villager(
            conn,
            uuid=v["uuid"],
            first_seen_snapshot=pre_snap,
            last_seen_snapshot=post_snap,
            spawn_reason=v["spawn_reason"],
            origin_x=v["origin_x"],
            origin_y=v["origin_y"],
            origin_z=v["origin_z"],
        )
        insert_villager_state(
            conn,
            snapshot_id=post_snap,
            villager_uuid=v["uuid"],
            pos_x=v.get("origin_x") or v["pos_x"],
            pos_y=v.get("origin_y") or v["pos_y"],
            pos_z=v.get("origin_z") or v["pos_z"],
            health=None,
            food_level=None,
            profession=v["profession"],
            profession_level=v["profession_level"],
            villager_type=v["villager_type"],
            xp=None,
            ticks_lived=None,
            age=None,
            home_x=None, home_y=None, home_z=None,
            job_site_x=None, job_site_y=None, job_site_z=None,
            meeting_point_x=None, meeting_point_y=None, meeting_point_z=None,
            last_slept=None, last_woken=None, last_worked=None,
            last_restock=None, restocks_today=None, on_ground=None,
            last_gossip_decay=None,
        )

    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd villager-census && python -m pytest tests/test_census_seed.py -v
```

Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add villager-census/census_seed.py villager-census/tests/test_census_seed.py
git commit -m "feat(census): add historical seeding from culling death logs"
```

---

### Task 7: Add census.db to .gitignore and create tests/__init__.py

**Files:**
- Modify: `.gitignore`
- Create: `villager-census/__init__.py` (empty)
- Create: `villager-census/tests/__init__.py` (empty)
- Create: `villager-census/tests/conftest.py`

- [ ] **Step 1: Add census.db to .gitignore**

Append to `.gitignore`:

```
# Census database
villager-census/census.db
```

- [ ] **Step 2: Create package files and conftest**

```python
# villager-census/tests/conftest.py
import sys
from pathlib import Path

# Add parent directory to path so tests can import census modules
sys.path.insert(0, str(Path(__file__).parent.parent))
```

Create empty `villager-census/__init__.py` and `villager-census/tests/__init__.py`.

- [ ] **Step 3: Run all tests to verify everything works**

```bash
cd villager-census && python -m pytest tests/ -v
```

Expected: All tests pass (8 + 16 + 3 + 5 + 1 + 2 = 35 tests)

- [ ] **Step 4: Commit**

```bash
git add .gitignore villager-census/__init__.py villager-census/tests/__init__.py villager-census/tests/conftest.py
git commit -m "chore(census): add gitignore, package files, and test conftest"
```

---

### Task 8: Write the SKILL.md for /villager-census

**Files:**
- Create: `plugins/minecraft-papermc-server/skills/villager-census/SKILL.md`

This task uses `/writing-skills` to create the skill definition. The skill orchestrates the full census pipeline and finishes by invoking the `playground` skill.

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p plugins/minecraft-papermc-server/skills/villager-census
```

- [ ] **Step 2: Write SKILL.md**

```markdown
---
name: villager-census
description: Run a villager population census on the PaperMC server. Collects entity data via SSH/tmux, parses POI files for beds, stores everything in SQLite, detects births and deaths since the last census, and opens an interactive HTML playground to inspect results and compare snapshots.
---

# Villager Census

Collect a full population snapshot of Minecraft villagers in a specified area, store it in a SQLite database, and produce an interactive visual report.

## Prerequisites

- A player must be online and near the target area (chunks must be loaded for entity data to be available)
- SSH access to the Minecraft server via `ssh minecraft`
- The server console is accessible via tmux at `/tmp/tmux-1000/pmcserver-bb664df1`

## Inputs

Ask for any not already known:

- **Area center** — defaults to Piwigord: x=3150, z=-950
- **Scan radius** — defaults to 300 blocks
- **Notes** — optional free-text annotation for this snapshot (e.g. "post-culling", "after bed expansion")

## Step 1 — Verify server access

1. Run `ssh minecraft "tmux -S /tmp/tmux-1000/pmcserver-bb664df1 send-keys -t pmcserver 'list' Enter"` and check the log for players online
2. If no players are online, STOP and tell the user: "No players online — chunks aren't loaded, so villager data is unavailable. Someone needs to be near Piwigord for the census to work."
3. Get the nearest player's position and verify they're within range of the target area

## Step 2 — Run the census pipeline

Run the Python census tool:

```bash
cd villager-census && python census.py --db census.db --center-x 3150 --center-z -950 --radius 300
```

If this is the first run and `census.db` doesn't exist yet, first run the seeding script:

```bash
cd villager-census && python census_seed.py --db census.db
```

The pipeline will:
1. Send `execute as @e[type=minecraft:villager,...] run data get entity @s` to the server console
2. Parse all entity data from the server log
3. Download POI region files and extract bed locations
4. Cross-reference beds with villager brain data
5. Write everything to the SQLite database
6. Detect births (new UUIDs) and deaths (missing UUIDs) since last snapshot

## Step 3 — Report summary

Print the census summary to the user:

```
## Census Summary — [date]

**Population:** [count] villagers ([+/-delta] from last census)
**Beds:** [count] ([claimed]/[total] claimed)
**Births:** [count] new villagers since last census
**Deaths:** [count] villagers disappeared since last census
**Homeless:** [count] villagers without a bed

### Profession breakdown
| Profession | Count | Change |
|---|---|---|
| farmer | 31 | +2 |
| ... | ... | ... |
```

## Step 4 — Launch playground

Invoke the `playground` skill to generate an interactive HTML viewer. The playground should:

1. Read the full database export from `villager-census/census.db` using `census.export_census_json()`
2. Embed the JSON data directly in the HTML
3. Include these views:
   - **Population timeline** — line chart of villager count and bed count across all snapshots
   - **Current census table** — sortable list of all villagers with profession, health, bed status, position
   - **Map view** — 2D scatter plot of villager positions, color-coded by profession, with bed markers
   - **Snapshot comparison** — dropdown to select two snapshots, shows births, deaths, movement, bed changes
   - **Villager detail** — click a villager to see full history across snapshots (position trail, profession changes, gossip)
4. Open the playground in the user's browser

## Database location

The SQLite database lives at `villager-census/census.db` in this repo. It is gitignored.
```

- [ ] **Step 3: Validate skill with /writing-skills**

Invoke `/writing-skills` to quality-check the SKILL.md, verify it follows the correct patterns, and make any needed adjustments.

- [ ] **Step 4: Commit**

```bash
git add plugins/minecraft-papermc-server/skills/villager-census/SKILL.md
git commit -m "feat(census): add /villager-census skill definition"
```

---

### Task 9: Update plugin metadata and CLAUDE.md

**Files:**
- Modify: `plugins/minecraft-papermc-server/.claude-plugin/plugin.json` — bump version
- Modify: `.claude-plugin/marketplace.json` — bump version
- Modify: `CLAUDE.md` — add skill to tables

- [ ] **Step 1: Bump plugin version to 1.0.4**

In `plugins/minecraft-papermc-server/.claude-plugin/plugin.json`, change `"version": "1.0.3"` to `"version": "1.0.4"`.

In `.claude-plugin/marketplace.json`, update the minecraft-papermc-server version from `1.0.3` to `1.0.4`.

- [ ] **Step 2: Update CLAUDE.md**

Add to the Repository Structure tree:

```
  plugins/minecraft-papermc-server/           # Server plugin management (v1.0.4) — skills: ..., villager-census
```

Add to the Server skill invocations table:

```
| `/villager-census` | Run a population census, store in SQLite, open playground viewer |
```

Add to Docs table:

```
| Villager census design | `docs/superpowers/specs/2026-04-03-villager-census-design.md` |
| Villager census plan | `docs/superpowers/plans/2026-04-03-villager-census.md` |
```

- [ ] **Step 3: Commit**

```bash
git add plugins/minecraft-papermc-server/.claude-plugin/plugin.json .claude-plugin/marketplace.json CLAUDE.md
git commit -m "docs: add villager-census skill to plugin metadata and CLAUDE.md"
```

---

### Task 10: Run the initial seed + first live census

This is the execution task that actually populates the database for the first time.

**Files:**
- Uses: `villager-census/census_seed.py`, `villager-census/census.py`

- [ ] **Step 1: Download the culling death log**

```bash
scp minecraft:/home/minecraft/serverfiles/logs/2026-03-30-3.log.gz /tmp/
gunzip -k /tmp/2026-03-30-3.log.gz
grep "died" /tmp/2026-03-30-3.log | grep "Villager" > /tmp/culling_deaths.txt
wc -l /tmp/culling_deaths.txt
```

Expected: 107 lines

- [ ] **Step 2: Run the seeding script**

```bash
cd villager-census && python census_seed.py --db census.db --deaths /tmp/culling_deaths.txt
```

Verify: `sqlite3 census.db "SELECT id, timestamp, villager_count, notes FROM snapshots"`

Expected: 2 rows (pre-culling ~118, post-culling ~43)

- [ ] **Step 3: Run the first live census**

Verify a player is online near Piwigord first, then:

```bash
cd villager-census && python census.py --db census.db --center-x 3150 --center-z -950 --radius 300 --notes "First live census"
```

Verify: `sqlite3 census.db "SELECT id, timestamp, villager_count, bed_count FROM snapshots"`

Expected: 3 rows total

- [ ] **Step 4: Verify data integrity**

```bash
sqlite3 census.db "SELECT COUNT(*) FROM villagers"
sqlite3 census.db "SELECT COUNT(*) FROM villager_states"
sqlite3 census.db "SELECT COUNT(*) FROM beds WHERE snapshot_id=3"
sqlite3 census.db "SELECT COUNT(*) FROM villager_trades WHERE snapshot_id=3"
sqlite3 census.db "SELECT presumed_dead, COUNT(*) FROM villagers GROUP BY presumed_dead"
```

- [ ] **Step 5: Commit the seeded state (not the db, just confirm)**

The database is gitignored, so just verify everything looks correct and report the summary to the user.
