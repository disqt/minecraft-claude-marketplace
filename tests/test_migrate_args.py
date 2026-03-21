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
