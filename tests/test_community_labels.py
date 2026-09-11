"""Tests for path-based community naming."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypercharge.community_labels import (
    _heuristic_name,
    build_heuristic_labels,
    labels_are_placeholder,
    name_communities_for_host_agent,
    write_labels,
)
from hypercharge.graph import graphify_out_dir


def test_heuristic_name_from_paths():
    paths = [
        "acme/ML/v2/train.py",
        "acme/ML/v2/model.py",
        "acme/ML/v2/data.py",
    ]
    assert _heuristic_name(paths) == "acme · ML"


def test_labels_placeholder_detection():
    assert labels_are_placeholder({0: "Community 0", 1: "Community 1"})
    assert not labels_are_placeholder({0: "acme · ML", 1: "Community 1"})


def test_name_communities_writes_and_skips_second_time():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gdir = graphify_out_dir(root)
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "graph.json").write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": "a",
                            "community": 0,
                            "source_file": "acme/ML/train.py",
                        },
                        {
                            "id": "b",
                            "community": 0,
                            "source_file": "acme/ML/model.py",
                        },
                    ],
                    "links": [],
                }
            ),
            encoding="utf-8",
        )
        labels = build_heuristic_labels(root)
        assert labels[0] == "acme · ML"
        write_labels(root, labels)
        ok, msg, _ = name_communities_for_host_agent(root)
        assert ok
        assert "kept" in msg or "acme" in msg
