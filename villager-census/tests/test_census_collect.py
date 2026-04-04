"""Tests for census_collect.py — SSH/tmux data collection module."""

import pytest
from unittest.mock import patch

from census_collect import (
    check_chunks_loaded,
    check_players_online,
    get_player_position,
    parse_death_log,
)
from census_zones import make_single_zone

SAMPLE_LIST_OUTPUT = "[19:20:22] [Server thread/INFO]: There are 1 of a max of 20 players online: Termiduck"
SAMPLE_LIST_EMPTY = "[19:20:22] [Server thread/INFO]: There are 0 of a max of 20 players online: "
SAMPLE_POS_OUTPUT = "[19:20:31] [Server thread/INFO]: Termiduck has the following entity data: [3159.209198957126d, 58.0d, -930.0230847671345d]"
SAMPLE_DEATH_LINE = "[19:54:24] [Server thread/INFO]: Villager Villager['Villager'/15678, uuid='d68d9d96-4802-4899-9b8e-bb8709eda5c0', l='ServerLevel[world_new]', x=3145.37, y=63.00, z=-965.30, cpos=[196, -61], tl=59771, v=true] died, message: 'Villager was killed'"
SAMPLE_DEATH_LINE_NAMED = "[18:32:16] [Server thread/INFO]: Villager Villager['Villager'/214, uuid='0a077d31-a230-41b5-bf50-c74d83892338', l='ServerLevel[world_new]', x=3158.63, y=64.00, z=-917.15, cpos=[197, -58], tl=708, v=true] died, message: 'Villager hit the ground too hard'"


# --- parse_death_log ---

def test_parse_death_log_extracts_fields():
    result = parse_death_log(SAMPLE_DEATH_LINE)
    assert result is not None
    assert result["uuid"] == "d68d9d96-4802-4899-9b8e-bb8709eda5c0"
    assert result["x"] == pytest.approx(3145.37)
    assert result["y"] == pytest.approx(63.0)
    assert result["z"] == pytest.approx(-965.30)
    assert result["ticks_lived"] == 59771
    assert result["message"] == "Villager was killed"


def test_parse_death_log_hit_ground():
    result = parse_death_log(SAMPLE_DEATH_LINE_NAMED)
    assert result is not None
    assert result["uuid"] == "0a077d31-a230-41b5-bf50-c74d83892338"
    assert result["ticks_lived"] == 708
    assert result["message"] == "Villager hit the ground too hard"


def test_parse_death_log_returns_none_on_non_match():
    result = parse_death_log("[19:20:22] [Server thread/INFO]: Some other log line")
    assert result is None


# --- check_players_online ---

def test_check_players_online():
    with patch("census_collect._run_command", return_value=[SAMPLE_LIST_OUTPUT]):
        players = check_players_online()
    assert players == ["Termiduck"]


def test_check_players_online_empty():
    with patch("census_collect._run_command", return_value=[SAMPLE_LIST_EMPTY]):
        players = check_players_online()
    assert players == []


def test_check_players_online_multiple():
    line = "[19:20:22] [Server thread/INFO]: There are 3 of a max of 20 players online: Alice, Bob, Charlie"
    with patch("census_collect._run_command", return_value=[line]):
        players = check_players_online()
    assert players == ["Alice", "Bob", "Charlie"]


# --- get_player_position ---

def test_get_player_position():
    with patch("census_collect._tail_log_after_command", return_value=[SAMPLE_POS_OUTPUT]):
        pos = get_player_position("Termiduck")
    assert pos is not None
    x, y, z = pos
    assert x == pytest.approx(3159.21, rel=1e-3)
    assert y == pytest.approx(58.0)
    assert z == pytest.approx(-930.02, rel=1e-3)


def test_get_player_position_not_found():
    with patch("census_collect._tail_log_after_command", return_value=["some unrelated log line"]):
        pos = get_player_position("Termiduck")
    assert pos is None


# --- check_chunks_loaded ---

def test_check_chunks_loaded_all_loaded():
    """All zones report loaded when markers appear in log."""
    zones = [
        make_single_zone(center_x=100, center_z=200, radius=50, name="zone-a"),
        make_single_zone(center_x=300, center_z=400, radius=50, name="zone-b"),
    ]

    def fake_ssh(cmd):
        # Return log lines with both markers present
        return [
            "[12:00:00] [Server thread/INFO]: [Server] CHUNKPROBE_12345_START",
            "[12:00:01] [Server thread/INFO]: [Server] CHUNKPROBE_12345_zone-a",
            "[12:00:01] [Server thread/INFO]: [Server] CHUNKPROBE_12345_zone-b",
            "[12:00:02] [Server thread/INFO]: [Server] CHUNKPROBE_12345_END",
        ]

    with (
        patch("census_collect._send_tmux"),
        patch("census_collect._run_command", side_effect=fake_ssh),
        patch("census_collect.time.sleep"),
        patch("census_collect.time.time", return_value=12345),
    ):
        loaded = check_chunks_loaded(zones)

    assert set(loaded) == {"zone-a", "zone-b"}


def test_check_chunks_loaded_partial():
    """Only zones whose markers appear are returned."""
    zones = [
        make_single_zone(center_x=100, center_z=200, radius=50, name="loaded-zone"),
        make_single_zone(center_x=300, center_z=400, radius=50, name="unloaded-zone"),
    ]

    def fake_ssh(cmd):
        return [
            "[12:00:00] [Server thread/INFO]: [Server] CHUNKPROBE_99_START",
            "[12:00:01] [Server thread/INFO]: [Server] CHUNKPROBE_99_loaded-zone",
            "[12:00:02] [Server thread/INFO]: [Server] CHUNKPROBE_99_END",
        ]

    with (
        patch("census_collect._send_tmux"),
        patch("census_collect._run_command", side_effect=fake_ssh),
        patch("census_collect.time.sleep"),
        patch("census_collect.time.time", return_value=99),
    ):
        loaded = check_chunks_loaded(zones)

    assert loaded == ["loaded-zone"]


def test_check_chunks_loaded_none():
    """No markers means no zones loaded."""
    zones = [make_single_zone(center_x=100, center_z=200, radius=50, name="zone-a")]

    def fake_ssh(cmd):
        return [
            "[12:00:00] [Server thread/INFO]: [Server] CHUNKPROBE_55_START",
            "[12:00:02] [Server thread/INFO]: [Server] CHUNKPROBE_55_END",
        ]

    with (
        patch("census_collect._send_tmux"),
        patch("census_collect._run_command", side_effect=fake_ssh),
        patch("census_collect.time.sleep"),
        patch("census_collect.time.time", return_value=55),
    ):
        loaded = check_chunks_loaded(zones)

    assert loaded == []
