"""census_collect.py — Data collection from PaperMC server (local or SSH)."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Defaults — assume local execution on the minecraft server
TMUX_SOCKET = "/tmp/tmux-1000/pmcserver-bb664df1"
TMUX_SESSION = "pmcserver"
LOG_PATH = "/home/minecraft/serverfiles/logs/latest.log"
POI_DIR = "/home/minecraft/serverfiles/world_new/poi"

# Set via configure() — None means local mode
_ssh_host = None


def configure(*, ssh_host=None):
    """Set the transport mode. Call once at startup.

    ssh_host=None: local mode (default, for running on the VPS)
    ssh_host="minecraft": SSH mode (for running remotely)
    """
    global _ssh_host
    _ssh_host = ssh_host


def _run_command(cmd):
    """Run a command locally (as minecraft user) or via SSH, return stdout lines."""
    if _ssh_host:
        full_cmd = ["ssh", _ssh_host, cmd]
    else:
        full_cmd = ["sudo", "-u", "minecraft", "bash", "-c", cmd]
    result = subprocess.run(
        full_cmd, capture_output=True, text=True, timeout=30,
    )
    return result.stdout.splitlines()


def _send_tmux(command):
    """Send a command to the tmux session."""
    tmux_cmd = f"tmux -S {TMUX_SOCKET} send-keys -t {TMUX_SESSION} '{command}' Enter"
    if _ssh_host:
        full_cmd = ["ssh", _ssh_host, tmux_cmd]
    else:
        full_cmd = ["sudo", "-u", "minecraft", "bash", "-c", tmux_cmd]
    subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)


def _tail_log_after_command(command, wait_seconds=5, tail_lines=200):
    """Send tmux command, sleep, then tail the server log. Return lines."""
    _send_tmux(command)
    time.sleep(wait_seconds)
    return _run_command(f"tail -n {tail_lines} {LOG_PATH}")


# ---------------------------------------------------------------------------
# High-level collection functions
# ---------------------------------------------------------------------------

def _forceload_cmd(zones, action):
    """Send /forceload add|remove for each zone's bounding box in chunk coordinates."""
    from census_zones import zone_bounds

    for zone in zones:
        x_min, z_min, x_max, z_max = zone_bounds(zone)
        cx_min, cz_min = x_min >> 4, z_min >> 4
        cx_max, cz_max = x_max >> 4, z_max >> 4
        _send_tmux(f"forceload {action} {cx_min} {cz_min} {cx_max} {cz_max}")
        time.sleep(0.3)


def forceload_zones(zones):
    """Forceload all zone chunks and wait for them to load."""
    _forceload_cmd(zones, "add")
    time.sleep(2)  # wait for chunks to load


def unforceload_zones(zones):
    """Remove forceload marks from all zone chunks."""
    _forceload_cmd(zones, "remove")


def check_chunks_loaded(zones):
    """Probe which zones have loaded chunks using 'execute if loaded'.

    Sends one probe per zone via tmux, then reads the log for markers.
    Returns a list of zone names whose chunks are loaded.
    """
    from census_zones import zone_center

    timestamp = int(time.time())
    start_marker = f"CHUNKPROBE_{timestamp}_START"
    end_marker = f"CHUNKPROBE_{timestamp}_END"

    _send_tmux(f"say {start_marker}")
    time.sleep(0.5)

    for zone in zones:
        cx, cz = zone_center(zone)
        marker = f"CHUNKPROBE_{timestamp}_{zone['name']}"
        _send_tmux(f"execute if loaded {cx} 64 {cz} run say {marker}")
        time.sleep(0.3)

    time.sleep(1)
    _send_tmux(f"say {end_marker}")
    time.sleep(1)

    all_lines = _run_command(f"tail -n 500 {LOG_PATH}")

    collecting = False
    loaded = []
    zone_markers = {
        f"CHUNKPROBE_{timestamp}_{z['name']}": z["name"] for z in zones
    }
    for line in all_lines:
        if start_marker in line:
            collecting = True
            continue
        if end_marker in line:
            break
        if collecting:
            for marker, name in zone_markers.items():
                if marker in line and name not in loaded:
                    loaded.append(name)

    return loaded


def check_players_online():
    """Send 'list' command and return a list of online player names.

    Returns an empty list if no players are online.
    """
    lines = _run_command(f"tail -n 50 {LOG_PATH}")
    pattern = re.compile(
        r"There are (\d+) of a max of \d+ players online:(.*)"
    )
    for line in lines:
        m = pattern.search(line)
        if m:
            count = int(m.group(1))
            if count == 0:
                return []
            names_raw = m.group(2).strip()
            if not names_raw:
                return []
            return [n.strip() for n in names_raw.split(",") if n.strip()]
    return []


def get_player_position(player_name):
    """Return (x, y, z) for a player, or None if not found.

    Sends `data get entity <name> Pos` via tmux and parses the log output.
    """
    lines = _tail_log_after_command(f"data get entity {player_name} Pos")
    pattern = re.compile(
        re.escape(player_name)
        + r" has the following entity data: \[(-?[\d.]+)d, (-?[\d.]+)d, (-?[\d.]+)d\]"
    )
    for line in lines:
        m = pattern.search(line)
        if m:
            x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return (x, y, z)
    return None


def collect_villager_dumps(center_x, center_z, radius):
    """Collect raw entity-data lines for all villagers within radius of (cx, cz)."""
    selector = (
        f"@e[type=minecraft:villager,"
        f"x={center_x},y=70,z={center_z},distance=..{radius}]"
    )
    return _collect_with_selector(selector)


def collect_villager_dumps_box(x_min, z_min, x_max, z_max):
    """Collect raw entity-data lines for all villagers within a bounding box."""
    dx = x_max - x_min
    dz = z_max - z_min
    selector = (
        f"@e[type=minecraft:villager,"
        f"x={x_min},y=-64,z={z_min},dx={dx},dy=384,dz={dz}]"
    )
    return _collect_with_selector(selector)


def _collect_with_selector(selector):
    """Send an execute/data-get command with START/END markers, return entity lines."""
    timestamp = int(time.time())
    start_marker = f"CENSUS_{timestamp}_START"
    end_marker = f"CENSUS_{timestamp}_END"

    _send_tmux(f"say {start_marker}")
    time.sleep(0.5)

    _send_tmux(f"execute as {selector} run data get entity @s")
    time.sleep(5)

    _send_tmux(f"say {end_marker}")
    time.sleep(1)

    all_lines = _run_command(f"tail -n 2000 {LOG_PATH}")

    collecting = False
    results = []
    for line in all_lines:
        if start_marker in line:
            collecting = True
            continue
        if end_marker in line:
            break
        if collecting and "has the following entity data: {" in line:
            results.append(line)

    return results


def get_poi_files(region_coords, local_dir):
    """Get POI .mca files — copy locally or download via SCP.

    Returns a list of Path objects for files that were successfully obtained.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for rx, rz in region_coords:
        filename = f"r.{rx}.{rz}.mca"
        local_path = local_dir / filename

        if _ssh_host:
            remote = f"{_ssh_host}:{POI_DIR}/{filename}"
            result = subprocess.run(
                ["scp", remote, str(local_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and local_path.exists():
                downloaded.append(local_path)
        else:
            source = Path(POI_DIR) / filename
            result = subprocess.run(
                ["sudo", "cp", str(source), str(local_path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and local_path.exists():
                # Fix ownership so current user can read
                subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", str(local_path)],
                               capture_output=True, timeout=5)
                downloaded.append(local_path)

    return downloaded


# ---------------------------------------------------------------------------
# Log parsing helpers
# ---------------------------------------------------------------------------

_DEATH_PATTERN = re.compile(
    r"Villager\[.*?uuid='([0-9a-f-]+)'.*?"
    r"x=(-?[\d.]+),\s*y=(-?[\d.]+),\s*z=(-?[\d.]+),\s*"
    r"cpos=\[.*?\],\s*tl=(\d+),.*?\]"
    r"\s+died,\s+message:\s+'(.+?)'"
)


def parse_death_log(line):
    """Parse a villager death log line.

    Returns a dict with keys: uuid, x, y, z, ticks_lived, message
    or None if the line does not match.
    """
    m = _DEATH_PATTERN.search(line)
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
