"""Human decisions on REVIEW kits, and how they feed back into the damage check.

Decisions are an append-only JSONL log; the latest decision per image wins. Every decision lists
the flags the reviewer saw. Reviewed kits become labelled examples for Muse Spark
(``damage.Example``): a kit a reviewer passed shows it what counts as fine here, a kit they
rejected shows it real damage. The question stays on; the model is shown, not retrained.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from inspec.damage import Example

DECISIONS = ("PASS", "FAIL")
PER_QUESTION = 2  # passed kits shown per damage question
MAX_EXAMPLES = 6  # photos per request, on top of the kit being inspected


def record(log_path: Path, image: str, decision: str, *, kit: str, flags: list[str],
           note: str = "", reviewer: str = "") -> dict:
    """Append one decision on `image` (with the flags the reviewer saw) and return the entry."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    entry = dict(image=image, kit=kit, decision=decision, flags=list(flags), note=note.strip(),
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


def tally(decisions: dict[str, dict], kit: str, questions: list[str]) -> dict[str, dict]:
    """Per damage question: how many kits it flagged that reviewers passed / rejected."""
    stats = {q: {"passed": 0, "rejected": 0} for q in questions}
    for entry in decisions.values():
        if entry.get("kit") != kit:
            continue
        for q in entry["flags"]:
            if q in stats:
                stats[q]["passed" if entry["decision"] == "PASS" else "rejected"] += 1
    return stats


def pick_examples(decisions: dict[str, dict], kit: str, questions: list[str], resolve, *,
                  per_question: int = PER_QUESTION, max_total: int = MAX_EXAMPLES) -> list[Example]:
    """Newest reviewed kits first, at most ``per_question`` passed and one rejected kit per damage
    question, ``max_total`` in all. ``resolve(image_key)`` gives the photo's path, or None if
    it's gone (those are skipped)."""
    taken: dict[tuple[str, str], int] = {}
    out: list[Example] = []
    for entry in sorted(decisions.values(), key=lambda e: e["time"], reverse=True):
        flags = tuple(q for q in entry["flags"] if q in questions)
        path = resolve(entry["image"]) if entry.get("kit") == kit and flags else None
        if path is None:
            continue
        limit = per_question if entry["decision"] == "PASS" else 1
        if any(taken.get((q, entry["decision"]), 0) < limit for q in flags):
            for q in flags:
                taken[(q, entry["decision"])] = taken.get((q, entry["decision"]), 0) + 1
            out.append(Example(str(path), flags, entry["decision"], entry.get("note", "")))
            if len(out) == max_total:
                break
    return out
