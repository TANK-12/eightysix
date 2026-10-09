"""Tests for the worlds content store."""

import os
import re
import sys

import pytest

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from janhollow import content


# Load and validate the worlds content
def test_worlds_store_loads():
    """The worlds store should load with no problems."""
    result = content.store()
    assert result["root"] is not None
    worlds_problems = [p for p in result["problems"] if "worlds" in str(p)]
    assert not worlds_problems, f"Store has world-related problems: {worlds_problems}"


def test_all_worlds_present():
    """The worlds store should contain the expected entries."""
    result = content.store()
    worlds = result["types"].get("worlds", {})
    assert len(worlds) > 0, "No worlds found in store"


def test_world_kinds_are_valid():
    """Every world's kind must be one of the allowed values."""
    result = content.store()
    worlds = result["types"].get("worlds", {})
    valid_kinds = {"planet", "moon", "star", "station", "ship", "wreck", "field"}

    for world_id, world in worlds.items():
        kind = world.get("kind")
        assert kind in valid_kinds, (
            f"World '{world_id}' has invalid kind '{kind}'. "
            f"Must be one of: {valid_kinds}"
        )


def test_visible_from_location_ids_are_valid():
    """Every location id in visible_from must be a real location id."""
    result = content.store()
    worlds = result["types"].get("worlds", {})
    locations = result["types"].get("locations", {})
    valid_location_ids = set(locations.keys())

    for world_id, world in worlds.items():
        visible_from = world.get("visible_from", [])
        for location_id in visible_from:
            assert location_id in valid_location_ids, (
                f"World '{world_id}' references unknown location '{location_id}'. "
                f"Valid locations are: {sorted(valid_location_ids)}"
            )


def test_world_colours_format():
    """Every world's colour must match the hex colour format #rrggbb."""
    result = content.store()
    worlds = result["types"].get("worlds", {})
    colour_pattern = re.compile(r"^#[0-9a-f]{6}$", re.IGNORECASE)

    for world_id, world in worlds.items():
        colour = world.get("colour", "")
        assert colour_pattern.match(colour), (
            f"World '{world_id}' has invalid colour '{colour}'. "
            f"Must be in format #rrggbb (lowercase hex)"
        )


def test_world_descriptions_are_nonempty():
    """Every world's description must be non-empty."""
    result = content.store()
    worlds = result["types"].get("worlds", {})

    for world_id, world in worlds.items():
        description = world.get("description", "").strip()
        assert description, f"World '{world_id}' has an empty or missing description"


def test_world_labels_are_nonempty():
    """Every world's label must be non-empty."""
    result = content.store()
    worlds = result["types"].get("worlds", {})

    for world_id, world in worlds.items():
        label = world.get("label", "").strip()
        assert label, f"World '{world_id}' has an empty or missing label"
