"""census.py — CLI entry point and pipeline orchestrator for the villager census."""

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from census_collect import (
    check_chunks_loaded,
    check_players_online,
    collect_villager_dumps,
    collect_villager_dumps_box,
    configure as configure_transport,
    get_poi_files,
    get_player_position,
)
from census_db import (
    export_all_json,
    get_latest_snapshot,
    get_snapshot_villager_uuids,
    init_db,
    insert_bed,
    insert_census_run,
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
from census_zones import bounding_box, classify_bed, classify_villager, make_single_zone


# ---------------------------------------------------------------------------
# Defaults (backward compat for single-point mode)
# ---------------------------------------------------------------------------

DEFAULT_CENTER_X = 3150
DEFAULT_CENTER_Z = -950
DEFAULT_RADIUS = 300
DEFAULT_POI_REGIONS = [(5, -3), (5, -2), (6, -3), (6, -2)]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_census(*, db_path, zones, poi_regions, notes=None, skipped_zones=None):
    """Run the full census pipeline and return a summary dict.

    zones: list of zone dicts to scan (only loaded zones in --auto mode)
    poi_regions: list of (rx, rz) tuples for bed data
    skipped_zones: list of zone names that were skipped (chunks not loaded)

    Steps:
    1. Init DB, get previous snapshot UUIDs.
    2. Check players online.
    3. Collect villager entity dumps (box query covering all zones).
    4. Parse entity lines into villager dicts.
    5. Download and parse POI files for bed data.
    6. Filter beds to bounding box.
    7. Insert snapshot row (with coverage info).
    8. Classify and insert villagers, states, trades, inventory, gossip.
    9. Classify and insert beds (with home→uuid cross-reference).
    10. Detect deaths and births vs previous snapshot.
    11. Return summary with per-zone breakdown.
    """
    skipped_zones = skipped_zones or []
    conn = init_db(db_path)

    # Step 1: previous snapshot
    prev_snapshot = get_latest_snapshot(conn)
    prev_uuids = set()
    if prev_snapshot is not None:
        prev_uuids = get_snapshot_villager_uuids(conn, prev_snapshot["id"])

    # Step 2: players online
    players = check_players_online()

    # Step 3: collect entity lines using bounding box
    x_min, z_min, x_max, z_max = bounding_box(zones)
    entity_lines = collect_villager_dumps_box(x_min, z_min, x_max, z_max)

    # Step 4: parse each line
    villagers = []
    for line in entity_lines:
        try:
            v = parse_entity_line(line)
            if v.get("uuid"):
                villagers.append(v)
        except (ValueError, KeyError):
            pass

    # Step 5: download and parse POI files
    poi_local_dir = Path("/tmp/census_poi")
    poi_paths = get_poi_files(poi_regions, poi_local_dir)
    all_beds = parse_poi_regions(poi_paths)

    # Step 6: filter beds to bounding box (with margin)
    margin = 50
    beds = [
        b for b in all_beds
        if (x_min - margin) <= b["pos"][0] <= (x_max + margin)
        and (z_min - margin) <= b["pos"][2] <= (z_max + margin)
    ]

    # Step 7: insert snapshot — store bounding box center as area_center
    cx = (x_min + x_max) / 2
    cz = (z_min + z_max) / 2
    scan_radius = max(x_max - x_min, z_max - z_min) // 2
    timestamp = datetime.now(timezone.utc).isoformat()
    zone_names_scanned = [z["name"] for z in zones]
    snapshot_id = insert_snapshot(
        conn,
        timestamp=timestamp,
        players_online=json.dumps(players),
        area_center_x=cx,
        area_center_z=cz,
        scan_radius=scan_radius,
        villager_count=len(villagers),
        bed_count=len(beds),
        notes=notes,
        zones_scanned=json.dumps(zone_names_scanned),
        zones_skipped=json.dumps(skipped_zones),
    )

    # Step 8: classify and insert villagers
    home_to_uuid = {}
    current_uuids = set()
    zone_counts = Counter()

    for v in villagers:
        uuid = v["uuid"]
        current_uuids.add(uuid)

        # Classify into zone
        vx = v.get("pos_x")
        vz = v.get("pos_z")
        zone_name = None
        if vx is not None and vz is not None:
            zone_name = classify_villager(zones, x=vx, z=vz)
        zone_counts[zone_name or "unclassified"] += 1

        insert_villager(
            conn,
            uuid=uuid,
            first_seen_snapshot=snapshot_id,
            last_seen_snapshot=snapshot_id,
            spawn_reason=v.get("spawn_reason"),
            origin_x=v.get("origin_x"),
            origin_y=v.get("origin_y"),
            origin_z=v.get("origin_z"),
        )

        insert_villager_state(
            conn,
            snapshot_id=snapshot_id,
            villager_uuid=uuid,
            pos_x=vx,
            pos_y=v.get("pos_y"),
            pos_z=vz,
            health=v.get("health"),
            food_level=v.get("food_level"),
            profession=v.get("profession"),
            profession_level=v.get("profession_level"),
            villager_type=v.get("villager_type"),
            xp=v.get("xp"),
            ticks_lived=v.get("ticks_lived"),
            age=v.get("age"),
            home_x=v.get("home_x"),
            home_y=v.get("home_y"),
            home_z=v.get("home_z"),
            job_site_x=v.get("job_site_x"),
            job_site_y=v.get("job_site_y"),
            job_site_z=v.get("job_site_z"),
            meeting_point_x=v.get("meeting_point_x"),
            meeting_point_y=v.get("meeting_point_y"),
            meeting_point_z=v.get("meeting_point_z"),
            last_slept=v.get("last_slept"),
            last_woken=v.get("last_woken"),
            last_worked=v.get("last_worked"),
            last_restock=v.get("last_restock"),
            restocks_today=v.get("restocks_today"),
            on_ground=v.get("on_ground"),
            last_gossip_decay=v.get("last_gossip_decay"),
            zone=zone_name,
        )

        for trade in v.get("trades", []):
            insert_trade(
                conn,
                snapshot_id=snapshot_id,
                villager_uuid=uuid,
                slot=trade["slot"],
                buy_item=trade.get("buy_item"),
                buy_count=trade.get("buy_count"),
                buy_b_item=trade.get("buy_b_item"),
                buy_b_count=trade.get("buy_b_count"),
                sell_item=trade.get("sell_item"),
                sell_count=trade.get("sell_count"),
                price_multiplier=trade.get("price_multiplier"),
                max_uses=trade.get("max_uses"),
                xp=trade.get("xp"),
            )

        for item in v.get("inventory", []):
            insert_inventory_item(
                conn,
                snapshot_id=snapshot_id,
                villager_uuid=uuid,
                item=item["item"],
                count=item["count"],
            )

        for g in v.get("gossip", []):
            insert_gossip(
                conn,
                snapshot_id=snapshot_id,
                villager_uuid=uuid,
                gossip_type=g["gossip_type"],
                target_uuid=g.get("target_uuid"),
                value=g["value"],
            )

        # Build home lookup for bed cross-ref
        hx, hy, hz = v.get("home_x"), v.get("home_y"), v.get("home_z")
        if hx is not None and hy is not None and hz is not None:
            home_to_uuid[(int(hx), int(hy), int(hz))] = uuid

    # Step 9: classify and insert beds
    bed_zone_counts = Counter()
    for bed in beds:
        bx, by, bz = bed["pos"][0], bed["pos"][1], bed["pos"][2]
        claimed_by = home_to_uuid.get((int(bx), int(by), int(bz)))
        bed_zone = classify_bed(zones, x=bx, z=bz)
        bed_zone_counts[bed_zone or "unclassified"] += 1
        insert_bed(
            conn,
            snapshot_id=snapshot_id,
            pos_x=bx,
            pos_y=by,
            pos_z=bz,
            free_tickets=bed.get("free_tickets", 0),
            claimed_by=claimed_by,
            zone=bed_zone,
        )

    # Step 10: deaths and births
    deaths_uuids = prev_uuids - current_uuids
    births_uuids = current_uuids - prev_uuids

    for uuid in deaths_uuids:
        mark_dead(conn, uuid, snapshot_id)

    # Step 11: compute homeless count
    homeless = sum(
        1 for v in villagers
        if v.get("home_x") is None
    )

    conn.close()

    # Build per-zone summary (always includes every defined zone + unclassified)
    zone_summary = {}
    for zone in zones:
        name = zone["name"]
        zone_summary[name] = {
            "villagers": zone_counts.get(name, 0),
            "beds": bed_zone_counts.get(name, 0),
        }
    unclassified_v = zone_counts.get("unclassified", 0)
    unclassified_b = bed_zone_counts.get("unclassified", 0)
    if unclassified_v or unclassified_b:
        zone_summary["unclassified"] = {
            "villagers": unclassified_v,
            "beds": unclassified_b,
        }

    return {
        "snapshot_id": snapshot_id,
        "timestamp": timestamp,
        "villager_count": len(villagers),
        "bed_count": len(beds),
        "births": len(births_uuids),
        "deaths": len(deaths_uuids),
        "homeless": homeless,
        "players_online": players,
        "zones": zone_summary,
    }


def export_census_json(db_path):
    """Export the entire census DB as a JSON-serializable dict."""
    conn = init_db(db_path)
    data = export_all_json(conn)
    conn.close()
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

CRON_TAG = "# villager-census"


def _build_cron_command(args):
    """Build the cron command line from current args."""
    script = str(Path(__file__).resolve())
    python = sys.executable
    db = str(Path(args.db).resolve())

    parts = [python, script, "--auto", "--db", db]
    if args.config:
        parts += ["--config", str(Path(args.config).resolve())]
        if args.place:
            parts += ["--place", args.place]
    elif args.center:
        parts += ["--center", args.center]
        if args.radius is not None:
            parts += ["--radius", str(args.radius)]
        if args.name:
            parts += ["--name", args.name]
    elif args.rect:
        parts += ["--rect", args.rect]
        if args.name:
            parts += ["--name", args.name]
    else:
        return None

    if args.ssh:
        parts += ["--ssh", args.ssh]
    if args.poi_regions:
        parts += ["--poi-regions", args.poi_regions]

    return " ".join(parts)


def _install_cron(args, parser):
    """Install a cron job for automatic census runs."""
    minutes = int(args.install)
    cmd = _build_cron_command(args)
    if cmd is None:
        parser.error("--install requires --config, --center, or --rect")

    cron_line = f"*/{minutes} * * * * {cmd} >> /tmp/villager-census.log 2>&1 {CRON_TAG}"

    # Remove existing census cron entries, then add the new one
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""
    filtered = [line for line in existing.splitlines() if CRON_TAG not in line]
    filtered.append(cron_line)
    new_crontab = "\n".join(filtered) + "\n"

    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    print(f"Installed cron: every {minutes} min")
    print(f"  {cron_line}")
    print(f"  Log: /tmp/villager-census.log")


def _uninstall_cron():
    """Remove the villager census cron job."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        print("No crontab found")
        return

    lines = result.stdout.splitlines()
    filtered = [line for line in lines if CRON_TAG not in line]

    if len(filtered) == len(lines):
        print("No villager-census cron job found")
        return

    new_crontab = "\n".join(filtered) + "\n" if filtered else ""
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    print("Removed villager-census cron job")


def _parse_poi_regions(raw):
    """Parse 'rx,rz;rx,rz' string into list of tuples, or return defaults."""
    if not raw:
        return DEFAULT_POI_REGIONS
    return [tuple(int(v) for v in pair.split(",")) for pair in raw.split(";")]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run a villager census.")
    parser.add_argument("--db", default="census.db", help="SQLite database path")
    parser.add_argument("--notes", default=None, help="Snapshot annotation")
    parser.add_argument("--export-json", action="store_true", help="Export DB as JSON and exit")
    parser.add_argument("--auto", action="store_true",
                        help="Cron-friendly: check chunk loading, skip gracefully, log runs")
    parser.add_argument("--ssh", default=None, metavar="HOST",
                        help="Run via SSH to HOST (default: local execution)")
    parser.add_argument("--install", nargs="?", const="30", metavar="MINUTES",
                        help="Install cron job (default: every 30 min)")
    parser.add_argument("--uninstall", action="store_true", help="Remove cron job")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--config", help="Path to zones.toml config file")
    group.add_argument("--center", help="Center as x,z (requires --radius)")
    group.add_argument("--rect", help="Rectangle as x_min,z_min,x_max,z_max")

    parser.add_argument("--place", default=None,
                        help="Place name within config file (default: first place)")
    parser.add_argument("--radius", type=int, default=None, help="Scan radius (required with --center)")
    parser.add_argument("--name", default=None, help="Zone name for ad-hoc scans")
    parser.add_argument("--poi-regions", default=None,
                        help="POI regions as 'rx,rz;rx,rz' (e.g. '5,-3;5,-2')")

    args = parser.parse_args()

    if args.install is not None:
        _install_cron(args, parser)
        return
    if args.uninstall:
        _uninstall_cron()
        return

    configure_transport(ssh_host=args.ssh)

    if args.export_json:
        data = export_census_json(args.db)
        print(json.dumps(data, indent=2))
        return

    if args.config:
        from census_zones import load_place
        if args.place:
            place = load_place(args.place, zones_path=args.config)
        else:
            import tomllib
            with open(args.config, "rb") as f:
                config = tomllib.load(f)
            first_place = next(iter(config.get("places", {})))
            place = load_place(first_place, zones_path=args.config)
        zones = place["zones"]
        poi_regions = place["poi_regions"]
    elif args.center:
        parts = args.center.split(",")
        if len(parts) != 2:
            parser.error("--center must be x,z (e.g. 3150,-950)")
        cx, cz = int(parts[0]), int(parts[1])
        if args.radius is None:
            parser.error("--radius is required with --center")
        zone_name = args.name or f"scan-{cx}-{cz}"
        zones = [make_single_zone(center_x=cx, center_z=cz, radius=args.radius, name=zone_name)]
        poi_regions = _parse_poi_regions(args.poi_regions)
    elif args.rect:
        parts = args.rect.split(",")
        if len(parts) != 4:
            parser.error("--rect must be x_min,z_min,x_max,z_max")
        x_min, z_min, x_max, z_max = (int(p) for p in parts)
        if args.radius is not None:
            parser.error("--radius cannot be used with --rect")
        zone_name = args.name or f"rect-{x_min}-{z_min}-{x_max}-{z_max}"
        zones = [{
            "name": zone_name, "type": "rect",
            "x_min": min(x_min, x_max), "z_min": min(z_min, z_max),
            "x_max": max(x_min, x_max), "z_max": max(z_min, z_max),
        }]
        poi_regions = _parse_poi_regions(args.poi_regions)
    else:
        parser.error("one of --config, --center, or --rect is required")

    timestamp = datetime.now(timezone.utc).isoformat()
    skipped_zones = []

    if args.auto:
        # Check which zones have loaded chunks
        players = check_players_online()
        if not players:
            conn = init_db(args.db)
            insert_census_run(conn, timestamp=timestamp,
                              status="skipped_no_players", reason="No players online")
            conn.close()
            print(f"[{timestamp}] Skipped: no players online")
            return

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

    if args.auto:
        conn = init_db(args.db)
        insert_census_run(conn, timestamp=timestamp, status="completed",
                          snapshot_id=summary["snapshot_id"])
        conn.close()

    # Print summary
    print(f"\n## Census — {summary['timestamp']}")
    print(f"**Population:** {summary['villager_count']}  |  "
          f"**Beds:** {summary['bed_count']}  |  "
          f"**Births:** {summary['births']}  |  "
          f"**Deaths:** {summary['deaths']}  |  "
          f"**Homeless:** {summary['homeless']}")
    if summary.get("zones"):
        print("\n| Zone | Villagers | Beds |")
        print("|------|-----------|------|")
        for name, data in summary["zones"].items():
            print(f"| {name} | {data['villagers']} | {data['beds']} |")
    if skipped_zones:
        print(f"\nSkipped (chunks not loaded): {', '.join(skipped_zones)}")
    print()


if __name__ == "__main__":
    main()
