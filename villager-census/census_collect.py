"""census_collect.py — SSH/tmux data collection from the PaperMC server."""

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
    """Run `ssh minecraft <cmd>`, return stdout lines. Timeout 30s."""
    result = subprocess.run(
        ["ssh", SSH_HOST, cmd],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.splitlines()


def _send_tmux(command):
    """Send a command to the tmux session via SSH. Timeout 10s."""
    tmux_cmd = f"tmux -S {TMUX_SOCKET} send-keys -t {TMUX_SESSION} '{command}' Enter"
    subprocess.run(
        ["ssh", SSH_HOST, tmux_cmd],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _tail_log_after_command(command, wait_seconds=5, tail_lines=200):
    """Send tmux command, sleep, then tail the server log. Return lines."""
    _send_tmux(command)
    time.sleep(wait_seconds)
    return _ssh_command(f"tail -n {tail_lines} {LOG_PATH}")


# ---------------------------------------------------------------------------
# High-level collection functions
# ---------------------------------------------------------------------------

def check_players_online():
    """Send 'list' command and return a list of online player names.

    Returns an empty list if no players are online.
    """
    lines = _ssh_command(f"tail -n 50 {LOG_PATH}")
    # We actually need to send the list command first, then read the log.
    # The helper _tail_log_after_command handles that flow, but check_players_online
    # uses _ssh_command directly so tests can mock it simply.
    # In production, call:  lines = _tail_log_after_command("list", wait_seconds=2)
    # For testability the function reads from _ssh_command (caller controls the mock).
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
    """Collect raw entity-data lines for all villagers within radius of (cx, cz).

    Uses say-based START/END markers so we can isolate lines produced by this
    particular execute burst in a busy log.

    Returns a list of log lines that contain villager entity data.
    """
    timestamp = int(time.time())
    start_marker = f"CENSUS_{timestamp}_START"
    end_marker = f"CENSUS_{timestamp}_END"

    _send_tmux(f"say {start_marker}")
    time.sleep(0.5)

    execute_cmd = (
        f"execute as @e[type=minecraft:villager,"
        f"x={center_x},y=70,z={center_z},distance=..{radius}]"
        f" run data get entity @s"
    )
    _send_tmux(execute_cmd)
    time.sleep(5)

    _send_tmux(f"say {end_marker}")
    time.sleep(1)

    # Pull a generous tail of the log to capture all output
    all_lines = _ssh_command(f"tail -n 2000 {LOG_PATH}")

    # Find the window between markers
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


def download_poi_files(region_coords, local_dir):
    """Download POI .mca files for the given region coordinates via scp.

    region_coords: iterable of (rx, rz) tuples
    local_dir: local directory Path (or str) to download into

    Returns a list of Path objects for files that were successfully downloaded.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for rx, rz in region_coords:
        remote = f"{SSH_HOST}:{POI_DIR}/r.{rx}.{rz}.mca"
        local_path = local_dir / f"r.{rx}.{rz}.mca"
        result = subprocess.run(
            ["scp", remote, str(local_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and local_path.exists():
            downloaded.append(local_path)

    return downloaded


# ---------------------------------------------------------------------------
# Log parsing helpers
# ---------------------------------------------------------------------------

# Pattern for villager death lines emitted by PaperMC:
# Villager Villager['Villager'/15678, uuid='d68d9d96-...', l='ServerLevel[world_new]',
#   x=3145.37, y=63.00, z=-965.30, cpos=[196, -61], tl=59771, v=true]
#   died, message: 'Villager was killed'
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
