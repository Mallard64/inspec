"""Human decisions on REVIEW kits: an append-only JSONL log, latest decision per image wins."""

from __future__ import annotations

import json
import time
from pathlib import Path

DECISIONS = ("PASS", "FAIL")


def record(log_path: Path, image: str, decision: str, *, flags: list[str], note: str = "",
           reviewer: str = "") -> dict:
    """Append one decision on `image` (with the flags the reviewer saw) and return the entry."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    entry = dict(image=image, decision=decision, flags=list(flags), note=note.strip(),
                 reviewer=reviewer.strip(), time=time.strftime("%Y-%m-%dT%H:%M:%S"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load(log_path: Path) -> dict[str, dict]:
    """Latest decision per image. A missing log means no decisions yet."""
    if not log_path.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in log_path.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            latest[entry["image"]] = entry
    return latest
