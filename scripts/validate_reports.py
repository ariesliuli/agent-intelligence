#!/usr/bin/env python3
"""Validate the public report archive. Standard library only."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
state = json.loads((ROOT / "state" / "processed.json").read_text(encoding="utf-8"))
ids = state["known_hint_ids"]
assert len(ids) == len(set(ids)), "Duplicate Hint IDs"
assert all(re.fullmatch(r"HINT-\d{3}", x) for x in ids), "Invalid Hint ID"
assert max(int(x[-3:]) for x in ids) == state["last_hint_id"], "Hint counter mismatch"
daily = ROOT / "daily"
if daily.exists():
    for path in daily.rglob("*.md"):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.parent.name), f"Invalid date directory: {path}"
        assert path.name in ("codex-evolution.md", "productivity-gap.md"), f"Unexpected daily report: {path}"
print("Archive validation passed")
